export function usdFromMajor(value: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}

export function usdFromCents(cents: number): string {
  return usdFromMajor(cents / 100);
}

export function usdFromCanonical(amount: string): string {
  return usdFromMajor(Number(amount));
}

export function nav(active: string): string {
  const links = [
    ["/", "Home"],
    ["/redwood", "Redwood"],
    ["/northstar", "Northstar"],
    ["/calloway", "Calloway"],
    ["/console", "Console"],
  ];
  return `<nav class="site-nav">
    ${links
      .map(
        ([href, label]) =>
          `<a data-link href="${href}" class="${href === active ? "is-active" : ""}">${label}</a>`,
      )
      .join("")}
  </nav>`;
}
