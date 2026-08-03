# Stage 7B.1 -- Vector vs Graph Retrieval Scorecard

Generated from the same run objects as
`reports/stage7b1_graph_build_results.json` and
`reports/stage7b1_graph_retrieval_results.json`. The Vector baseline is
the FROZEN Stage 7B.0 result (loaded, never rerun or rescored); Graph is
scored by the SAME frozen Stage 7B.0 `_evaluate_question` over the SAME
fact alignment. NO answer generation, NO graph framework, NO Neo4j.

`contract_version`: `cross_document_relationship_benchmark_v1`
`corpus_id`: `CROSS-DOC-RELATIONSHIP-001`
`generated_at`: `2026-08-02T23:51:29.945779+00:00`
`embedding_model`: `sentence-transformers/all-MiniLM-L6-v2`
`extractor`: `openai:gpt-4o-mini`
`frozen input verified`: **True** (index_hash `63e130e86da53ebe...`)
`graph authority correct`: 12/12
`improved / unchanged / regressed`: 0 / 7 / 5

## Graph build

- extractor: `openai:gpt-4o-mini` (model `gpt-4o-mini`, prompt `stage7b1-extract-v1` sha `977cb1f457d8...`)
- nodes: 17, edge assertions: 14, distinct evidence chunks: 10
- graph payload hash: `1ffd01c8f7977d82e8e67e381ee71ce4045a64e0e5e788784193941c56c25d38`
- storage estimate: 24697 bytes, build latency: 24.309s
- extraction tokens (in/out): 3708/958, estimated cost: 0.001131, failures: 0
- rejected (unsupported) relationships during build: 1

## Graph build accuracy (vs Stage 7B.0 facts)

- expected-fact edge recall: **0.80** (12/15); missing: `['F_adj_prc', 'F_prc_current', 'F_svc']`
- extracted-edge precision: **0.86**; unsupported extracted edges: 2
- duplicate assertions: 0
- provenance completeness: **1.00**; edges with invalid/missing supporting chunk: 0
- entity normalization collisions: 0 `[]`

## Vector vs Graph, per question

| Question | Type | Intent | K | V cov | G cov | delta | V chain | G chain | MRR V/G | nDCG V/G | G auth-leak | latency ms V/G | change |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Q01_direct_service_of_app | direct_semantic_lookup | current | 3 | 1.00 | 1.00 | +0.00 | True | True | 1.00/1.00 | 1.00/1.00 | 0 | 168.5/122.0 | unchanged |
| Q02_one_hop_control_of_obligation | one_hop_relationship_lookup | current | 3 | 1.00 | 1.00 | +0.00 | True | True | 1.00/1.00 | 1.00/1.00 | 0 | 127.4/105.0 | unchanged |
| Q03_two_hop_obligation_of_app | distributed_two_hop_lookup | current | 3 | 1.00 | 0.50 | -0.50 | True | False | 1.00/1.00 | 1.00/0.61 | 0 | 138.7/113.6 | regressed |
| Q04_two_hop_control_of_service | distributed_two_hop_lookup | current | 3 | 0.50 | 0.00 | -0.50 | False | False | 1.00/0.00 | 0.61/0.00 | 0 | 136.3/109.1 | regressed |
| Q05_three_hop_procedure_of_obligation | distributed_multi_hop_lookup | current | 4 | 1.00 | 1.00 | +0.00 | True | True | 1.00/1.00 | 0.97/1.00 | 0 | 132.2/131.6 | unchanged |
| Q06_four_hop_procedure_of_app | distributed_multi_hop_lookup | current | 5 | 0.80 | 0.20 | -0.60 | False | False | 1.00/1.00 | 0.83/0.34 | 0 | 131.0/132.0 | regressed |
| Q07_consolidation_payment_settlement | relationship_consolidation | current | 5 | 0.80 | 0.20 | -0.60 | False | False | 1.00/1.00 | 0.83/0.34 | 0 | 118.1/130.3 | regressed |
| Q08_distractor_resistance_current_control | distractor_resistance | current | 3 | 1.00 | 1.00 | +0.00 | True | True | 1.00/1.00 | 1.00/1.00 | 0 | 120.8/127.8 | unchanged |
| Q09_current_authority_app | current_authority_relationship_lookup | current | 3 | 1.00 | 1.00 | +0.00 | True | True | 1.00/1.00 | 1.00/1.00 | 0 | 121.5/115.4 | unchanged |
| Q10_historical_procedure_of_obligation | historical_comparison | as_of | 4 | 1.00 | 1.00 | +0.00 | True | True | 1.00/1.00 | 0.91/1.00 | 0 | 112.9/124.3 | unchanged |
| Q11_historical_app_of_service | historical_comparison | as_of | 3 | 1.00 | 1.00 | +0.00 | True | True | 1.00/1.00 | 1.00/1.00 | 0 | 127.7/129.0 | unchanged |
| Q12_draft_proposed_control | draft_lookup | draft | 3 | 1.00 | 0.00 | -1.00 | True | False | 1.00/0.00 | 1.00/0.00 | 0 | 39.6/29.6 | regressed |

