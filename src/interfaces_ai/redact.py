"""Mask identifiers for logs and stored run/hold copies.

Last-4 only: account numbers, customer ids, phones. Never log email, PAN/SAD,
names, memos, or live balances. Transfer *intent* amount is logged so a hold
can be diagnosed; extracted available/current is not.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from interfaces_ai.schema.canonical import CanonicalSnapshot

# Safety net on log records (does not replace field-level masking).
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}"
)
# PAN or long DDA: 13–19 digits (PCI) and 8–12 digit account-like runs.
_LONG_DIGITS_RE = re.compile(r"\b\d{8,19}\b")

# Native transfer keys that are account ids, not amounts.
_ID_KEYS = frozenset(
    {
        "from",
        "to",
        "debitInstance",
        "creditInstance",
        "fromSfx",
        "toSfx",
        "from_n",
        "to_n",
        "from_account_id",
        "to_account_id",
        "customer_id",
        "sfx",
        "n",
        "productInstance",
    }
)
_MEMO_KEYS = frozenset({"note", "txt", "t", "memo", "description"})


def mask_last4(value: Any) -> str:
    """Keep only the last four digits (or last four characters if few digits).

    Values of length 4 or less are already truncation-sized (e.g. Northstar
    suffix `00`) and are returned unchanged so from/to stay distinguishable.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 5:
        return f"••••{digits[-4:]}"
    if len(text) <= 4:
        return text
    return f"••••{text[-4:]}"


def redact_email(_value: Any = None) -> str:
    return "••••"


def sample_kind(canonical_path: str) -> str:
    """What to store on DiscoveryField.sample: a kind token, never a live value."""
    path = canonical_path.lower()
    if any(marker in path for marker in ("available", "current", "amount")):
        return "<money>"
    if path.endswith(".id") or path.endswith("[].id"):
        return "<id>"
    if "type" in path or path.endswith(".status"):
        return "<enum>"
    return "<string>"


def mask_mapping(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Mask a native or step payload. Drops memo/free text; last-4 on ids."""
    if not payload:
        return {}
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _MEMO_KEYS:
            continue
        if key in _ID_KEYS or key.endswith("_id") or key.endswith("Id"):
            out[key] = mask_last4(value)
        elif isinstance(value, dict):
            out[key] = mask_mapping(value)
        elif isinstance(value, str) and ("@" in value or _PHONE_RE.search(value)):
            out[key] = "••••"
        elif isinstance(value, str) and _LONG_DIGITS_RE.fullmatch(value):
            out[key] = mask_last4(value)
        else:
            out[key] = value
    return out


def redact_text(message: str) -> str:
    """Last-pass scrub for a log line that accidentally inlined a raw value."""
    text = _EMAIL_RE.sub("••••", message)

    def _digits(match: re.Match[str]) -> str:
        return mask_last4(match.group(0))

    # Account/PAN digit runs before phone, so 900210001 is not treated as a phone.
    text = _LONG_DIGITS_RE.sub(_digits, text)
    return _PHONE_RE.sub("••••", text)


def redact_discovery_report(report: dict[str, Any]) -> dict[str, Any]:
    """Force discovery samples to kind tokens. Safe if an agent stuffed a live value."""
    data = copy.deepcopy(report)
    for field in data.get("fields") or []:
        path = str(field.get("canonical_path") or "")
        kind = sample_kind(path)
        field["sample"] = kind
        field["value_kind"] = kind.strip("<>")
    return data


def redact_escalation_case(case: dict[str, Any]) -> dict[str, Any]:
    """Last-4 ids, no memo/email, summary scrubbed. Shared with discovery via operator screen."""
    data = copy.deepcopy(case)
    data["summary"] = redact_text(str(data.get("summary") or ""))
    data["context"] = mask_mapping(data.get("context") if isinstance(data.get("context"), dict) else {})
    return data


def agent_snapshot_view(snapshot: CanonicalSnapshot) -> dict[str, Any]:
    """GET /canonical?view=agent: contact and transactions are unused by agents."""
    data = snapshot.model_dump(mode="json")
    customer = dict(data.get("customer") or {})
    customer.pop("email", None)
    customer.pop("phone", None)
    data["customer"] = customer
    data.pop("transactions", None)
    return data


def redact_operator_screen(
    *,
    discoveries: list[dict[str, Any]],
    escalations: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Single gate for the console: discovery samples and hold context together."""
    return {
        "discoveries": [redact_discovery_report(item) for item in discoveries],
        "escalations": [redact_escalation_case(item) for item in escalations],
    }
