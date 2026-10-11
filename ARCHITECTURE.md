# Architecture

## The problem

Three questions must all be answered correctly:

1. "How much has the construction cost index for residential buildings
   risen since January 2024?" This needs exact arithmetic on two rows.
2. "What does Byggkostnadsindex include?" This needs a definition from
   documentation.
3. "The index rose sharply in 2022 — why?" This needs both: the size of
   the rise from data, and the cause from text.

## Why pure RAG fails on question 1

The obvious design embeds everything (methodology pages, news releases,
even the tables rendered as text), retrieves the top chunks and lets the
model answer. That works for question 2 and fails on question 1, silently.

- **The figure usually isn't in any chunk.** The change from January 2024
  to the latest month doesn't appear in any document. SCB's releases quote
  month-on-month and year-on-year changes for the month they cover. Nobody
  published "January 2024 to July 2026".
- **The retriever still finds something.** Chunks that *mention* index
  values rank highly: a release with "steg med 0,6 procent", a table row
  from 2024. The model reads them and composes a confident answer from
  numbers that belong to other periods, or interpolates one.
- **Nothing signals the failure.** The answer has the right shape, uses
  real-looking SCB figures and cites a real SCB URL. No exception, no
  empty result, no low similarity score to warn anyone.
- **Embedding tables as text doesn't fix it.** Turning 11,040 index values
  into chunks makes retrieval worse at finding exact rows than a `where`
  clause is. It also hands the model the arithmetic, which is the step
  most likely to go wrong without anyone noticing.

So the system has two paths that are never merged:

- **Numbers go through `query_price_index`.** It runs parameterised SQL
  over the stored rows. Python computes `first`, `last`,
  `absolute_change` and `percent_change` with `Decimal`, and returns them
  with the rows.
- **Text goes through `search_docs`.** It runs cosine search over chunked
  SCB documents.

The system prompt tells the model to quote the computed values rather
than do its own arithmetic. Every number in an answer can be traced to a
row, and the UI shows that row.

## Routing

Routing is done by the model through tool use, not by a separate
classifier. The tool descriptions in `api/app/agent/descriptions.py` *are*
the routing logic: they say which tool answers which kind of question, and
they list the valid codes for each parameter. The descriptions live in
their own file so they can be rewritten without touching anything else.

The loop (`api/app/agent/loop.py`):

1. Send the question, the system prompt and both tool schemas to Claude.
2. If the reply stops with `tool_use`, validate each call's arguments with
   Pydantic. Run the valid calls. A call with invalid arguments returns
   an `is_error` tool result the model can read and correct, rather than
   raising.
3. Append every result in one user message and repeat, up to 5
   iterations. Past that, the API returns a clear error instead of a
   partial answer.
4. Return `{answer, tool_calls, sources, latency_ms}`. Tool calls, with
   their arguments and outputs, are first-class in the response. The
   frontend renders them as the main evidence, not as debug output.
5. Log the question, the tools called and the latency to `query_log`. A
   failed log write never fails the request.

Hybrid questions need no special case. The model calls both tools,
sometimes in parallel in one turn, and composes the answer.

**The model never writes SQL.** `query_price_index` takes `cost_class`
(an enum of SCB codes), `from_date`, an optional `to_date` and an
optional `building_type` (an enum). The SQL in
`api/app/queries/price_index.py` is fixed and parameterised; nothing the
model produces is ever interpolated into a query string.

## Schema

`sql/001_init.sql` creates five tables:

| Table | Purpose | Key points |
|---|---|---|
| `price_index` | One row per (table, series, month) | `unique (table_id, series_key, period)` is the idempotent upsert key; `series_key` joins the SCB dimension values (`FLERBO\|TOTAL`) |
| `documents` | Clean text of each fetched page or PDF | `content_hash` (SHA-256 of clean text) lets re-runs skip unchanged pages |
| `doc_chunks` | Chunks with `vector(1024)` embeddings | HNSW index with cosine ops; `embedding_model` stored on every row |
| `eval_runs` | One row per evaluation run | git SHA plus the three metrics; `notes` carries the branch for the regression baseline |
| `query_log` | Every question asked in production | tools called (JSONB) and latency |

Row-level security is enabled on all five tables with no policies.
Supabase exposes the `public` schema over its REST API to anyone holding
the anon key. The app connects as the database owner, so RLS closes the
REST path without affecting the app.

## Ingestion