## Highlighted distributed multi-hop questions (Q04, Q06, Q07)

The Graph retriever was NOT given these questions' expected paths.

### Q04_two_hop_control_of_service

- Vector coverage@3: **0.50** (complete chain: False) -> Graph coverage@3: **0.00** (complete chain: False) [regressed]

### Q06_four_hop_procedure_of_app

- Vector coverage@5: **0.80** (complete chain: False) -> Graph coverage@5: **0.20** (complete chain: False) [regressed]

### Q07_consolidation_payment_settlement

- Vector coverage@5: **0.80** (complete chain: False) -> Graph coverage@5: **0.20** (complete chain: False) [regressed]


## Per-question graph detail

### Q01_direct_service_of_app -- direct_semantic_lookup

- intent: `current`, top_k: 3, graph outcome: **solved**, authority correct: **True**
- seed entities: `['APP-224510']`
- graph hit documents (ranked): `['APP-PORTFOLIO']`
- coverage@3: **1.00**, all-required: True, complete chain: True, MRR: 1.00, nDCG: 1.00
- authority leakage (must be 0): **0**, forbidden facts in hits: `[]`
- traversed edges: 1, evidence hits: 1, total latency: 122.0ms


### Q02_one_hop_control_of_obligation -- one_hop_relationship_lookup

- intent: `current`, top_k: 3, graph outcome: **solved**, authority correct: **True**
- seed entities: `['O-31']`
- graph hit documents (ranked): `['OBLIGATION-REGISTER', 'CONTROL-LIBRARY', 'PROCEDURE-CATALOGUE']`
- coverage@3: **1.00**, all-required: True, complete chain: True, MRR: 1.00, nDCG: 1.00
- authority leakage (must be 0): **0**, forbidden facts in hits: `[]`
- traversed edges: 3, evidence hits: 3, total latency: 105.0ms


### Q03_two_hop_obligation_of_app -- distributed_two_hop_lookup

- intent: `current`, top_k: 3, graph outcome: **partial**, authority correct: **True**
- seed entities: `['APP-224510']`
- graph hit documents (ranked): `['APP-PORTFOLIO']`
- coverage@3: **0.50**, all-required: False, complete chain: False, MRR: 1.00, nDCG: 0.61
- authority leakage (must be 0): **0**, forbidden facts in hits: `[]`
- traversed edges: 1, evidence hits: 1, total latency: 113.6ms


### Q04_two_hop_control_of_service -- distributed_two_hop_lookup

- intent: `current`, top_k: 3, graph outcome: **failed**, authority correct: **True**
- seed entities: `['Payment Settlement']`
- graph hit documents (ranked): `['APP-PORTFOLIO']`
- coverage@3: **0.00**, all-required: False, complete chain: False, MRR: 0.00, nDCG: 0.00
- authority leakage (must be 0): **0**, forbidden facts in hits: `[]`
- traversed edges: 1, evidence hits: 1, total latency: 109.1ms


### Q05_three_hop_procedure_of_obligation -- distributed_multi_hop_lookup

- intent: `current`, top_k: 4, graph outcome: **solved**, authority correct: **True**
- seed entities: `['O-31']`
- graph hit documents (ranked): `['OBLIGATION-REGISTER', 'CONTROL-LIBRARY', 'PROCEDURE-CATALOGUE']`
- coverage@4: **1.00**, all-required: True, complete chain: True, MRR: 1.00, nDCG: 1.00
- authority leakage (must be 0): **0**, forbidden facts in hits: `[]`
- traversed edges: 3, evidence hits: 3, total latency: 131.6ms


### Q06_four_hop_procedure_of_app -- distributed_multi_hop_lookup

- intent: `current`, top_k: 5, graph outcome: **partial**, authority correct: **True**
- seed entities: `['APP-224510']`
- graph hit documents (ranked): `['APP-PORTFOLIO']`
- coverage@5: **0.20**, all-required: False, complete chain: False, MRR: 1.00, nDCG: 0.34
- authority leakage (must be 0): **0**, forbidden facts in hits: `[]`
- traversed edges: 1, evidence hits: 1, total latency: 132.0ms


### Q07_consolidation_payment_settlement -- relationship_consolidation

- intent: `current`, top_k: 5, graph outcome: **partial**, authority correct: **True**
- seed entities: `['Payment Settlement']`
- graph hit documents (ranked): `['APP-PORTFOLIO']`
- coverage@5: **0.20**, all-required: False, complete chain: False, MRR: 1.00, nDCG: 0.34
- authority leakage (must be 0): **0**, forbidden facts in hits: `[]`
- traversed edges: 1, evidence hits: 1, total latency: 130.3ms


### Q08_distractor_resistance_current_control -- distractor_resistance

