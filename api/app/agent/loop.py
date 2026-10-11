"""Tool-use orchestration.

Claude picks tools; we run them and feed the results back until Claude
answers or the iteration cap is hit. Every tool call (name, arguments,
output) is returned to the caller as a first-class part of the response.
"""

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import anthropic

from app.agent.descriptions import TOOL_SCHEMAS
from app.agent.tools import run_tool
from app.config import get_settings
from app.db import connection
from app.logging_setup import log

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5
MAX_TOKENS = 16000

SYSTEM_PROMPT = """You answer questions about Swedish construction cost statistics \
(SCB's Byggkostnadsindex) using only the tools provided.

Rules:
- Answer only from tool output. Never use prior knowledge for figures, dates or causes.
- Every number must come from query_price_index. Quote the computed values it returns \
(first, last, percent_change) rather than doing your own arithmetic.
- Cite numbers with the SCB table id and the periods used, e.g. "(SCB FPIBOM, \
2024-01 to 2026-07)". Cite text with the document URL.
- Questions that ask why something happened need both tools: numbers from \
query_price_index, explanations from search_docs.
- If the tools return nothing relevant, say so plainly instead of guessing.
- Answer in English. Answer in Swedish only if the whole question is written in \
Swedish. Swedish source text and Swedish terms inside an English question (such \
as "Byggkostnadsindex") do not make it a Swedish question; translate what you \
quote and keep the Swedish term in parentheses where it helps.
- Be concise.

Today's date is {today}."""


@dataclass
class ToolCall:
    name: str
    input: dict[str, Any]
    output: dict[str, Any]
    is_error: bool
    latency_ms: int


@dataclass
class AgentResult:
    answer: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentLoopExceeded(RuntimeError):
    pass


_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key or None)
    return _client


def collect_sources(tool_calls: list[ToolCall]) -> list[dict[str, Any]]:
    """Deduplicated citations derived from tool output, not from model text."""
    seen: set[str] = set()
    sources: list[dict[str, Any]] = []
    for call in tool_calls:
        if call.is_error:
            continue
        if call.name == "query_price_index":
            for s in call.output.get("series", []):
                key = f"{s['table_id']}|{s['building_type']}|{s['first_period']}|{s['last_period']}"
                if key not in seen:
                    seen.add(key)
                    sources.append(
                        {
                            "type": "table",
                            "table_id": s["table_id"],
                            "building_type": s["building_type"],
                            "cost_class": s["cost_class"],
                            "periods": [s["first_period"], s["last_period"]],
                            "source_url": s["source_url"],
                        }
                    )
        elif call.name == "search_docs":
            for h in call.output.get("hits", []):
                key = f"chunk|{h['chunk_id']}"
                if key not in seen:
                    seen.add(key)
                    sources.append(
                        {
                            "type": "document",
                            "title": h["title"],
                            "source_url": h["source_url"],
                            "similarity": h["similarity"],
                        }
                    )
    return sources


def _text_of(content: list[Any]) -> str:
    return "\n".join(b.text for b in content if getattr(b, "type", None) == "text").strip()


def _create(msgs: list[Any]) -> Any:
    s = get_settings()
    return get_client().beta.messages.create(  # type: ignore[call-overload]
        model=s.anthropic_model,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT.format(today=date.today().isoformat()),
        tools=TOOL_SCHEMAS,
        messages=msgs,
        output_config={"effort": s.anthropic_effort},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )


def run_agent(question: str) -> AgentResult:
    started = time.perf_counter()
    msgs: list[Any] = [{"role": "user", "content": question}]
    tool_calls: list[ToolCall] = []
    result: AgentResult | None = None

    try:
        for _ in range(MAX_ITERATIONS):
            resp = _create(msgs)
            if resp.stop_reason == "refusal":
                result = AgentResult(
                    answer="The model declined to answer this question.", error="refusal"
                )
                break
            if resp.stop_reason != "tool_use":
                answer = _text_of(resp.content)
                if resp.stop_reason == "max_tokens":
                    answer += "\n\n[Answer truncated at the token limit.]"
                result = AgentResult(answer=answer)
                break

            msgs.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                t0 = time.perf_counter()
                out, is_error = run_tool(block.name, dict(block.input))
                tool_calls.append(
                    ToolCall(
                        block.name,
                        dict(block.input),
                        out,
                        is_error,
                        int((time.perf_counter() - t0) * 1000),
                    )
                )
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(out, default=str, ensure_ascii=False),
                        "is_error": is_error,
                    }
                )
            msgs.append({"role": "user", "content": results})
        else:
            raise AgentLoopExceeded(f"No answer after {MAX_ITERATIONS} tool iterations.")
    except AgentLoopExceeded as exc:
        result = AgentResult(answer=f"Error: {exc}", error="max_iterations")
    except anthropic.APIError as exc:
        logger.exception("anthropic call failed")
        result = AgentResult(
            answer="Error: the language model call failed.", error=type(exc).__name__
        )

    assert result is not None
    result.tool_calls = tool_calls
    result.sources = collect_sources(tool_calls)
    result.latency_ms = int((time.perf_counter() - started) * 1000)
    _log_query(question, result)
    return result


def _log_query(question: str, result: AgentResult) -> None:
    tools_called = [
        {"name": c.name, "input": c.input, "is_error": c.is_error} for c in result.tool_calls
    ]
    log(
        logger,
        "ask",
        tools=[c.name for c in result.tool_calls],
        latency_ms=result.latency_ms,
        error=result.error,
    )
    try:
        with connection() as conn:
            conn.execute(
                "insert into query_log (question, tools_called, answer, latency_ms) "
                "values (%s, %s, %s, %s)",
                (question, json.dumps(tools_called, default=str), result.answer, result.latency_ms),
            )
    except Exception:
        # Logging must never take down an answer.
        logger.exception("query_log insert failed")
