"""PxWebApi v1 client for SCB.

Dimension codes are read from each table's metadata, never hardcoded: the
two tables we load use different ContentsCode values, and a guessed code
returns an HTTP 400 rather than an empty result.
"""

import json
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.http import http_retry

_PERIOD = re.compile(r"^(\d{4})M(\d{2})$")
_BASE_YEAR = re.compile(r"(\d{4})=100")
MISSING = {"..", ".", "-", ""}


class Throttle:
    """At most `max_calls` per `period` seconds (SCB allows about 10 per 10 s)."""

    def __init__(self, max_calls: int = 10, period: float = 10.0) -> None:
        self.max_calls = max_calls
        self.period = period
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            while self._calls and now - self._calls[0] >= self.period:
                self._calls.popleft()
            if len(self._calls) >= self.max_calls:
                time.sleep(self.period - (now - self._calls[0]) + 0.05)
                self._calls.popleft()
            self._calls.append(time.monotonic())


def normalize_period(period: str) -> date:
    """'2026M07' -> date(2026, 7, 1)."""
    m = _PERIOD.match(period.strip())
    if not m:
        raise ValueError(f"Unrecognised SCB period: {period!r}")
    year, month = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"Month out of range in period: {period!r}")
    return date(year, month, 1)


def parse_base_year(title: str) -> str | None:
    m = _BASE_YEAR.search(title)
    return m.group(1) if m else None


def build_query(metadata: dict[str, Any]) -> dict[str, Any]:
    """Select every value of every dimension, using codes from the metadata."""
    return {
        "query": [
            {"code": v["code"], "selection": {"filter": "item", "values": v["values"]}}
            for v in metadata["variables"]
        ],
        "response": {"format": "json"},
    }


@dataclass(frozen=True)
class PriceRow:
    table_id: str
    series_key: str
    building_type: str | None
    cost_class: str
    period: date
    value: Decimal
    base_year: str | None
    source_url: str


def parse_rows(
    table_id: str,
    metadata: dict[str, Any],
    data: dict[str, Any],
    source_url: str,
    default_building_type: str | None = None,
) -> list[PriceRow]:
    key_cols = [c for c in data["columns"] if c["type"] in ("d", "t")]
    codes = [c["code"] for c in key_cols]
    time_idx = next(i for i, c in enumerate(key_cols) if c["type"] == "t")
    base_year = parse_base_year(metadata.get("title", ""))

    rows: list[PriceRow] = []
    for item in data["data"]:
        key: list[str] = item["key"]
        raw = item["values"][0]
        if raw in MISSING:
            continue
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise ValueError(f"Bad value {raw!r} for {table_id} {key}") from exc
        dims = {codes[i]: key[i] for i in range(len(key)) if i != time_idx}
        rows.append(
            PriceRow(
                table_id=table_id,
                series_key="|".join(key[i] for i in range(len(key)) if i != time_idx),
                building_type=dims.get("Hustyp", default_building_type),
                cost_class=dims["Kostnadsslag"],
                period=normalize_period(key[time_idx]),
                value=value,
                base_year=base_year,
                source_url=source_url,
            )
        )
    return rows


class ScbClient:
    def __init__(self, base_url: str, throttle: Throttle | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.throttle = throttle or Throttle()
        self._http = httpx.Client(timeout=60, headers={"User-Agent": "byggkostnad-agent"})

    def table_url(self, table_id: str) -> str:
        return f"{self.base_url}/{table_id}"

    @http_retry
    def get_metadata(self, table_id: str) -> dict[str, Any]:
        self.throttle.wait()
        resp = self._http.get(self.table_url(table_id))
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    @http_retry
    def get_data(self, table_id: str, query: dict[str, Any]) -> dict[str, Any]:
        self.throttle.wait()
        resp = self._http.post(self.table_url(table_id), json=query)
        resp.raise_for_status()
        # utf-8-sig reads plain UTF-8 too; it only guards against a BOM.
        result: dict[str, Any] = json.loads(resp.content.decode("utf-8-sig"))
        return result

    def close(self) -> None:
        self._http.close()
