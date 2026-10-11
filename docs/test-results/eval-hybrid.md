# Evaluation: hybrid design (the shipped system)

`python -m evals.run_evals --no-record`, 2026-10-11, `claude-opus-5` (effort medium), judge `claude-haiku-4-5`. Full answers and tool calls: [eval-hybrid.json](eval-hybrid.json).

| id | type | tools called | routing ok | numeric ok | grounded | latency |
|---|---|---|---|---|---|---|
| q01 | numeric | query_price_index | yes | yes | 1.00 | 4538 ms |
| q02 | numeric | query_price_index | yes | yes | 1.00 | 2976 ms |
| q03 | numeric | query_price_index | yes | yes | 1.00 | 5302 ms |
| q04 | numeric | query_price_index | yes | yes | 1.00 | 3592 ms |
| q05 | definition | search_docs, search_docs | yes | — | 1.00 | 11878 ms |
| q06 | definition | search_docs, search_docs | yes | — | 1.00 | 91255 ms |
| q07 | hybrid | query_price_index, query_price_index, search_docs, query_price_index, query_price_index, search_docs | yes | yes | 1.00 | 15496 ms |
| q08 | hybrid | query_price_index, search_docs | yes | yes | 1.00 | 45055 ms |
| metric | this run | main baseline | delta |
|---|---|---|---|
| recall_at_5 | 1.000 | — | — |
| numeric_accuracy | 1.000 | — | — |
| groundedness | 1.000 | — | — |
