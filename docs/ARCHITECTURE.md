# Architecture

Python owns mapping and the three modules. TypeScript only renders whatever JSON that bank actually ships.

New to the repo? [GUIDE.md](GUIDE.md). Overall plan? [PLAN.md](PLAN.md). Snapshot/log PII? [PLAN-COMPLIANCE.md](PLAN-COMPLIANCE.md).

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

Run history lives in process memory (`Store`). Extracts also live in process memory after first load.

## Tests

`tests/conftest.py` clears in-memory extracts around every test. Adapters are checked by converting all three files and asserting Jordan’s email and checking available `2190.40`.
