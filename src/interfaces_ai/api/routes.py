"""HTTP surface. Portals read native JSON; console and CLI also hit canonical/discover/replay.

There is no second “mutate JSON” route: transfers always go through ReplayEngine
so policy runs first.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from interfaces_ai.agents.base import IdempotencyConflict, intent_fingerprint
from interfaces_ai.cardholder import CardholderDataRejected
from interfaces_ai.redact import (
    agent_snapshot_view,
    redact_discovery_report,
    redact_escalation_case,
    redact_operator_screen,
)
from interfaces_ai.schema.adapters import get_adapter
from interfaces_ai.schema.canonical import Money, TransferIntent
from interfaces_ai.schema.registry import institutions, load_native, reset_native


class TransferRequest(BaseModel):
    institution_id: str
    from_account_id: str
    to_account_id: str
    amount: Decimal = Field(gt=0)
    currency: str = "USD"
    memo: str = ""
    idempotency_key: str | None = Field(default=None, max_length=128)


class DiscoverRequest(BaseModel):
    institution_id: str | None = None  # omit to discover every bank


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict:
        return {"ok": True}

    @router.get("/api/v1/institutions")
    def list_institutions() -> list[dict]:
        return [
            {
                "id": inst.id,
                "name": inst.name,
                "ui_path": inst.ui_path,
                "extract_kind": inst.extract_kind,
                "notes": inst.notes,
            }
            for inst in institutions()
        ]

    @router.get("/api/v1/institutions/{institution_id}/native")
    def native_payload(institution_id: str) -> dict:
        """Working extract (bank-shaped). Portals must render these keys, not the snapshot.

        Unauthenticated `/native` is demo-only. It is the portal contract, not an audit log.
        """
        try:
            return load_native(institution_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except CardholderDataRejected as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/api/v1/institutions/{institution_id}/canonical")
    def canonical_payload(
        institution_id: str,
        view: str | None = Query(
            default=None,
            description="Omit for full snapshot; `agent` drops contact and transactions.",
        ),
    ) -> dict:
        try:
            native = load_native(institution_id)
            snapshot = get_adapter(institution_id).to_canonical(native)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except CardholderDataRejected as exc:
            raise HTTPException(422, str(exc)) from exc
        if view is None or view == "":
            return snapshot.model_dump(mode="json")
        if view == "agent":
            return agent_snapshot_view(snapshot)
        raise HTTPException(422, "view must be omitted or 'agent'")

    @router.post("/api/v1/agents/discover")
    def discover(request: Request, body: DiscoverRequest | None = None) -> dict:
        ids = [body.institution_id] if body and body.institution_id else [i.id for i in institutions()]
        store = request.app.state.store
        agent = request.app.state.discovery
        escalation = request.app.state.escalation
        reports = []
        cases = []
        for institution_id in ids:
            try:
                report = agent.discover(institution_id)
            except KeyError as exc:
                raise HTTPException(404, str(exc)) from exc
            store.add_discovery(report)
            case = escalation.maybe_open_for_discovery(report)
            reports.append(redact_discovery_report(report.model_dump(mode="json")))
            if case:
                cases.append(redact_escalation_case(case.model_dump(mode="json")))
        return {"reports": reports, "escalations": cases}

    @router.post("/api/v1/agents/replay")
    def replay(request: Request, body: TransferRequest) -> dict:
        try:
            get_adapter(body.institution_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        intent = TransferIntent(
            institution_id=body.institution_id,
            from_account_id=body.from_account_id,
            to_account_id=body.to_account_id,
            amount=Money(amount=body.amount, currency=body.currency),
            memo=body.memo,
        )
        discovery = request.app.state.store.latest_discovery(body.institution_id)
        key = (body.idempotency_key or "").strip() or None

        def _run():
            result = request.app.state.replay.replay(intent, discovery)
            if key:
                return result.model_copy(update={"idempotency_key": key})
            return result

        store = request.app.state.store
        try:
            result = store.replay_once(
                body.institution_id,
                key,
                intent_fingerprint(intent),
                _run,
            )
        except IdempotencyConflict as exc:
            raise HTTPException(
                409,
                "idempotency_key already used with a different transfer body",
            ) from exc
        return result.model_dump(mode="json")

    @router.get("/api/v1/runs")
    def runs(request: Request) -> dict:
        store = request.app.state.store
        screen = redact_operator_screen(
            discoveries=[item.model_dump(mode="json") for item in store.discoveries[:50]],
            escalations=[item.model_dump(mode="json") for item in store.escalations[:50]],
        )
        return {
            "discoveries": screen["discoveries"],
            "replays": [item.model_dump(mode="json") for item in store.replays[:50]],
            "escalations": screen["escalations"],
        }

    @router.get("/api/v1/escalations")
    def escalations(request: Request) -> list[dict]:
        return [
            redact_escalation_case(item.model_dump(mode="json"))
            for item in request.app.state.store.escalations
        ]

    @router.post("/api/v1/dev/reset")
    def reset_demo_ledgers() -> dict:
        """Reload seeds into memory. Does not wipe Store (discovery/replay/hold history)."""
        reset_native()
        return {"ok": True, "message": "In-memory ledgers restored from data/native JSON seeds."}

    return router
