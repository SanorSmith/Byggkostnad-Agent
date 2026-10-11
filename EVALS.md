# Evaluation

The golden set (`api/evals/golden_set.json`) is replayed end to end through
the same `run_agent` the API uses. The runner (`api/evals/run_evals.py`)
scores three metrics, prints a table and records a row in `eval_runs`
with the git SHA. In CI (`.github/workflows/evals.yml`) it runs on every
pull request and on manual dispatch. It compares against the latest run
recorded on `main` and **fails if any metric drops by more than 3
percentage points**.

```bash
cd api
python -m evals.run_evals                      # run and record
python -m evals.run_evals --compare            # also apply the regression gate
python -m evals.run_evals --baseline rag-only  # retrieval-only comparison, never recorded
python -m evals.judge_sanity                   # can the judge fail a wrong answer?
```

## The golden set

There are 8 questions: 4 numeric, 2 definition, 2 hybrid. Expected values
are computed from the stored SCB rows, which were checked against SCB's
published releases (see NOTES.md).
- **Questions name fixed periods** ("January 2024 to July 2026"), so the
  expected values don't move when SCB publishes a new month.
- **The set is a scaffold** (marked `TODO — Sanor rewrites this`). It is
  too easy, as the scores below show.

## Metrics

### recall@5 (definition and hybrid questions)

**What it measures:** whether retrieval surfaces the right source at all.

**How it's computed:**
- Run `search_docs(question, k=5)` directly on the question text.
- A question counts as a hit if any of the five chunks has
  `expected_source_contains` in its `source_url` or text, matched
  case-insensitively. The needles are URL fragments like `december-2022`
  or Swedish terms like `byggherrekostnader`.
- The score is hits divided by questions.

**Limitation:** this measures retrieval on the user's own wording, not on
the queries the agent actually sends. The agent usually rewrites the
query into Swedish, so recall@5 is a lower bound on what the agent sees.

### numeric_accuracy (numeric and hybrid questions)

**What it measures:** whether the answer contains the right figure.

**How it's computed:**
- Parse every number in the answer, accepting `3,96`, `1 848,9`,
  `1,848.9` and `−0,5`.
- The question passes if *any* parsed number is within `tolerance_pct`
  (relative) of `expected_value`. An answer with no number fails.

**Limitation:** "any number" is lenient. An answer listing many figures
has more chances to hit. It was chosen because answers quote first, last
and percent change together, and picking the "main" figure would need
another model call.

### groundedness (all questions)

**What it measures:** whether each claim in the answer is supported by
what the tools returned.

**How it's computed:**
- Separately from the agent, call `claude-haiku-4-5` with a fixed prompt
  (`JUDGE_PROMPT` in `metrics.py`), the exact JSON tool output, and the
  answer.
- Structured output forces a list of `{claim, supported}`.
- An answer's score is supported claims divided by all claims, and the
  metric is the mean across answers.
- An answer with no tool calls scores 0. An answer with no factual claims
  scores 1.

**Judge model:** `claude-haiku-4-5`, configurable as `JUDGE_MODEL`, and
deliberately cheaper than the agent model (`claude-opus-5`).

## Current scores

Recorded run on `main`, 2026-10-11, `claude-opus-5` at effort `medium`:

| metric | score |
|---|---|
| recall@5 | 1.000 (4/4) |
| numeric_accuracy | 1.000 (6/6) |
| groundedness | 1.000 |

Per question:

| id | type | tools called | latency |
|---|---|---|---|
| q01 | numeric | query_price_index | 5.3 s |
| q02 | numeric | query_price_index | 3.0 s |
| q03 | numeric | query_price_index | 3.5 s |
| q04 | numeric | query_price_index | 3.4 s |
| q05 | definition | search_docs ×2 | 12.6 s |
| q06 | definition | search_docs ×3, query_price_index | 95.8 s |
| q07 | hybrid | query_price_index ×4, search_docs ×2 | 54.2 s |
| q08 | hybrid | query_price_index, search_docs | 7.3 s |

The slow rows are not the model. They are Voyage's rate limit (3
requests per minute on the tier without a payment method), which the
query embeddings hit after several searches in the same minute.

A perfect score on a set its author wrote is weak evidence. The two
experiments below are what the numbers actually show.

## Before and after: pure RAG versus the hybrid design

Same 8 questions, same corpus and model. The only differences: the agent
gets only `search_docs`, and a plain "answer from the documents" prompt
(`--baseline rag-only`).

| metric | pure RAG | hybrid | change |
|---|---|---|---|
| recall@5 | 1.000 | 1.000 | 0 |
| numeric_accuracy | **0.667** | **1.000** | **+33 pp** |
| groundedness | 0.982 | 1.000 | +2 pp |

