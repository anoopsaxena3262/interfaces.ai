# File catalog

Every **source file** in this repo, with what it is and when you touch it.

Not listed (generated or local, see `.gitignore`): `.venv/`, `banks-ui/node_modules/`, `banks-ui/dist/`, `__pycache__/`, `.pytest_cache/`, `.env`.

Read order if you are new: `README.md` (doc index) → `docs/GUIDE.md` → this catalog when you need a specific file.

---

## Repository root

| Name | Type | Folder | Description | Usage |
| --- | --- | --- | --- | --- |
| `README.md` | Markdown | `/` | Clone, run, test, bank URLs, **index of every Markdown file** | First file for clone and demo |
| `LICENSE` | Text (GPL-3.0) | `/` | GNU GPL v3 license text | Legal; do not edit unless relicensing |
| `Makefile` | Make | `/` | Shortcuts: `setup`, `dev`, `dev-api`, `dev-ui`, `test`, `lint`, `clean` | Daily commands |
| `pyproject.toml` | TOML | `/` | Python package metadata, dependencies, pytest and ruff config, `iai` CLI entry | `pip install -e ".[dev]"` |
| `.gitignore` | Git ignore | `/` | Excludes venv, node_modules, caches, `.env` | Keep secrets and generated trees out of git |
| `.env.example` | Env template | `/` | Sample `IAI_*` settings (ports, hold thresholds) | Copy to `.env` to override defaults |

---

## `docs/` — design and onboarding

| Name | Type | Folder | Description | Usage |
| --- | --- | --- | --- | --- |
| `PLAN.md` | Markdown | `docs/` | Goals, non-goals, concurrency, schema versioning, **now vs later (status: in repo vs not built)**, risks | Architecture discussion and product path |
| `PLAN-COMPLIANCE.md` | Markdown | `docs/` | PII/PCI: processing vs copies; Phase 1 redaction and `redact_operator_screen`; encrypt later | Operator copies and `/runs` |
| `PLAN-DISCOVERY-EVAL.md` | Markdown | `docs/` | Explore evals/judges for discovery (programmatic yes, LLM judge not yet) | Decide before a corpus |
| `GUIDE.md` | Markdown | `docs/` | Mental model, glossary, how a transfer/hold moves | New developer first hour |
| `ARCHITECTURE.md` | Markdown | `docs/` | Runtime diagram, layer rules, HTTP, one-worker memory | “Where does this request go?” |
| `DESIGN.md` | Markdown | `docs/` | Extract shapes, locators, hold reasons, redacted context | Field-level mapping |
| `DEVELOPER.md` | Markdown | `docs/` | Add a bank, policy, `IAI_*` config, troubleshooting | When changing code |
| `SCENARIOS.md` | Markdown | `docs/` | Manual discovery, post, HOLD, amount-cap walks | After `make test` |
| `CATALOG.md` | Markdown | `docs/` | This file: every source file | Find a file by name or role |

---

## `scripts/`

| Name | Type | Folder | Description | Usage |
| --- | --- | --- | --- | --- |
| `dev.sh` | Bash | `scripts/` | Starts API (8000) and Vite (5173) together; Ctrl-C stops both | Invoked by `make dev` |

---

## `data/native/` — bank seed extracts

Working copies at runtime live in memory (`registry.load_native`); these files are the git-stable seeds.

| Name | Type | Folder | Description | Usage |
| --- | --- | --- | --- | --- |
| `redwood.json` | JSON | `data/native/` | Redwood household/products extract; balances as decimal **strings** | Seed for `/redwood` and `RedwoodAdapter` |
| `northstar.json` | JSON | `data/native/` | Northstar FCU member/suffix extract; amounts in **cents** | Seed for `/northstar` and `NorthstarAdapter` |
| `calloway.json` | JSON | `data/native/` | Calloway short-key dump; LOC `s: HOLD` | Seed for `/calloway`; HOLD path in replay tests |

---

## `data/contracts/` — discovery locator HTML

Vite’s first HTML is an empty `#app`. Discovery falls back to these published contracts.

| Name | Type | Folder | Description | Usage |
| --- | --- | --- | --- | --- |
| `redwood.html` | HTML | `data/contracts/` | `data-iai-*` locators for Redwood | Discovery when live DOM has no fields |
| `northstar.html` | HTML | `data/contracts/` | Same contract pattern for Northstar | Discovery fallback |
| `calloway.html` | HTML | `data/contracts/` | Same for Calloway | Discovery fallback |

