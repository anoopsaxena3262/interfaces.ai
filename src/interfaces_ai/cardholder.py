"""Reject PAN/SAD at ingest. Not encryption; fail closed so card data never maps.

PCI DSS stays out of scope for the three seeds. This is the Phase 3 guard so
`AccountType.CREDIT` cannot become a cardholder-data path by accident.

Published test PANs (e.g. 4242424242424242) belong only in throwaway test dicts.
"""

from __future__ import annotations

from typing import Any

# Exact keys after lowercasing and stripping `_` / `-`. Not substrings (avoid `expansion`).
_SAD_KEYS = frozenset(
    {
        "pan",
        "cvv",
        "cvc",
        "csc",
        "cid",
        "cvv2",
        "cvc2",
        "pin",
        "pinblock",
        "track1",
        "track2",
        "track2equiv",
        "cardnumber",
        "primaryaccountnumber",
        "cardpan",
    }
)


class CardholderDataRejected(ValueError):
    """Native extract contained PAN-shaped or SAD fields. Do not map or persist them."""


def luhn_ok(value: str) -> bool:
    """ISO/IEC 7812 Luhn checksum. Digits only; other characters are ignored."""
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def looks_like_pan(value: Any) -> bool:
    """13–19 digits (spaces/dashes allowed) that pass Luhn. Short DDA/routing stay out."""
    if value is None or isinstance(value, bool):
        return False
    text = str(value).strip()
    compact = "".join(ch for ch in text if ch.isdigit())
    if len(compact) < 13 or len(compact) > 19:
        return False
    if any(ch not in "0123456789 -" for ch in text):
        return False
    return luhn_ok(compact)


def _norm_key(key: Any) -> str:
    return str(key).lower().replace("_", "").replace("-", "")


def reject_cardholder_data(native: Any, *, path: str = "$") -> None:
    """Walk a native extract. SAD keys or Luhn-valid PAN strings raise."""
    if isinstance(native, dict):
        for key, value in native.items():
            here = f"{path}.{key}"
            if _norm_key(key) in _SAD_KEYS:
                raise CardholderDataRejected(f"SAD/PAN key {key!r} at {here}")
            reject_cardholder_data(value, path=here)
        return
    if isinstance(native, list):
        for i, item in enumerate(native):
            reject_cardholder_data(item, path=f"{path}[{i}]")
        return
    if looks_like_pan(native):
        raise CardholderDataRejected(f"PAN-shaped value at {path}")
