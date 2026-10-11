# Test results

Outputs from the test and evaluation runs on 2026-10-11. The summary is in
the main [README](../../README.md#tests-and-results).

| File | What it contains | How to reproduce |
|---|---|---|
| [unit-tests.md](unit-tests.md) | All 30 unit tests and their results from CI | `cd api && pytest -v` |
| [scb-verification.md](scb-verification.md) | Stored data compared with SCB's published figures (6 of 6 match) | `python -m ingest.verify_against_scb` |
| [eval-hybrid.md](eval-hybrid.md) | Evaluation of the shipped system | `python -m evals.run_evals --no-record` |
| [eval-hybrid.json](eval-hybrid.json) | Every answer and tool call from that run | same |
| [eval-rag-only.md](eval-rag-only.md) | The same questions with document search only | `python -m evals.run_evals --baseline rag-only` |
| [eval-rag-only.json](eval-rag-only.json) | Every answer from that run | same |
| [regression-gate-pr2.md](regression-gate-pr2.md) | The CI gate failing a deliberately broken change | open a PR; the evals workflow runs |
| [judge-sanity.md](judge-sanity.md) | Whether the AI judge notices a wrong figure | `python -m evals.judge_sanity` |