---

## `data/schemas/`

| Name | Type | Folder | Description | Usage |
| --- | --- | --- | --- | --- |
| `canonical.schema.json` | JSON Schema | `data/schemas/` | Machine-readable `CanonicalSnapshot` contract | Keep aligned with `canonical.py`; future codegen/CI |

---

## `src/interfaces_ai/` — Python control plane

| Name | Type | Folder | Description | Usage |
| --- | --- | --- | --- | --- |
| `__init__.py` | Python | `src/interfaces_ai/` | Package version | Import `interfaces_ai` |
| `config.py` | Python | `src/interfaces_ai/` | `Settings` from `IAI_*` env / `.env` | Thresholds, `BANK_UI_BASE_URL`, log level |
| `redact.py` | Python | `src/interfaces_ai/` | Last-4, sample kinds, `redact_operator_screen` | Logs; GET `/runs` console copies |
| `observability.py` | Python | `src/interfaces_ai/` | `configure_logging`, redacting StreamHandler | `create_app` and `iai` CLI |
| `cli.py` | Python | `src/interfaces_ai/` | CLI: `institutions`, `canonical`, `discover`, `replay` | `iai …` after install |

### `src/interfaces_ai/schema/`

| Name | Type | Folder | Description | Usage |
| --- | --- | --- | --- | --- |
| `__init__.py` | Python | `schema/` | Re-exports snapshot types | `from interfaces_ai.schema import …` |
| `canonical.py` | Python | `schema/` | Pydantic models: Money, Party, Account, snapshot, intent, discovery/replay/hold types | Shared vocabulary for all agents |
| `adapters.py` | Python | `schema/` | `RedwoodAdapter`, `NorthstarAdapter`, `CallowayAdapter`; unit conversion and `apply_transfer` | Native ↔ snapshot; ledger mutation |
| `registry.py` | Python | `schema/` | Institution list, `load_native` / `save_native` / `reset_native` (in-memory working copy) | Resolve id → file + adapter |

### `src/interfaces_ai/agents/`

| Name | Type | Folder | Description | Usage |
| --- | --- | --- | --- | --- |
| `__init__.py` | Python | `agents/` | Exports Discovery, Replay, Escalation agents | Package imports |
| `base.py` | Python | `agents/` | In-process `Store` for reports, runs, hold cases | Run history for this API process |
| `discovery.py` | Python | `agents/` | Locator parse, `NATIVE_HINTS`, coverage score, contract fallback | `POST /agents/discover`, `iai discover` |
| `replay.py` | Python | `agents/` | Step machine: navigate → fill → policy → submit → post | `POST /agents/replay`, bank/console transfers |
| `escalation.py` | Python | `agents/` | Hold rules: amount, status, coverage, failed steps | Opens `EscalationCase`; does not call an LLM |

### `src/interfaces_ai/api/`

| Name | Type | Folder | Description | Usage |
| --- | --- | --- | --- | --- |
| `__init__.py` | Python | `api/` | Exports `app`, `create_app` | Uvicorn import path |
| `app.py` | Python | `api/` | FastAPI factory, CORS, wires Store + agents | `uvicorn interfaces_ai.api.app:app` |
| `routes.py` | Python | `api/` | HTTP routes: health, institutions, native/canonical, discover, replay, runs, holds, reset | Browser, console, OpenAPI `/docs` |

---

## `tests/`

| Name | Type | Folder | Description | Usage |
| --- | --- | --- | --- | --- |
| `conftest.py` | Python (pytest) | `tests/` | Autouse fixture: `reset_native()` around every test | Isolates ledger mutations |
| `test_schema.py` | Python (pytest) | `tests/` | Same person, checking $2190.40, Calloway HOLD mapping | Adapter correctness |
| `test_discovery.py` | Python (pytest) | `tests/` | Locator extract, coverage score, empty-SPA fallback | Discovery behavior |
| `test_replay.py` | Python (pytest) | `tests/` | Redwood post; Calloway HOLD block; Northstar large amount | Write vs no-write |
| `test_escalation.py` | Python (pytest) | `tests/` | Amount + HOLD are distinct reason codes | Hold policy |
| `test_api.py` | Python (pytest) | `tests/` | Health, 404/422, `/runs` redaction after discover + HOLD | HTTP including error and compliance paths |
| `redwood.html` | HTML fixture | `tests/fixtures/` | Sample marked-up page for discovery unit tests | Injected via `html_loader` |

