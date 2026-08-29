export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${text}`);
  }
  return response.json() as Promise<T>;
}

export function getNative<T>(id: string): Promise<T> {
  return api<T>(`/api/v1/institutions/${id}/native`);
}

export function getCanonical(id: string) {
  return api<CanonicalSnapshot>(`/api/v1/institutions/${id}/canonical`);
}

export type Money = { amount: string; currency: string };

export type CanonicalAccount = {
  id: string;
  masked_number: string;
  name: string;
  type: string;
  status: string;
  available: Money;
  current: Money;
};

export type CanonicalSnapshot = {
  institution_id: string;
  institution_name: string;
  as_of: string;
  customer: { id: string; display_name: string; email?: string | null; phone?: string | null };
  accounts: CanonicalAccount[];
  transactions: Array<{
    id: string;
    account_id: string;
    posted_on: string;
    description: string;
    amount: Money;
    direction: string;
  }>;
  mapping_notes: string[];
};

export type ReplayResult = {
  run_id: string;
  succeeded: boolean;
  escalation_id: string | null;
  steps: Array<{ kind: string; description: string; ok: boolean; detail: string; locator?: string | null }>;
  native_receipt: Record<string, unknown> | null;
};

export function replayTransfer(body: {
  institution_id: string;
  from_account_id: string;
  to_account_id: string;
  amount: number;
  memo: string;
}): Promise<ReplayResult> {
  return api<ReplayResult>("/api/v1/agents/replay", { method: "POST", body: JSON.stringify(body) });
}
