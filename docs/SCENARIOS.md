# Test scenarios

Step-by-step checks for discovery, a successful transfer, and holds. For why the rules exist, see [DESIGN.md](DESIGN.md). For how to change a bank or a limit, see [DEVELOPER.md](DEVELOPER.md).

Holds are not a separate scenario file. A case opens when **replay** hits a rule in `src/interfaces_ai/agents/escalation.py`. You trigger a scenario by choosing institution, from/to accounts, and amount.

## Before you start

1. First clone only: `make setup`.
2. Start the app: `make dev`.
3. UI: http://127.0.0.1:5173 — API: http://127.0.0.1:8000/docs.

Most scenarios below use the **operator console**: http://127.0.0.1:5173/console

Ledger writes are in memory. Between scenarios, click **Reset ledgers** on the console (or restart the API) so balances match `data/native/` again. The hold queue is also in memory; it clears on API restart.

Automated equivalent of the hold and post paths:

```bash
make test
```

## Console replay (how every transfer scenario is entered)

1. Open http://127.0.0.1:5173/console
2. Under **Replay transfer**, set **Institution** (account dropdowns reload for that bank).
3. Set **From**, **To**, **Amount (USD)**.
4. Click **Replay**.
5. Read the step list under the form, then the **Hold queue** at the bottom.

You can run the same intent on a bank portal (`/redwood`, `/northstar`, `/calloway`) instead. The portal still calls replay. Status text is `Posted (…)` or `Held for review — esc-…`.

CLI (venv activated), same intents:

```bash
source .venv/bin/activate
iai replay <institution_id> <from_id> <to_id> <amount> --memo "scenario"
```

---

## Scenario 1 — Native screens still look native

**Goal:** Schema mismatch is visible. Portals must not render the snapshot.

1. Open http://127.0.0.1:5173
2. Open **Redwood**. Confirm labels like `productInstance`, `kind`, `avail` (not a generic “Account ID” everywhere).
3. Open **Northstar**. Confirm `sfx`, cents, `Hale, Jordan A`.
4. Open **Calloway**. Confirm `acct_rel` / short keys and a **HOLD** row on PERSONAL LOC.

**Pass:** Each page still speaks that bank’s JSON.

---

## Scenario 2 — Discovery scores all three extracts

**Goal:** Locators exist and coverage is high enough that discovery does **not** open a hold.

1. Console → **Run discovery**.
2. Each bank chip should show a confidence score (not `—`).
3. Hold queue should stay empty for this step (defaults: score ≥ `0.72`, required snapshot paths present).

CLI: `iai discover`

**Pass:** Three scores. No `low_discovery_confidence` / `unmapped_fields` cases.

**Pytest:** `tests/test_discovery.py`

---

## Scenario 3 — Redwood $40 posts (happy path)

**Goal:** Shared intent becomes a Redwood write. Checking available drops by 40. No hold.

| Field | Value |
| --- | --- |
| Institution | Redwood Community Bank (`redwood`) |
| From | Everyday checking `CHK-77` |
| To | Reserve `SAV-12` |
| Amount | `40` |

1. Note checking available on `/redwood` (seed is **$2190.40**).
2. Console: institution **redwood**, from `CHK-77`, to `SAV-12`, amount `40` → **Replay**.
3. Step list should end with a successful **post**.
4. Reload `/redwood`. Checking available is **$2150.40**. Reserve is $40 higher.
5. Hold queue has **no** new row for this run.

CLI: `iai replay redwood CHK-77 SAV-12 40 --memo "happy path"`

**Pass:** `succeeded`; balances moved; no `escalation_id`.

**Pytest:** `test_replay_updates_redwood_string_balances` in `tests/test_replay.py`

---

## Scenario 4 — Calloway HOLD (account status)

**Goal:** Native `s: "HOLD"` maps to snapshot `status: "hold"`. Replay stops. Reason is `account_status`, not a sentence from an LLM.

| Field | Value |
| --- | --- |
| Institution | Calloway State Bank (`calloway`) |
| From | CHECKING `900210001` |
| To | PERSONAL LOC `900210099` |
| Amount | `20` (any small amount) |

