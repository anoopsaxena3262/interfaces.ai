import { api, getCanonical, replayTransfer, type CanonicalSnapshot } from "../api";
import { nav, usdFromCanonical } from "../format";

type Institution = { id: string; name: string; extract_kind: string; notes: string };
type DiscoveryReport = {
  institution_id: string;
  confidence: number;
  missing_canonical_paths: string[];
  unmapped_native_paths: string[];
  fields: Array<{ canonical_path: string; native_path: string; sample?: string }>;
};
type Escalation = {
  id: string;
  created_at: string;
  institution_id: string;
  severity: string;
  summary: string;
  reasons: string[];
  status: string;
  context?: Record<string, unknown>;
};
type Replay = {
  run_id: string;
  institution_id: string;
  succeeded: boolean;
  escalation_id: string | null;
  steps: Array<{ kind: string; description: string; ok: boolean; detail: string }>;
};

export async function renderConsole(app: HTMLElement): Promise<void> {
  document.title = "Operator console";
  document.body.className = "theme-console";
  app.innerHTML = `${nav("/console")}<main class="shell"><p>Loading console…</p></main>`;

  const [institutions, runs] = await Promise.all([
    api<Institution[]>("/api/v1/institutions"),
    api<{ discoveries: DiscoveryReport[]; replays: Replay[]; escalations: Escalation[] }>("/api/v1/runs"),
  ]);
  const snapshots: Record<string, CanonicalSnapshot> = {};
  for (const inst of institutions) {
    snapshots[inst.id] = await getCanonical(inst.id);
  }

  const latestDiscovery = (id: string) => runs.discoveries.find((d) => d.institution_id === id);
  const defaultBank = institutions[0]?.id ?? "redwood";
  const accounts = snapshots[defaultBank]?.accounts ?? [];

  app.innerHTML = `${nav("/console")}
    <main class="shell">
      <h1>Operator console</h1>
      <p class="lede">
        Discovery scores each extract against the shared snapshot. Replay writes a
        bank-shaped transfer. Holds are opened by local rules (amount, account status, failed steps).
      </p>
      <div class="actions">
        <button type="button" data-action="discover">Run discovery</button>
        <button type="button" class="secondary" data-action="reset">Reset ledgers</button>
      </div>
      <div class="chips">
        ${institutions
          .map((inst) => {
            const report = latestDiscovery(inst.id);
            const score = report ? report.confidence.toFixed(2) : "—";
            return `<div class="chip"><div class="eyebrow">${inst.name}</div><div class="n">${score}</div>
              <small>${inst.extract_kind}</small></div>`;
          })
          .join("")}
      </div>
      <div class="row">
        <section class="panel">
          <h2>Replay transfer</h2>
          <form data-console-replay>
            <label>Institution
              <select name="institution_id">
                ${institutions.map((i) => `<option value="${i.id}">${i.name}</option>`).join("")}
              </select>
            </label>
            <label>From
              <select name="from_account_id">
                ${accounts.map((a) => `<option value="${a.id}">${a.name} (${a.id})</option>`).join("")}
              </select>
            </label>
            <label>To
              <select name="to_account_id">
                ${[...accounts]
                  .reverse()
                  .map((a) => `<option value="${a.id}">${a.name} (${a.id})</option>`)
                  .join("")}
              </select>
            </label>
            <label>Amount (USD)
              <input name="amount" type="number" step="0.01" value="50" />
            </label>
            <label>Memo
              <input name="memo" value="Console replay" />
            </label>
            <button type="submit">Replay</button>
          </form>
          <ul class="steps" data-steps></ul>
        </section>
        <section class="panel">
          <h2>Canonical snapshot</h2>
          <pre data-canonical>${escapeHtml(preview(snapshots[defaultBank]))}</pre>
        </section>
      </div>
      <section class="panel" style="margin-top:1rem">
        <h2>Operator copies</h2>
        <p class="lede">
          Discovery samples and hold context are redacted together before this screen
          (<code>redact_operator_screen</code>). Kinds only for samples; last-4 ids on holds.
        </p>
        <div class="row">
          <div>
            <h3>Discovery samples</h3>
            ${operatorDiscoveryHtml(latestDiscovery(defaultBank))}
          </div>
          <div>
            <h3>Hold context</h3>
            ${operatorHoldHtml(runs.escalations[0])}
          </div>
        </div>
      </section>
      <section class="panel" style="margin-top:1rem">
          <h2>Hold queue</h2>
        ${
          runs.escalations.length === 0
            ? "<p>No holds yet. Try Calloway checking → PERSONAL LOC, or an amount ≥ $5,000.</p>"
            : `<table><thead><tr><th>ID</th><th>Bank</th><th>Severity</th><th>Reasons</th><th>Summary</th></tr></thead><tbody>
              ${runs.escalations
                .map(
                  (c) => `<tr>
                    <td>${c.id}</td>
                    <td>${c.institution_id}</td>
                    <td class="sev-${c.severity}">${c.severity}</td>
                    <td>${c.reasons.join(", ")}</td>
                    <td>${escapeHtml(c.summary)}</td>
                  </tr>`,
                )
                .join("")}
            </tbody></table>`
        }
      </section>
    </main>`;

  const institutionSelect = app.querySelector<HTMLSelectElement>('select[name="institution_id"]');
  const fromSelect = app.querySelector<HTMLSelectElement>('select[name="from_account_id"]');
  const toSelect = app.querySelector<HTMLSelectElement>('select[name="to_account_id"]');
  const canonicalPre = app.querySelector("[data-canonical]");

  async function fillAccounts(id: string) {
    const snap = snapshots[id] ?? (await getCanonical(id));
    snapshots[id] = snap;
    if (fromSelect && toSelect) {
      fromSelect.innerHTML = snap.accounts
        .map((a) => `<option value="${a.id}">${a.name} (${a.id}) · ${usdFromCanonical(a.available.amount)}</option>`)
        .join("");
      toSelect.innerHTML = [...snap.accounts]
        .reverse()
        .map((a) => `<option value="${a.id}">${a.name} (${a.id}) · ${a.status}</option>`)
        .join("");
    }
    if (canonicalPre) canonicalPre.textContent = preview(snap);
  }

  institutionSelect?.addEventListener("change", () => void fillAccounts(institutionSelect.value));

  app.querySelector("[data-action='discover']")?.addEventListener("click", async () => {
    await api("/api/v1/agents/discover", { method: "POST", body: JSON.stringify({}) });
    await renderConsole(app);
  });
  app.querySelector("[data-action='reset']")?.addEventListener("click", async () => {
    await api("/api/v1/dev/reset", { method: "POST", body: "{}" });
    await renderConsole(app);
  });

  app.querySelector<HTMLFormElement>("[data-console-replay]")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget as HTMLFormElement;
    const data = new FormData(form);
    const result = await replayTransfer({
      institution_id: String(data.get("institution_id")),
      from_account_id: String(data.get("from_account_id")),
      to_account_id: String(data.get("to_account_id")),
      amount: Number(data.get("amount")),
      memo: String(data.get("memo")),
    });
    const steps = app.querySelector("[data-steps]");
    if (steps) {
      steps.innerHTML = result.steps
        .map(
          (s) =>
            `<li class="${s.ok ? "pass" : "fail"}"><strong>${s.kind}</strong> ${escapeHtml(s.description)}${s.detail ? ` — ${escapeHtml(s.detail)}` : ""}</li>`,
        )
        .join("");
    }
    if (!result.succeeded) {
      await renderConsole(app);
      return;
    }
    await fillAccounts(String(data.get("institution_id")));
  });
}

