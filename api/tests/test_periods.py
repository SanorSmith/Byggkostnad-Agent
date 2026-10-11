from datetime import date

import pytest

from ingest.scb_client import normalize_period, parse_base_year


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026M07", date(2026, 7, 1)),
        ("1975M01", date(1975, 1, 1)),
        ("2024M12", date(2024, 12, 1)),
        (" 2022M03 ", date(2022, 3, 1)),
    ],
)
def test_normalize_period(raw: str, expected: date) -> None:
    assert normalize_period(raw) == expected


@pytest.mark.parametrize("raw", ["2026M13", "2026M00", "2026K1", "2026", "202607", ""])
def test_normalize_period_rejects(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_period(raw)


def test_base_year_from_title() -> None:
    assert parse_base_year("Byggkostnadsindex ... 1968=100, efter hustyp") == "1968"
    assert parse_base_year("no base year here") is None
