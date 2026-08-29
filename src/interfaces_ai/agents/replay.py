from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from interfaces_ai.agents.escalation import EscalationAgent
from interfaces_ai.schema.adapters import get_adapter
from interfaces_ai.schema.canonical import DiscoveryReport, ReplayResult, ReplayStep, ReplayStepKind, TransferIntent
from interfaces_ai.schema.registry import get_institution, load_native, save_native


class ReplayEngine:
    """Turn a canonical transfer into the bank's own request body, then apply it.

    Every attempt is stored as steps. A blocked transfer still leaves a trail so
    you can see whether the failure was mapping, policy, or the write itself.
    """

    def __init__(self, escalation: EscalationAgent) -> None:
        self.escalation = escalation

    def replay(self, intent: TransferIntent, discovery: DiscoveryReport | None = None) -> ReplayResult:
        started = datetime.now(UTC)
        run_id = f"run-{uuid4().hex[:10]}"
        adapter = get_adapter(intent.institution_id)
        native = load_native(intent.institution_id)
        snapshot = adapter.to_canonical(native)
        inst = get_institution(intent.institution_id)
        steps: list[ReplayStep] = []

        steps.append(
            ReplayStep(
                kind=ReplayStepKind.NAVIGATE,
                description=f"Open {adapter.institution_name} transfer form",
                locator=f"{inst.ui_path} [data-iai-page]",
            )
        )

        try:
            source = adapter.account_by_id(snapshot, intent.from_account_id)
            dest = adapter.account_by_id(snapshot, intent.to_account_id)
        except KeyError as exc:
            steps.append(
                ReplayStep(
                    kind=ReplayStepKind.ASSERT,
                    description="Match canonical account ids to this bank's ledger",
                    ok=False,
                    detail=f"Unknown account: {exc}",
                )
            )
            result = self._finish(run_id, intent, started, steps, False)
            case = self.escalation.maybe_open_for_replay(result, snapshot)
            if case:
                result.escalation_id = case.id
            return result

        steps.append(
            ReplayStep(
                kind=ReplayStepKind.FILL,
                description="Bind transfer fields from the canonical intent",
                locator=_locator(discovery, "transfer.from_account")
                or "[data-iai-canonical='transfer.from_account']",
                payload={
                    "from": intent.from_account_id,
                    "to": intent.to_account_id,
                    "amount": str(intent.amount.amount),
                },
            )
        )

        blocked = self.escalation.evaluate_transfer(intent, source, dest)
        if blocked:
            steps.append(
                ReplayStep(
                    kind=ReplayStepKind.ASSERT,
                    description="Stop before writing if local policy says no",
                    ok=False,
                    detail=blocked.summary,
                )
            )
            result = self._finish(run_id, intent, started, steps, False)
            result.escalation_id = self.escalation.open(blocked).id
            return result

        native_payload = adapter.to_native_transfer(intent, snapshot)
        steps.append(
            ReplayStep(
                kind=ReplayStepKind.SUBMIT,
                description="Submit the bank-shaped transfer body",
                locator=_action_locator(discovery, "transfer.submit")
                or "[data-iai-action='transfer.submit']",
                payload=native_payload,
            )
        )
        receipt = adapter.apply_transfer(native, native_payload, intent, source, dest)
        save_native(intent.institution_id, native)
        steps.append(
            ReplayStep(
                kind=ReplayStepKind.POST,
                description="Update the in-memory extract",
                payload={"receipt_id": receipt["receipt_id"]},
            )
        )
        return self._finish(run_id, intent, started, steps, True, receipt)

    def _finish(
        self,
        run_id: str,
        intent: TransferIntent,
        started: datetime,
        steps: list[ReplayStep],
        succeeded: bool,
        receipt: dict | None = None,
    ) -> ReplayResult:
        return ReplayResult(
            run_id=run_id,
            institution_id=intent.institution_id,
            intent=intent,
            started_at=started,
            finished_at=datetime.now(UTC),
            steps=steps,
            succeeded=succeeded,
            native_receipt=receipt,
        )


def _locator(discovery: DiscoveryReport | None, canonical: str) -> str | None:
    if not discovery:
        return None
    for field in discovery.fields:
        if field.canonical_path == canonical and field.locator:
            return field.locator
    for item in discovery.page_contract.get("fields", []):
        if item.get("canonical") == canonical:
            return item.get("locator")
    return None


def _action_locator(discovery: DiscoveryReport | None, name: str) -> str | None:
    if not discovery:
        return None
    for action in discovery.actions:
        if action.name == name or action.canonical_intent == name:
            return action.locator
    return None
