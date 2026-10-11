# Notes

A running log of decisions, surprises and assumptions that turned out wrong.
Newest entries are at the bottom of each section.

## Verification: our rows against SCB's own publications (2026-10-11)

First ingest of `FPIBOM` (residential, 1968=100) and `FPIJBM15`
(agricultural, 2015=100): 11,040 rows, 24 series, 1975-01 to 2026-08.

SCB's monthly news releases quote the flerbostadshus index on a **2015=100**
base, while `FPIBOM` is **1968=100**, so index levels cannot be compared
directly. Percentage changes are base-independent, so those are what I
checked. Our figures are computed from our parsed rows with the same
`compute_change` function the agent uses.

| Check (flerbostadshus, total) | Our rows (FPIBOM) | SCB published | Source |
|---|---|---|---|
| Feb → Mar 2022 | 1.5 % | 1,5 % | statistiknyhet mars 2022 |
| Mar 2021 → Mar 2022 | 9.6 % | 9,6 % | statistiknyhet mars 2022 |
| Nov → Dec 2022 | 0.4 % | 0,4 % | statistiknyhet december 2022 |
| Dec 2021 → Dec 2022 | 15.6 % | 15,6 % | statistiknyhet december 2022 |
| Jul → Aug 2026 | 0.6 % (1922.1 → 1934.2) | 0,6 % (155,3 → 156,3, 2015=100) | statistiknyhet augusti 2026 and the "Faktorprisindex för flerbostadshus" table on scb.se |

Transport, fuel and electricity, Mar 2021 → Mar 2022: our rows give 26.72 %,
SCB's release says 26,7 %.

Five stored rows used as anchors in the golden set:

| table | building type | cost class | period | value |
|---|---|---|---|---|
| FPIBOM | FLERBO | TOTAL | 2024-01 | 1848.9 |
| FPIBOM | FLERBO | TOTAL | 2026-07 | 1922.1 |
| FPIBOM | GRUPPSMÅ | TOTAL | 2022-12 | 1645.2 |
| FPIBOM | FLERBO | MATERIAL | 2022-03 | 2589.1 |
| FPIJBM15 | JORDBRUK | TOTAL | 2024-01 | 155.9 |

Everything agrees, so I kept building.

## SCB API

- **The v1 API answers as the brief described.** `GET` on a table returns
  metadata and `POST` with a query returns data. The dimensions are `Hustyp`,
  `Kostnadsslag`, `ContentsCode` and `Tid`.
- **The two tables use different `ContentsCode` values:** `PR0502A3` for
  `FPIBOM` and `0000020J` for `FPIJBM15`. Hardcoding the first and reusing it
  for the second would have broken the second table. The query is built
  from each table's metadata instead.
- **`FPIJBM15` has no `Hustyp` dimension.** Its rows get
  `building_type = 'JORDBRUK'` so a single `building_type` filter works
  across both tables. The `series_key` is still built from real dimension
  values only (`TOTAL`, not `JORDBRUK|TOTAL`).
- **Missing values come back as `".."`, not null.** They are skipped
  rather than stored as zero. A zero would be the worst failure here: it
  is a plausible-looking number that silently corrupts a percent change.
- **I expected a UTF-8 BOM on the JSON responses and checked: there
  isn't one.** The decoder uses `utf-8-sig`, which reads plain UTF-8 the
  same way, so it costs nothing.
- **The tables have been renamed.** They are titled "Byggkostnadsindex …
  exkl. löneglidning och moms", but the news releases say the product was
  previously called *Faktorprisindex*. The documents use both names, so
  retrieval has to cope with both.
- **`source_url` holds the human-readable Statistikdatabasen page**
  (`statistikdatabasen.scb.se/goto/sv/ssd/<table>`), not the API URL. A
  citation should be something a person can click. The API URL is
  derivable from config.

## Document corpus

- **News-release URLs are irregular.** Examples:
  `byggkostnadsindex-for-byggnader-februri-2026`,
  `byggkostnadsindex-for-byggnader-maj-20252`, and there is no `juni`
  release in 2022 or 2023. The ingest generates candidates
  (`<month>-<year>`, 2021 to now), and 404s are skipped and counted. This
  means some months are silently absent from the corpus. A crawl of the
  news archive would fix that; I chose not to build one yet.
