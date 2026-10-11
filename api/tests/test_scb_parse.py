from datetime import date
from decimal import Decimal

from ingest.scb_client import build_query, parse_rows

META = {
    "title": "Byggkostnadsindex ... 1968=100, index efter hustyp, kostnadsslag",
    "variables": [
        {"code": "Hustyp", "values": ["FLERBO", "GRUPPSMÅ"]},
        {"code": "Kostnadsslag", "values": ["TOTAL"]},
        {"code": "ContentsCode", "values": ["PR0502A3"]},
        {"code": "Tid", "values": ["2024M01", "2024M02"], "time": True},
    ],
}
DATA = {
    "columns": [
        {"code": "Hustyp", "type": "d"},
        {"code": "Kostnadsslag", "type": "d"},
        {"code": "Tid", "type": "t"},
        {"code": "PR0502A3", "type": "c"},
    ],
    "data": [
        {"key": ["FLERBO", "TOTAL", "2024M01"], "values": ["1848.9"]},
        {"key": ["FLERBO", "TOTAL", "2024M02"], "values": [".."]},
        {"key": ["GRUPPSMÅ", "TOTAL", "2024M01"], "values": ["1702.4"]},
    ],
}


def test_query_uses_codes_from_metadata() -> None:
    q = build_query(META)
    assert [d["code"] for d in q["query"]] == ["Hustyp", "Kostnadsslag", "ContentsCode", "Tid"]
    assert q["query"][2]["selection"]["values"] == ["PR0502A3"]


def test_parse_rows_skips_missing_and_builds_series_key() -> None:
    rows = parse_rows("FPIBOM", META, DATA, "https://example/FPIBOM")
    assert len(rows) == 2
    first = rows[0]
    assert first.series_key == "FLERBO|TOTAL"
    assert first.building_type == "FLERBO"
    assert first.cost_class == "TOTAL"
    assert first.period == date(2024, 1, 1)
    assert first.value == Decimal("1848.9")
    assert first.base_year == "1968"


def test_default_building_type_when_no_hustyp() -> None:
    data = {
        "columns": [
            {"code": "Kostnadsslag", "type": "d"},
            {"code": "Tid", "type": "t"},
            {"code": "0000020J", "type": "c"},
        ],
        "data": [{"key": ["TOTAL", "2024M01"], "values": ["155.9"]}],
    }
    rows = parse_rows("FPIJBM15", {"title": "2015=100"}, data, "u", "JORDBRUK")
    assert rows[0].building_type == "JORDBRUK"
    assert rows[0].series_key == "TOTAL"