The move in numeric accuracy is what the architecture predicts. *How*
pure RAG failed is not, and it's the more useful finding:

- **q02 (group-built houses, December 2022) and q04 (agricultural
  buildings 2020–2025): pure RAG declined.** "I couldn't find that
  specific number in the documents available to me." It did not invent a
  figure. The current model fails safe when the figure is absent.
- **q01 (+3.96 %): pure RAG answered 3.95 % and was scored correct.** Two
  news releases happen to quote the index *level* on the 2015=100 base
  (149.4 and 155.3). The model divided them itself. Right, but only
  because SCB printed both endpoints, and the rounding already shows
  (3.95 vs 3.96).
- **q03 (+30.94 %): pure RAG answered "roughly +31 %" and was scored
  correct.** It chained three rounded year-on-year changes from three
  different releases (1.166 × 1.137 / 1.012). That is the
  model-does-the-arithmetic path, scored as a pass because the error
  stayed under the 1 % tolerance.

So the honest statement is not "pure RAG hallucinates numbers". It is:
pure RAG can answer only when the figure, or its parts, happen to be
published in prose. When it does answer, the model does the arithmetic on
rounded inputs, and nothing in the output distinguishes a lucky
derivation from a wrong one. The hybrid answer to q03 is 30.94 % from two
exact rows, with the rows shown.

## A metric that contradicted expectation: groundedness

**Expectation:** an answer with a wrong headline figure gets a low
groundedness score.

**Test** (`python -m evals.judge_sanity`): take the hybrid answer, raise
its main figure by 25 %, and judge both versions against the same tool
output.

| question | figure | original | altered |
|---|---|---|---|
| q01 | 3.96 → 4.95 | 1.00 | 0.71 |
| q07 | 15.63 → 19.54 | 1.00 | **1.00** (first run) |
| q07 | 15.63 → 19.54 | 1.00 | 0.93 (re-run: 14 of 15 claims supported) |

Three things this shows:
1. **The judge isn't deterministic.** On the first run it missed a wrong
   headline figure entirely.
2. **Averaging per claim dilutes the claim that matters most.** When the
   judge did catch it, one wrong figure among 15 claims cost 7 points.
   Averaged over 8 questions, that's under 1 point, well inside the
   3-point regression gate. **The gate as specified would not catch a
   single wrong headline number.**
3. **Derived arithmetic counts as "supported".** Groundedness rated the
   pure-RAG answers 0.98, including q03's chained percentages. The judge
   accepts a derived figure if its inputs appear in the tool output.

`numeric_accuracy`, not groundedness, is what protects the numbers. The
fix I'd make next is to score groundedness as the *minimum* over numeric
claims (any unsupported number gives 0) and keep the per-claim mean only
for text claims.

## Does the regression gate fire?

I opened a throwaway pull request (#2, closed unmerged) that multiplies
every computed percent change by 1.1, a plausible-looking arithmetic bug.

| metric | PR #2 | main baseline | delta |
|---|---|---|---|
| recall@5 | 1.000 | 1.000 | 0 |
| numeric_accuracy | 0.500 | 1.000 | **−50 pp** |
| groundedness | 1.000 | 1.000 | 0 |

The evals job failed and posted the table on the PR, and the unit tests in
CI failed as well. So the gate works. Which questions still passed is
the interesting part:

- **q02 passed correctly.** It asks for an index level, which the bug
  doesn't touch.
- **q07 and q08 passed, wrongly.** Their computed percentages were 10 %
  too high, but hybrid answers also quote SCB's published figure from the
  news release (15,6 %, 26,7 %). numeric_accuracy accepts *any* matching
  number in the answer, so the document's correct figure masked the
  tool's wrong one. Requiring the expected figure to come from a
  `query_price_index` result, not just appear somewhere, would close
  this.
- **Groundedness stayed at 1.000.** The judge compares the answer with
  the tool output, and the tool output was itself wrong. Groundedness
  measures faithfulness to the tools, not truth. Only a check against
  independently known values (the golden set) catches a broken tool.

## What the metrics don't see

- **Answer language.** Before the fix in commit `6e148eb`, English
  questions were answered in Swedish. I found that by reading answers,
  not from a metric, and the suite was never run on that version. None
  of the three metrics checks language: numbers parse in either language,
  the judge reads Swedish, and recall uses the question text. A language
  check is missing.
- **Latency and cost.** Not gated. q06 took 96 s because of embedding
  rate limits, and nothing failed.
- **Tool-call efficiency.** "routing ok" checks that the expected tools
  were called, not how many times. q07 made six calls where two would do.
