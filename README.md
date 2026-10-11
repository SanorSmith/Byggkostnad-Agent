# Byggkostnad Agent

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
   python -m evals.run_evals --no-record     # replays the golden set, prints the scores
   ```

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
