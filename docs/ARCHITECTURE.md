# Architecture

Python owns mapping and the three modules. TypeScript only renders whatever JSON that bank actually ships.

New to the repo? [GUIDE.md](GUIDE.md). Overall plan? [PLAN.md](PLAN.md). Snapshot/log PII? [PLAN-COMPLIANCE.md](PLAN-COMPLIANCE.md). Discovery evals? [PLAN-DISCOVERY-EVAL.md](PLAN-DISCOVERY-EVAL.md). File inventory? [CATALOG.md](CATALOG.md). All docs listed in [README.md](../README.md#docs).

```text
  /redwood        /northstar       /calloway
  household       suffixList       acct_rel / hist
        \              |                /
         \             |               /
          v            v              v
              adapters (one class each)
                       |
                       v
                 shared snapshot
                       |
          discovery    replay    hold-for-review
                       |
                   FastAPI :8000
```

Locally Vite is on 5173 and proxies `/api` to 8000.

## What each layer is allowed to do

- **Portals** (`banks-ui`) read `/api/v1/institutions/{id}/native` and paint that payload. They do not pretty-print the shared snapshot. Transfer submits still go through replay so there is a single write path.
- **Adapters** (`schema/adapters.py`) convert inbound extracts and outbound transfer bodies. Each adapter also applies its own ledger mutation (`apply_transfer`). Replay does not contain per-bank `if` trees for posting.
- **Discovery** scores required snapshot paths, locators, and leftover native keys. If the live page is an empty SPA shell, it reads `data/contracts/{id}.html`.
- **Replay** records navigate / fill / policy / submit / post. A failed policy check does not write.
- **Hold** opens a case with reason codes. Limits are settings (`IAI_TRANSFER_ESCALATION_USD`, `IAI_DISCOVERY_MIN_CONFIDENCE`).

## HTTP

| Method | Path |
| --- | --- |
| GET | `/health` |
| GET | `/api/v1/institutions` |
| GET | `/api/v1/institutions/{id}/native` |
| GET | `/api/v1/institutions/{id}/canonical` |
| POST | `/api/v1/agents/discover` |
| POST | `/api/v1/agents/replay` |
| GET | `/api/v1/runs` |
| GET | `/api/v1/escalations` |
| POST | `/api/v1/dev/reset` |

`GET /canonical` is the full snapshot (email/phone/transactions). `?view=agent` omits those; the console uses that. `GET /native` is the portal contract (full extract; demo-only without auth). PAN/SAD on ingest is `422`.

Run history lives in process memory (`Store`), including replay `idempotency_key` → first `ReplayResult`. Same key + same body returns that run; same key + different body is `409`. Extracts also live in process memory after first load (`_working` in `registry.py`). Sync FastAPI handlers run in a thread pool, so two overlapping replays with *different* keys can still lose an update; two Uvicorn workers cannot see each other’s dict. Stay on one worker until durable ledgers exist. See [PLAN.md concurrency](PLAN.md#concurrency) and [schema versioning](PLAN.md#canonical-schema-versioning).

## Tests

`tests/conftest.py` clears in-memory extracts around every test. Adapters are checked by converting all three files and asserting Jordan’s email and checking available `2190.40`.
