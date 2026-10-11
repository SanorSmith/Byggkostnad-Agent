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
    out: list[float] = []
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
            out.append(float(s))
        except ValueError:
            continue
    return out


def numeric_correct(answer: str, expected: float, tolerance_pct: float) -> bool:
    """True if any figure in the answer is within tolerance_pct (relative) of expected.
    An answer with no parseable figure fails."""
    tol = abs(expected) * tolerance_pct / 100
    return any(abs(n - expected) <= tol for n in parse_numbers(answer))


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


def numeric_accuracy(items: Sequence[dict[str, Any]], answers: dict[str, str]) -> float | None:
    scored = [i for i in items if i["type"] in ("numeric", "hybrid")]
    if not scored:
        return None
    correct = sum(
        numeric_correct(answers.get(i["id"], ""), i["expected_value"], i["tolerance_pct"])
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
number that appears in the tool output counts as supported. Claims that only \
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
                    "supported": {"type": "boolean"},
                },
                "required": ["claim", "supported"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}

MAX_TOOL_OUTPUT_CHARS = 60_000


def make_llm_judge(client: anthropic.Anthropic, model: str) -> Judge:
    """Groundedness judge: per-claim support, averaged. 1.0 when there are no claims."""

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
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        claims = json.loads(text).get("claims", [])
        if not claims:
            return 1.0
        return sum(1 for c in claims if c["supported"]) / len(claims)

    return judge
