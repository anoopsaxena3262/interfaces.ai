from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from interfaces_ai.agents.base import Store
from interfaces_ai.config import Settings, get_settings
from interfaces_ai.schema.canonical import (
    Account,
    CanonicalSnapshot,
    DiscoveryReport,
    EscalationCase,
    EscalationReason,
    EscalationSeverity,
    ReplayResult,
    TransferIntent,
)


class EscalationDecision:
    def __init__(
        self,
        institution_id: str,
        reasons: list[EscalationReason],
        severity: EscalationSeverity,
        summary: str,
        context: dict,
    ) -> None:
        self.institution_id = institution_id
        self.reasons = reasons
        self.severity = severity
        self.summary = summary
        self.context = context


class EscalationAgent:
    """Local rules that decide whether a run may finish unattended.

    Reason codes are an enum so a later reviewer can filter the queue without
    parsing sentences. Dollar limits come from settings, not from this file.
    """

    def __init__(self, store: Store, settings: Settings | None = None) -> None:
        self.store = store
        self.settings = settings or get_settings()

    def evaluate_discovery(self, report: DiscoveryReport) -> EscalationDecision | None:
        reasons: list[EscalationReason] = []
        if report.confidence < self.settings.discovery_min_confidence:
            reasons.append(EscalationReason.LOW_DISCOVERY_CONFIDENCE)
        if report.missing_canonical_paths:
            reasons.append(EscalationReason.UNMAPPED_FIELDS)
        if not reasons:
            return None
        severity = EscalationSeverity.HIGH if report.missing_canonical_paths else EscalationSeverity.MEDIUM
        return EscalationDecision(
            institution_id=report.institution_id,
            reasons=reasons,
            severity=severity,
            summary=(
                f"Discovery for {report.institution_id} scored {report.confidence:.2f}; "
                f"missing={report.missing_canonical_paths or 'none'}"
            ),
            context={
                "confidence": report.confidence,
                "missing_canonical_paths": report.missing_canonical_paths,
                "unmapped_native_paths": report.unmapped_native_paths,
                "ui_url": report.ui_url,
            },
        )

    def evaluate_transfer(
        self, intent: TransferIntent, source: Account, dest: Account
    ) -> EscalationDecision | None:
        reasons: list[EscalationReason] = []
        if intent.amount.as_float() >= self.settings.transfer_escalation_usd:
            reasons.append(EscalationReason.AMOUNT_THRESHOLD)
        if source.status.lower() != "open" or dest.status.lower() != "open":
            reasons.append(EscalationReason.ACCOUNT_STATUS)
        if source.id == dest.id:
            reasons.append(EscalationReason.POLICY)
        if intent.amount.as_float() > source.available.as_float():
            reasons.append(EscalationReason.POLICY)
        if not reasons:
            return None
        severity = (
            EscalationSeverity.CRITICAL
            if EscalationReason.ACCOUNT_STATUS in reasons
            else EscalationSeverity.HIGH
        )
        return EscalationDecision(
            institution_id=intent.institution_id,
            reasons=reasons,
            severity=severity,
            summary=(
                f"Transfer {intent.amount.amount} {intent.amount.currency} "
                f"{source.id} → {dest.id} blocked ({', '.join(r.value for r in reasons)})"
            ),
            context={
                "intent": intent.model_dump(mode="json"),
                "source_status": source.status,
                "dest_status": dest.status,
                "available": str(source.available.amount),
            },
        )

    def maybe_open_for_replay(self, result: ReplayResult, snapshot: CanonicalSnapshot) -> EscalationCase | None:
        failed = [step for step in result.steps if not step.ok]
        if not failed:
            return None
        decision = EscalationDecision(
            institution_id=result.institution_id,
            reasons=[EscalationReason.REPLAY_STEP_FAILED],
            severity=EscalationSeverity.HIGH,
            summary=failed[0].detail or failed[0].description,
            context={
                "run_id": result.run_id,
                "customer_id": snapshot.customer.id,
                "failed_step": failed[0].model_dump(mode="json"),
            },
        )
        return self.open(decision)

    def maybe_open_for_discovery(self, report: DiscoveryReport) -> EscalationCase | None:
        decision = self.evaluate_discovery(report)
        if not decision:
            return None
        return self.open(decision)

    def open(self, decision: EscalationDecision) -> EscalationCase:
        case = EscalationCase(
            id=f"esc-{uuid4().hex[:10]}",
            created_at=datetime.now(UTC),
            institution_id=decision.institution_id,
            severity=decision.severity,
            reasons=decision.reasons,
            summary=decision.summary,
            context=decision.context,
            status="open",
        )
        return self.store.add_escalation(case)
