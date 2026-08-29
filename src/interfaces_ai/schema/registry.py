"""Institution catalog and in-memory working ledgers.

Git seeds live in data/native/*.json. First load copies into `_working`. Replay
mutates that copy; reset_native() drops it so the next load re-reads the seed.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from interfaces_ai.schema.adapters import ADAPTERS, NativeAdapter

# registry.py is src/interfaces_ai/schema/ → parents[3] is the repo root.
ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data" / "native"
_working: dict[str, dict[str, Any]] = {}  # one process; overlapping load/save races — PLAN.md concurrency


@dataclass(frozen=True)
class Institution:
    id: str
    name: str
    ui_path: str
    native_file: Path
    adapter: NativeAdapter
    extract_kind: str
    notes: str


def institutions() -> list[Institution]:
    """Catalog for the API/CLI. A fourth bank needs a row here and an ADAPTERS entry."""
    return [
        Institution(
            id="redwood",
            name="Redwood Community Bank",
            ui_path="/redwood",
            native_file=DATA_DIR / "redwood.json",
            adapter=ADAPTERS["redwood"],
            extract_kind="household / products tree; balances as decimal strings",
            notes="Checking lives under products.deposits with kind=demand.",
        ),
        Institution(
            id="northstar",
            name="Northstar FCU",
            ui_path="/northstar",
            native_file=DATA_DIR / "northstar.json",
            adapter=ADAPTERS["northstar"],
            extract_kind="memberRec + suffixList; integer cents; LAST, FIRST name line",
            notes="Share draft is suffix 00. Amounts are cents.",
        ),
        Institution(
            id="calloway",
            name="Calloway State Bank",
            ui_path="/calloway",
            native_file=DATA_DIR / "calloway.json",
            adapter=ADAPTERS["calloway"],
            extract_kind="short-key core dump; sign split from amount; HOLD on LOC",
            notes="acct_rel n=900210099 is on HOLD and should fail replay.",
        ),
    ]


def get_institution(institution_id: str) -> Institution:
    for item in institutions():
        if item.id == institution_id:
            return item
    raise KeyError(institution_id)


def load_native(institution_id: str) -> dict[str, Any]:
    """Return a deep copy of the working extract so callers cannot mutate `_working` by accident."""
    if institution_id not in _working:
        inst = get_institution(institution_id)
        _working[institution_id] = json.loads(inst.native_file.read_text())
    return copy.deepcopy(_working[institution_id])


def save_native(institution_id: str, payload: dict[str, Any]) -> None:
    """Persist a working copy after apply_transfer. Does not write git seeds."""
    get_institution(institution_id)
    _working[institution_id] = copy.deepcopy(payload)


def reset_native(institution_id: str | None = None) -> None:
    """Drop working copies so the next load_native re-reads data/native. Used by tests and /dev/reset."""
    if institution_id is None:
        _working.clear()
        return
    _working.pop(institution_id, None)
