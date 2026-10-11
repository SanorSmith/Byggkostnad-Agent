from decimal import Decimal

from app.queries.price_index import compute_change


def test_percent_change_matches_scb_figure() -> None:
    # FPIBOM, flerbostadshus, total: Jan 2024 -> Jul 2026.
    out = compute_change([Decimal("1848.9"), Decimal("1900.0"), Decimal("1922.1")])
    assert out["first"] == Decimal("1848.9")
    assert out["last"] == Decimal("1922.1")
    assert out["absolute_change"] == Decimal("73.2")
    assert out["percent_change"] == Decimal("3.96")


def test_negative_change() -> None:
    out = compute_change([Decimal("200"), Decimal("150")])
    assert out["absolute_change"] == Decimal("-50")
    assert out["percent_change"] == Decimal("-25.00")


def test_rounds_half_up() -> None:
    # 1/32 = 3.125 % -> 3.13
    assert compute_change([Decimal("32"), Decimal("33")])["percent_change"] == Decimal("3.13")


def test_single_value_and_empty() -> None:
    assert compute_change([Decimal("100")])["percent_change"] == Decimal("0.00")
    assert compute_change([])["percent_change"] is None


def test_zero_base_has_no_percent() -> None:
    assert compute_change([Decimal("0"), Decimal("5")])["percent_change"] is None