- **The first extraction pass kept the site chrome.** The footer ("Missa
  inte viktig statistik", "Prenumerera på statistiknyheter") became its own
  chunk on every news page. That would have added about 70 near-identical
  chunks to every search. Extraction now stops at those headings.
- **SCB's PDFs repeat a page header on every page and include a dotted
  table of contents.** Stripping both shrank the quality declaration from
  34.7k to 27.3k characters. Numbered headings (`2.1 Målstorheter`) are
  turned into section headings so the heading-first chunker can use them.
- **Tiny sections produced 12–40-token chunks.** The first chunker emitted
  one chunk per section, so "Kort information" became a 12-token chunk.
  Sections under 120 tokens are now merged into the next section.
- **The quality declaration and production description PDFs have
  date-stamped URLs** (`pr0502_kd_2026_260216.pdf`). Next year's versions
  will have new URLs and need adding by hand.
- **The corpus is in Swedish but the demo questions are in English.**
  voyage-3 is multilingual, and the tool description also tells the model
  that Swedish search terms work better.

## Agent and model

- **Default model is `claude-opus-5`, pinned in config and overridable
  with `ANTHROPIC_MODEL`.** Effort is `medium`, since the task is routing
  plus short synthesis, not deep reasoning. The judge is
  `claude-haiku-4-5`.
- **Requests opt into the server-side refusal fallback**
  (`fallbacks="default"`), so a classifier decline on a harmless
  statistics question is retried on another model instead of failing the
  demo.
- **`to_date` is optional in `query_price_index`, although the brief's
  signature has it required.** Question 1 says "since January 2024", and
  the model cannot know which month SCB published last. Without this, it
  would either guess a date or need a separate "latest period" tool.
  Omitted means "latest available month", and the resolved date is
  returned in `query.to_date` so the answer can cite it.
- **`cost_class` and `building_type` hold SCB's codes** (`TOTAL`,
  `FLERBO`, …), not translated labels. The labels live in the tool
  description, so the description can be rewritten without touching
  stored data.
- **Calling `query_price_index` without `building_type` returns every
  matching series,** each with its own computed change. Otherwise
  "residential" would be silently resolved to one building type.

## Evaluation

- **Golden-set questions use fixed periods** ("January 2024 to July
  2026"), not "since January 2024". Otherwise the expected value would
  change every month and the regression gate would fire on new data
  rather than on code.
- **`tolerance_pct` is relative to `expected_value`.** For an answer that
  is itself a percentage (3.96 %), 2 % relative tolerance accepts "4.0 %"
  but not "4.5 %".
- **Numeric accuracy passes if *any* figure in the answer is within
  tolerance.** Answers quote first, last and percent change together, so
  insisting on one "main" figure would need a second LLM call to pick it.
  The cost: an answer that lists many numbers is easier to pass. EVALS.md
  says this.

## First live ingest (2026-10-11)

- **Voyage returned 429 after three documents.** On the tier with no
  payment method, Voyage allows roughly 3 requests and 10k tokens per
  minute. The first retry policy (5 attempts, at most 30 s apart) gave up
  in under two minutes. Fixes:
  - a client-side requests-per-minute cap (`VOYAGE_RPM`, default 3);
  - batches capped by estimated tokens;
  - backoff up to 65 s;
  - one failed document no longer aborts the run. The exit code still
    reports it, so CI sees it.
- **A token estimate that is fine for chunk sizing was wrong for quota
  maths.** The production-description PDF kept failing even with
  retries. Its 8,000-token batch (by the 4 chars/token estimate) was over
  10k tokens by Voyage's own count. Swedish text with long compounds and
  table fragments tokenises denser than English. No amount of waiting
  helps a request that exceeds the per-minute quota on its own. The batch
  cap is now 4,000 estimated tokens.
- **Every 2021 news release returned 404.** Until 2022 the index was
  called *Faktorprisindex*, and those releases keep the old name in their
  URL (`faktorprisindex-for-byggnader-mars-2021`). Ingest now tries both
  slugs for every month. Without this fix the corpus held nothing from
  before 2022, so questions about what led up to the 2022 rise had no
  sources.
- **Three releases have URLs no pattern would generate:**
  `maj-20252`, `februri-2026`, and `august-2026` (English month name).
  They are listed explicitly in `IRREGULAR_NEWS_SLUGS`. June never has a
  release. The final corpus is 67 documents and 290 chunks, averaging 343
  tokens (min 100, max 498).
