"""Idempotency of the price upsert. Needs a Postgres with sql/001_init.sql applied
(CI provides one); skipped when TEST_DATABASE_URL is not set."""

import os
from datetime import date
from decimal import Decimal

import psycopg
import pytest
from psycopg.rows import dict_row

from ingest.ingest_prices import upsert_rows
from ingest.scb_client import PriceRow

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")

TABLE = "TEST_UPSERT"


def _rows(value: str) -> list[PriceRow]:
    return [
        PriceRow(
            TABLE,
            "FLERBO|TOTAL",
            "FLERBO",
            "TOTAL",
            date(2024, m, 1),
            Decimal(value),
            "1968",
            "https://example/test",
        )
        for m in (1, 2, 3)
    ]


def test_upsert_is_idempotent() -> None:
    assert URL is not None
    with psycopg.connect(URL, row_factory=dict_row) as conn:
        conn.execute("delete from price_index where table_id = %s", (TABLE,))
        upsert_rows(conn, _rows("100.0"))
        upsert_rows(conn, _rows("100.0"))
        count = conn.execute(
            "select count(*) as n from price_index where table_id = %s", (TABLE,)
        ).fetchone()
        assert count is not None
        assert count["n"] == 3

        # A revised value from SCB updates in place rather than duplicating.
        upsert_rows(conn, _rows("101.5"))
        rows = conn.execute(
            "select value from price_index where table_id = %s", (TABLE,)
        ).fetchall()
        assert [r["value"] for r in rows] == [Decimal("101.50")] * 3
        conn.execute("delete from price_index where table_id = %s", (TABLE,))
