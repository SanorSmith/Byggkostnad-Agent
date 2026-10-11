# Byggkostnad Agent

**Live demo:** https://byggkostnad-agent.vercel.app · **API:** https://api-production-6fea9.up.railway.app/docs

A question-answering agent over Swedish construction cost statistics from
Statistics Sweden (SCB). It answers three kinds of question:

| Kind | Example | How it is answered |
|---|---|---|
| Numeric | "How much has the construction cost index for residential buildings risen since January 2024?" | Parameterised SQL over the exact monthly rows; the change is computed in Python |
| Definition | "What does Byggkostnadsindex include?" | Vector search over SCB's methodology pages and statistical news |
| Hybrid | "The index rose sharply in 2022 — why?" | Both: the numbers from SQL, the explanation from the documents |

The rule the design rests on: **numbers are computed, never retrieved.** A
retriever can find a paragraph that mentions a figure, but it cannot tell
you the index moved 3.96 % between two months that no paragraph mentions.
A model asked to answer anyway will produce a plausible figure, and nothing
reports an error. So numeric questions never go through retrieval, and the
model never writes SQL or does arithmetic. It picks a tool and supplies
typed parameters.

## Architecture

```
                        user question
                              │
                    Claude API (tool use)
                    ╱                   ╲
      query_price_index              search_docs
      parameterised SQL              pgvector cosine
            │                              │
      price_index table              doc_chunks table
            ╲                             ╱
                  answer + citations
                          │
                     query_log
```

