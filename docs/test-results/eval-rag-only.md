# Evaluation: retrieval-only baseline (the rejected design)

`python -m evals.run_evals --baseline rag-only`, 2026-10-11. Same questions, corpus and model; the agent gets only `search_docs` and a plain "answer from the documents" prompt. "routing ok" is **no** for numeric questions by construction (the price tool is withheld). Full answers: [eval-rag-only.json](eval-rag-only.json).

| id | type | tools called | routing ok | numeric ok | grounded | latency |
|---|---|---|---|---|---|---|
| q01 | numeric | search_docs, search_docs | **no** | yes | 1.00 | 12658 ms |
| q02 | numeric | search_docs, search_docs | **no** | **no** | 0.86 | 93372 ms |
| q03 | numeric | search_docs, search_docs, search_docs, search_docs | **no** | yes | 1.00 | 79463 ms |
| q04 | numeric | search_docs, search_docs, search_docs | **no** | **no** | 1.00 | 56762 ms |
| q05 | definition | search_docs, search_docs | yes | — | 1.00 | 70366 ms |
| q06 | definition | search_docs, search_docs, search_docs | yes | — | 1.00 | 52131 ms |
| q07 | hybrid | search_docs, search_docs | **no** | yes | 1.00 | 16119 ms |
| q08 | hybrid | search_docs, search_docs | **no** | yes | 1.00 | 65347 ms |
| metric | this run | main baseline | delta |
|---|---|---|---|
| recall_at_5 | 1.000 | — | — |
| numeric_accuracy | 0.667 | — | — |
| groundedness | 0.982 | — | — |
