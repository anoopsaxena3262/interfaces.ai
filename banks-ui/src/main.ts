import { renderCalloway } from "./pages/calloway";
import { renderConsole } from "./pages/console";
import { renderHub } from "./pages/hub";
import { renderNorthstar } from "./pages/northstar";
import { renderRedwood } from "./pages/redwood";
import "./styles/global.css";
import "./styles/redwood.css";
import "./styles/northstar.css";
import "./styles/calloway.css";
import "./styles/console.css";

type Page = (app: HTMLElement) => Promise<void>;

const routes: Record<string, Page> = {
  "/": renderHub,
  "/redwood": renderRedwood,
  "/northstar": renderNorthstar,
  "/calloway": renderCalloway,
  "/console": renderConsole,
};

async function load(): Promise<void> {
  const app = document.querySelector<HTMLElement>("#app");
  if (!app) return;
  const page = routes[window.location.pathname] ?? renderHub;
  try {
    await page(app);
  } catch (err) {
    app.innerHTML = `<main class="hub"><h1>API is not running</h1>
      <p>Start the Python server on port 8000 (<code>make dev</code>), then reload.</p>
      <pre>${err instanceof Error ? err.message : String(err)}</pre></main>`;
  }
}

document.addEventListener("click", (event) => {
  const target = (event.target as HTMLElement | null)?.closest("a[data-link]");
  if (!target) return;
  const href = target.getAttribute("href");
  if (!href || href.startsWith("http")) return;
  event.preventDefault();
  history.pushState({}, "", href);
  void load();
});

window.addEventListener("popstate", () => void load());
void load();
