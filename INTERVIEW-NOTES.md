# Interview notes

For me, not for visitors. Everything here is something I can point to in
the code, the database or a CI run. Where the project is weak, it says so.

---

## The 90-second version (say it, don't read it)

> It's a question-answering agent over SCB's construction cost index. The
> interesting part is that it has to answer two very different kinds of
> question. "How much has the index risen since January 2024" needs exact
> arithmetic on two rows of a monthly table. "What does the index include"
> needs a paragraph from SCB's methodology documents. And "why did it rise
> in 2022" needs both.
>
> The obvious build, embed everything and do RAG, handles the second kind
> and is unreliable on the first. Nobody published "January 2024 to now",
> so the model either finds the inputs scattered in news releases and does
> the arithmetic itself, or it can't answer.
>
> So I split it. Numbers go through a tool that runs fixed, parameterised
> SQL over the 11,000 monthly rows I load from SCB's API, and computes the
> change in Python. Text goes through vector search over about 300 chunks
> of SCB's documents in pgvector. Claude picks the tool through ordinary
> tool use; it never writes SQL and never does the arithmetic. The
> frontend shows every tool call with its arguments, so you can see the
> routing.
>
> I measured it. Against a retrieval-only version of the same agent,
> numeric accuracy goes from 0.67 to 1.0. More interesting: the
> retrieval-only version didn't hallucinate. It either declined or did its
> own arithmetic on rounded published figures. That changed how I'd
> describe the risk.

---

## The core insight, stated sharply

**A number you can audit has to come from a computation you can see, not
from text you retrieved.** Retrieval finds text that *mentions* figures.
It can't produce a figure nobody wrote down, and when the model derives
one, the answer looks the same whether the derivation was right or wrong.
So the system never asks the model to find or compute a number. It asks
the model to choose parameters, and the code produces the number.

The correction my own measurements forced: the failure isn't that the
model invents numbers. With this model, retrieval-only either declined (2
of 6 numeric questions) or derived the figure from rounded inputs it found
(4 of 6, all within tolerance). The real argument is **coverage and
auditability**, not hallucination.

---

## Decisions: what I chose, what I rejected, and when I'd switch

| Decision | Rejected alternative | Why | When I'd switch |
|---|---|---|---|
| Two tools: SQL for numbers, vector search for text | Pure RAG (tables embedded as text) | Most numeric questions ask about spans nobody published. RAG either can't answer or does unauditable arithmetic. | Never for the numbers themselves. |
| Model chooses tools (tool use) | A classifier routes first | With two tools, tool choice *is* the classifier. A separate stage can be wrong on its own, and hybrid questions need both tools anyway. | Dozens of tools, or a hard per-request cost/latency budget where a small classifier is much cheaper than a large-model turn. |
| Fixed, parameterised SQL with typed enums | Text-to-SQL | A wrong generated query returns plausible numbers with no error: the same silent failure, moved. It also needs read-only roles and statement checks on a public endpoint. | Many tables, analyst users, unpredictable joins and aggregations, and a human reviewing the SQL. |
| pgvector in the same Postgres | Pinecone / Qdrant | 290 chunks. One database, one backup, and re-embedding a document is one transaction. A second store is a sync problem. | Tens of millions of vectors, heavy filtered multi-tenant search, or vector load competing with transactions. |
| Chunks ~500 tokens, 80 overlap, heading first | Fixed-size windows | A news-release section ("Utvecklingen det senaste året") is the unit a "why" question needs. Fixed windows split cause from effect. | Very short documents (whole-document embedding) or very long structured ones (hierarchical: section summary plus chunks). |
| Merge sections under 120 tokens forward | One chunk per section | "Kort information" boxes became 12-token chunks that matched keywords and carried nothing. | If the small sections were the actual answers (FAQ-style docs). |
| One pinned embedding model, stored per chunk, filtered at search | Model name only in config | Mixing vector spaces fails silently. Storing and filtering turns a half-migration into fewer hits, not wrong hits. | No reason to drop it. |
| `to_date` optional (= latest month) | Brief's required `to_date` | The model doesn't know which month SCB published last; it would guess. The resolved date comes back in the output and gets cited. | If questions always named both ends. |
| Store SCB codes (`TOTAL`, `FLERBO`), labels in the tool description | Store translated labels | Descriptions can be rewritten without a migration; codes trace back to SCB. | A UI that filters on stored labels directly. |
| Omitted `building_type` returns every series | Default to one type | Silently picking "flerbostadshus" for "residential" hides a choice. Returning both makes the choice visible. | If the extra series blew up the context (see 100× below). |
| English by default, Swedish only for fully Swedish questions | "Answer in the question's language" | The weaker rule failed. Swedish sources plus the word "Byggkostnadsindex" made the model answer English questions in Swedish. | Real multilingual users: detect language explicitly. |
| `claude-opus-5`, effort `medium`, server-side refusal fallback | Smaller model / higher effort | Routing plus short synthesis; numeric questions answer in 3–7 s. The fallback prevents a spurious classifier decline from breaking the demo. | Measured cost pressure: try `claude-sonnet-5` against the same evals first. |
| Judge: `claude-haiku-4-5`, separate call | Same model judges itself | Cheaper, and a different model from the agent. | If the judge's misses (see below) can't be fixed with a stricter rubric. |
| RLS on, no policies | Leave tables open | Supabase exposes `public` over REST with the anon key. The app uses the owner role, so this closes that path at no cost. | Never off. Next step is a least-privilege app role. |
| Rate limit /ask per IP (10/min, in memory) | None | A public endpoint that calls Opus is a free proxy otherwise. | Multiple replicas: move it to Redis or the edge. |

