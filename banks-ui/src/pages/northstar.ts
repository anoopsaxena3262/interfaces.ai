import { getNative } from "../api";
import { nav, usdFromCents } from "../format";
import { bindTransfer, transferForm } from "../transfer";

type NorthstarNative = {
  header: { cu: string; asOfEpoch: number };
  memberRec: { mbrNo: string; nmLine: string; eml: string; ph10: string };
  suffixList: Array<{
    sfx: string;
    ttl: string;
    cls: string;
    avail: number;
    bal: number;
    stat: string;
  }>;
  actv: Array<{ id: string; day: string; txt: string; cents: number; sfx: string }>;
};

function displayName(nmLine: string): string {
  const [last, rest] = nmLine.split(",");
  return rest ? `${rest.trim()} ${last.trim()}` : nmLine;
}

export async function renderNorthstar(app: HTMLElement): Promise<void> {
  document.title = "Northstar FCU";
  document.body.className = "theme-northstar";
  const native = await getNative<NorthstarNative>("northstar");

  app.innerHTML = `${nav("/northstar")}
    <div class="banner">${native.header.cu} · MEMBER EXTRACT · DEMO ONLY</div>
    <main class="shell" data-iai-page="dashboard" data-iai-institution="northstar">
      <p class="wordmark">Northstar FCU</p>
      <h1 data-iai-field="customer.display_name" data-iai-canonical="customer.display_name">${displayName(native.memberRec.nmLine)}</h1>
      <p class="member-chip">
        Member
        <span data-iai-field="customer.id" data-iai-canonical="customer.id">${native.memberRec.mbrNo}</span>
        · ${native.memberRec.eml}
      </p>
      <section class="shares">
        ${native.suffixList
          .map(
            (row) => `<article class="share" data-iai-field="accounts" data-iai-canonical="accounts[].id">
              <div>
                <div>${row.ttl}</div>
                <small>sfx ${row.sfx} · ${row.cls} · ledger ${usdFromCents(row.bal)}</small>
              </div>
              <strong data-iai-field="available" data-iai-canonical="accounts[].available">${usdFromCents(row.avail)}</strong>
            </article>`,
          )
          .join("")}
      </section>
      <section class="panel">
        <h2>Suffix to suffix</h2>
        ${transferForm(
          "northstar",
          native.suffixList.map((s) => ({ id: s.sfx, label: `${s.ttl} · ${s.sfx}` })),
        )}
      </section>
      <section class="panel">
        <h2>Activity (cents in the extract)</h2>
        <table>
          <thead><tr><th>Id</th><th>Day</th><th>Text</th><th>Sfx</th><th>Amount</th></tr></thead>
          <tbody>
            ${native.actv
              .map(
                (row) => `<tr>
                  <td>${row.id}</td>
                  <td>${row.day}</td>
                  <td>${row.txt}</td>
                  <td>${row.sfx}</td>
                  <td class="amount ${row.cents < 0 ? "debit" : "credit"}">${usdFromCents(row.cents)}</td>
                </tr>`,
              )
              .join("")}
          </tbody>
        </table>
      </section>
    </main>`;
  bindTransfer(app, () => void renderNorthstar(app));
}
