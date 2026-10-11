export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type Row = { period: string; value: string | number };

export type Series = {
  table_id: string;
  building_type: string | null;
  cost_class: string;
  base_year: string | null;
  source_url: string;
  first_period: string;
  last_period: string;
  first: string | number | null;
  last: string | number | null;
  absolute_change: string | number | null;
  percent_change: string | number | null;
  rows: Row[];
};

export type Hit = {
  chunk_id: number;
  text: string;
  source_url: string;
  title: string | null;
  similarity: number;
};

export type ToolCall = {
  name: string;
  input: Record<string, unknown>;
  output: { series?: Series[]; hits?: Hit[]; note?: string; error?: string; [k: string]: unknown };
  is_error: boolean;
  latency_ms: number;
};

export type AskResponse = {
  answer: string;
  tool_calls: ToolCall[];
  sources: Record<string, unknown>[];
  latency_ms: number;
  error: string | null;
};

export type Example = { path: string; question: string };

export type EvalRun = {
  run_at: string;
  git_sha: string | null;
  recall_at_5: string | number | null;
  numeric_accuracy: string | number | null;
  groundedness: string | number | null;
};

export async function ask(question: string): Promise<AskResponse> {
  const res = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ? String(body.detail) : `Request failed (${res.status})`);
  }
  return res.json();
}

export async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_URL}${path}`);
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

/** Render a tool call the way it was made: name(arg="value", ...). */
export function formatCall(call: ToolCall): string {
  const args = Object.entries(call.input)
    .map(([k, v]) => `${k}=${typeof v === "string" ? `"${v}"` : JSON.stringify(v)}`)
    .join(", ");
  return `${call.name}(${args})`;
}
