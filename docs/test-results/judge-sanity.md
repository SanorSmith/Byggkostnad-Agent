# Can the groundedness judge fail a wrong answer?

`python -m evals.judge_sanity`: the hybrid answer's main figure is raised by 25 % and both versions are judged against the same tool output.

| question | figure | original | altered |
|---|---|---|---|
| q01 | 3.96 → 4.95 | 1.00 | 0.71 |
| q07 | 15.63 → 19.54 | 1.00 | **1.00** (first run: missed) |
| q07 | 15.63 → 19.54 | 1.00 | 0.93 (re-run: 14 of 15 claims supported) |

The judge is not deterministic, and per-claim averaging means one wrong headline figure costs little. See EVALS.md.