function operatorDiscoveryHtml(report: DiscoveryReport | undefined): string {
  if (!report?.fields?.length) {
    return "<p>Run discovery to see kind tokens for each required path.</p>";
  }
  const rows = report.fields
    .map(
      (f) =>
        `<tr><td>${escapeHtml(f.canonical_path)}</td><td>${escapeHtml(f.native_path)}</td><td><code>${escapeHtml(String(f.sample ?? ""))}</code></td></tr>`,
    )
    .join("");
  return `<table><thead><tr><th>Snapshot path</th><th>Native path</th><th>Sample</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function operatorHoldHtml(caseRow: Escalation | undefined): string {
  if (!caseRow) {
    return "<p>No hold yet. Context appears here after a blocked replay.</p>";
  }
  return `<pre>${escapeHtml(JSON.stringify(caseRow.context ?? {}, null, 2))}</pre>`;
}

function preview(snapshot: CanonicalSnapshot | undefined): string {
  if (!snapshot) return "";
  return JSON.stringify(
    {
      customer: {
        id: snapshot.customer.id,
        display_name: snapshot.customer.display_name,
      },
      accounts: snapshot.accounts.map((a) => ({
        id: a.id,
        type: a.type,
        status: a.status,
        available: a.available,
      })),
      mapping_notes: snapshot.mapping_notes,
    },
    null,
    2,
  );
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}
