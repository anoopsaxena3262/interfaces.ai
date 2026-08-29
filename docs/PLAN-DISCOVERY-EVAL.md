# Plan: discovery evals and judges (explore)

This is an **exploration** of whether discovery can grow an eval corpus and judges. It does not implement either. Overall discovery design stays in [PLAN.md](PLAN.md). Confidence today is called out there as a made-up 0–1, not a calibrated control. Sample/PII rules for any future corpus: [PLAN-COMPLIANCE.md](PLAN-COMPLIANCE.md). Doc index: [README.md](../README.md#docs).

**Verdict in one line:** Yes for **programmatic evals** (labeled pages + extracts, exact checks). No for **LLM judges on the current agent** — discovery is a lookup plus a formula, so a model judge would grade our own answer key. LLM judges become useful only if discovery starts *proposing* maps (the “optional model assist” row in PLAN.md). **Not implemented** — this file is the decision, not a corpus in the tree. See [PLAN.md now vs later](PLAN.md#now-vs-later-sandbox-vs-product).

## What discovery is today

`DiscoveryAgent.discover` is deterministic:

1. Parse `data-iai-*` from live HTML, or fall back to `data/contracts/<id>.html`.
2. Load native JSON, run `to_canonical`.
3. For each `CANONICAL_REQUIRED` path, copy `NATIVE_HINTS[institution][path]` and a live sample from the snapshot.
4. Emit `confidence ≈ 0.9 * coverage + locator bonus + submit bonus − leftover penalty`.

Holds then compare that number to `IAI_DISCOVERY_MIN_CONFIDENCE` (0.72).

`tests/test_discovery.py` already asserts a happy Redwood score (`confidence >= 0.85`), empty-SPA fallback, and “no hold when confident.” That is **regression**, not an eval: three fixtures, no negatives, no gold field maps, no claim that the 0–1 is calibrated.

`NATIVE_HINTS` is a second copy of the adapter map. An eval that only re-runs the three seeds will always pass. The interesting cases are **drift and damage**: missing locators, wrong canonical attributes, extract keys the hints do not know, contract HTML that disagrees with the live page.

## Can we add evals?

**Yes.** Discovery has a stable output type (`DiscoveryReport`) and a small required-path list. An eval is a folder of cases, each with inputs and an expected judgment — independent of the formula inside `discovery.py`.

### What an eval case is

| Piece | Role |
| --- | --- |
| `institution_id` | Which adapter / hints |
| `html` (or path) | Page under test; may be empty `#app`, published contract, or a mutated contract |
| `native` (or “use seed”) | Extract; optional mutant (drop `position.avail`, rename `partyKey`) |
| `expect` | Gold: required paths present/absent, locators, actions, hold or not |
| `tags` | `happy`, `empty_spa`, `missing_locator`, `hint_mismatch`, `pii_sample` |

Three banks × one happy path is the **smoke set**. The eval set is the same agent run against **labeled mutants**. Without mutants, evals duplicate pytest.

### What evals can measure (this sandbox)

| Claim | Measurable without a model? | Notes |
| --- | --- | --- |
| Required snapshot paths are bound | Yes | Compare `fields[].canonical_path` to gold |
| Native path matches the adapter | Yes, if gold is generated from the mapping file — **not** from `NATIVE_HINTS` copied into the case | Otherwise the eval rubber-stamps the bug |
| Locators exist for transfer bind | Yes | `transfer.from_account`, `to`, `amount`, `transfer.submit` |
| Empty SPA still discovers via contract | Yes | Already a unit test; promote to a tagged case |
| Missing required path opens a hold | Yes | Mutant extract; `EscalationReason.UNMAPPED_FIELDS` |
| Score ≥ 0.72 iff coverage is complete | Weak | The formula can be gamed (bonuses). Prefer **coverage %** and **missing paths** as the eval metrics; keep `confidence` as telemetry |
| Live DOM matches `data/contracts/` | Not in this sandbox | Needs a browser worker (PLAN later row). Eval can still **diff** page TS locators vs contract files as a static check |

### What evals cannot measure yet

- “Is this a reasonable mapping for an unknown core dump?” — no unlabeled dumps; hints are hardcoded.
- Calibration of confidence vs real automation success — three always-succeed banks.
- Locator health on a live SPA — first HTML is empty `#app`.

### Eval vs pytest vs hold module

| Layer | Job |
| --- | --- |
| pytest | Fast invariants: parse contract, fallback HTML, API lists banks |
| Eval corpus | Labeled cases, including failures; scores over time; CI gate on the corpus |
| EscalationAgent | Runtime gate for a *single* live report (missing paths, low score) |

Do not replace holds with “the eval passed last night.” Evals certify the agent on a frozen set. Holds still run on the report in front of you.

**Gold source of truth.** If case `expect.native_path` is copied from `NATIVE_HINTS`, adapter drift is invisible. Prefer gold from the same artifact adapters use, or from a checked-in `expected_report.json` that humans edit when a bank mapping *intentionally* changes. PLAN’s “one mapping file” increment makes this honest; until then, goldens must be reviewed, not generated from `discovery.py` output in CI.

## Can we add judges?

A **judge** scores a `DiscoveryReport` (and maybe HTML + native) and returns pass/fail plus reason codes. Same idea as hold reasons: enum, not a paragraph.

### Programmatic judges — yes, add these

These are functions. They belong next to eval cases, not inside `ReplayEngine`. They must not write ledgers.

| Judge | Input | Pass when | Why |
| --- | --- | --- | --- |
| `coverage` | report + `CANONICAL_REQUIRED` | `missing_canonical_paths` equals gold (often empty) | This is the real “can we automate?” signal |
| `locator_bind` | report | Transfer locators present if gold says the page is interactive | Replay FILL/SUBMIT need them |
| `hint_agreement` | report + adapter or mapping file | Each `native_path` matches gold | Catches `NATIVE_HINTS` vs adapter drift |
| `contract_drift` | report vs `data/contracts/<id>.html` | Locators in the report ⊆ contract (or exact set) | Catches “we parsed a fixture we wrote” lying |
| `no_live_pii_sample` | report | Samples are kinds/masks, not email/phone/balances | Aligns with [PLAN-COMPLIANCE.md](PLAN-COMPLIANCE.md) |
| `hold_alignment` | report + EscalationAgent | Hold opened iff gold `should_hold` | Stops confidence formula from disagreeing with missing-path holds |

A runner: for each case, `discover(...)` → run judges → compare to `expect`. CI fails on unexpected fail (or unexpected pass on a `should_fail` case).

These judges **are** the eval. You do not need a second LLM to say “coverage is 8/8.”

### LLM-as-judge — not for the current agent

The current report is almost entirely copied from `NATIVE_HINTS` and `data-iai-canonical`. Asking a model “is `household.partyKey` a good customer.id?” will either echo the hints or disagree with the adapter we already trust. Cost, keys, and non-determinism buy nothing on three labeled banks.

PLAN already says: LLM may *propose* a mapping; this module still gates. That is the right split.

**When an LLM judge is worth exploring**

1. Discovery (or a sidecar) **proposes** `native_path` / locators from HTML + JSON **without** `NATIVE_HINTS`.
2. Goldens exist for a held-out set of banks or mutated pages the proposer has not memorized.
3. The judge scores the *proposal* against gold (programmatic first: exact path match, then maybe a rubric for “acceptable alternate path”).
4. The judge **never** sits on the transfer path. A bad proposal → hold / human accept into the map file. Replay still uses the adapter.

Until (1) exists, skip LLM judges.

If we add a proposer later, prefer **programmatic agreement with gold** as the primary judge, and an LLM judge only for “unlabeled HTML, is this locator plausible?” — with a human still required before the map ships. Do not let an LLM judge clear `low_discovery_confidence` by itself.

### Hold module is already a runtime judge

`EscalationAgent.evaluate_discovery` is a judge: confidence floor + missing paths → case. Evals should **test** that judge on mutants, not wrap it in a model. Splitting “coverage” from “confidence” (PLAN ideal column) makes the runtime judge honest; evals then assert coverage, not `>= 0.85`.

## Recommended shape if we proceed

Keep it laptop-local, no API keys, same as the sandbox goals.

```text
data/evals/discovery/
  cases/
    redwood-happy.yaml
    calloway-empty-spa.yaml
    redwood-drop-avail.yaml      # native mutant → missing accounts[].available
    northstar-strip-locators.yaml
  expected/                      # optional golden reports (redacted samples)
```

Runner: `pytest tests/test_discovery_eval.py` or `iai eval discovery` that loads cases, runs judges, prints a table (passed/failed by tag). No new service.

**Do not** put eval cases’ native mutants in `data/native/` (those are demo seeds). Do not log live samples in expected files (compliance plan).

## What we would not do

- Use eval scores as a PCI/credit/compliance control (PLAN already forbids this for `confidence`).
- Gate `POST /agents/replay` on “last eval run was green.”
- Add an LLM judge in front of the three current banks.
- Generate goldens by dumping `DiscoveryReport` in CI without a human diff.
- Expand `CANONICAL_REQUIRED` just to make the eval look harder — coverage denominator is a product decision.

## Fit with other plans

| Plan | Interaction |
| --- | --- |
| [PLAN.md](PLAN.md) discovery confidence risk | Evals replace “believe the 0–1” with labeled coverage; confidence stays telemetry. Corpus is sandbox-now, **not in repo**. |
| PLAN.md model assist | Proposer + gold evals + programmatic judge; LLM judge optional and off the money path |
| PLAN.md real DOM | Eval corpus can grow a `live_dom` tag once Playwright exists; not a blocker for HTML-file cases |
| [PLAN-COMPLIANCE.md](PLAN-COMPLIANCE.md) | `no_live_pii_sample` judge; eval fixtures must not freeze Jordan’s email into goldens |

## Phased delivery (only if we choose to build)

Exploration is done enough to decide. Implementation would be:

1. **Judges as pure functions** over `DiscoveryReport` (+ optional HTML). Unit-test each judge on hand-built reports (no HTTP).
2. **Corpus** of happy + mutant cases for the three banks. Runner in pytest. CI on the corpus.
3. **Stop using confidence as the eval metric**; report coverage and hold alignment. Optionally stop using confidence as the *only* runtime hold input (that is a product change; not required to land evals).
4. **Later:** mapping-file gold; live DOM cases; proposer + gold match. LLM judge last, if ever.

## Success for this exploration

We can answer: evals yes (labeled mutants + programmatic judges); LLM judges no until discovery proposes. The hold module stays the runtime gate. The first useful eval is “redwood with `position.avail` removed → missing path + hold,” not “confidence is still 0.9.”
