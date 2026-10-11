"""Replay the golden set end to end, score it, record the run.

python -m evals.run_evals                 # run and record
python -m evals.run_evals --compare       # also fail on a >3 pp regression vs main
python -m evals.run_evals --no-record     # dry run, nothing written to eval_runs
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.agent.loop import SYSTEM_PROMPT, get_client, run_agent
from app.config import get_settings
from app.db import connection
from app.retrieval.search import search_docs
from evals.metrics import (
    answer_groundedness,
    groundedness,
    make_llm_judge,
    numeric_accuracy,
    numeric_correct,
    parse_numbers,
    recall_at_5,
    unsupported_figures,
)

HERE = Path(__file__).parent
RESULTS_DIR = HERE / "results"
METRICS = ("recall_at_5", "numeric_accuracy", "groundedness")
REGRESSION_THRESHOLD = 0.03  # 3 percentage points
# Bump when a metric's definition changes. The gate only compares runs with
# the same version; scores under different definitions are not comparable.
# v2: numeric figures must come from query_price_index; groundedness is 0 on
# any unsupported figure (deterministic check or judge).
METRICS_VERSION = "v2"

# The design this project rejects: retrieve documents, let the model read
# figures out of them. Used only as a comparison baseline.
RAG_ONLY_PROMPT = """You answer questions about Swedish construction cost statistics \
(SCB's Byggkostnadsindex). Use the search_docs tool to find relevant SCB documents \
and answer from them. Cite the document URL. Answer in English unless the question \
is written entirely in Swedish. Be concise.

Today's date is {today}."""


def git_sha() -> str | None:
    # On pull requests GITHUB_SHA is a temporary merge commit; prefer the PR head.
    if sha := os.environ.get("EVAL_GIT_SHA") or os.environ.get("GITHUB_SHA"):
        return sha
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def git_ref() -> str:
    if ref := os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME"):
        return ref
    try:
        return subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def baseline() -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            "select * from eval_runs where notes like 'ref=main%%' and notes like %s "
            "order by run_at desc limit 1",
            (f"%metrics={METRICS_VERSION}%",),
        ).fetchone()
    return dict(row) if row else None


def fmt(x: float | None) -> str:
    return "—" if x is None else f"{x:.3f}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--no-record", action="store_true")
    parser.add_argument(
        "--baseline",
        choices=["hybrid", "rag-only"],
        default="hybrid",
        help="rag-only: answer with search_docs alone and a plain RAG prompt (never recorded)",
    )
    args = parser.parse_args()
    if args.baseline != "hybrid":
        args.no_record = True
    tool_names = ["search_docs"] if args.baseline == "rag-only" else None
    system_prompt = RAG_ONLY_PROMPT if args.baseline == "rag-only" else SYSTEM_PROMPT

    items = json.loads((HERE / "golden_set.json").read_text(encoding="utf-8"))["items"]
    judge = make_llm_judge(get_client(), get_settings().judge_model)

    answers: dict[str, str] = {}
    price_values: dict[str, list[float]] = {}
    ground_scores: list[float] = []
    rows: list[dict[str, Any]] = []
    for item in items:
        result = run_agent(
            item["question"], tool_names, system_prompt=system_prompt, log_query=False
        )
        answers[item["id"]] = result.answer
        called = [c.name for c in result.tool_calls]
        tool_output = json.dumps(
            [{"tool": c.name, "input": c.input, "output": c.output} for c in result.tool_calls],
            default=str,
            ensure_ascii=False,
        )
        # Figures the price tool computed or returned; document text excluded.
        price_values[item["id"]] = parse_numbers(
            json.dumps(
                [c.output for c in result.tool_calls if c.name == "query_price_index"],
                default=str,
            )
        )
        missing = unsupported_figures(result.answer, tool_output)
        g = answer_groundedness(result.answer, tool_output, judge) if result.tool_calls else 0.0
        ground_scores.append(g)
        num_ok = (
            numeric_correct(
                result.answer,
                item["expected_value"],
                item["tolerance_pct"],
                price_values[item["id"]],
            )
            if item["type"] in ("numeric", "hybrid")
            else None
        )
        rows.append(
            {
                "id": item["id"],
                "type": item["type"],
                "tools": called,
                "tools_as_expected": set(item["expected_tools"]) <= set(called),
                "numeric_ok": num_ok,
                "groundedness": round(g, 3),
                "unsupported_figures": missing,
                "latency_ms": result.latency_ms,
                "answer": result.answer,
                # Kept so a run can be re-scored offline when a metric changes.
                "tool_output": json.loads(tool_output),
            }
        )

    scores = {
        "recall_at_5": recall_at_5(items, search_docs),
        "numeric_accuracy": numeric_accuracy(items, answers, price_values),
        "groundedness": groundedness(ground_scores),
    }

    lines = [
        "| id | type | tools called | routing ok | numeric ok | grounded "
        "| figures not in tool output | latency |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        num = "—" if r["numeric_ok"] is None else ("yes" if r["numeric_ok"] else "**no**")
        missing_txt = ", ".join(f"{v:g}" for v in r["unsupported_figures"]) or "—"
        lines.append(
            f"| {r['id']} | {r['type']} | {', '.join(r['tools']) or '—'} | "
            f"{'yes' if r['tools_as_expected'] else '**no**'} | {num} | "
            f"{r['groundedness']:.2f} | {missing_txt} | {r['latency_ms']} ms |"
        )

    base = baseline() if args.compare else None
    lines += ["", "| metric | this run | main baseline | delta |", "|---|---|---|---|"]
    failed: list[str] = []
    for m in METRICS:
        cur = scores[m]
        prev = float(base[m]) if base and base[m] is not None else None
        delta = None if cur is None or prev is None else cur - prev
        if delta is not None and delta < -REGRESSION_THRESHOLD:
            failed.append(m)
        lines.append(
            f"| {m} | {fmt(cur)} | {fmt(prev)} | {'—' if delta is None else f'{delta:+.3f}'} |"
        )
    if args.compare and base is None:
        lines.append(
            f"\nNo main baseline recorded yet for metrics {METRICS_VERSION}; "
            "regression gate skipped."
        )
    if failed:
        lines.append(f"\n**Regression > 3 pp in: {', '.join(failed)}**")

    table = "\n".join(lines)
    print(table)
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "latest.md").write_text(table + "\n", encoding="utf-8")
    (RESULTS_DIR / "latest.json").write_text(
        json.dumps({"scores": scores, "items": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if not args.no_record:
        with connection() as conn:
            conn.execute(
                "insert into eval_runs "
                "(git_sha, recall_at_5, numeric_accuracy, groundedness, notes) "
                "values (%s, %s, %s, %s, %s)",
                (
                    git_sha(),
                    scores["recall_at_5"],
                    scores["numeric_accuracy"],
                    scores["groundedness"],
                    f"ref={git_ref()};metrics={METRICS_VERSION}",
                ),
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
