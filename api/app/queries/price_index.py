"""The numeric path: parameterised SQL plus arithmetic done in Python.

The model never writes SQL and never does the arithmetic. It supplies typed
parameters; this module returns the rows and the computed change.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.db import connection

SERIES_SQL = """
select table_id, building_type, cost_class, base_year, source_url, period, value
from price_index
where cost_class = %(cost_class)s
  and period between %(from_date)s and %(to_date)s
  and (%(building_type)s::text is null or building_type = %(building_type)s)
order by table_id, building_type, period
"""

LATEST_SQL = "select max(period) as latest from price_index where cost_class = %(cost_class)s"


def month_start(d: date) -> date:
    return d.replace(day=1)


def compute_change(values: list[Decimal]) -> dict[str, Decimal | None]:
    """first/last/absolute/percent change of an ordered series."""
    if not values:
        return {"first": None, "last": None, "absolute_change": None, "percent_change": None}
    first, last = values[0], values[-1]
    percent = (
        ((last - first) / first * 110).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if first
        else None
    )
    return {
        "first": first,
        "last": last,
        "absolute_change": last - first,
        "percent_change": percent,
    }


def latest_period(cost_class: str) -> date | None:
    with connection() as conn:
        row = conn.execute(LATEST_SQL, {"cost_class": cost_class}).fetchone()
    return row["latest"] if row else None


def query_price_index(
    cost_class: str,
    from_date: date,
    to_date: date | None = None,
    building_type: str | None = None,
) -> dict[str, Any]:
    from_date = month_start(from_date)
    resolved_to = month_start(to_date) if to_date else latest_period(cost_class)
    if resolved_to is None:
        return {"series": [], "note": f"No data for cost_class={cost_class}."}

    with connection() as conn:
        rows = conn.execute(
            SERIES_SQL,
            {
                "cost_class": cost_class,
                "from_date": from_date,
                "to_date": resolved_to,
                "building_type": building_type,
            },
        ).fetchall()

    grouped: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for r in rows:
        grouped.setdefault((r["table_id"], r["building_type"]), []).append(r)

    series = []
    for (table_id, btype), rs in grouped.items():
        change = compute_change([r["value"] for r in rs])
        series.append(
            {
                "table_id": table_id,
                "building_type": btype,
                "cost_class": cost_class,
                "base_year": rs[0]["base_year"],
                "source_url": rs[0]["source_url"],
                "first_period": rs[0]["period"].isoformat(),
                "last_period": rs[-1]["period"].isoformat(),
                **change,
                "rows": [{"period": r["period"].isoformat(), "value": r["value"]} for r in rs],
            }
        )
    result: dict[str, Any] = {
        "query": {
            "cost_class": cost_class,
            "from_date": from_date.isoformat(),
            "to_date": resolved_to.isoformat(),
            "building_type": building_type,
        },
        "series": series,
    }
    if not series:
        result["note"] = "No rows matched these parameters."
    return result