---

## The numbers (all measured, all reproducible)

**Data**
- 11,040 index rows, 24 series, January 1975 to August 2026, from
  `FPIBOM` (residential, 1968=100) and `FPIJBM15` (agricultural,
  2015=100).
- 67 documents, 290 chunks, averaging 343 tokens (min 100, max 498).
- Verified against SCB's own publications: 5 of 5 percentage changes
  match (e.g. December 2021 to December 2022, 15.6 % both ways). The
  base years differ, so I compared changes, not levels. Table in
  NOTES.md.
- Re-running ingest leaves 11,040 rows: the upsert is idempotent, tested
  in CI against real Postgres and confirmed in production.

**Answers**
- Question 1, live: 1848.9 → 1934.2, **+4.61 %**, January 2024 to August
  2026, 4.5 s, one tool call.
- Numeric questions: 3–7 s.
- Definition questions: 12–96 s. The slow end is the Voyage rate limit,
  not the model.

**Evals**
- Hybrid: recall@5 **1.000**, numeric accuracy **1.000**, groundedness
  **1.000**. The scaffold set is too easy, and I say so.
- Retrieval-only baseline: numeric accuracy **0.667**, groundedness
  **0.982**, recall unchanged.
- Gate test (PR #2, every percent ×1.1): numeric accuracy **1.000 →
  0.500**. Job failed, unit tests failed.

**The case where a metric contradicted expectation:**
- **I expected groundedness to punish a wrong figure.** I raised q07's
  headline from 15.63 % to 19.54 %. The judge scored it **1.00** the
  first time. On a re-run it caught it, scoring 0.93, because one wrong
  claim out of 15 only costs 7 points.
- **So the 3-point regression gate cannot see one wrong headline
  number** through groundedness.
- **In the gate test, groundedness stayed at 1.000 while the tool was
  broken.** It measures faithfulness to the tool output, not truth.
- **In the same test, two hybrid questions passed numeric accuracy
  wrongly.** The answer also quoted SCB's published figure from a
  document, and the metric accepts any matching number.

---

## What breaks at 100× data

- **Price rows (about 1.1M) are fine.** The `(cost_class, period)` and
  `(building_type, cost_class, period)` indexes cover the only query
  shapes.
- **Tool output size breaks first.** The tool returns *every row* in the
  range, for *every* matching series when `building_type` is omitted.
  With 100× series, an open-ended question returns thousands of rows into
  the model's context: slower, more expensive, and the judge's 60k-char
  cap starts truncating. Fix: return stats plus a downsampled series, and
  make the tool page.
- **The corpus (about 29k chunks) is fine for HNSW.** Ingest is not. At 3
  embedding requests a minute it would take days, and the news-URL
  guessing (two slug patterns plus a hand list of irregular ones) won't
  scale to more products. Fix: a paid embedding tier or batch API, and
  crawling SCB's release archive instead of guessing URLs.
- **Retrieval quality drops before latency does.** More near-duplicate
  monthly releases compete for the top 5. I'd add metadata filters
  (release month, product) and a reranker before touching the index.

## What breaks at 100 concurrent users

- **The embedding rate limit breaks first.** Voyage without a payment
  method allows 3 requests a minute, and each question makes 1–3. Two
  users in the same minute already queue. Fix: a paid tier, plus caching
  query embeddings (many questions repeat).
- **The threadpool is next.** `/ask` runs the synchronous agent in
  FastAPI's threadpool (40 threads by default), and each request holds a
  thread for 5–90 s. Fix: the async Anthropic client and async psycopg.
- **Anthropic rate limits and cost.** About 2–6 model calls per question
  on Opus. Fix: answer caching keyed on the normalised question plus the
  latest data period; consider Sonnet for routing.
- **Database connections.** The pool is capped at 10 per process; the
  Supabase session pooler caps clients too. Fine for one replica, needs
  planning for several.
- **The per-IP rate limit is per process.** With replicas it stops
  working. Fix: Redis, or the platform edge.
- **The UI has no streaming.** Users stare at "Thinking…" for up to a
  minute. Fix: stream tool calls as they happen. The response already
  makes them first-class, so it's a transport change.

## Honest limits and what is unfinished

- **The golden set is 8 easy questions I wrote.** A 1.000 score is not
  evidence of much. It needs adversarial cases: ambiguous building type,
  base-year confusion, questions the data can't answer, Swedish
  questions, out-of-range dates.
- **Groundedness is weak as specified.** It averages per claim, the judge
  is nondeterministic, it accepts derived arithmetic, and it can't see a
  broken tool. Next step: any unsupported *numeric* claim scores 0.
- **Numeric accuracy is lenient.** "Any number in the answer" let two
  wrong answers pass in the gate test. Next step: require the expected
  figure to match a `query_price_index` result.
- **recall@5 uses the user's question, not the agent's actual queries.**
- **Base-year mixing is a live risk.** News releases quote levels on
  2015=100, `FPIBOM` is 1968=100. A question comparing a document's level
  with a table level would mix bases. Nothing guards against it except
  the prompt saying numbers come from the tool.
- **Corpus maintenance is manual in places.** The PDFs have date-stamped
  URLs that will change next year, and irregular news URLs are a
  hand-maintained list. Missing months are counted but not alerted on.
- **Least privilege isn't done.** The API connects with the database
  owner role through the pooler. It should be a role with `select` on
  the data and `insert` on the logs only.
- **No answer cache, no streaming, no cost tracking, no frontend tests.**
- **Eval runs cost money and minutes** (about 8 agent runs plus 8 judge
  calls). On every PR that's fine for a demo, too much for a busy repo.

---

## Ten questions I should expect

**1. Why not just use RAG?**
RAG can only answer a numeric question if someone already wrote the
number down, and most "since January 2024"-style spans were never
published. When I measured a retrieval-only version, it declined two of
six numeric questions and did its own arithmetic on rounded figures for
the other four. Right within tolerance this time, but you can't tell a
lucky derivation from a wrong one. SQL plus Python arithmetic gives the
same exact number every time, with the rows shown.

**2. How does routing actually work, and what happens if the model picks
the wrong tool?**
Plain tool use: two tool schemas whose descriptions say which questions
each answers, and Claude chooses. Wrong arguments come back as an
`is_error` tool result the model can read and correct, capped at 5
iterations. A wrong *choice* shows up in the eval's "routing ok" column
and, more usefully, in the UI, because every call is printed with its
arguments.

**3. How do you know the numbers are right?**
Two layers. The ingest is checked against SCB's own published releases:
five percentage changes match exactly. The arithmetic is `Decimal` in
Python with unit tests, and the golden set's expected values are computed
from the verified rows. The model's only job on the numeric path is
picking parameters.

**4. Your eval scores are all 1.0. What does that tell you?**
Mostly that the scaffold set is too easy. The informative numbers are the
comparisons: retrieval-only drops numeric accuracy to 0.67, and a
deliberately broken tool drops it to 0.50 and fails the CI gate. I also
found the gate's blind spots that way. Groundedness missed a falsified
figure once, and "any number matches" let two wrong answers pass.

**5. Why pgvector instead of a vector database?**
At 290 chunks, a second datastore adds a sync problem for no measurable
benefit. Keeping vectors next to the documents means re-embedding is
delete-and-insert in one transaction, with one backup. I'd move at tens
of millions of vectors or when vector queries compete with transactional
load.

**6. Why not let the model write SQL? It would answer more questions.**
It would, and every wrong query would return plausible numbers with no
error: the same silent failure I built this to avoid. With one table and
a handful of dimensions, two typed parameters cover the real question
space. I'd revisit with many tables and an analyst who reads the SQL.

**7. What happens when SCB publishes a new month or revises old data?**
A monthly GitHub Action re-runs both ingests. The price upsert is keyed
on `(table_id, series_key, period)`, so new months insert and revisions
update in place. Documents are re-embedded only when the hash of their
cleaned text changes. Expected values in the golden set use fixed
periods, so a new month doesn't fail the gate. A revision to a historical
month would, which is arguably correct.

**8. What breaks first at scale?**
The embedding rate limit (3 requests/minute on the current tier), then
the synchronous threadpool holding a thread for the full agent run. After
that, Anthropic cost and rate limits, which an answer cache keyed on
question plus latest data period would cut. The data size itself is not
the problem; tool output size is, because the tool returns every row in
the range.

**9. What is the weakest part of the project?**
The evaluation. The set is small and easy, groundedness averages away the
one claim that matters, and numeric accuracy accepts any matching number.
I can show each of those with a measurement. The fix is clear: per-claim
minimum for numeric claims, figures traced to tool output, and an
adversarial golden set.

**10. If you had another week, what would you do?**
Rewrite the golden set adversarially and fix the two metric weaknesses
the gate test exposed. Then make the API async and stream tool calls to
the UI, and add an embedding and answer cache. Then a least-privilege
database role and a real crawl of SCB's release archive instead of URL
guessing.

---

## Things to have open during the interview

- The live page, with the three example buttons. Click the hybrid one
  and point at the tool calls.
- `api/app/agent/descriptions.py`: "this text is the router".
- `api/app/queries/price_index.py`: the fixed SQL and `compute_change`.
- EVALS.md: the retrieval-only comparison and the groundedness surprise.
- NOTES.md: the verification table, and the Faktorprisindex URL story.
- PR #2 on GitHub: the gate failing on purpose.
