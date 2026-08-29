import { getNative } from "../api";
import { nav, usdFromCents } from "../format";
import { bindTransfer, transferForm } from "../transfer";

type CallowayNative = {
  sys: string;
  cust: { cif: string; name1: string; email: string; voice: string };
  acct_rel: Array<{
    n: string;
    d: string;
    t: string;
    m: string;
    a: number;
    l: number;
    s: string;
  }>;
  hist: Array<{ k: string; ymd: string; t: string; s: string; p: number; n: string }>;
};

export async function renderCalloway(app: HTMLElement): Promise<void> {
  document.title = "Calloway State Bank";
  document.body.className = "theme-calloway";
  const native = await getNative<CallowayNative>("calloway");

  app.innerHTML = `${nav("/calloway")}
    <div class="banner">${native.sys} · INQUIRY SCREEN · HOLD ACCOUNTS WILL NOT POST</div>
    <main class="shell" data-iai-page="dashboard" data-iai-institution="calloway">
      <p class="wordmark">Calloway State Bank</p>
      <h1 data-iai-field="customer.display_name" data-iai-canonical="customer.display_name">${native.cust.name1}</h1>
      <p class="cif">
        CIF
        <span data-iai-field="customer.id" data-iai-canonical="customer.id">${native.cust.cif}</span>
        · ${native.cust.email}
      </p>
      <table>
        <thead>
          <tr><th>n</th><th>d</th><th>t</th><th>s</th><th>a</th><th>l</th></tr>
        </thead>
        <tbody>
          ${native.acct_rel
            .map(
              (row) => `<tr data-iai-field="accounts" data-iai-canonical="accounts[].id">
                <td>${row.n}</td>
                <td>${row.d}</td>
                <td>${row.t}</td>
                <td class="${row.s === "HOLD" ? "frozen" : ""}">${row.s}</td>
                <td data-iai-field="available" data-iai-canonical="accounts[].available">${usdFromCents(row.a)}</td>
                <td>${usdFromCents(row.l)}</td>
              </tr>`,
            )
            .join("")}
        </tbody>
      </table>
      <section class="panel">
        <h2>Internal transfer (dollars in the form; extract stores cents)</h2>
        ${transferForm(
          "calloway",
          native.acct_rel.map((r) => ({ id: r.n, label: `${r.d} · ${r.n} · ${r.s}` })),
        )}
      </section>
      <section class="panel">
        <h2>hist</h2>
        <table>
          <thead><tr><th>k</th><th>ymd</th><th>t</th><th>n</th><th>s</th><th>p</th></tr></thead>
          <tbody>
            ${native.hist
              .map(
                (row) => `<tr>
                  <td>${row.k}</td>
                  <td>${row.ymd}</td>
                  <td>${row.t}</td>
                  <td>${row.n}</td>
                  <td>${row.s}</td>
                  <td class="amount ${row.s === "-" ? "debit" : "credit"}">${usdFromCents(row.p)}</td>
                </tr>`,
              )
              .join("")}
          </tbody>
        </table>
      </section>
    </main>`;
  bindTransfer(app, () => void renderCalloway(app));
}
