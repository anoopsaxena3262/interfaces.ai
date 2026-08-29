# Maintaining this repo

How to change the sandbox once you already understand it. Mental model: [GUIDE.md](GUIDE.md). Why the pieces exist: [PLAN.md](PLAN.md). PII/PCI copies: [PLAN-COMPLIANCE.md](PLAN-COMPLIANCE.md). Discovery evals: [PLAN-DISCOVERY-EVAL.md](PLAN-DISCOVERY-EVAL.md). Manual walks: [SCENARIOS.md](SCENARIOS.md). Runtime: [ARCHITECTURE.md](ARCHITECTURE.md). Doc index: [README.md](../README.md#docs).

## Commands

```bash
make test
make coverage
make lint
make dev
```

Python 3.11+, Node 20+. Do not commit `.venv/` or `banks-ui/node_modules/`.

## Where things live

| Change | File |
| --- | --- |
| Jordan’s Redwood balance | `data/native/redwood.json` |
| String vs cents conversion | `schema/adapters.py` |
| New snapshot field | `canonical.py`, `canonical.schema.json`, every adapter, `CANONICAL_REQUIRED` |
| Dollar hold limit | `IAI_TRANSFER_ESCALATION_USD` |
| Portal look | `banks-ui/src/pages/<bank>.ts` and `styles/<bank>.css` |

## Adding a fourth bank

1. New seed: `data/native/<id>.json` with a shape the existing adapters cannot parse.
2. New adapter class with `map_to_canonical`, `to_native_transfer`, and `apply_transfer`. `to_canonical` on the base class runs the PAN/SAD ingest guard first. Register the class on `ADAPTERS`. Do not put PAN/CVV in `data/native/`.
3. Row in `institutions()` (`schema/registry.py`).
4. `NATIVE_HINTS` plus `data/contracts/<id>.html` matching the TypeScript `data-iai-*` marks.
5. Page + CSS + route in `banks-ui`. Hub card. The page must still render **native** keys.
6. Tests: same person, checking available `2190.40` or document why not, and one hold path if you add a risky account.
7. A short table row in `docs/DESIGN.md`.

Do not teach a portal to render `CanonicalSnapshot`. If the UI looks “normalized,” schema drift becomes invisible.

## Holds

Add a new `EscalationReason` rather than stuffing text into `summary`. Test the code, not the sentence. Built-in hold walks (Calloway HOLD, Northstar $9000, policy) are in [SCENARIOS.md](SCENARIOS.md).

## Replay writes

Each adapter owns `apply_transfer`. Do not add bank-specific posting logic back into `ReplayEngine`.

## Discovery

Tests inject HTML through `html_loader`. Keep the default loader as HTTP GET. When you add a bindable field, update both the page and `data/contracts/`.

## Config

| Variable | Default |
| --- | --- |
| `IAI_BANK_UI_BASE_URL` | `http://127.0.0.1:5173` |
| `IAI_TRANSFER_ESCALATION_USD` | `5000` |
| `IAI_DISCOVERY_MIN_CONFIDENCE` | `0.72` |
| `IAI_LOG_LEVEL` | `INFO` (`DEBUG` adds per-field discovery and per-step replay lines; still masked) |

## If something looks wrong

| Symptom | Check |
| --- | --- |
| Portal error, hub ok | API not on 8000 |
| Discovery has locators but empty actions after a new bank | missing `data/contracts/<id>.html` |
| Balance did not move | in-memory extract; reload the page. Reset if you restarted the API |
| Two posts, one “lost” or workers disagree on balances | One Uvicorn worker only. `_working` is process-local and `load`/`save` is not atomic. See PLAN.md concurrency |
| `Unknown institution` | id missing from `ADAPTERS` and `institutions()` |
