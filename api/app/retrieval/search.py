"""Cosine search over doc_chunks with pgvector."""

from typing import Any

import numpy as np

from app.config import get_settings
from app.db import connection
from app.retrieval.embed import embed_query

SEARCH_SQL = """
select c.id, c.text, d.source_url, d.title,
       1 - (c.embedding <=> %(q)s) as similarity
from doc_chunks c
join documents d on d.id = c.document_id
where c.embedding_model = %(model)s
order by c.embedding <=> %(q)s
limit %(k)s
"""


def search_docs(query: str, k: int = 5) -> list[dict[str, Any]]:
    k = max(1, min(int(k), 20))
    vec = np.array(embed_query(query), dtype=np.float32)
    with connection() as conn:
        rows = conn.execute(
            SEARCH_SQL, {"q": vec, "model": get_settings().embedding_model, "k": k}
        ).fetchall()
    return [
        {
            "chunk_id": r["id"],
            "text": r["text"],
            "source_url": r["source_url"],
            "title": r["title"],
            "similarity": round(float(r["similarity"]), 4),
        }
        for r in rows
    ]
