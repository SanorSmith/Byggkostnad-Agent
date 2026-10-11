from typing import Any

from evals.metrics import (
    answer_groundedness,
    groundedness,
    numeric_accuracy,
    numeric_correct,
    parse_numbers,
    recall_at_5,
    score_claims,
    unsupported_figures,
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


# --- Issue 13: the figure must come from the price tool -------------------


def test_document_figure_cannot_mask_a_wrong_computed_one() -> None:
    # PR #2: the tool returned 17.19 (inflated), the answer also quoted SCB's
    # published 15.6 from a news release. That used to pass.
    answer = "The tool says +17.19 %; SCB's release says 15,6 %."
    assert numeric_correct(answer, 15.63, 1.0)  # old, lenient behaviour
    assert not numeric_correct(answer, 15.63, 1.0, tool_values=[1508.9, 1768.3, 17.19])


def test_figure_from_the_tool_passes() -> None:
    answer = "It rose 15.6 % (1508.9 to 1744.8)."
    assert numeric_correct(answer, 15.63, 1.0, tool_values=[1508.9, 1744.8, 15.63])


def test_no_price_tool_output_fails() -> None:
    assert not numeric_correct("It rose 15.63 %.", 15.63, 1.0, tool_values=[])


def test_numeric_accuracy_uses_tool_values() -> None:
    answers = {"n1": "10.0", "h1": "it rose 49.9"}
    assert numeric_accuracy(ITEMS, answers, {"n1": [10.0], "h1": [62.0]}) == 0.5


# --- Issue 12: groundedness must fail a wrong figure ----------------------


def test_unsupported_figures_accepts_rounding_and_sign() -> None:
    tool = '{"percent_change": "4.61", "first": "1848.90", "rows": [{"value": "-0.50"}]}'
    assert unsupported_figures("Up 4.61 %, about 4.6 %, from 1 848,9; fell 0.5 %.", tool) == []


def test_unsupported_figures_flags_altered_and_derived_numbers() -> None:
    tool = '{"percent_change": "15.63", "text": "index 149,4 then 155,3"}'
    # 19.54: a falsified figure. 3.95: arithmetic the model did itself.
    assert unsupported_figures("It rose 19.54 %.", tool) == [19.54]
    assert unsupported_figures("155.3 / 149.4 - 1 = 3.95 %", tool) == [3.95]


def test_unsupported_figures_ignores_whole_numbers() -> None:
    assert unsupported_figures("Between 2021 and 2022, base 1968=100.", "{}") == []


def test_one_unsupported_numeric_claim_zeroes_the_answer() -> None:
    claims = [{"claim": f"fact {i}", "is_numeric": False, "supported": True} for i in range(14)]
    claims.append({"claim": "It rose 19.54 %", "is_numeric": True, "supported": False})
    assert score_claims(claims) == 0.0  # was 14/15 = 0.93 under plain averaging


def test_unsupported_text_claim_is_averaged() -> None:
    claims = [
        {"claim": "a", "is_numeric": False, "supported": True},
        {"claim": "b", "is_numeric": False, "supported": False},
    ]
    assert score_claims(claims) == 0.5
    assert score_claims([]) == 1.0


def test_deterministic_check_overrides_the_judge() -> None:
    def lenient_judge(answer: str, tool_output: str) -> float:
        return 1.0

    tool = '{"percent_change": "15.63"}'
    assert answer_groundedness("It rose 19.54 %.", tool, lenient_judge) == 0.0
    assert answer_groundedness("It rose 15.63 %.", tool, lenient_judge) == 1.0
