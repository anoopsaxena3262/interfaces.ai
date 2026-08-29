"""Phase 3: Luhn + SAD keys reject at ingest. Never commit real PANs; use published test numbers."""

from copy import deepcopy

import pytest

from interfaces_ai.cardholder import (
    CardholderDataRejected,
    looks_like_pan,
    luhn_ok,
    reject_cardholder_data,
)
from interfaces_ai.schema.adapters import get_adapter
from interfaces_ai.schema.canonical import AccountType
from interfaces_ai.schema.registry import load_native

# Visa test PAN (Luhn-valid). Throwaway dicts only — not in data/native.
_TEST_PAN = "4242424242424242"


def test_luhn_accepts_published_test_pan_and_rejects_bad_check() -> None:
    assert luhn_ok(_TEST_PAN) is True
    assert luhn_ok("4242424242424243") is False
    assert looks_like_pan(_TEST_PAN) is True
    assert looks_like_pan("4242 4242 4242 4242") is True
    assert looks_like_pan("900210001") is False  # Calloway DDA length
    assert looks_like_pan("121140399") is False  # routing length
    assert looks_like_pan("4242424242424243") is False
    assert looks_like_pan(None) is False
    assert looks_like_pan(True) is False
    assert luhn_ok("50") is False  # doubled 5 → 10, exercises n > 9
    assert looks_like_pan(4242424242424242) is True
    assert looks_like_pan("") is False
    assert luhn_ok("") is False


def test_sixteen_digit_non_luhn_value_is_not_treated_as_pan() -> None:
    native = deepcopy(load_native("redwood"))
    native["household"]["primary"]["note"] = "4242424242424243"
    snap = get_adapter("redwood").to_canonical(native)
    assert snap.customer.email == "jordan.hale@example.net"


def test_seeds_are_not_cardholder_data() -> None:
    for bank in ("redwood", "northstar", "calloway"):
        reject_cardholder_data(load_native(bank))
        snap = get_adapter(bank).to_canonical(load_native(bank))
        assert AccountType.CREDIT not in {acct.type for acct in snap.accounts}


def test_pan_shaped_value_is_rejected_and_not_mapped() -> None:
    native = deepcopy(load_native("redwood"))
    native["products"]["deposits"].append(
        {
            "productInstance": "CRD-99",
            "nickname": "card",
            "kind": "demand",
            "mask": "••••4242",
            "lifecycle": "active",
            "position": {"avail": "0", "ledger": "0", "iso": "USD"},
            "pan": _TEST_PAN,
        }
    )
    with pytest.raises(CardholderDataRejected, match="SAD/PAN key"):
        get_adapter("redwood").to_canonical(native)


def test_luhn_pan_in_unrelated_field_is_rejected() -> None:
    native = deepcopy(load_native("calloway"))
    native["cust"]["note"] = _TEST_PAN
    with pytest.raises(CardholderDataRejected, match="PAN-shaped"):
        get_adapter("calloway").to_canonical(native)


def test_cvv_key_is_rejected_without_a_pan() -> None:
    native = deepcopy(load_native("northstar"))
    native["memberRec"]["cvv"] = "123"
    with pytest.raises(CardholderDataRejected, match="SAD/PAN key"):
        get_adapter("northstar").to_canonical(native)


def test_cvc_key_is_rejected() -> None:
    native = deepcopy(load_native("redwood"))
    native["household"]["cvc"] = "FAKESECRET_i2j3k4l5m6n7o8p9q0r1"
    with pytest.raises(CardholderDataRejected, match="SAD/PAN key"):
        get_adapter("redwood").to_canonical(native)


def test_dashed_luhn_pan_in_value_is_rejected() -> None:
    native = deepcopy(load_native("redwood"))
    native["household"]["primary"]["note"] = "4242-4242-4242-4242"
    with pytest.raises(CardholderDataRejected, match="PAN-shaped"):
        get_adapter("redwood").to_canonical(native)
