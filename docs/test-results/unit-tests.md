# Unit tests

From CI run [38153606734](https://github.com/SanorSmith/Byggkostnad-Agent/actions/runs/38153606734) on commit `67778f4` (`pytest -v`, Python 3.11, Postgres 16 with pgvector as a service container).

**Result: 30 passed, 0 failed.** Ruff lint, ruff format and mypy (strict) also passed in the same run.

## `api/tests/test_change.py`

Percent-change arithmetic, including rounding, negative changes and a zero base

| test | result |
|---|---|
| `test_percent_change_matches_scb_figure` | passed |
| `test_negative_change` | passed |
| `test_rounds_half_up` | passed |
| `test_single_value_and_empty` | passed |
| `test_zero_base_has_no_percent` | passed |

## `api/tests/test_chunk.py`

Chunks never cross a heading, stay under the size limit, overlap, and small sections merge forward

| test | result |
|---|---|
| `test_sections_split_on_headings` | passed |
| `test_chunks_do_not_cross_headings` | passed |
| `test_long_section_chunks_are_bounded_and_overlap` | passed |
| `test_small_sections_merge_forward` | passed |
| `test_estimate_tokens` | passed |

## `api/tests/test_metrics.py`

Number parsing in Swedish and English formats, numeric tolerance, recall@5 and groundedness averaging

| test | result |
|---|---|
| `test_parse_numbers_swedish_and_english` | passed |
| `test_numeric_correct_tolerance` | passed |
| `test_numeric_accuracy_counts_numeric_and_hybrid` | passed |
| `test_recall_at_5_matches_url_or_text` | passed |
| `test_groundedness_average` | passed |

## `api/tests/test_periods.py`

SCB period strings (`2026M07`) become the first day of the month; bad periods are rejected

| test | result |
|---|---|
| `test_normalize_period[2026M07-expected0]` | passed |
| `test_normalize_period[1975M01-expected1]` | passed |
| `test_normalize_period[2024M12-expected2]` | passed |
| `test_normalize_period[ 2022M03 -expected3]` | passed |
| `test_normalize_period_rejects[2026M13]` | passed |
| `test_normalize_period_rejects[2026M00]` | passed |
| `test_normalize_period_rejects[2026K1]` | passed |
| `test_normalize_period_rejects[2026]` | passed |
| `test_normalize_period_rejects[202607]` | passed |
| `test_normalize_period_rejects[]` | passed |
| `test_base_year_from_title` | passed |

## `api/tests/test_scb_parse.py`

The SCB query is built from table metadata; missing values (`..`) are skipped; series keys and building types

| test | result |
|---|---|
| `test_query_uses_codes_from_metadata` | passed |
| `test_parse_rows_skips_missing_and_builds_series_key` | passed |
| `test_default_building_type_when_no_hustyp` | passed |

## `api/tests/test_upsert.py`

Loading the same rows twice changes nothing; a revised value updates in place (real Postgres in CI)

| test | result |
|---|---|
| `test_upsert_is_idempotent` | passed |
