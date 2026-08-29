# FI extract sandbox

Three mock bank portals, three incompatible JSON extracts, one shared snapshot, and three Python modules:

1. **Discovery** — find locators and score whether an extract covers the snapshot.
2. **Replay** — take a shared transfer intent, convert it to that bank’s body, apply it.
3. **Hold / review** — stop the write when amount, account status, or a failed step says so.

Jordan Hale is the same person at all three institutions. The JSON is not.

## Banks

| Portal | URL | What is weird about the JSON |
| --- | --- | --- |
| Redwood Community Bank | http://127.0.0.1:5173/redwood | Household tree; balances as **strings** |
| Northstar FCU | http://127.0.0.1:5173/northstar | `LAST, FIRST` name; amounts in **cents**; suffixes |
| Calloway State Bank | http://127.0.0.1:5173/calloway | One-letter keys; sign split from amount; LOC on **HOLD** |
| Console | http://127.0.0.1:5173/console | Run the three modules |
| API | http://127.0.0.1:8000/docs | OpenAPI |

## Setup

Python 3.11+ and Node 20+.

```bash
make setup
```

Same steps without Make:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cd banks-ui && npm install && cd ..
```

## How to run

From the repo root, with the venv already created by `make setup`:

```bash
make dev
```

That starts both processes:

| Process | URL |
| --- | --- |
| Bank UIs + console | http://127.0.0.1:5173 |
| API (OpenAPI) | http://127.0.0.1:8000/docs |

Two terminals instead of `make dev`:

```bash
make dev-api
make dev-ui
```

Stop with Ctrl-C. Ledger writes are in memory; **Reset ledgers** on the console, or restart the API, to reload `data/native/`.

## How to test

Automated tests (schema mapping, discovery, replay, holds, API 404/422, operator-copy redaction):

```bash
make test
```

Lint:

```bash
make lint
```

After `make test` is green, run the app (`make dev`) and walk the scenarios in [docs/SCENARIOS.md](docs/SCENARIOS.md) (console, holds, CLI). Short version:

1. Open http://127.0.0.1:5173 and each bank portal. Screens must still show **native** field names (`productInstance`, `sfx`, `acct_rel`), not a cleaned-up snapshot.
2. Console → **Run discovery**. Each bank should report locators and a coverage score.
3. Replay **$40** Redwood checking `CHK-77` → reserve `SAV-12`. Should **post**; checking available drops by 40.
4. Replay Calloway `900210001` → `900210099`. Should **open a hold** (LOC is HOLD); balances must not move.
5. Replay Northstar **$9000** from suffix `01`. Should **open a hold** (over the dollar limit).

Optional CLI (venv activated):

```bash
source .venv/bin/activate
iai institutions
iai canonical redwood
iai discover
iai replay redwood CHK-77 SAV-12 40 --memo "cli"
```

## Layout

```
banks-ui/          TypeScript portals + console (operator copies are redacted)
data/native/       Seed extracts (do not edit from the UI)
data/contracts/    Locator HTML used when the SPA has not rendered
src/interfaces_ai/ Snapshot models, adapters, discovery, replay, holds, API
docs/              Design, runtime, scenarios, and increment plans
```

## Docs

Every Markdown file in the repo:

| File | Description |
| --- | --- |
| [README.md](README.md) | Clone, `make setup` / `make dev` / `make test`, bank URLs, CLI, and this index. |
| [docs/GUIDE.md](docs/GUIDE.md) | First-hour mental model: native vs snapshot, adapters, discovery/replay/holds, glossary. |
| [docs/CATALOG.md](docs/CATALOG.md) | Inventory of every source file (path, type, when to touch it). |
| [docs/PLAN.md](docs/PLAN.md) | Why the sandbox exists: goals, non-goals, concurrency, schema versioning, now vs later (what is **in the repo** vs sandbox-next vs product), risks. |
| [docs/PLAN-COMPLIANCE.md](docs/PLAN-COMPLIANCE.md) | PII/PCI: what processing needs vs copies; Phase 1 redaction (kinds, empty SUBMIT, `redact_operator_screen`); encryption later. |
| [docs/PLAN-DISCOVERY-EVAL.md](docs/PLAN-DISCOVERY-EVAL.md) | Exploration only: programmatic evals/judges for discovery vs LLM-as-judge (not for the current agent). |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Runtime diagram, layer rules, HTTP routes, one-worker `_working` / `Store`. |
| [docs/DESIGN.md](docs/DESIGN.md) | Per-bank extract quirks, `data-iai-*` locators, hold reason table, redacted hold context. |
| [docs/DEVELOPER.md](docs/DEVELOPER.md) | Add a bank, change policy/config (`IAI_*`), troubleshooting (including two-worker split-brain). |
| [docs/SCENARIOS.md](docs/SCENARIOS.md) | Manual walks: discovery, Redwood $40 post, Calloway HOLD, Northstar $9000, CLI equivalents. |

Start with the README, then [GUIDE.md](docs/GUIDE.md) if you are new. Use [CATALOG.md](docs/CATALOG.md) to find a file.

## License

GNU GPL v3. See [LICENSE](LICENSE).
