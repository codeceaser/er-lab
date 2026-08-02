# Stage 7R.2 -- Authority-Aware Vector Retrieval Scorecard

Generated from a single `BenchmarkRunResult` -- this Markdown and
`reports/stage7r2_authority_aware_vector_results.json` come from the
SAME execution, over the isolated POLICY-RETENTION-001 index (never
Stage 7A.1's own table).

`contract_version`: `revision_search_benchmark_v1`
`generated_at`: `2026-08-02T04:37:11.207993+00:00`
`embedding_model`: `sentence-transformers/all-MiniLM-L6-v2`
`query_scenarios`: 4/4 passed
`authority_switch`: PASSED
`all_passed`: **True**

## Fixture inventory

| Symbol | Revision # | source_document_sha256 | document_revision_id | Chunks | Retention value |
|---|---|---|---|---|---|
| v1 | 1 | ad07edda961b2339... | e421c4084cee42fb... | 4 | 3 years |
| v2 | 2 | cb8962d0f37323c6... | fdeda1920250c9c4... | 4 | 5 years |
| v3 | 3 | a41da20acee3878b... | 661952d0a87e2491... | 4 | 7 years |
| v4 | 4 | 3b54ba6bd1415784... | 68791e8a5359582f... | 4 | 10 years |
| v5 | 5 | f2d23ac23db9c4ff... | 3c827a7c1eb9afcd... | 4 | 8 years |

## Index build

- candidate chunks: 20
- indexed (embedded): 20
- skipped unchanged: 0
- total records: 20
- index_hash: `f08bbf07ee9d5b37a4fe7181d73e14607c327737754a2ece7e50a9b7392f5c9e`
- embedding calls: 20

## Query scenarios

| Question | Intent | As of | Eligible | Leakage@K (unfiltered) | Precision@K (aware) | Hit@K (aware) | Value retrieved | Result |
|---|---|---|---|---|---|---|---|---|
| A_current | current | 2026-06-01 | v3 | 8 | 1.00 | True | True | PASS |
| B_historical | as_of | 2019-06-01 | v2 | 8 | 1.00 | True | True | PASS |
| C_draft | draft | 2026-06-01 | v4 | 8 | 1.00 | True | True | PASS |
| D_comparison | comparison | 2026-06-01 | v2, v3 | 6 | 1.00 | True | True | PASS |

## Scenario detail

### A_current

Scenario A: plain current query -- exactly v3 (7 years) is eligible; v1/v2 historical, v4 draft, v5 an unactivated candidate must never appear.

- query_intent: `current`, as_of_date: `2026-06-01`, requested: `[]`
- expected eligible: `['v3']` / actual: `['v3']`
- forbidden: `['v1', 'v2', 'v4', 'v5']`
- expected authority labels: `{'v3': 'effective'}` / actual: `{'v5': 'draft', 'v3': 'effective', 'v4': 'draft', 'v1': 'superseded', 'v2': 'superseded'}`
- authority-aware top-K revisions: `['v3', 'v3', 'v3', 'v3']`
- unfiltered top-K revisions: `['v1', 'v3', 'v5', 'v2', 'v4', 'v3', 'v4', 'v5', 'v1', 'v2']`
- ineligible-revision leakage@K (unfiltered): **8**
- eligible-revision precision@K (authority-aware): **1.00**
- required-revision hit@K (authority-aware): **True**
- expected-value retrieved (authority-aware): **True**
- resolver latency: 0.040644s, authority-aware vector search: 0.011784s, unfiltered vector search: 0.016001s, total: 0.068429s
- **PASSED**


### B_historical

Scenario B: an as_of query dated inside v2's own authority window (2018-01-01..2022-01-01) resolves v2 (5 years), never the currently-effective v3.

- query_intent: `as_of`, as_of_date: `2019-06-01`, requested: `[]`
- expected eligible: `['v2']` / actual: `['v2']`
- forbidden: `['v1', 'v3', 'v4', 'v5']`
- expected authority labels: `{'v2': 'effective'}` / actual: `{'v5': 'draft', 'v3': 'approved_future', 'v4': 'draft', 'v1': 'superseded', 'v2': 'effective'}`
- authority-aware top-K revisions: `['v2', 'v2', 'v2', 'v2']`
- unfiltered top-K revisions: `['v1', 'v3', 'v5', 'v2', 'v4', 'v3', 'v4', 'v5', 'v1', 'v2']`
- ineligible-revision leakage@K (unfiltered): **8**
- eligible-revision precision@K (authority-aware): **1.00**
- required-revision hit@K (authority-aware): **True**
- expected-value retrieved (authority-aware): **True**
- resolver latency: 0.043673s, authority-aware vector search: 0.012436s, unfiltered vector search: 0.014587s, total: 0.070697s
- **PASSED**


### C_draft

Scenario C: an explicit draft-intent query for v4 returns v4 (proposed 10 years), visibly labeled draft -- never treated as current authority.

- query_intent: `draft`, as_of_date: `2026-06-01`, requested: `['v4']`
- expected eligible: `['v4']` / actual: `['v4']`
- forbidden: `['v1', 'v2', 'v3', 'v5']`
- expected authority labels: `{'v4': 'draft'}` / actual: `{'v4': 'draft'}`
- authority-aware top-K revisions: `['v4', 'v4', 'v4', 'v4']`
- unfiltered top-K revisions: `['v1', 'v3', 'v5', 'v2', 'v4', 'v3', 'v4', 'v5', 'v1', 'v2']`
- ineligible-revision leakage@K (unfiltered): **8**
- eligible-revision precision@K (authority-aware): **1.00**
- required-revision hit@K (authority-aware): **True**
- expected-value retrieved (authority-aware): **True**
- resolver latency: 0.044874s, authority-aware vector search: 0.010472s, unfiltered vector search: 0.017527s, total: 0.072873s
- **PASSED**


### D_comparison

Scenario D: an explicit comparison query for v2 and v3 returns EXACTLY those two, each with its own value and its own authority label -- never merged, never a third revision.

- query_intent: `comparison`, as_of_date: `2026-06-01`, requested: `['v2', 'v3']`
- expected eligible: `['v2', 'v3']` / actual: `['v2', 'v3']`
- forbidden: `['v1', 'v4', 'v5']`
- expected authority labels: `{'v2': 'superseded', 'v3': 'effective'}` / actual: `{'v2': 'superseded', 'v3': 'effective'}`
- authority-aware top-K revisions: `['v3', 'v2', 'v3', 'v2', 'v3', 'v2', 'v2', 'v3']`
- unfiltered top-K revisions: `['v1', 'v3', 'v5', 'v2', 'v4', 'v3', 'v4', 'v5', 'v1', 'v2']`
- ineligible-revision leakage@K (unfiltered): **6**
- eligible-revision precision@K (authority-aware): **1.00**
- required-revision hit@K (authority-aware): **True**
- expected-value retrieved (authority-aware): **True**
- resolver latency: 0.037181s, authority-aware vector search: 0.011669s, unfiltered vector search: 0.012056s, total: 0.060906s
- **PASSED**


## Scenario E -- authority switch without reindexing

- question_id: `E_authority_switch`, as_of_date: `2026-08-01`
- BEFORE activation: eligible = `['v3']`, top-1 = `v3`, value found = **True**
- AFTER activation (v5 supersedes v3): eligible = `['v5']`, top-1 = `v5`, value found = **True**
- registry_snapshot_hash: `5591b6efe9b8bea074d611e300d690829c51e2712b0e9bc4cac97c3c5e0b2095` -> `7d91314b3f726a3943369797a7e8c14213ec94221cfeaa1f33e39efd5168cc13` (changed = **True**, expected True)
- index_hash: `f08bbf07ee9d5b37a4fe7181d73e14607c327737754a2ece7e50a9b7392f5c9e` -> `f08bbf07ee9d5b37a4fe7181d73e14607c327737754a2ece7e50a9b7392f5c9e` (unchanged = **True**, expected True)
- row_count: 20 -> 20 (unchanged = **True**, expected True)
- chunk_ids unchanged: **True** (expected True)
- chunk content hashes unchanged: **True** (expected True)
- embedding calls during the switch itself: **0** (expected 0)
- **PASSED**


## What this report does NOT establish

- Any answer generation over these results -- Stage 7R.2 stops at
  retrieval evaluation.
- Graph RAG, wiki retrieval, ADK, or vision enrichment -- none of this
  package depends on any of them.
