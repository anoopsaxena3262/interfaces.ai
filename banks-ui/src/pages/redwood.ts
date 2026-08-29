import { getNative } from "../api";
import { nav, usdFromMajor } from "../format";
import { bindTransfer, transferForm } from "../transfer";

type RedwoodNative = {
  extractedAt: string;
  household: {
    partyKey: string;
    primary: { given: string; surname: string; mail: string; tel: string };
  };
  products: {
    deposits: Array<{
      productInstance: string;
      nickname: string;
      kind: string;
      mask: string;
      lifecycle: string;
      position: { avail: string; ledger: string; iso: string };
    }>;
  };
  posted: Array<{
    ref: string;
    on: string;
    note: string;
    signed: string;
    productInstance: string;
  }>;
};

export async function renderRedwood(app: HTMLElement): Promise<void> {
  document.title = "Redwood Community Bank";
  document.body.className = "theme-redwood";
  const native = await getNative<RedwoodNative>("redwood");
  const { primary, partyKey } = native.household;

  app.innerHTML = `${nav("/redwood")}
    <div class="banner">DEMO EXTRACT · NOT A REAL BANK</div>
    <main class="shell" data-iai-page="dashboard" data-iai-institution="redwood">
      <p class="wordmark">Redwood Community Bank</p>
      <h1 data-iai-field="customer.display_name" data-iai-canonical="customer.display_name">
        ${primary.given} ${primary.surname}
      </h1>
      <p>
        Household
        <span data-iai-field="customer.id" data-iai-canonical="customer.id">${partyKey}</span>
        · ${primary.mail}
      </p>
      <section class="accounts">
        ${native.products.deposits
          .map(
            (row) => `<article class="acct" data-iai-field="accounts" data-iai-canonical="accounts[].id">
              <div>${row.nickname}</div>
              <div class="bal" data-iai-field="available" data-iai-canonical="accounts[].available">${usdFromMajor(Number(row.position.avail))}</div>
              <small>${row.mask} · ${row.kind} · ledger ${usdFromMajor(Number(row.position.ledger))}</small>
            </article>`,
          )
          .join("")}
      </section>
      <section class="panel">
        <h2>Book transfer</h2>
        ${transferForm(
          "redwood",
          native.products.deposits.map((a) => ({
            id: a.productInstance,
            label: `${a.nickname} · ${a.productInstance}`,
          })),
        )}
      </section>
      <section class="panel">
        <h2>Posted</h2>
        <table>
          <thead><tr><th>On</th><th>Note</th><th>Product</th><th>Signed</th></tr></thead>
          <tbody>
            ${native.posted
              .map(
                (row) => `<tr>
                  <td>${row.on}</td>
                  <td>${row.note}</td>
                  <td>${row.productInstance}</td>
                  <td class="amount ${Number(row.signed) < 0 ? "debit" : "credit"}">${usdFromMajor(Number(row.signed))}</td>
                </tr>`,
              )
              .join("")}
          </tbody>
        </table>
      </section>
    </main>`;
  bindTransfer(app, () => void renderRedwood(app));
}
