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
