"""Check that the groundedness judge can fail an answer.

Takes each numeric/hybrid answer from the latest eval run, swaps its
expected figure for a wrong one, and scores the original and the altered
answer against the same tool output. A judge that scores both the same is
not measuring anything.

    python -m evals.run_evals --no-record   # writes evals/results/latest.json
    python -m evals.judge_sanity
"""

import json
import re
from pathlib import Path

from app.agent.loop import get_client, run_agent
from app.config import get_settings
from evals.metrics import make_llm_judge

HERE = Path(__file__).parent


def main() -> None:
    golden = {
        i["id"]: i
        for i in json.loads((HERE / "golden_set.json").read_text(encoding="utf-8"))["items"]
    }
    judge = make_llm_judge(get_client(), get_settings().judge_model)
    print("| id | figure | original | altered (figure +25 %) |")
    print("|---|---|---|---|")
    for item_id in ("q01", "q07"):
        item = golden[item_id]
        result = run_agent(item["question"], log_query=False)
        tool_output = json.dumps(
            [{"tool": c.name, "input": c.input, "output": c.output} for c in result.tool_calls],
            default=str,
            ensure_ascii=False,
        )
        expected = item["expected_value"]
        wrong = round(expected * 1.25, 2)
        # Replace the figure however it was written (3.96 / 3,96 / 4.0).
        pattern = re.compile(rf"{int(expected)}[.,]\d+")
        altered, n = pattern.subn(f"{wrong}", result.answer)
        if n == 0:
            print(f"| {item_id} | {expected} | figure not found in answer | — |")
            continue
        print(
            f"| {item_id} | {expected} -> {wrong} | {judge(result.answer, tool_output):.2f} "
            f"| {judge(altered, tool_output):.2f} |"
        )


if __name__ == "__main__":
    main()