- **api/**: FastAPI service with the agent loop, the two tools, ingestion
  scripts and the evaluation harness. It is deployed to Railway.
- **web/**: a single Next.js page. It shows the answer plus every tool call
  with its real arguments, the returned rows with a chart, and the
  retrieved chunks with their similarity scores. It is deployed to Vercel.
- **sql/001_init.sql**: the schema. It runs on Supabase Postgres with
  pgvector.

ARCHITECTURE.md explains the design decisions, EVALS.md covers how
quality is measured, and NOTES.md records what turned out differently
from expected.

## Stack

| Layer | Choice |
|---|---|
| Model | Claude (`claude-opus-5` default, pinned in `api/app/config.py`), manual tool-use loop |
| Embeddings | Voyage `voyage-3`, 1024 dimensions, pinned |
| Database | Supabase Postgres + pgvector (HNSW index, cosine distance) |
| API | Python 3.11, FastAPI, psycopg 3 |
| Frontend | Next.js (app router), no UI or chart libraries |
| CI/CD | GitHub Actions: lint/type/test, monthly ingest, eval regression gate |
| Hosting | Railway (API), Vercel (web), Supabase (database) |

## Run it locally

You need Python 3.11+, Node 20+, a Supabase project (the free tier is
enough), an Anthropic API key and a Voyage AI API key.

1. **Clone the repository.**

   ```bash
   git clone https://github.com/SanorSmith/Byggkostnad-Agent.git
   cd Byggkostnad-Agent
   ```

2. **Create the schema.** In the Supabase dashboard open SQL Editor and
   run `sql/001_init.sql`. If you have `psql`, this does the same:

   ```bash
   psql "$DATABASE_URL" -f sql/001_init.sql
   ```

3. **Configure the API.**

   ```bash
   cd api
   cp .env.example .env      # then fill in DATABASE_URL, ANTHROPIC_API_KEY, VOYAGE_API_KEY
   python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -e ".[dev]"
   ```

   For `DATABASE_URL`, use the Supabase **pooler** connection string
   (Connect → Session pooler). The direct connection is IPv6-only, and
   many hosts cannot reach it.

4. **Load the data.** Run both ingest scripts. The first takes about ten
   seconds; the second fetches about 70 pages from scb.se, throttled to
   one request per second, and embeds them.

   ```bash
   python -m ingest.ingest_prices --verify   # SCB tables -> price_index, prints anchor rows
   python -m ingest.ingest_docs              # SCB pages -> documents + doc_chunks
   ```

5. **Start the API.**

   ```bash
   uvicorn app.main:app --reload             # http://localhost:8000/docs
   ```

6. **Start the web app** in a second terminal.

   ```bash
   cd web
   cp .env.example .env.local                # NEXT_PUBLIC_API_URL=http://localhost:8000
   npm install
   npm run dev                               # http://localhost:3000
   ```

7. **Run the checks and the evaluation.**

   ```bash
   cd api
   ruff check . && mypy app ingest evals tests && pytest -q
   python -m ingest.verify_against_scb       # stored data vs SCB's published figures
   python -m evals.run_evals --no-record     # replays the golden set, prints the scores
   ```

## Tests and results

Everything below was run against the deployed system on 2026-10-11. The
full outputs are committed in [`docs/test-results/`](docs/test-results/),
so every number here can be checked.

### 1. Unit tests: 30 of 30 passed

These run on every push in [CI](.github/workflows/ci.yml), together with
ruff and mypy (strict), against a real Postgres with pgvector. The full
list is in [unit-tests.md](docs/test-results/unit-tests.md).

| Test file | What it proves | Tests | Result |
|---|---|---|---|
| `test_periods.py` | SCB periods like `2026M07` become dates; bad periods are rejected | 11 | passed |
| `test_scb_parse.py` | Queries are built from SCB's metadata; missing values are skipped, never stored as 0 | 3 | passed |
| `test_change.py` | Percent-change arithmetic, including rounding, negative changes and a zero base | 5 | passed |
| `test_upsert.py` | Loading the same data twice changes nothing; a revised value updates in place | 1 | passed |
| `test_chunk.py` | Chunks never cross a heading, stay under the size limit, and overlap | 5 | passed |
| `test_metrics.py` | The evaluation metrics: number parsing (Swedish and English), tolerance, recall, averaging | 5 | passed |

### 2. Our data against SCB's own published figures: 6 of 6 match

SCB's news releases quote the index on a different base year (2015=100)
than the table we load (1968=100), so percentage changes are compared,
since they don't depend on the base. `python -m ingest.verify_against_scb`
does this and runs after every monthly data refresh. Full table:
[scb-verification.md](docs/test-results/scb-verification.md).

| Check (multi-dwelling buildings) | Our rows | Our change | SCB published |
|---|---|---|---|
| Feb → Mar 2022 | 1545.5 → 1568.0 | 1.5 % | 1,5 % |
| Mar 2021 → Mar 2022 | 1430.9 → 1568.0 | 9.6 % | 9,6 % |
| Nov → Dec 2022 | 1737.7 → 1744.8 | 0.4 % | 0,4 % |
| Dec 2021 → Dec 2022 | 1508.9 → 1744.8 | 15.6 % | 15,6 % |
| Jul → Aug 2026 | 1922.1 → 1934.2 | 0.6 % | 0,6 % |
| Transport, fuel and electricity, Mar 2021 → Mar 2022 | 2194.5 → 2780.8 | 26.7 % | 26,7 % |

### 3. Answer quality: the evaluation

Eight questions (4 numeric, 2 definition, 2 hybrid) are answered end to
end and scored. Details are in [EVALS.md](EVALS.md); every answer is in
[eval-hybrid.json](docs/test-results/eval-hybrid.json).

| Metric | What it measures | Score |
|---|---|---|
| recall@5 | Does search find the right SCB document in the top 5? | 1.000 |
| numeric accuracy | Is the right figure in the answer (within tolerance)? | 1.000 |
| groundedness | Is every claim supported by what the tools returned? (judged by Claude Haiku) | 1.000 |

A perfect score on eight questions I wrote is weak evidence on its own,
so I ran three experiments to test the design and the tests themselves.

**Experiment A: is the hybrid design actually better than plain RAG?**
Same questions, but the agent may only search documents
([eval-rag-only.md](docs/test-results/eval-rag-only.md)).

| Metric | Plain RAG | This design |
|---|---|---|
| numeric accuracy | 0.667 | **1.000** |
| groundedness | 0.982 | 1.000 |

Plain RAG declined 2 of 6 number questions. On the other 4 it found
rounded figures in SCB's news releases and did the arithmetic itself.

**Experiment B: does the CI gate stop a bad change?** Pull request
[#2](https://github.com/SanorSmith/Byggkostnad-Agent/pull/2) deliberately
inflated every percentage by 10 %. Numeric accuracy fell from 1.000 to
0.500, and both the eval gate and the unit tests failed it
([regression-gate-pr2.md](docs/test-results/regression-gate-pr2.md)).

**Experiment C: can the AI judge spot a wrong number?** I changed one
figure in a correct answer by 25 %. The judge caught it in one case
(1.00 → 0.71), missed it completely in another, and caught it on a
re-run (1.00 → 0.93) ([judge-sanity.md](docs/test-results/judge-sanity.md)).

### 4. Problems found, how they were found, and how they were fixed

| # | Problem | How it was found | Fix | Commit |
|---|---|---|---|---|
| 1 | The two SCB tables use different internal codes; hardcoding one would break the other | Read SCB's live metadata before writing the loader | Query codes are read from each table's metadata | `4bd623d` |
| 2 | SCB marks missing values as `..`; storing them as 0 would corrupt percentages | Inspected a live data response | Missing values are skipped (unit-tested) | `4bd623d` |
| 3 | The website footer ("Subscribe…") was becoming its own search chunk on every page | Printed the extracted text of a news page | Extraction stops at the footer headings | `4bd623d` |
| 4 | PDFs repeated a page header on every page, plus a dotted contents list | Printed the extracted PDF text (34.7k characters, 27.3k after cleaning) | Header and contents lines removed; numbered headings kept | `4bd623d` |
| 5 | Tiny 12-token chunks that matched keywords but carried nothing | Printed chunk sizes per page | Sections under 120 tokens merge into the next one | `4bd623d` |
| 6 | The embedding service (Voyage) refused requests after 3 documents (HTTP 429) | First live data load stopped with errors | Paced requests, smaller batches, longer retries; one bad page no longer stops the run | `5899d43` |
| 7 | One PDF could never load: the token estimate undercounts Swedish text | It kept failing even with retries | Batch size halved | `070fe2b` |
| 8 | Every 2021 news release returned 404 | The load reported 12 "missing" months in a row | Pre-2022 pages use the old name *Faktorprisindex*; both names are tried | `070fe2b` |
| 9 | Three releases have misspelled URLs (`februri`, `maj-20252`, `august`) | Missing-month list compared with scb.se | Listed explicitly | `9e37267` |
| 10 | English questions were answered in Swedish | Read the answers of the first end-to-end run | English by default; Swedish only for Swedish questions | `6e148eb` |
| 11 | A question took 72 seconds | Timed the first runs | My own rate limiter was also slowing users' searches; it now applies to data loading only | `6e148eb` |
| 12 | The AI judge can miss a wrong number, and averaging hides one wrong figure | Experiment C | **Open.** Documented in EVALS.md with the proposed fix | — |
| 13 | Numeric accuracy accepts *any* matching number, so a correct figure quoted from a document hid a wrong computed one | Experiment B (two hybrid questions passed wrongly) | **Open.** Documented in EVALS.md with the proposed fix | — |
| 14 | The free Voyage tier allows 3 requests a minute, too low for several visitors at once | Definition questions took up to 96 s | **Open.** Needs a payment method on the Voyage account | — |

Problems 1–5 were caught while building, before the first commit of that
code. 6–11 were found and fixed during the first live runs. 12–14 are
known and still open.

## Changing the embedding model

The embedding model and its dimension are pinned in `api/app/config.py`.
The dimension is also fixed in the schema (`vector(1024)`).

**Changing the model means re-embedding every stored chunk.** Vectors from
two different models live in unrelated spaces, so cosine similarity
between them is meaningless. Search still returns results and still
reports similarity scores; nothing raises an error. That is why mixing
models silently degrades retrieval rather than failing loudly.

Two safeguards exist:
- The config refuses to start if the model and dimension disagree.
- Every chunk stores its `embedding_model`, and search only reads chunks
  from the current model. A half-migrated corpus therefore returns fewer
  hits, never wrong ones.

To switch models:

1. Change `EMBEDDING_MODEL` and `EMBEDDING_DIM` in the environment.
2. Change `vector(1024)` in the schema to match.
3. Run `python -m ingest.ingest_docs --force` (or the `ingest` workflow
   with `force_reembed`).

## API

| Method | Path | Returns |
|---|---|---|
| POST | `/ask` | `{answer, tool_calls[], sources[], latency_ms, error}`. `tool_calls` includes each call's arguments and output |
| GET | `/examples` | The three demo questions, one per routing path |
| GET | `/eval/latest` | The most recent evaluation run (preferring runs on `main`) |
| GET | `/health` | Service and database status |

`/ask` is rate-limited per IP: 10 questions per minute by default.

## Data

- Construction cost index from [SCB](https://www.scb.se/pr0502), PxWebApi
  v1, subject area PR0502:
  - `FPIBOM`: residential, monthly, 1968=100
  - `FPIJBM15`: agricultural buildings, monthly, 2015=100
- The text corpus is SCB's product page, methodology pages, the 2026
  quality declaration and production description, and the monthly
  statistical news releases from 2021 onward.