**Prices** (`api/ingest/ingest_prices.py`):
1. `GET` the table metadata and build the query from the dimension codes
   it lists. Nothing is hardcoded; the two tables use different
   `ContentsCode` values.
2. `POST` the query and normalise `2026M07` to `2026-07-01`.
3. Skip missing values (`..`).
4. Upsert with `on conflict … do update`. Running it twice changes
   nothing; an SCB revision updates rows in place.

The client throttles to 10 calls per 10 seconds and retries 429s and 5xx
responses with jittered exponential backoff.

**Documents** (`api/ingest/ingest_docs.py`) cover the product page,
methodology pages, the quality declaration and production description
PDFs, and the monthly news releases since 2021.
- HTML is reduced to the `#pageContent` element, with headings kept as
  markdown headings and the site footer cut.
- PDFs lose their repeated page headers and dotted contents lines, and
  numbered headings become section headings.
- A document is re-embedded only when its clean-text hash changes or it
  has no chunks from the current embedding model.

## Chunking

The target is about **500 tokens with 80 tokens of overlap**, split on
**headings first, paragraphs second**:

1. **Split the text into sections at headings.** A chunk never spans two
   sections, so a chunk about "Byggherrekostnader" doesn't trail into
   "Transporter".
2. **Prefix each chunk with its section heading.** A chunk retrieved on
   its own still says what it is about.
3. **Pack paragraphs into chunks up to the target.** A paragraph larger
   than the budget is split on sentences, then on words.
4. **Overlap stays inside a section.** It is taken from the end of the
   previous chunk so a sentence cut at a boundary is still whole in one
   of the two chunks.
5. **Merge sections under 120 tokens into the next section,** with their
   heading kept as a line of text. Without this, SCB's "Kort information"
   boxes became 12-token chunks that ranked well on keyword overlap and
   carried nothing.

The reasoning behind those numbers:
- **500 tokens** fits one SCB news-release section (a monthly or annual
  analysis) or one numbered subsection of the quality declaration. That
  is the unit someone asking "why" needs.
- **Smaller chunks (about 200 tokens)** split a cause from its effect,
  e.g. "steel rose 75.7 %" landing in a different chunk from "because of
  raw material shortages".
- **Larger chunks (1,000+ tokens)** blend several topics into one vector,
  which lowers similarity for each of them.
- **80 tokens of overlap** is roughly two sentences. That is enough to
  keep a sentence cut at a boundary whole in one of the chunks, without
  duplicating much text.

Token counts are estimated at four characters per token, not computed
with a tokenizer. Chunk sizing does not need to be exact, and a tokenizer
from a different model family would be no more correct for Voyage's
embeddings.

## Rejected alternatives

| Alternative | Why not here | When it would be right |
|---|---|---|
| **Dedicated vector database** (Pinecone, Qdrant, Weaviate) | The corpus is about 300 chunks. pgvector with HNSW returns in milliseconds, and keeping vectors next to `documents` and `price_index` means one database, one backup and transactional re-embedding (delete and insert in one transaction). A second store adds a sync problem and a failure mode for no measurable gain. | Tens of millions of vectors, heavy filtered search across many tenants, or query volume large enough that vector search competes with the transactional workload. |
| **Model-generated SQL** (text-to-SQL over `price_index`) | It would answer more question shapes for free, but every wrong query returns plausible numbers with no error: the same silent failure that rules out pure RAG, moved to a new place. It also needs a read-only role, statement whitelisting and timeouts to be safe on a public endpoint. Two typed parameters cover the questions this data supports. | Many tables, analysts as users, questions that can't be enumerated in advance (joins, aggregations across series), and a human checking the SQL before trusting the result. |
| **Classifier-based routing** (a cheap model or embedding classifier picks numeric/definition/hybrid first) | It adds a stage that can be wrong independently, and the hybrid class still has to call both tools anyway. With two tools, the model's own tool choice is the classifier, and its decision is visible in the response. | Many tools (dozens), strict latency or cost budgets where a small classifier is much cheaper than a large-model turn, or a need to route to different models per class. |
| **Embedding the tables as text** | See "Why pure RAG fails on question 1". | Never as the source of numbers. Possibly as an extra retrieval hint for what series exist. |
| **Agent framework** (LangChain, LlamaIndex) | The loop is about 100 lines. A framework would hide exactly the part that has to be explained and tested: what is sent, what comes back, and when it stops. | Many agents sharing memory, tools and tracing, where the framework's plumbing replaces code you would otherwise write. |
