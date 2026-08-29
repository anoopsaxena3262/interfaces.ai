from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

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


class DiscoverRequest(BaseModel):
    institution_id: str | None = None


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
        try:
            return load_native(institution_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/api/v1/institutions/{institution_id}/canonical")
    def canonical_payload(institution_id: str) -> dict:
        try:
            native = load_native(institution_id)
            snapshot = get_adapter(institution_id).to_canonical(native)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return snapshot.model_dump(mode="json")

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
            reports.append(report.model_dump(mode="json"))
            if case:
                cases.append(case.model_dump(mode="json"))
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
        result = request.app.state.replay.replay(intent, discovery)
        request.app.state.store.add_replay(result)
        return result.model_dump(mode="json")

    @router.get("/api/v1/runs")
    def runs(request: Request) -> dict:
        store = request.app.state.store
        return {
            "discoveries": [item.model_dump(mode="json") for item in store.discoveries[:50]],
            "replays": [item.model_dump(mode="json") for item in store.replays[:50]],
            "escalations": [item.model_dump(mode="json") for item in store.escalations[:50]],
        }

    @router.get("/api/v1/escalations")
    def escalations(request: Request) -> list[dict]:
        return [item.model_dump(mode="json") for item in request.app.state.store.escalations]

    @router.post("/api/v1/dev/reset")
    def reset_demo_ledgers() -> dict:
        reset_native()
        return {"ok": True, "message": "In-memory ledgers restored from data/native JSON seeds."}

    return router
