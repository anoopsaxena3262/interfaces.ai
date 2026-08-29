"""Adapters: same person and $2190.40 checking after unit conversion; Calloway HOLD maps."""

from decimal import Decimal

from interfaces_ai.schema.adapters import get_adapter
from interfaces_ai.schema.canonical import AccountType, TransactionDirection
from interfaces_ai.schema.registry import load_native


def test_all_three_extracts_describe_the_same_person() -> None:
    banks = ("redwood", "northstar", "calloway")
    snapshots = {bank: get_adapter(bank).to_canonical(load_native(bank)) for bank in banks}
    for snap in snapshots.values():
        assert "jordan" in snap.customer.display_name.lower()
        assert "hale" in snap.customer.display_name.lower()
        assert snap.customer.email == "jordan.hale@example.net"
        assert {acct.type for acct in snap.accounts} >= {AccountType.CHECKING, AccountType.SAVINGS}
        assert snap.transactions
        assert all(txn.direction in TransactionDirection for txn in snap.transactions)


def test_checking_available_agrees_after_unit_conversion() -> None:
    snaps = [get_adapter(bank).to_canonical(load_native(bank)) for bank in ("redwood", "northstar", "calloway")]
    checking = [next(a for a in snap.accounts if a.type == AccountType.CHECKING) for snap in snaps]
    assert {acct.available.amount for acct in checking} == {Decimal("2190.40")}


def test_calloway_hold_status_survives_mapping() -> None:
    snap = get_adapter("calloway").to_canonical(load_native("calloway"))
    loc = next(a for a in snap.accounts if a.id == "900210099")
    assert loc.status == "hold"
    assert loc.type == AccountType.LOAN
