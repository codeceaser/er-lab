# Stage 7A.1 -- Regular Vector Retrieval Baseline: Scorecard

Generated from a single in-memory `RetrievalEvaluationRun` -- this
Markdown and `reports/stage7a_vector_retrieval_results.json` come from
the SAME execution, never two separate runs (same discipline as Stage
5A.1/D-039 and every stage since).

`corpus_profile`: `baseline_demo`
`embedding_model`: `sentence-transformers/all-MiniLM-L6-v2`
`generated_at`: `2026-07-24T20:26:03.442790+00:00`
`index_hash`: `5a30726295c00494edcdaa44c40eae393e0548515e021e4c79e3f2604002245d`
`total_indexed_records`: 11
`K values evaluated`: 1, 3, 5

This report compares real retrieval results, computed by exact chunk_id
membership against the Stage 6A/6B gold evidence catalog, against the 12
frozen Stage 6B benchmark questions. No LLM or semantic judge scores
anything here. A retrieved chunk counts as relevant to a required fact
ONLY when its chunk_id is a member of that fact's resolved gold
chunk_ids (fixture + fact_id + chunk_id scoped, see
`src/ingestion_bench/retrieval_baseline/gold.py`).

## Index build

- Candidate chunks: 11
- Empty-retrieval_text chunks skipped (never indexed): 0
- Indexed this run: 0
- Skipped as unchanged: 11
- Build latency: 0.298s (embedding: 0.000s)
- Embedding cost (USD, where available): 0.0

## Aggregate scorecard (mean across 12 questions)

| K | 1 | 3 | 5 |
|---|---:|---:|---:|
| Mean required-fact coverage@K | 83.3% | 95.8% | 95.8% |
| Mean Recall@K (chunk-level) | 83.3% | 95.8% | 95.8% |
| All-required-facts-retrieved rate@K | 75.0% | 91.7% | 91.7% |
| Mean forbidden-fact hit rate@K | 45.8% | 54.2% | 54.2% |

`n/a` means the metric had no applicable denominator for that K (e.g. a
question whose required facts were all missing-from-ingestion/not-
applicable/not-indexed in this corpus profile) -- never silently
reported as 0%. Mean reciprocal rank of the first relevant chunk (over
the full ranked list, not per-K): 0.944.
Mean retrieval latency: 27.8ms.

## Per-question summary

| Question | Difficulty | Coverage@5 | Recall@5 | Reciprocal rank | Forbidden hit@5 | Available req. facts | Excluded req. facts | Available forbidden facts |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Q_DIRECT_001 | direct | 100.0% | 100.0% | 1.000 | 100.0% | 1 | 0 | 1 |
| Q_DIRECT_002 | direct | 100.0% | 100.0% | 1.000 | 0.0% | 1 | 0 | 0 |
| Q_DIRECT_003 | direct | 100.0% | 100.0% | 0.333 | 100.0% | 2 | 0 | 2 |
| Q_DIRECT_004 | direct | 100.0% | 100.0% | 1.000 | 0.0% | 1 | 0 | 0 |
| Q_DISTRACTOR_001 | distractor_sensitive | 100.0% | 100.0% | 1.000 | 100.0% | 2 | 0 | 1 |
| Q_DISTRACTOR_002 | distractor_sensitive | 100.0% | 100.0% | 1.000 | 100.0% | 1 | 0 | 1 |
| Q_DISTRACTOR_003 | distractor_sensitive | 100.0% | 100.0% | 1.000 | 100.0% | 1 | 0 | 1 |
| Q_RELATIONAL_001 | relational | 100.0% | 100.0% | 1.000 | 0.0% | 2 | 0 | 0 |
| Q_RELATIONAL_002 | relational | 100.0% | 100.0% | 1.000 | 0.0% | 2 | 0 | 0 |
| Q_MULTIHOP_001 | multi_hop | 100.0% | 100.0% | 1.000 | 100.0% | 4 | 0 | 2 |
| Q_MULTIHOP_002 | multi_hop | 100.0% | 100.0% | 1.000 | 0.0% | 2 | 0 | 0 |
| Q_CONSOLIDATION_001 | consolidation | 50.0% | 50.0% | 1.000 | 50.0% | 8 | 0 | 4 |

Full per-question provenance (top-K results, matched/leaked fact ids,
resolved gold evidence) is in `artifacts/stage7a/question_results/`
and `reports/stage7a_vector_retrieval_results.json`.

## What this report does NOT establish

- Answer quality or correctness of any kind -- no answer-generation
  layer exists (this stage performs retrieval only).
- Graph-enriched retrieval, wiki retrieval, or vision-enriched ingestion
  quality -- not implemented (later stages).
- Cross-corpus-profile comparison beyond index-build metadata -- the
  scorecard above is computed against `baseline_demo` only; see
  `artifacts/stage7a/index_manifest.json` for the other built indexes'
  own chunk counts.
