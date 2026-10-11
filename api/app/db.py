"""Postgres connection pool (Supabase)."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings

_pool: ConnectionPool | None = None


def _configure(conn: psycopg.Connection[Any]) -> None:
    register_vector(conn)


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        url = get_settings().database_url
        if not url:
            raise RuntimeError("DATABASE_URL is not set")
        # prepare_threshold=None: the Supabase transaction pooler does not
        # support server-side prepared statements.
        _pool = ConnectionPool(
            url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row, "prepare_threshold": None},
            configure=_configure,
            open=True,
        )
    return _pool


@contextmanager
def connection() -> Iterator[psycopg.Connection[DictRow]]:
    # The pool is created with row_factory=dict_row; tell the type checker.
    with get_pool().connection() as conn:
        yield cast("psycopg.Connection[DictRow]", conn)


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
