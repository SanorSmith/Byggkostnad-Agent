"""Compare stored rows with figures SCB published in its own news releases.

SCB's releases quote the flerbostadshus index on a 2015=100 base, while
FPIBOM is 1968=100, so levels cannot be compared directly. Percentage
changes do not depend on the base, so those are checked.

    python -m ingest.verify_against_scb            # prints a markdown table, exit 1 on mismatch
"""

import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.db import connection
from app.queries.price_index import compute_change

NEWS = (
    "https://www.scb.se/hitta-statistik/statistik-efter-amne/priser-och-ekonomiska-tendenser"
    "/priser/byggkostnadsindex-bki/pong/statistiknyhet/"
)


@dataclass(frozen=True)
class Published:
    label: str
    cost_class: str
    start: date
    end: date
    scb_percent: Decimal
    source: str


# Figures copied from SCB's releases (Swedish decimal commas written as points).
PUBLISHED = [
    Published(
        "Feb → Mar 2022",
        "TOTAL",
        date(2022, 2, 1),
        date(2022, 3, 1),
        Decimal("1.5"),
        NEWS + "byggkostnadsindex-for-byggnader-mars-2022/",
    ),
    Published(
        "Mar 2021 → Mar 2022",
        "TOTAL",
        date(2021, 3, 1),
        date(2022, 3, 1),
        Decimal("9.6"),
        NEWS + "byggkostnadsindex-for-byggnader-mars-2022/",
    ),
    Published(
        "Nov → Dec 2022",
        "TOTAL",
        date(2022, 11, 1),
        date(2022, 12, 1),
        Decimal("0.4"),
        NEWS + "byggkostnadsindex-for-byggnader-december-2022/",
    ),
    Published(
        "Dec 2021 → Dec 2022",
        "TOTAL",
        date(2021, 12, 1),
        date(2022, 12, 1),
        Decimal("15.6"),
        NEWS + "byggkostnadsindex-for-byggnader-december-2022/",
    ),
    Published(
        "Jul → Aug 2026",
        "TOTAL",
        date(2026, 7, 1),
        date(2026, 8, 1),
        Decimal("0.6"),
        NEWS + "byggkostnadsindex-for-byggnader-august-2026/",
    ),
    Published(
        "Transport, fuel, electricity: Mar 2021 → Mar 2022",
        "TRANS",
        date(2021, 3, 1),
        date(2022, 3, 1),
        Decimal("26.7"),
        NEWS + "byggkostnadsindex-for-byggnader-mars-2022/",
    ),
]

SQL = """
select period, value from price_index
where table_id = 'FPIBOM' and building_type = 'FLERBO' and cost_class = %s
  and period in (%s, %s)
order by period
"""


def main() -> int:
    print(
        "| check (flerbostadshus) | our rows (FPIBOM, 1968=100) "
        "| our change | SCB published | match |"
    )
    print("|---|---|---|---|---|")
    failures = 0
    with connection() as conn:
        for p in PUBLISHED:
            rows = conn.execute(SQL, (p.cost_class, p.start, p.end)).fetchall()
            values = [r["value"] for r in rows]
            if len(values) != 2:
                print(f"| {p.label} | missing rows | — | {p.scb_percent} % | **no** |")
                failures += 1
                continue
            pct = compute_change(values)["percent_change"]
            assert pct is not None
            ours = pct.quantize(Decimal("0.1"))
            ok = ours == p.scb_percent
            failures += not ok
            print(
                f"| {p.label} | {values[0]} → {values[1]} | {ours} % | "
                f"[{p.scb_percent} %]({p.source}) | {'yes' if ok else '**no**'} |"
            )
    print(f"\n{len(PUBLISHED) - failures} of {len(PUBLISHED)} match.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
