"""FastAPI entrypoint."""

import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agent.loop import run_agent
from app.config import get_settings
from app.db import close_pool, connection
from app.logging_setup import setup_logging

EXAMPLES = [
    {
        "path": "numeric",
        "question": "How much has the construction cost index for residential "
        "buildings risen since January 2024?",
    },
    {"path": "definition", "question": "What does Byggkostnadsindex include?"},
    {"path": "hybrid", "question": "The index rose sharply in 2022 — why?"},
]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    yield
    close_pool()


app = FastAPI(title="Byggkostnad Agent", version="1.0.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Per-IP sliding window. In-memory, so it is per process; enough to stop a
# public demo from being used as a free Claude proxy.
_hits: dict[str, deque[float]] = defaultdict(deque)


def _rate_limit(request: Request) -> None:
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else "unknown"
    )
    now = time.monotonic()
    window = _hits[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= get_settings().ask_rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="Too many questions; wait a minute.")
    window.append(now)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@app.post("/ask")
async def ask(body: AskRequest, request: Request) -> dict[str, Any]:
    _rate_limit(request)
    result = await run_in_threadpool(run_agent, body.question.strip())
    return {
        "answer": result.answer,
        "tool_calls": [
            {
                "name": c.name,
                "input": c.input,
                "output": c.output,
                "is_error": c.is_error,
                "latency_ms": c.latency_ms,
            }
            for c in result.tool_calls
        ],
        "sources": result.sources,
        "latency_ms": result.latency_ms,
        "error": result.error,
    }


@app.get("/examples")
def examples() -> list[dict[str, str]]:
    return EXAMPLES


@app.get("/eval/latest")
def eval_latest() -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute(
            "select run_at, git_sha, recall_at_5, numeric_accuracy, groundedness, notes "
            "from eval_runs order by (notes like 'ref=main%') desc, run_at desc limit 1"
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="No evaluation runs recorded yet.")
    return dict(row)


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        with connection() as conn:
            conn.execute("select 1")
        db = "ok"
    except Exception:
        db = "unavailable"
    return {"status": "ok" if db == "ok" else "degraded", "database": db}
