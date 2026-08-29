"""Holds: amount_threshold and account_status are separate reason codes on one transfer."""

from decimal import Decimal

from interfaces_ai.agents.base import Store
from interfaces_ai.agents.escalation import EscalationAgent
from interfaces_ai.schema.adapters import get_adapter
from interfaces_ai.schema.canonical import Money, TransferIntent
from interfaces_ai.schema.registry import load_native


def test_amount_limit_and_hold_status_are_distinct_codes() -> None:
    store = Store()
    agent = EscalationAgent(store)
    snap = get_adapter("calloway").to_canonical(load_native("calloway"))
    source = next(a for a in snap.accounts if a.id == "900210001")
    held = next(a for a in snap.accounts if a.id == "900210099")
    decision = agent.evaluate_transfer(
        TransferIntent(
            institution_id="calloway",
            from_account_id=source.id,
            to_account_id=held.id,
            amount=Money(amount=Decimal("9000")),
        ),
        source,
        held,
    )
    assert decision is not None
    codes = {reason.value for reason in decision.reasons}
    assert "amount_threshold" in codes
    assert "account_status" in codes
    case = agent.open(decision)
    assert store.escalations[0].id == case.id
    ctx = case.context
    assert "intent" not in ctx
    assert "memo" not in ctx
    assert "mail" not in str(ctx).lower()
    assert "eml" not in str(ctx)
    assert "900210001" not in str(ctx)
    assert ctx["from_account_id"] == "••••0001"


def test_same_account_and_nsf_are_policy() -> None:
    agent = EscalationAgent(Store())
    snap = get_adapter("redwood").to_canonical(load_native("redwood"))
    checking = next(a for a in snap.accounts if a.id == "CHK-77")
    same = agent.evaluate_transfer(
        TransferIntent(
            institution_id="redwood",
            from_account_id=checking.id,
            to_account_id=checking.id,
            amount=Money(amount=Decimal("10")),
        ),
        checking,
        checking,
    )
    assert same is not None
    assert "policy" in {r.value for r in same.reasons}
    nsf = agent.evaluate_transfer(
        TransferIntent(
            institution_id="redwood",
            from_account_id=checking.id,
            to_account_id="SAV-12",
            amount=Money(amount=Decimal("3000")),
        ),
        checking,
        next(a for a in snap.accounts if a.id == "SAV-12"),
    )
    assert nsf is not None
    assert "policy" in {r.value for r in nsf.reasons}
    assert "amount_threshold" not in {r.value for r in nsf.reasons}


def test_discovery_hold_on_missing_paths_and_low_confidence() -> None:
    from datetime import UTC, datetime

    from interfaces_ai.schema.canonical import DiscoveryReport

    agent = EscalationAgent(Store())
    report = DiscoveryReport(
        institution_id="redwood",
        ui_url="/redwood",
        discovered_at=datetime.now(UTC),
        fields=[],
        actions=[],
        confidence=0.1,
        missing_canonical_paths=["accounts[].available"],
        unmapped_native_paths=["routing"],
    )
    case = agent.maybe_open_for_discovery(report)
    assert case is not None
    assert "unmapped_fields" in {r.value for r in case.reasons}
    assert "low_discovery_confidence" in {r.value for r in case.reasons}


def test_maybe_open_for_replay_skips_when_all_steps_ok() -> None:
    from datetime import UTC, datetime

    from interfaces_ai.schema.canonical import ReplayResult, ReplayStep, ReplayStepKind

    agent = EscalationAgent(Store())
    snap = get_adapter("redwood").to_canonical(load_native("redwood"))
    result = ReplayResult(
        run_id="run-ok",
        institution_id="redwood",
        intent=TransferIntent(
            institution_id="redwood",
            from_account_id="CHK-77",
            to_account_id="SAV-12",
            amount=Money(amount=Decimal("1")),
        ),
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        steps=[ReplayStep(kind=ReplayStepKind.NAVIGATE, description="ok")],
        succeeded=True,
    )
    assert agent.maybe_open_for_replay(result, snap) is None
