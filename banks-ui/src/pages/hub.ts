import { nav } from "../format";

export async function renderHub(app: HTMLElement): Promise<void> {
  document.title = "FI extract sandbox";
  document.body.className = "";
  app.innerHTML = `${nav("/")}
    <main class="hub">
      <header>
        <h1>Three extracts. One transfer intent.</h1>
        <p>
          Each mock bank below is a stand-in for a different core export. The Python service
          maps those exports onto a shared snapshot, then discovery / replay / hold-for-review
          work only against that snapshot.
        </p>
      </header>
      <section class="grid">
        <a class="card" data-link href="/redwood">
          <div class="eyebrow">Household tree</div>
          <h2>Redwood Community Bank</h2>
          <p>Balances are decimal <em>strings</em> under <code>products.deposits[].position</code>.</p>
        </a>
        <a class="card" data-link href="/northstar">
          <div class="eyebrow">Suffix ledger</div>
          <h2>Northstar FCU</h2>
          <p>Member line is <code>LAST, FIRST</code>. Share amounts are integer cents.</p>
        </a>
        <a class="card" data-link href="/calloway">
          <div class="eyebrow">Short-key dump</div>
          <h2>Calloway State Bank</h2>
          <p>Sign lives on <code>hist[].s</code>. The personal LOC is on <code>HOLD</code>.</p>
        </a>
        <a class="card" data-link href="/console">
          <div class="eyebrow">Operators</div>
          <h2>Console</h2>
          <p>Run discovery, fire a transfer, and read the hold queue.</p>
        </a>
      </section>
      <div class="notice">
        Seed files are <code>data/native/*.json</code>. Writes stay in process memory.
        Reset from the console or restart the API.
      </div>
    </main>`;
}
