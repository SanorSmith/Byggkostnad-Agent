"use client";

import { useEffect, useState } from "react";
import { LineChart } from "@/components/LineChart";
import {
  API_URL,
  ask,
  type AskResponse,
  type EvalRun,
  type Example,
  formatCall,
  getJson,
  type Hit,
  type Series,
  type ToolCall,
} from "@/lib/api";

const FALLBACK_EXAMPLES: Example[] = [
  { path: "numeric", question: "How much has the construction cost index for residential buildings risen since January 2024?" },
  { path: "definition", question: "What does Byggkostnadsindex include?" },
  { path: "hybrid", question: "The index rose sharply in 2022 — why?" },
];

const PATH_LABEL: Record<string, string> = {
  numeric: "Numeric → query_price_index",
  definition: "Definition → search_docs",
  hybrid: "Hybrid → both tools",
};

const COST_CLASS: Record<string, string> = {
  TOTAL: "total index",
  MATERIAL: "materials",
  ARBL: "wages",
  MASK: "machinery",
  TRANS: "transport, fuel, electricity",
  OMK: "overheads",
  ETTILLFEM: "contractor's costs",
  BYGGKOST: "client's costs",
};

const BUILDING: Record<string, string> = {
  FLERBO: "multi-dwelling buildings",
  "GRUPPSMÅ": "group-built small houses",
  JORDBRUK: "agricultural buildings",
};

function fmt(v: string | number | null | undefined, digits = 1): string {
  if (v === null || v === undefined) return "—";
  return Number(v).toFixed(digits);
}

function EvalBadge({ run }: { run: EvalRun | null | undefined }) {
  if (run === undefined) return null;
  if (run === null) return <span className="badge">eval: no recorded run yet</span>;
  const when = new Date(run.run_at).toLocaleDateString();
  return (
    <span className="badge" title={`Recorded ${when} at ${run.git_sha?.slice(0, 7) ?? "unknown commit"}`}>
      <span>latest eval</span>
      <span>recall@5 <strong>{fmt(run.recall_at_5, 2)}</strong></span>
      <span>numeric <strong>{fmt(run.numeric_accuracy, 2)}</strong></span>
      <span>grounded <strong>{fmt(run.groundedness, 2)}</strong></span>
    </span>
  );
}

function SeriesView({ s }: { s: Series }) {
  const pct = s.percent_change === null ? null : Number(s.percent_change);
  const building = BUILDING[s.building_type ?? ""] ?? s.building_type ?? "";
  const title = `${building} — ${COST_CLASS[s.cost_class] ?? s.cost_class}`;
  return (
    <div className="series">
      <div className="series-head">
        <div>
          <h3>{title}</h3>
          <div className="figure">{pct === null ? "—" : `${pct > 0 ? "+" : ""}${pct.toFixed(2)} %`}</div>
          <p className="muted">
            {fmt(s.first)} ({s.first_period.slice(0, 7)}) → {fmt(s.last)} ({s.last_period.slice(0, 7)})
            <br />
            <a href={s.source_url} target="_blank" rel="noreferrer">SCB {s.table_id}</a>, {s.base_year}=100
          </p>
        </div>
        <LineChart rows={s.rows} label={`${title}, ${s.first_period} to ${s.last_period}`} />
      </div>
      <div className="rows">
        <table>
          <thead>
            <tr><th>period</th><th className="num">index</th></tr>
          </thead>
          <tbody>
            {s.rows.map((r) => (
              <tr key={r.period}><td>{r.period.slice(0, 7)}</td><td className="num">{fmt(r.value)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function HitView({ h }: { h: Hit }) {
  return (
    <div className="hit">
      <div className="hit-head">
        <a href={h.source_url} target="_blank" rel="noreferrer">{h.title || h.source_url}</a>
        <span className="mono muted">sim {h.similarity.toFixed(3)}</span>
      </div>
      <div className="hit-text">{h.text}</div>
    </div>
  );
}

function ToolOutput({ call }: { call: ToolCall }) {
  if (call.is_error) return <p className="error mono">{JSON.stringify(call.output)}</p>;
  if (call.name === "query_price_index") {
    const series = call.output.series ?? [];
    if (!series.length) return <p className="muted">{call.output.note ?? "No rows returned."}</p>;
    return <>{series.map((s) => <SeriesView key={`${s.table_id}-${s.building_type}`} s={s} />)}</>;
  }
  if (call.name === "search_docs") {
    const hits = call.output.hits ?? [];
    if (!hits.length) return <p className="muted">No documents matched.</p>;
    return <>{hits.map((h) => <HitView key={h.chunk_id} h={h} />)}</>;
  }
  return null;
}

export default function Page() {
  const [examples, setExamples] = useState<Example[]>(FALLBACK_EXAMPLES);
  const [evalRun, setEvalRun] = useState<EvalRun | null | undefined>(undefined);
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getJson<Example[]>("/examples").then((e) => e && setExamples(e));
    getJson<EvalRun>("/eval/latest").then(setEvalRun);
  }, []);

  async function submit(q: string) {
    const text = q.trim();
    if (text.length < 3 || loading) return;
    setQuestion(text);
    setAsked(text);
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await ask(text));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <h1>Byggkostnad Agent</h1>
      <p className="lede">
        Ask about SCB&apos;s construction cost index. Numbers are computed from the exact
        monthly rows by SQL; explanations come from searching SCB&apos;s own documents. Every
        answer shows which tool the model chose and the arguments it passed.
      </p>
      <EvalBadge run={evalRun} />

      <div className="examples">
        {examples.map((ex) => (
          <button key={ex.question} className="example" disabled={loading} onClick={() => submit(ex.question)}>
            <span className="path">{PATH_LABEL[ex.path] ?? ex.path}</span>
            {ex.question}
          </button>
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(question);
        }}
      >
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(question);
            }
          }}
          placeholder="Ask a question about Swedish construction costs…"
          maxLength={500}
          aria-label="Question"
        />
        <button className="primary" type="submit" disabled={loading || question.trim().length < 3}>
          {loading ? "Thinking…" : "Ask"}
        </button>
      </form>

      {loading && <p className="muted" style={{ marginTop: 16 }}>Routing “{asked}”…</p>}
      {error && <p className="error" style={{ marginTop: 16 }}>{error}</p>}

      {result && (
        <>
          <h2>Answer</h2>
          <div className={result.error ? "answer error" : "answer"}>{result.answer}</div>
          <p className="muted" style={{ marginTop: 8 }}>{(result.latency_ms / 1000).toFixed(1)} s total</p>

          <h2>Tool calls</h2>
          {result.tool_calls.length === 0 && <p className="muted">The model called no tools for this question.</p>}
          {result.tool_calls.map((c, i) => (
            <div key={i} className={c.is_error ? "call mono failed" : "call mono"}>
              {formatCall(c)}
              <span className="meta">{`  // ${c.latency_ms} ms${c.is_error ? ", failed" : ""}`}</span>
            </div>
          ))}

          {result.tool_calls.map((c, i) => (
            <section key={`out-${i}`}>
              <h2>
                {c.name === "search_docs"
                  ? `Retrieved chunks for “${String(c.input.query ?? "")}”`
                  : `Rows returned by call ${i + 1}`}
              </h2>
              <ToolOutput call={c} />
            </section>
          ))}
        </>
      )}

      <footer>
        Data: Statistics Sweden (SCB), tables FPIBOM and FPIJBM15, and SCB&apos;s methodology
        pages and statistical news. API: <span className="mono">{API_URL}</span>
      </footer>
    </main>
  );
}
