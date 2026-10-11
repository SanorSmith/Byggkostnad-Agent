from typing import Any

from evals.metrics import (
    groundedness,
    numeric_accuracy,
    numeric_correct,
    parse_numbers,
    recall_at_5,
)


def test_parse_numbers_swedish_and_english() -> None:
    assert parse_numbers("steg med 3,96 procent") == [3.96]
    assert parse_numbers("from 1 848,9 to 1 922,1") == [1848.9, 1922.1]
    assert parse_numbers("1,848.9 -> 1,922.1 (+3.96%)") == [1848.9, 1922.1, 3.96]
    assert parse_numbers("sjönk −0,5 procent") == [-0.5]
    assert parse_numbers("no figures here") == []


def test_numeric_correct_tolerance() -> None:
    assert numeric_correct("It rose 3.96 percent.", 3.96, 1.0)
    assert numeric_correct("It rose about 4.0 percent.", 3.96, 2.0)
    assert not numeric_correct("It rose 4.5 percent.", 3.96, 2.0)
    assert not numeric_correct("It rose sharply.", 3.96, 2.0)  # unparseable fails


ITEMS: list[dict[str, Any]] = [
    {
        "id": "n1",
        "type": "numeric",
        "question": "q",
        "expected_value": 10.0,
        "tolerance_pct": 1.0,
        "expected_source_contains": None,
    },
    {
        "id": "d1",
        "type": "definition",
        "question": "what is A",
        "expected_value": None,
        "tolerance_pct": None,
        "expected_source_contains": "alpha",
    },
    {
        "id": "h1",
        "type": "hybrid",
        "question": "why B",
        "expected_value": 50.0,
        "tolerance_pct": 1.0,
        "expected_source_contains": "mars-2022",
    },
]


def test_numeric_accuracy_counts_numeric_and_hybrid() -> None:
    assert numeric_accuracy(ITEMS, {"n1": "10.0", "h1": "it rose 49.9"}) == 1.0
    assert numeric_accuracy(ITEMS, {"n1": "10.0", "h1": "no number"}) == 0.5
    assert numeric_accuracy(ITEMS, {}) == 0.0


def test_recall_at_5_matches_url_or_text() -> None:
    def retrieve(question: str, k: int) -> list[dict[str, Any]]:
        assert k == 5
        if question == "what is A":
            return [{"source_url": "https://x/doc", "text": "Alpha is ..."}]
        return [{"source_url": "https://x/other", "text": "nothing"}]

    assert recall_at_5(ITEMS, retrieve) == 0.5

    def retrieve_all(question: str, k: int) -> list[dict[str, Any]]:
        return [{"source_url": "https://x/byggkostnadsindex-mars-2022/", "text": "alpha"}]

    assert recall_at_5(ITEMS, retrieve_all) == 1.0


def test_groundedness_average() -> None:
    assert groundedness([1.0, 0.5, 0.0]) == 0.5
    assert groundedness([]) is None
