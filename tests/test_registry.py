"""Store lookup and per-institution ledger reset."""

from interfaces_ai.agents.base import Store
from interfaces_ai.schema.registry import load_native, reset_native, save_native


def test_latest_discovery_is_none_when_empty() -> None:
    assert Store().latest_discovery("redwood") is None


def test_reset_one_institution_reloads_seed() -> None:
    blob = load_native("redwood")
    blob["products"]["deposits"][0]["position"]["avail"] = "1.00"
    save_native("redwood", blob)
    reset_native("redwood")
    restored = load_native("redwood")
    assert restored["products"]["deposits"][0]["position"]["avail"] == "2190.40"
