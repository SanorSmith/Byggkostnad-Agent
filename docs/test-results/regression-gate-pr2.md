# Regression gate test (PR #2, closed without merging)

PR [#2](https://github.com/SanorSmith/Byggkostnad-Agent/pull/2) multiplied every computed percent change by 1.1. The evals job compared it with the `main` baseline and failed; the unit tests failed too. This is the comment the workflow posted:

#### Eval results for 3b6f544

| id | type | tools called | routing ok | numeric ok | grounded | latency |
|---|---|---|---|---|---|---|
| q01 | numeric | query_price_index | yes | **no** | 1.00 | 7330 ms |
| q02 | numeric | query_price_index | yes | yes | 1.00 | 3104 ms |
| q03 | numeric | query_price_index | yes | **no** | 1.00 | 5641 ms |
| q04 | numeric | query_price_index | yes | **no** | 1.00 | 3569 ms |
| q05 | definition | search_docs, search_docs | yes | — | 1.00 | 12893 ms |
| q06 | definition | search_docs, search_docs | yes | — | 1.00 | 92366 ms |
| q07 | hybrid | query_price_index, query_price_index, search_docs, search_docs, query_price_index, query_price_index | yes | yes | 1.00 | 22665 ms |
| q08 | hybrid | query_price_index, search_docs, search_docs, search_docs, search_docs | yes | yes | 1.00 | 104499 ms |

| metric | this run | main baseline | delta |
|---|---|---|---|
| recall_at_5 | 1.000 | 1.000 | +0.000 |
| numeric_accuracy | 0.500 | 1.000 | -0.500 |
| groundedness | 1.000 | 1.000 | +0.000 |

**Regression > 3 pp in: numeric_accuracy**