- intent: `current`, top_k: 3, graph outcome: **solved**, authority correct: **True**
- seed entities: `['O-31']`
- graph hit documents (ranked): `['OBLIGATION-REGISTER', 'CONTROL-LIBRARY', 'PROCEDURE-CATALOGUE']`
- coverage@3: **1.00**, all-required: True, complete chain: True, MRR: 1.00, nDCG: 1.00
- authority leakage (must be 0): **0**, forbidden facts in hits: `[]`
- traversed edges: 3, evidence hits: 3, total latency: 127.8ms


### Q09_current_authority_app -- current_authority_relationship_lookup

- intent: `current`, top_k: 3, graph outcome: **solved**, authority correct: **True**
- seed entities: `['Payment Settlement']`
- graph hit documents (ranked): `['APP-PORTFOLIO']`
- coverage@3: **1.00**, all-required: True, complete chain: True, MRR: 1.00, nDCG: 1.00
- authority leakage (must be 0): **0**, forbidden facts in hits: `[]`
- traversed edges: 1, evidence hits: 1, total latency: 115.4ms


### Q10_historical_procedure_of_obligation -- historical_comparison

- intent: `as_of`, top_k: 4, graph outcome: **solved**, authority correct: **True**
- seed entities: `['O-31']`
- graph hit documents (ranked): `['OBLIGATION-REGISTER', 'CONTROL-LIBRARY', 'PROCEDURE-CATALOGUE']`
- coverage@4: **1.00**, all-required: True, complete chain: True, MRR: 1.00, nDCG: 1.00
- authority leakage (must be 0): **0**, forbidden facts in hits: `[]`
- traversed edges: 3, evidence hits: 3, total latency: 124.3ms


### Q11_historical_app_of_service -- historical_comparison

- intent: `as_of`, top_k: 3, graph outcome: **solved**, authority correct: **True**
- seed entities: `['Payment Settlement']`
- graph hit documents (ranked): `['APP-PORTFOLIO']`
- coverage@3: **1.00**, all-required: True, complete chain: True, MRR: 1.00, nDCG: 1.00
- authority leakage (must be 0): **0**, forbidden facts in hits: `[]`
- traversed edges: 1, evidence hits: 1, total latency: 129.0ms


### Q12_draft_proposed_control -- draft_lookup

- intent: `draft`, top_k: 3, graph outcome: **failed**, authority correct: **True**
- seed entities: `[]`
- graph hit documents (ranked): `[]`
- coverage@3: **0.00**, all-required: False, complete chain: False, MRR: 0.00, nDCG: 0.00
- authority leakage (must be 0): **0**, forbidden facts in hits: `[]`
- traversed edges: 0, evidence hits: 0, total latency: 29.6ms
- outcome: `no_seed_entity`


## Decision report

- Questions Graph **improves**: `[]`
- Questions **unchanged**: `['Q01_direct_service_of_app', 'Q02_one_hop_control_of_obligation', 'Q05_three_hop_procedure_of_obligation', 'Q08_distractor_resistance_current_control', 'Q09_current_authority_app', 'Q10_historical_procedure_of_obligation', 'Q11_historical_app_of_service']`
- Questions Graph **regresses**: `['Q03_two_hop_obligation_of_app', 'Q04_two_hop_control_of_service', 'Q06_four_hop_procedure_of_app', 'Q07_consolidation_payment_settlement', 'Q12_draft_proposed_control']`
- Q04/Q06/Q07 become complete-chain under Graph: [False, False, False]
- Graph extraction accuracy: recall 0.80, precision 0.86, unsupported edges 2
- Authority leakage across all questions: 0 (must be 0)
- Graph build tokens/cost: 3708/958 tokens, 0.001131 USD; storage 24697 bytes
- Vector vs Graph query latency (mean ms): 122.9 vs 114.1

**Recommendation: defer Graph because its benefit does not justify its cost.**

With the real LLM extractor the graph improved NO question and regressed 5: a single missed or inconsistently-normalized edge breaks a multi-hop chain, so traversal retrieves less than Vector, and extraction is non-deterministic and adds real cost/maintenance. (The deterministic best-case -- a perfect extractor -- does improve the deep endpoint multi-hop questions, so the benefit is latent but not reliably achievable with a real extractor here.)

### Implementation and maintenance limitations

- Graph retrieval depends on the query naming a seedable graph entity; a
  question that never names one (e.g. the draft-control question, which
  does not mention C-91) yields `no_seed_entity` and retrieves nothing,
  where lexical Vector still matches.
- Hop-distance-first ranking under a tight top-K budget can drop a far
  but required hop when a mid-chain seed reaches the rest of the chain in
  both directions.
- Graph adds an extraction step (real model cost, prompt maintenance,
  entity-normalization risk) that Vector does not have.
- This is a small controlled corpus; absolute deltas would differ on a
  larger, noisier corpus.
