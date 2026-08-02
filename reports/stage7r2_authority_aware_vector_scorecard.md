# Stage 7R.2 -- Authority-Aware Vector Retrieval Scorecard

Generated from a single `BenchmarkRunResult` -- this Markdown,
`reports/stage7r2_authority_aware_vector_results.json`, and every
per-question artifact under `artifacts/stage7r2/query_results/` come
from the SAME execution, over the isolated POLICY-RETENTION-001 index
(never Stage 7A.1's own table).

`contract_version`: `revision_search_benchmark_v1`
`generated_at`: `2026-08-02T18:38:28.949587+00:00`
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
| v4 | 4 | 8b29928081c63934... | d87f88b7b6a8f297... | 4 | 10 years |
| v5 | 5 | f2d23ac23db9c4ff... | 3c827a7c1eb9afcd... | 4 | 8 years |

## Index build

- candidate chunks: 20
- indexed (embedded): 20
- skipped unchanged: 0
- total records: 20
- index_hash: `6c73ffbf48da970d765add47e1d2c97aee639dbebe2e2e265aa7b8c596aee4b5`
- embedding_payload_sha256: `9b468e67bab567cbbcc5132345acdb13d027b97708b8e9e283363d1ee87979f1`
- embedding calls: 20

## Query scenarios

| Question | Intent | As of | Eligible | Ineligible hits@K | Distinct ineligible@K | Precision@K (aware) | Hit@K (aware) | Value retrieved | Result |
|---|---|---|---|---|---|---|---|---|---|
| A_current | current | 2026-06-01 | v3 | 8 | 4 | 1.00 | True | True | PASS |
| B_historical | as_of | 2019-06-01 | v2 | 8 | 4 | 1.00 | True | True | PASS |
| C_draft | draft | 2026-06-01 | v4 | 8 | 4 | 1.00 | True | True | PASS |
| D_comparison | comparison | 2026-06-01 | v2, v3 | 6 | 3 | 1.00 | True | True | PASS |

## Scenario detail

### A_current

Scenario A: plain current query -- exactly v3 (7 years) is eligible; v1/v2 historical, v4 draft, v5 an unactivated candidate must never appear.

- query_intent: `current`, as_of_date: `2026-06-01`, requested: `[]`
- expected eligible: `['v3']` / actual: `['v3']`
- forbidden: `['v1', 'v2', 'v4', 'v5']`
- expected authority labels: `{'v3': 'effective'}` / actual: `{'v5': 'draft', 'v3': 'effective', 'v4': 'draft', 'v1': 'superseded', 'v2': 'superseded'}`
- authority-aware top-K revisions: `['v3', 'v3', 'v3', 'v3']`
- unfiltered top-K revisions: `['v1', 'v3', 'v5', 'v2', 'v4', 'v3', 'v4', 'v5', 'v1', 'v2']`
- ineligible-hit count@K (unfiltered): **8**
- distinct ineligible-revision count@K (unfiltered): **4**
- eligible-hit precision@K (authority-aware): **1.00**
- required-revision hit@K (authority-aware): **True**
- expected-value retrieved (authority-aware): **True**
- resolver latency: 0.034812s, authority-aware vector search: 0.010527s, unfiltered vector search: 0.010217s, total: 0.055556s
- registry_snapshot_hash: `a5b51dd7f86388f42d961f38bfec84e42f9d71fbeb0ef70c9d6ed65ffd3bc9fb`
- eligible_revision_ids: `['661952d0a87e24913e91ecaac232a99c8d5f6358c5e9d404d7eeba5d2e0053dc']`
- excluded: `[('3c827a7c1eb9afcd19f7acb3da0856b6500442ac9229a3ac4cc3ed700ae22be5', 'not_effective_draft'), ('d87f88b7b6a8f297da164c9163bea79ce038997bce803f3edacb7747aa56431d', 'not_effective_draft'), ('e421c4084cee42fbb5ba4a46db69c021944991704a9b8e90287526066e2672d6', 'not_effective_superseded'), ('fdeda1920250c9c4d345e4fa416a6d2997ff469665a0af24c4c03750be1b1918', 'not_effective_superseded')]`
- **PASSED**


### B_historical

Scenario B: an as_of query dated inside v2's own authority window (2018-01-01..2022-01-01) resolves v2 (5 years), never the currently-effective v3.

- query_intent: `as_of`, as_of_date: `2019-06-01`, requested: `[]`
- expected eligible: `['v2']` / actual: `['v2']`
- forbidden: `['v1', 'v3', 'v4', 'v5']`
- expected authority labels: `{'v2': 'effective'}` / actual: `{'v5': 'draft', 'v3': 'approved_future', 'v4': 'draft', 'v1': 'superseded', 'v2': 'effective'}`
- authority-aware top-K revisions: `['v2', 'v2', 'v2', 'v2']`
- unfiltered top-K revisions: `['v1', 'v3', 'v5', 'v2', 'v4', 'v3', 'v4', 'v5', 'v1', 'v2']`
- ineligible-hit count@K (unfiltered): **8**
- distinct ineligible-revision count@K (unfiltered): **4**
- eligible-hit precision@K (authority-aware): **1.00**
- required-revision hit@K (authority-aware): **True**
- expected-value retrieved (authority-aware): **True**
- resolver latency: 0.026705s, authority-aware vector search: 0.005741s, unfiltered vector search: 0.008909s, total: 0.041355s
- registry_snapshot_hash: `a5b51dd7f86388f42d961f38bfec84e42f9d71fbeb0ef70c9d6ed65ffd3bc9fb`
- eligible_revision_ids: `['fdeda1920250c9c4d345e4fa416a6d2997ff469665a0af24c4c03750be1b1918']`
- excluded: `[('3c827a7c1eb9afcd19f7acb3da0856b6500442ac9229a3ac4cc3ed700ae22be5', 'not_effective_draft'), ('661952d0a87e24913e91ecaac232a99c8d5f6358c5e9d404d7eeba5d2e0053dc', 'not_effective_approved_future'), ('d87f88b7b6a8f297da164c9163bea79ce038997bce803f3edacb7747aa56431d', 'not_effective_draft'), ('e421c4084cee42fbb5ba4a46db69c021944991704a9b8e90287526066e2672d6', 'not_effective_superseded')]`
- **PASSED**


### C_draft

Scenario C: an explicit draft-intent query for v4 returns v4 (proposed 10 years), visibly labeled draft -- never treated as current authority.

- query_intent: `draft`, as_of_date: `2026-06-01`, requested: `['v4']`
- expected eligible: `['v4']` / actual: `['v4']`
- forbidden: `['v1', 'v2', 'v3', 'v5']`
- expected authority labels: `{'v4': 'draft'}` / actual: `{'v4': 'draft'}`
- authority-aware top-K revisions: `['v4', 'v4', 'v4', 'v4']`
- unfiltered top-K revisions: `['v1', 'v3', 'v5', 'v2', 'v4', 'v3', 'v4', 'v5', 'v1', 'v2']`
- ineligible-hit count@K (unfiltered): **8**
- distinct ineligible-revision count@K (unfiltered): **4**
- eligible-hit precision@K (authority-aware): **1.00**
- required-revision hit@K (authority-aware): **True**
- expected-value retrieved (authority-aware): **True**
- resolver latency: 0.029334s, authority-aware vector search: 0.008052s, unfiltered vector search: 0.010900s, total: 0.048286s
- registry_snapshot_hash: `a5b51dd7f86388f42d961f38bfec84e42f9d71fbeb0ef70c9d6ed65ffd3bc9fb`
- eligible_revision_ids: `['d87f88b7b6a8f297da164c9163bea79ce038997bce803f3edacb7747aa56431d']`
- excluded: `[]`
- **PASSED**


### D_comparison

Scenario D: an explicit comparison query for v2 and v3 returns EXACTLY those two, each with its own value and its own authority label -- never merged, never a third revision.

- query_intent: `comparison`, as_of_date: `2026-06-01`, requested: `['v2', 'v3']`
- expected eligible: `['v2', 'v3']` / actual: `['v2', 'v3']`
- forbidden: `['v1', 'v4', 'v5']`
- expected authority labels: `{'v2': 'superseded', 'v3': 'effective'}` / actual: `{'v2': 'superseded', 'v3': 'effective'}`
- authority-aware top-K revisions: `['v3', 'v2', 'v3', 'v2', 'v3', 'v2', 'v2', 'v3']`
- unfiltered top-K revisions: `['v1', 'v3', 'v5', 'v2', 'v4', 'v3', 'v4', 'v5', 'v1', 'v2']`
- ineligible-hit count@K (unfiltered): **6**
- distinct ineligible-revision count@K (unfiltered): **3**
- eligible-hit precision@K (authority-aware): **1.00**
- required-revision hit@K (authority-aware): **True**
- expected-value retrieved (authority-aware): **True**
- resolver latency: 0.028574s, authority-aware vector search: 0.008716s, unfiltered vector search: 0.008536s, total: 0.045825s
- registry_snapshot_hash: `a5b51dd7f86388f42d961f38bfec84e42f9d71fbeb0ef70c9d6ed65ffd3bc9fb`
- eligible_revision_ids: `['fdeda1920250c9c4d345e4fa416a6d2997ff469665a0af24c4c03750be1b1918', '661952d0a87e24913e91ecaac232a99c8d5f6358c5e9d404d7eeba5d2e0053dc']`
- excluded: `[]`
- **PASSED**


## Scenario E -- authority switch without reindexing

- question_id: `E_authority_switch`, as_of_date: `2026-08-01`
- BEFORE activation: eligible = `['v3']`, top-1 = `v3`, value found = **True**
  - expected authority labels: `{'v3': 'effective', 'v5': 'draft'}` / actual: `{'v5': 'draft', 'v3': 'effective', 'v4': 'draft', 'v1': 'superseded', 'v2': 'superseded'}`
- AFTER activation (v5 supersedes v3): eligible = `['v5']`, top-1 = `v5`, value found = **True**
  - expected authority labels: `{'v3': 'superseded', 'v5': 'effective'}` / actual: `{'v5': 'effective', 'v3': 'superseded', 'v4': 'draft', 'v1': 'superseded', 'v2': 'superseded'}`
- registry_snapshot_hash: `a5b51dd7f86388f42d961f38bfec84e42f9d71fbeb0ef70c9d6ed65ffd3bc9fb` -> `6db44b2809eac6ba2fcdba191f27cdb58e56a196d25f94dbfffe59645b5c428c` (changed = **True**, expected True)
- index_hash: `6c73ffbf48da970d765add47e1d2c97aee639dbebe2e2e265aa7b8c596aee4b5` -> `6c73ffbf48da970d765add47e1d2c97aee639dbebe2e2e265aa7b8c596aee4b5` (unchanged = **True**, expected True)
- embedding_payload_sha256: `9b468e67bab567cbbcc5132345acdb13d027b97708b8e9e283363d1ee87979f1` -> `9b468e67bab567cbbcc5132345acdb13d027b97708b8e9e283363d1ee87979f1` (unchanged = **True**, expected True)
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