---

## `banks-ui/` — TypeScript portals (Vite)

| Name | Type | Folder | Description | Usage |
| --- | --- | --- | --- | --- |
| `package.json` | JSON | `banks-ui/` | npm scripts (`dev`, `build`) and Vite/TypeScript deps | `npm install` / `npm run dev` |
| `package-lock.json` | JSON lockfile | `banks-ui/` | Pinned npm tree | Reproducible UI install |
| `tsconfig.json` | JSON | `banks-ui/` | TypeScript compiler options (strict, noEmit) | `tsc --noEmit` |
| `vite.config.ts` | TypeScript | `banks-ui/` | Dev server on `127.0.0.1:5173`; proxies `/api` and `/health` to 8000 | Local UI + API same-origin |
| `index.html` | HTML | `banks-ui/` | SPA shell: `#app`, fonts, entry `/src/main.ts` | Vite root page |

### `banks-ui/src/`

| Name | Type | Folder | Description | Usage |
| --- | --- | --- | --- | --- |
| `main.ts` | TypeScript | `banks-ui/src/` | Client router: `/`, `/redwood`, `/northstar`, `/calloway`, `/console` | App entry; history API |
| `api.ts` | TypeScript | `banks-ui/src/` | `fetch` helpers and types for native, canonical, replay | All pages that talk to FastAPI |
| `format.ts` | TypeScript | `banks-ui/src/` | Currency formatters and shared top nav | Nav + money display |
| `transfer.ts` | TypeScript | `banks-ui/src/` | Transfer form HTML (`data-iai-*`) and submit → replay API | Shared by the three bank pages |
| `vite-env.d.ts` | TypeScript | `banks-ui/src/` | Vite client types so CSS imports typecheck | `tsc` only |

### `banks-ui/src/pages/`

| Name | Type | Folder | Description | Usage |
| --- | --- | --- | --- | --- |
| `hub.ts` | TypeScript | `pages/` | Home: explains three extracts + links | Route `/` |
| `redwood.ts` | TypeScript | `pages/` | Redwood portal; renders **native** household/products JSON | Route `/redwood` |
| `northstar.ts` | TypeScript | `pages/` | Northstar portal; suffixes and cents | Route `/northstar` |
| `calloway.ts` | TypeScript | `pages/` | Calloway portal; short keys and HOLD row | Route `/calloway` |
| `console.ts` | TypeScript | `pages/` | Operator console: discovery, replay, snapshot, hold table | Route `/console` |

### `banks-ui/src/styles/`

| Name | Type | Folder | Description | Usage |
| --- | --- | --- | --- | --- |
| `global.css` | CSS | `styles/` | Reset, hub, shared tables/forms | Loaded on every route |
| `redwood.css` | CSS | `styles/` | Forest/terracotta theme | `/redwood` |
| `northstar.css` | CSS | `styles/` | Navy/ice theme | `/northstar` |
| `calloway.css` | CSS | `styles/` | Maroon/cream “core screen” theme | `/calloway` |
| `console.css` | CSS | `styles/` | Dark operator theme | `/console` |

---

## Quick “I need to…”

| I need to… | Start here |
| --- | --- |
| Run the app | `README.md`, `Makefile`, `scripts/dev.sh` |
| Change Jordan’s Redwood balance | `data/native/redwood.json` |
| Change how cents become Money | `src/interfaces_ai/schema/adapters.py` |
| Change hold dollar limit | `.env.example` / `config.py` (`IAI_TRANSFER_ESCALATION_USD`) |
| Change locator contract | matching file in `data/contracts/` **and** the bank page in `pages/` |
| Add an HTTP route | `src/interfaces_ai/api/routes.py` |
| Add a test | `tests/test_*.py` |
| Walk discovery / post / hold by hand | `docs/SCENARIOS.md` |
| List every Markdown doc | `README.md` (Docs table) |
| Understand the design | `docs/GUIDE.md`, `docs/PLAN.md`, `docs/ARCHITECTURE.md`, `docs/DESIGN.md`, `docs/PLAN-COMPLIANCE.md`, `docs/PLAN-DISCOVERY-EVAL.md` |
| See operator-copy redaction | `docs/PLAN-COMPLIANCE.md`, console **Operator copies**, `GET /api/v1/runs` |
