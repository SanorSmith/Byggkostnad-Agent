"""Check that groundedness fails an answer with a wrong figure.

Runs the hybrid agent on q01 and q07, raises the expected figure in the
answer by 25 %, and scores the original and the altered answer against the
same tool output. Both layers are reported: the deterministic figure check
and the LLM judge (run three times, since a judge can drift between runs).

    python -m evals.judge_sanity
"""

import json
import re
from pathlib import Path

from app.agent.loop import get_client, run_agent
from app.config import get_settings
from evals.metrics import answer_groundedness, make_llm_judge, unsupported_figures

HERE = Path(__file__).parent
JUDGE_RUNS = 3


def main() -> None:
    golden = {
        i["id"]: i
        for i in json.loads((HERE / "golden_set.json").read_text(encoding="utf-8"))["items"]
    }
    judge = make_llm_judge(get_client(), get_settings().judge_model)
    print(
        "| id | figure | original: groundedness | altered: figure check "
        "| altered: judge alone (3 runs) | altered: groundedness |"
    )
    print("|---|---|---|---|---|---|")
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
        altered, n = re.subn(rf"{int(expected)}[.,]\d+", f"{wrong}", result.answer)
        if n == 0:
            print(f"| {item_id} | {expected} | figure not found in answer | — | — | — |")
            continue
        flagged = unsupported_figures(altered, tool_output)
        judge_scores = ", ".join(f"{judge(altered, tool_output):.2f}" for _ in range(JUDGE_RUNS))
        print(
            f"| {item_id} | {expected} → {wrong} "
            f"| {answer_groundedness(result.answer, tool_output, judge):.2f} "
            f"| {'flags ' + ', '.join(f'{v:g}' for v in flagged) if flagged else 'passes'} "
            f"| {judge_scores} "
            f"| {answer_groundedness(altered, tool_output, judge):.2f} |"
        )


if __name__ == "__main__":
    main()