1. Optional: on `/calloway`, confirm PERSONAL LOC shows **HOLD**.
2. Console: institution **calloway**, from `900210001`, to `900210099`, amount `20` → **Replay**.
3. Form / portal shows **Held for review** and an `esc-…` id.
4. Hold queue: bank `calloway`, reasons include **`account_status`**, severity **critical**.
5. Reload `/calloway`. Checking **$2190.40** is unchanged.

CLI: `iai replay calloway 900210001 900210099 20 --memo "hold status"`

**Pass:** `succeeded` is false; balances unchanged; reason `account_status`.

**Pytest:** `test_replay_stops_on_calloway_hold` in `tests/test_replay.py`

---

## Scenario 5 — Northstar amount cap

**Goal:** Amount ≥ `IAI_TRANSFER_ESCALATION_USD` (default **5000**) opens `amount_threshold`. Write does not post.

| Field | Value |
| --- | --- |
| Institution | Northstar FCU (`northstar`) |
| From | Regular shares suffix `01` |
| To | Share draft suffix `00` |
| Amount | `9000` |

1. Console: institution **northstar**, from `01`, to `00`, amount `9000` → **Replay**.
2. Held for review. Hold queue reasons include **`amount_threshold`**.
3. Reload `/northstar`. Suffix `01` still **$8840.00** (884000 cents).

CLI: `iai replay northstar 01 00 9000 --memo "amount cap"`

**Pass:** no post; reason `amount_threshold`.

**Pytest:** `test_replay_stops_when_amount_hits_limit` in `tests/test_replay.py`

---

## Scenario 6 — Amount and HOLD are different codes

**Goal:** One intent can carry both reasons. Reviewers filter by enum, not by reading `summary`.

Use Calloway from `900210001` to `900210099` with amount **`9000`**.

1. Console replay as in scenario 4, amount `9000`.
2. Hold queue **Reasons** should include both `amount_threshold` and `account_status`.

**Pytest:** `tests/test_escalation.py`

---

## Scenario 7 — Policy (same account or over available)

These use existing seeds. No JSON edit.

**Same account**

1. Console, Redwood, from `CHK-77`, to `CHK-77`, amount `10`.
2. Hold: reason **`policy`**. Checking does not move.

**Insufficient funds**

Seed checking available is **$2190.40**.

1. Console, Redwood, from `CHK-77`, to `SAV-12`, amount `3000`.
2. Hold: reason **`policy`**. Balances unchanged.

---

## Scenario 8 — API smoke

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/api/v1/institutions
```

**Pass:** `{"ok":true}` and ids `redwood`, `northstar`, `calloway`.

**Pytest:** `tests/test_api.py`

---

## What each hold reason means

| Reason | How to trigger with current seeds |
| --- | --- |
| `account_status` | Calloway → PERSONAL LOC `900210099` |
| `amount_threshold` | Any bank, amount ≥ 5000 (Northstar $9000 is the fixture) |
| `policy` | Same from/to, or amount > available |
| `low_discovery_confidence` | Lower `IAI_DISCOVERY_MIN_CONFIDENCE` or break locators (not a default demo) |
| `unmapped_fields` | Remove a required mapping (not a default demo) |
| `replay_step_failed` | A replay step returns `ok: false` (hold path after a failed step) |

Limits live in `.env` / `.env.example` (`IAI_TRANSFER_ESCALATION_USD`, `IAI_DISCOVERY_MIN_CONFIDENCE`). Restart the API after changing them.

---

## Adding a new hold fixture

Example: freeze a Redwood product the same way Calloway HOLD works.

1. Edit `data/native/<bank>.json` so the native status is not the adapter’s “open” value (Calloway uses `s: "HOLD"`).
2. Confirm the adapter maps that to snapshot `status` other than `open`.
3. **Reset ledgers** or restart the API.
4. Replay using that account id. Expect `account_status` and no balance change.
5. Add a pytest that asserts `escalation_id` and the **reason code**, not the English summary.
6. Add a row to the table in [DESIGN.md](DESIGN.md) if the mapping is new.

Do not add a new `EscalationReason` unless the condition is actually new. Do not put the why in `summary` only.
