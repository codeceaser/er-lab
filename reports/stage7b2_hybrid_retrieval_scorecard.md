# Stage 7B.2 -- Hybrid Vector-Graph Retrieval Value Probe

Generated from one `ProbeRunResult` (same object as
`reports/stage7b2_hybrid_retrieval_results.json` and
`docs/STAGE7B2_HYBRID_GRAPH_CLOSURE_DECISION.md`). Vector (V) is the
FROZEN Stage 7B.0 baseline; every mode is scored by the SAME frozen
Stage 7B.0 `_evaluate_question`. No query-time LLM. Hybrid superiority is
never assumed.

`contract_version`: `hybrid_retrieval_probe_v1`
`generated_at`: `2026-08-03T14:58:38.562983+00:00`
`embedding_model`: `sentence-transformers/all-MiniLM-L6-v2`

## Decision

**Gate D: Keep Vector; use Graph only for navigation/offline analysis**

Real-graph H2 removed Graph regressions (no regression vs Vector) but improved only 0 of the three target questions (< 2).

## Frozen input verification

- corpus index_hash matches Stage 7B.0: **True** (`63e130e86da53ebe...`)
- real graph payload hash matches committed Stage 7B.1: **True** (`1ffd01c8f7977d82...`), loaded from snapshot (extraction run `extrun_openai_0beccdefb3e740b0`, NOT re-extracted)
- real graph: 17 nodes / 14 edges
- perfect graph: recall **1.00**, precision **1.00**, collisions **0**, payload `473eca6125d206bd...`

## Mode configuration (immutable, from the probe contract)

- vector_candidate_multiplier: 3, max_vector_seed_chunks: 8
- semantic_edge_candidate_count: 5, max_hop_depth: 5
- max_candidate_paths: 32, rrf_constant: 60
- final top-K comes only from the frozen Stage 7B.0 question contract

## Edge semantic-index manifests

- real graph: 14 edges, payload `4ab2a0b24fde73d9...`, 136944 bytes
- perfect graph: 15 edges, payload `3c536bbb307a2c95...`, 146760 bytes

## Coverage@K per question -- REAL graph

| Question | V | G | H0 | H1 | H2 |
|---|---|---|---|---|---|
| Q01_direct_service_of_app | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q02_one_hop_control_of_obligation | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q03_two_hop_obligation_of_app | 1.00 | 0.50 | 1.00 | 1.00 | 1.00 |
| Q04_two_hop_control_of_service | 0.50 | 0.00 | 0.50 | 0.50 | 0.50 |
| Q05_three_hop_procedure_of_obligation | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q06_four_hop_procedure_of_app | 0.80 | 0.20 | 0.80 | 0.80 | 0.80 |
| Q07_consolidation_payment_settlement | 0.80 | 0.20 | 0.80 | 0.80 | 0.80 |
| Q08_distractor_resistance_current_control | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q09_current_authority_app | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q10_historical_procedure_of_obligation | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q11_historical_app_of_service | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q12_draft_proposed_control | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 |

## Coverage@K per question -- PERFECT graph

| Question | V | G | H0 | H1 | H2 |
|---|---|---|---|---|---|
| Q01_direct_service_of_app | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q02_one_hop_control_of_obligation | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q03_two_hop_obligation_of_app | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q04_two_hop_control_of_service | 0.50 | 1.00 | 0.50 | 0.50 | 0.50 |
| Q05_three_hop_procedure_of_obligation | 1.00 | 0.67 | 1.00 | 1.00 | 1.00 |
| Q06_four_hop_procedure_of_app | 0.80 | 1.00 | 1.00 | 0.80 | 0.80 |
| Q07_consolidation_payment_settlement | 0.80 | 1.00 | 0.80 | 0.80 | 0.80 |
| Q08_distractor_resistance_current_control | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q09_current_authority_app | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q10_historical_procedure_of_obligation | 1.00 | 0.67 | 1.00 | 1.00 | 1.00 |
| Q11_historical_app_of_service | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q12_draft_proposed_control | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 |

## Target questions Q04/Q06/Q07 -- complete relationship chain represented

| Question | Vector | Real-graph H2 | Perfect-graph H2 |
|---|---|---|---|
| Q04_two_hop_control_of_service | False | False | False |
| Q06_four_hop_procedure_of_app | False | False | False |
| Q07_consolidation_payment_settlement | False | False | False |

## Ablation / attribution (coverage@K)

Isolates where any gain comes from: G (simple graph) -> H0 (fusion) ->
H1 (+ Vector/semantic seeds) -> H2 (+ semantic path ranking), plus the
perfect-graph G/H2 upper bound.

| Question | V | G(real) | H0(real) | H1(real) | H2(real) | G(perfect) | H2(perfect) |
|---|---|---|---|---|---|---|---|
| Q04_two_hop_control_of_service | 0.50 | 0.00 | 0.50 | 0.50 | 0.50 | 1.00 | 0.50 |
| Q06_four_hop_procedure_of_app | 0.80 | 0.20 | 0.80 | 0.80 | 0.80 | 1.00 | 0.80 |
| Q07_consolidation_payment_settlement | 0.80 | 0.20 | 0.80 | 0.80 | 0.80 | 1.00 | 0.80 |
| Q05_three_hop_procedure_of_obligation | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.67 | 1.00 |
| Q10_historical_procedure_of_obligation | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.67 | 1.00 |
| Q12_draft_proposed_control | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 |

## Mid-chain (Q05/Q10) and unnamed-entity (Q12)

- Q05/Q10 (mid-chain ranking regression risk): real-graph H2 coverage
  1.00 / 1.00 vs Vector
  1.00 / 1.00.
- Q12 (unnamed entity / no-seed): real-graph H2 coverage 1.00 vs Vector 1.00
  (Vector fallback via RRF is what preserves Q12).

## Safety and budget

- total authority leakage across ALL modes/questions/conditions: **0** (must be 0)
- final evidence budget never exceeds the frozen top-K: **True**
- query-time LLM calls: **0** (deterministic; no query-time model)
- mean latency (s) V / real-H2 / perfect-H2: 0.1229 / 0.2732 / 0.3448

## Decision-gate inputs

- real-graph H2: `{'target_complete_chain_improvements': 0, 'regressions_vs_vector': [], 'q12_regressed': False, 'total_authority_leakage': 0, 'same_final_k': True, 'uses_query_time_llm': False, 'mean_latency_ratio_vs_vector': 2.2233312059282517}`
- perfect-graph H2: `{'target_complete_chain_improvements': 0, 'regressions_vs_vector': [], 'q12_regressed': False, 'total_authority_leakage': 0, 'same_final_k': True, 'uses_query_time_llm': False, 'mean_latency_ratio_vs_vector': 2.805410282030595}`
