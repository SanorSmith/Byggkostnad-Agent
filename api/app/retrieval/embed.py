"""One pinned embedding model, used for both documents and queries.

The model name comes from config and is stored on every chunk row. Search
filters on it, so a half-migrated corpus returns fewer hits rather than
wrong ones.
"""

from typing import Literal

import httpx

from app.config import get_settings
from app.http import http_retry

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
BATCH_SIZE = 64

InputType = Literal["document", "query"]


@http_retry
def _voyage_batch(texts: list[str], input_type: InputType) -> list[list[float]]:
    s = get_settings()
    if not s.voyage_api_key:
        raise RuntimeError("VOYAGE_API_KEY is not set")
    resp = httpx.post(
        VOYAGE_URL,
        headers={"Authorization": f"Bearer {s.voyage_api_key}"},
        json={"input": texts, "model": s.embedding_model, "input_type": input_type},
        timeout=60,
    )
    resp.raise_for_status()
    data = sorted(resp.json()["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in data]


def embed(texts: list[str], input_type: InputType) -> list[list[float]]:
    s = get_settings()
    if s.embedding_provider != "voyage":
        raise RuntimeError(f"Unsupported EMBEDDING_PROVIDER: {s.embedding_provider}")
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        out.extend(_voyage_batch(texts[i : i + BATCH_SIZE], input_type))
    for vec in out:
        if len(vec) != s.embedding_dim:
            raise RuntimeError(
                f"{s.embedding_model} returned {len(vec)} dims, expected {s.embedding_dim}"
            )
    return out


def embed_query(text: str) -> list[float]:
    return embed([text], "query")[0]
