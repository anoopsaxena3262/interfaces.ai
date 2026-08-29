import { replayTransfer } from "./api";

export function transferForm(institutionId: string, accounts: Array<{ id: string; label: string }>): string {
  const options = accounts.map((a) => `<option value="${a.id}">${a.label}</option>`).join("");
  const dest = [...accounts].reverse().map((a) => `<option value="${a.id}">${a.label}</option>`).join("");
  return `<form class="transfer" data-transfer="${institutionId}">
    <label>From
      <select name="from" data-iai-field="from" data-iai-canonical="transfer.from_account">${options}</select>
    </label>
    <label>To
      <select name="to" data-iai-field="to" data-iai-canonical="transfer.to_account">${dest}</select>
    </label>
    <label>Amount
      <input name="amount" data-iai-field="amount" data-iai-canonical="transfer.amount" type="number" min="0.01" step="0.01" value="50.00" />
    </label>
    <label>Memo
      <input name="memo" data-iai-field="memo" data-iai-canonical="transfer.memo" value="Sandbox transfer" />
    </label>
    <button type="submit" data-iai-action="transfer.submit" data-iai-canonical="transfer.submit">Submit transfer</button>
    <div class="form-status"></div>
  </form>`;
}

export function bindTransfer(root: HTMLElement, onDone: () => void): void {
  const form = root.querySelector<HTMLFormElement>("form[data-transfer]");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = form.querySelector(".form-status");
    const data = new FormData(form);
    try {
      const result = await replayTransfer({
        institution_id: form.dataset.transfer ?? "",
        from_account_id: String(data.get("from")),
        to_account_id: String(data.get("to")),
        amount: Number(data.get("amount")),
        memo: String(data.get("memo") ?? ""),
      });
      if (status) {
        status.className = `form-status ${result.succeeded ? "ok" : "error"}`;
        status.textContent = result.succeeded
          ? `Posted (${result.run_id})`
          : `Held for review${result.escalation_id ? ` — ${result.escalation_id}` : ""}`;
      }
      if (result.succeeded) onDone();
    } catch (err) {
      if (status) {
        status.className = "form-status error";
        status.textContent = err instanceof Error ? err.message : "Transfer failed";
      }
    }
  });
}
