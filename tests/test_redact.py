"""Last-4 masking, kind tokens, and the operator-screen gate."""

import json

from interfaces_ai.redact import (
    agent_snapshot_view,
    mask_last4,
    mask_mapping,
    redact_email,
    redact_operator_screen,
    redact_text,
    sample_kind,
)
from interfaces_ai.schema.adapters import get_adapter
from interfaces_ai.schema.registry import load_native


def test_operator_screen_redacts_leaked_samples_and_hold_context() -> None:
    """Dirty agent output still cannot reach the console: one function owns both sides."""
    dirty = redact_operator_screen(
        discoveries=[
            {
                "institution_id": "redwood",
                "fields": [
                    {
                        "canonical_path": "customer.id",
                        "native_path": "household.partyKey",
                        "sample": "HH-20441",
                    },
                    {
                        "canonical_path": "accounts[].available",
                        "native_path": "position.avail",
                        "sample": "2190.40",
                    },
                ],
            }
        ],
        escalations=[
            {
                "summary": "Transfer blocked 900210001",
                "context": {
                    "intent": {
                        "from_account_id": "900210001",
                        "memo": "jordan.hale@example.net",
                    },
                    "customer_id": "HH-20441",
                },
            }
        ],
    )
    blob = json.dumps(dirty)
    assert "HH-20441" not in blob
    assert "2190.40" not in blob
    assert "900210001" not in blob
    assert "jordan.hale" not in blob
    samples = [field["sample"] for field in dirty["discoveries"][0]["fields"]]
    assert samples == ["<id>", "<money>"]
    assert "memo" not in dirty["escalations"][0]["context"].get("intent", {})


def test_mask_last4_keeps_only_trailing_digits() -> None:
    assert mask_last4("900210001") == "••••0001"
    assert mask_last4("900210099") == "••••0099"
    assert mask_last4("5105550199") == "••••0199"
    assert mask_last4("CHK-77") == "••••K-77"
    assert mask_last4("00") == "00"
    assert mask_last4("01") == "01"


def test_sample_kind_is_presence_not_a_live_value() -> None:
    assert sample_kind("accounts[].available") == "<money>"
    assert sample_kind("customer.id") == "<id>"
    assert sample_kind("customer.display_name") == "<string>"
    assert sample_kind("accounts[].type") == "<enum>"


def test_mask_mapping_drops_memo_and_masks_ids() -> None:
    out = mask_mapping(
        {
            "from_n": "900210001",
            "to_n": "900210002",
            "p": 4000,
            "t": "payroll note with jordan.hale@example.net",
        }
    )
    assert out["from_n"] == "••••0001"
    assert out["to_n"] == "••••0002"
    assert out["p"] == 4000
    assert "t" not in out


def test_redact_text_scrubs_email_phone_and_long_ids() -> None:
    line = "mail=jordan.hale@example.net tel=+1-510-555-0199 acct=900210001"
    scrubbed = redact_text(line)
    assert "jordan.hale" not in scrubbed
    assert "510-555-0199" not in scrubbed
    assert "900210001" not in scrubbed
    assert "••••0001" in scrubbed


def test_agent_snapshot_view_drops_contact_and_transactions() -> None:
    snap = get_adapter("redwood").to_canonical(load_native("redwood"))
    assert snap.customer.email
    assert snap.transactions
    view = agent_snapshot_view(snap)
    assert "email" not in view["customer"]
    assert "phone" not in view["customer"]
    assert "transactions" not in view
    assert view["customer"]["id"] == snap.customer.id
    assert view["accounts"]


def test_mask_last4_and_mapping_edge_cases() -> None:
    assert mask_last4(None) == ""
    assert mask_last4("  ") == ""
    assert mask_last4("ab") == "ab"
    assert mask_last4("hello") == "••••ello"
    assert redact_email() == "••••"
    assert mask_mapping(None) == {}
    nested = mask_mapping({"outer": {"from_account_id": "900210001"}, "mail": "a@b.co"})
    assert nested["outer"]["from_account_id"] == "••••0001"
    assert nested["mail"] == "••••"
    assert mask_mapping({"ref": "900210001"})["ref"] == "••••0001"
