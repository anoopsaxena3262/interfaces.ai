"""Replay: Redwood string balances move; Calloway HOLD and Northstar $9000 do not post."""

from decimal import Decimal

from interfaces_ai.agents.base import Store
from interfaces_ai.agents.escalation import EscalationAgent
from interfaces_ai.agents.replay import ReplayEngine
from interfaces_ai.schema.adapters import get_adapter
from interfaces_ai.schema.canonical import Money, TransferIntent
from interfaces_ai.schema.registry import load_native


def _engine() -> ReplayEngine:
    return ReplayEngine(EscalationAgent(Store()))


def test_replay_updates_redwood_string_balances() -> None:
    engine = _engine()
    before = get_adapter("redwood").to_canonical(load_native("redwood"))
    checking = next(a for a in before.accounts if a.type.value == "checking")
    savings = next(a for a in before.accounts if a.type.value == "savings")
    result = engine.replay(
        TransferIntent(
            institution_id="redwood",
            from_account_id=checking.id,
            to_account_id=savings.id,
            amount=Money(amount=Decimal("40.00")),
            memo="test",
        )
    )
    assert result.succeeded
    after = get_adapter("redwood").to_canonical(load_native("redwood"))
    after_checking = next(a for a in after.accounts if a.id == checking.id)
    assert after_checking.available.amount == checking.available.amount - Decimal("40.00")
    blob = result.model_dump_json()
    assert "majorUnits" not in blob
    assert "debitInstance" not in blob
    assert "fromSfx" not in blob
    assert "native_payload" not in blob
    submit = next(step for step in result.steps if step.kind.value == "submit")
    assert submit.payload == {}
    assert result.native_receipt is not None
    assert set(result.native_receipt) == {"receipt_id"}


def test_replay_stops_on_calloway_hold() -> None:
    result = _engine().replay(
        TransferIntent(
            institution_id="calloway",
            from_account_id="900210001",
            to_account_id="900210099",
            amount=Money(amount=Decimal("20.00")),
            memo="should not post",
        )
    )
    assert result.succeeded is False
    assert result.escalation_id
    assert any(not step.ok for step in result.steps)


def test_replay_stops_when_amount_hits_limit() -> None:
    result = _engine().replay(
        TransferIntent(
            institution_id="northstar",
            from_account_id="01",
            to_account_id="00",
            amount=Money(amount=Decimal("9000.00")),
            memo="too large",
        )
    )
    assert result.succeeded is False
    assert result.escalation_id
