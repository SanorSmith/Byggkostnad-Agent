"""Evaluation metrics: recall@5, numeric accuracy, groundedness."""

import json
import re
from collections.abc import Callable, Sequence
from typing import Any

import anthropic

Retriever = Callable[[str, int], list[dict[str, Any]]]
Judge = Callable[[str, str], float]

_NUMBER = re.compile(
    r"[-−‑]?\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?"  # 1 848,9 (Swedish grouping)
    r"|[-−‑]?\d+(?:[.,]\d+)*"
)


_THOUSANDS_COMMA = re.compile(r"^-?\d{1,3}(?:,\d{3})+$")


def parse_numbers(text: str) -> list[float]:
    """Every number in an answer, accepting Swedish and English notation.

    "1 848,9", "1,848.9" and "1848.9" all parse to 1848.9. A lone comma is a
    decimal separator ("3,96") unless it groups thousands exactly ("11,040").
    """
    return [value for value, _ in parse_figures(text)]


def parse_figures(text: str) -> list[tuple[float, int]]:
    """Like parse_numbers, but also returns how many decimals each number was
    written with, so a rounded figure can be matched to its source."""
    out: list[tuple[float, int]] = []
    for raw in _NUMBER.findall(text):
        s = re.sub(r"[   ]", "", raw).replace("−", "-").replace("‑", "-")
        if "," in s and "." in s:
            # Whichever separator comes first groups thousands.
            if s.index(",") < s.index("."):
                s = s.replace(",", "")
            else:
                s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", "") if _THOUSANDS_COMMA.match(s) else s.replace(",", ".")
        if s.count(".") > 1:
            continue  # a date like 2026.07.01, not a figure
        try:
            out.append((float(s), len(s.split(".")[1]) if "." in s else 0))
        except ValueError:
            continue
    return out


def _close(a: float, b: float, tolerance_pct: float) -> bool:
    return abs(a - b) <= abs(b) * tolerance_pct / 100


def numeric_correct(
    answer: str,
    expected: float,
    tolerance_pct: float,
    tool_values: Sequence[float] | None = None,
) -> bool:
    """True if a figure in the answer is within tolerance_pct (relative) of
    `expected`. An answer with no parseable figure fails.

    With `tool_values` (numbers returned by query_price_index), the matching
    figure must also be one the tool returned. Otherwise a correct figure
    quoted from a news release can hide a wrong computed one, which is what
    happened in the regression-gate test (PR #2).
    """
    for n in parse_numbers(answer):
        if not _close(n, expected, tolerance_pct):
            continue
        if tool_values is None or any(_close(n, t, tolerance_pct) for t in tool_values):
            return True
    return False


def unsupported_figures(answer: str, tool_output: str) -> list[float]:
    """Decimal figures in the answer that do not appear in the tool output.

    Deterministic, no model involved. A figure written with d decimals counts
    as supported if some number in the tool output rounds to it (4.6 matches
    4.61). Whole numbers are ignored: they are mostly years, counts and base
    years (1968=100), and checking them would flag every date. Sign is
    ignored ("fell 0.5 %" matches -0.5).
    """
    sources = [abs(v) for v in parse_numbers(tool_output)]
    missing = []
    for value, decimals in parse_figures(answer):
        if decimals == 0:
            continue
        half_step = 0.5 * 10**-decimals + 1e-9
        if not any(abs(abs(value) - s) <= half_step for s in sources):
            missing.append(value)
    return missing


def recall_at_5(items: Sequence[dict[str, Any]], retrieve: Retriever) -> float | None:
    scored = [i for i in items if i["type"] in ("definition", "hybrid")]
    if not scored:
        return None
    hits = 0
    for item in scored:
        needle = item["expected_source_contains"].lower()
        results = retrieve(item["question"], 5)
        if any(needle in (r["source_url"] + " " + r["text"]).lower() for r in results):
            hits += 1
    return hits / len(scored)


def numeric_accuracy(
    items: Sequence[dict[str, Any]],
    answers: dict[str, str],
    tool_values: dict[str, list[float]] | None = None,
) -> float | None:
    """Share of numeric and hybrid questions answered with the right figure.
    With `tool_values` (per question id), the figure must also come from
    query_price_index; a question with no price-tool output then fails."""
    scored = [i for i in items if i["type"] in ("numeric", "hybrid")]
    if not scored:
        return None
    correct = sum(
        numeric_correct(
            answers.get(i["id"], ""),
            i["expected_value"],
            i["tolerance_pct"],
            None if tool_values is None else tool_values.get(i["id"], []),
        )
        for i in scored
    )
    return correct / len(scored)


def groundedness(per_item_scores: Sequence[float]) -> float | None:
    return sum(per_item_scores) / len(per_item_scores) if per_item_scores else None


JUDGE_PROMPT = """You check whether an answer is supported by tool output.

<tool_output>
{tool_output}
</tool_output>

<answer>
{answer}
</answer>

List every factual claim in the answer (numbers, dates, causes, definitions). \
For each claim decide whether the tool output above supports it. Rounding of a \
number that appears in the tool output counts as supported. A number that \
does not itself appear in the tool output is NOT supported, even if it could \
be calculated from numbers that do. Mark is_numeric true for any claim that \
states a figure (an index value, a change, a percentage). Claims that only \
restate the question or say that data is missing are not factual claims. \
Return JSON only."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "is_numeric": {"type": "boolean"},
                    "supported": {"type": "boolean"},
                },
                "required": ["claim", "is_numeric", "supported"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}

MAX_TOOL_OUTPUT_CHARS = 60_000


def score_claims(claims: Sequence[dict[str, Any]]) -> float:
    """Per-answer score from the judge's claims.

    One unsupported numeric claim scores the whole answer 0: a wrong figure
    is the failure this system exists to prevent, and averaging it with
    fifteen correct sentences hid it. Otherwise the share of supported
    claims. 1.0 when there are no claims.
    """
    if not claims:
        return 1.0
    if any(c.get("is_numeric") and not c["supported"] for c in claims):
        return 0.0
    return sum(1 for c in claims if c["supported"]) / len(claims)


def make_llm_judge(client: anthropic.Anthropic, model: str) -> Judge:
    """Groundedness judge (strict on numbers, see score_claims)."""

    def judge(answer: str, tool_output: str) -> float:
        resp = client.messages.create(
            model=model,
            max_tokens=4000,
            messages=[
                {
                    "role": "user",
                    "content": JUDGE_PROMPT.format(
                        tool_output=tool_output[:MAX_TOOL_OUTPUT_CHARS], answer=answer
                    ),
                }
            ],
            output_config={"format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
            # The judge model accepts sampling parameters; the SDK no longer
            # exposes them as arguments. Temperature 0 cuts run-to-run drift.
            extra_body={"temperature": 0},
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        return score_claims(json.loads(text).get("claims", []))

    return judge


def answer_groundedness(answer: str, tool_output: str, judge: Judge) -> float:
    """Groundedness of one answer: 0 if a decimal figure in it is absent from
    the tool output (deterministic check), otherwise the judge's score."""
    if unsupported_figures(answer, tool_output):
        return 0.0
    return judge(answer, tool_output)
