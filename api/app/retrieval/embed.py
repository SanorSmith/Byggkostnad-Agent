"""One pinned embedding model, used for both documents and queries.

The model name comes from config and is stored on every chunk row. Search
filters on it, so a half-migrated corpus returns fewer hits rather than
wrong ones.
"""

import threading
import time
from collections import deque
from typing import Literal

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from app.config import get_settings
from app.http import is_retryable

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
MAX_BATCH = 64
# Voyage's lowest tier allows about 10k tokens and 3 requests per minute.
# Batches are capped by estimated tokens so one request never exceeds that.
# The estimate (4 chars/token) undercounts Swedish text, hence the margin.
MAX_BATCH_TOKENS = 4000
CHARS_PER_TOKEN = 4

InputType = Literal["document", "query"]


class _RateLimiter:
    """Client-side requests-per-minute cap, so bulk ingest stays under the limit
    instead of relying on 429s and retries."""

    def __init__(self) -> None:
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def wait(self, rpm: int) -> None:
        if rpm <= 0:
            return
        with self._lock:
            now = time.monotonic()
            while self._calls and now - self._calls[0] >= 60:
                self._calls.popleft()
            if len(self._calls) >= rpm:
                time.sleep(60 - (now - self._calls[0]) + 0.5)
                self._calls.popleft()
            self._calls.append(time.monotonic())


_limiter = _RateLimiter()


@retry(
    retry=retry_if_exception(is_retryable),
    # A 429 on a per-minute quota needs waits measured in tens of seconds.
    wait=wait_exponential_jitter(initial=5, max=65),
    stop=stop_after_attempt(8),
    reraise=True,
)
def _voyage_batch(texts: list[str], input_type: InputType) -> list[list[float]]:
    s = get_settings()
    if not s.voyage_api_key:
        raise RuntimeError("VOYAGE_API_KEY is not set")
    if input_type == "document":
        # Pace bulk ingest only. A user's query must not queue behind the cap.
        _limiter.wait(s.voyage_rpm)
    resp = httpx.post(
        VOYAGE_URL,
        headers={"Authorization": f"Bearer {s.voyage_api_key}"},
        json={"input": texts, "model": s.embedding_model, "input_type": input_type},
        timeout=60,
    )
    resp.raise_for_status()
    data = sorted(resp.json()["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in data]


def _batches(texts: list[str]) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    tokens = 0
    for t in texts:
        size = len(t) // CHARS_PER_TOKEN + 1
        if current and (len(current) >= MAX_BATCH or tokens + size > MAX_BATCH_TOKENS):
            batches.append(current)
            current, tokens = [], 0
        current.append(t)
        tokens += size
    if current:
        batches.append(current)
    return batches


def embed(texts: list[str], input_type: InputType) -> list[list[float]]:
    s = get_settings()
    if s.embedding_provider != "voyage":
        raise RuntimeError(f"Unsupported EMBEDDING_PROVIDER: {s.embedding_provider}")
    out: list[list[float]] = []
    for batch in _batches(texts):
        out.extend(_voyage_batch(batch, input_type))
    for vec in out:
        if len(vec) != s.embedding_dim:
            raise RuntimeError(
                f"{s.embedding_model} returned {len(vec)} dims, expected {s.embedding_dim}"
            )
    return out


def embed_query(text: str) -> list[float]:
    return embed([text], "query")[0]
