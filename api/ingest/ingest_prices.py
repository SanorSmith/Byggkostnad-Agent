"""Load SCB price index tables into price_index (idempotent upsert).

python -m ingest.ingest_prices            # all tables
python -m ingest.ingest_prices --verify   # also print rows to check against scb.se
"""

import argparse
import logging
from collections.abc import Iterable
from typing import Any

import psycopg

from app.config import get_settings
from app.db import connection
from app.logging_setup import log, setup_logging
from ingest.scb_client import PriceRow, ScbClient, build_query, parse_rows

logger = logging.getLogger("ingest.prices")

# table_id -> building_type to use when the table has no Hustyp dimension.
TABLES: dict[str, str | None] = {
    "FPIBOM": None,  # residential, monthly, 1968=100, split by Hustyp
    "FPIJBM15": "JORDBRUK",  # agricultural, monthly, 2015=100
}

UPSERT_SQL = """
insert into price_index
  (table_id, series_key, building_type, cost_class, period, value, base_year, source_url)
values
  (%(table_id)s, %(series_key)s, %(building_type)s, %(cost_class)s, %(period)s,
   %(value)s, %(base_year)s, %(source_url)s)
on conflict (table_id, series_key, period) do update set
  building_type = excluded.building_type,
  cost_class    = excluded.cost_class,
  value         = excluded.value,
  base_year     = excluded.base_year,
  source_url    = excluded.source_url,
  ingested_at   = now()
"""


def public_table_url(table_id: str) -> str:
    """Human-readable SCB page for a table (what a citation should link to)."""
    return f"https://www.statistikdatabasen.scb.se/goto/sv/ssd/{table_id}"


def upsert_rows(conn: psycopg.Connection[Any], rows: Iterable[PriceRow]) -> int:
    params = [r.__dict__ for r in rows]
    with conn.cursor() as cur:
        cur.executemany(UPSERT_SQL, params)
    return len(params)


def fetch_table(client: ScbClient, table_id: str) -> list[PriceRow]:
    meta = client.get_metadata(table_id)
    data = client.get_data(table_id, build_query(meta))
    return parse_rows(table_id, meta, data, public_table_url(table_id), TABLES[table_id])


VERIFY_SQL = """
select table_id, building_type, cost_class, period, value
from price_index
where (table_id, coalesce(building_type, ''), cost_class, period) in (
  ('FPIBOM', 'FLERBO', 'TOTAL', date '2024-01-01'),
  ('FPIBOM', 'FLERBO', 'TOTAL', date '2022-03-01'),
  ('FPIBOM', 'FLERBO', 'TOTAL', date '2022-02-01'),
  ('FPIBOM', 'GRUPPSMÅ', 'TOTAL', date '2022-12-01'),
  ('FPIJBM15', 'JORDBRUK', 'TOTAL', date '2024-01-01')
)
order by table_id, building_type, period
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tables", nargs="*", default=list(TABLES))
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    setup_logging()

    client = ScbClient(get_settings().scb_base_url)
    try:
        for table_id in args.tables:
            rows = fetch_table(client, table_id)
            with connection() as conn:
                n = upsert_rows(conn, rows)
            log(
                logger,
                "upserted",
                table_id=table_id,
                rows=n,
                series=len({r.series_key for r in rows}),
                latest=max(r.period for r in rows).isoformat(),
            )
    finally:
        client.close()

    if args.verify:
        with connection() as conn:
            for r in conn.execute(VERIFY_SQL).fetchall():
                print(
                    f"{r['table_id']:9} {r['building_type'] or '-':9} {r['cost_class']:6} "
                    f"{r['period']}  {r['value']}"
                )


if __name__ == "__main__":
    main()
