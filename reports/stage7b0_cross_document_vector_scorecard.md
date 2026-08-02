# Stage 7B.0 -- Cross-Document Relationship Vector Baseline Scorecard

Generated from a single `BenchmarkRunResult` -- this Markdown,
`reports/stage7b0_cross_document_vector_results.json`, and every
per-question artifact under `artifacts/stage7b0/query_results/` come from
the SAME execution. Retrieval is Vector-only; NO graph nodes, edges,
traversal, or answer generation exist in this stage.

`contract_version`: `cross_document_relationship_benchmark_v1`
`corpus_id`: `CROSS-DOC-RELATIONSHIP-001`
`generated_at`: `2026-08-02T19:41:21.754638+00:00`
`embedding_model`: `sentence-transformers/all-MiniLM-L6-v2`
`authority correct`: 12/12 (must be all)
`vector outcomes`: solved=9, partial=3, failed=0
`all_authority_correct`: **True**

## Source fixture inventory

| Symbol | Logical document | Rev # | source_document_sha256 | Chunks |
|---|---|---|---|---|
| adj_rev1 | ADJACENT-DOMAIN | 1 | 19f0adc8e8042ec3... | 1 |
| app_rev1 | APP-PORTFOLIO | 1 | aa584c4c983661a6... | 1 |
| app_rev2 | APP-PORTFOLIO | 2 | 69c504e74f62e941... | 1 |
| ctl_rev1 | CONTROL-LIBRARY | 1 | 8d378619827af625... | 1 |
| ctl_rev2 | CONTROL-LIBRARY | 2 | 7fb8a0698c64954b... | 1 |
| ctl_rev3 | CONTROL-LIBRARY | 3 | 041eac0d61ad714f... | 1 |
| obl_rev1 | OBLIGATION-REGISTER | 1 | f448abf11ebfd110... | 1 |
| obl_rev2 | OBLIGATION-REGISTER | 2 | 4828ed818726684c... | 1 |
| prc_rev1 | PROCEDURE-CATALOGUE | 1 | 46f354211b3c8af9... | 1 |
| prc_rev2 | PROCEDURE-CATALOGUE | 2 | bb175f1064b36ed4... | 1 |
| svc_rev1 | SERVICE-CATALOGUE | 1 | 55f7818e3e72f06b... | 1 |

## Relationship fact inventory (evidence alignment)

| Fact | Relationship | Supporting document | Temporal | Distractor | Supporting chunk |
|---|---|---|---|---|---|
| F_app_current | APP-224510 supports Payment Settlement | APP-PORTFOLIO | current | none | 2e409298eff5... |
| F_svc | Payment Settlement is_governed_by Obligation O-31 | SERVICE-CATALOGUE | current | none | d00ddb9a8090... |
| F_obl_current | Obligation O-31 is_satisfied_by Control C-88 | OBLIGATION-REGISTER | current | none | 5f10b139bf62... |
| F_ctl_current | Control C-88 is_implemented_through Procedure P-205 | CONTROL-LIBRARY | current | none | 57aae7e4f9ee... |
| F_prc_current | Procedure P-205 has_status current operating procedure | PROCEDURE-CATALOGUE | current | none | 1528d9434525... |
| F_app_historical | APP-224499 supports Payment Settlement | APP-PORTFOLIO | historical | retired | 1a5af9b5351c... |
| F_obl_historical | Obligation O-31 is_satisfied_by Control C-88a | OBLIGATION-REGISTER | historical | superseded | 54188cb210ab... |
| F_ctl_historical | Control C-88a is_implemented_through Procedure P-204 | CONTROL-LIBRARY | historical | superseded | dfca23730d42... |
| F_prc_historical | Procedure P-204 has_status retired operating procedure | PROCEDURE-CATALOGUE | historical | retired | cb11a6821864... |
| F_ctl_draft | Control C-91 is_proposed_to_implement Procedure P-205 | CONTROL-LIBRARY | draft | proposed | fac4d4cba8c7... |
| F_adj_app | APP-330012 supports Payment Reconciliation | ADJACENT-DOMAIN | current | adjacent_unrelated | ced1fc053598... |
| F_adj_svc | Payment Reconciliation is_governed_by Obligation O-32 | ADJACENT-DOMAIN | current | adjacent_unrelated | ced1fc053598... |
| F_adj_obl | Obligation O-32 is_satisfied_by Control C-77 | ADJACENT-DOMAIN | current | adjacent_unrelated | ced1fc053598... |
| F_adj_ctl | Control C-77 is_implemented_through Procedure P-301 | ADJACENT-DOMAIN | current | adjacent_unrelated | ced1fc053598... |
| F_adj_prc | Procedure P-301 has_status current operating procedure for reconciliation | ADJACENT-DOMAIN | current | adjacent_unrelated | ced1fc053598... |

## Question inventory by type

| Question type | Count |
|---|---|
| current_authority_relationship_lookup | 1 |
| direct_semantic_lookup | 1 |
| distractor_resistance | 1 |
| distributed_multi_hop_lookup | 2 |
| distributed_two_hop_lookup | 2 |
| draft_lookup | 1 |
| historical_comparison | 2 |
| one_hop_relationship_lookup | 1 |
| relationship_consolidation | 1 |

## Index build

- corpus documents: 6
- candidate chunks: 11
- indexed (embedded): 11
- total records: 11
- index_hash: `63e130e86da53ebe601d3f7167749c2e22652177c751684615307ee6117fbc14`

## Vector baseline results

| Question | Type | Intent | K | Coverage@K | All@K | MRR | nDCG@K | Auth leak | Unfilt. ineligible | Doc diversity | Outcome | Auth OK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Q01_direct_service_of_app | direct_semantic_lookup | current | 3 | 1.00 | True | 1.000 | 1.000 | 0 | 1 | 3 | solved | True |
| Q02_one_hop_control_of_obligation | one_hop_relationship_lookup | current | 3 | 1.00 | True | 1.000 | 1.000 | 0 | 1 | 3 | solved | True |
| Q03_two_hop_obligation_of_app | distributed_two_hop_lookup | current | 3 | 1.00 | True | 1.000 | 1.000 | 0 | 1 | 3 | solved | True |
| Q04_two_hop_control_of_service | distributed_two_hop_lookup | current | 3 | 0.50 | False | 1.000 | 0.613 | 0 | 1 | 3 | partial | True |
| Q05_three_hop_procedure_of_obligation | distributed_multi_hop_lookup | current | 4 | 1.00 | True | 1.000 | 0.967 | 0 | 3 | 4 | solved | True |
| Q06_four_hop_procedure_of_app | distributed_multi_hop_lookup | current | 5 | 0.80 | False | 1.000 | 0.830 | 0 | 3 | 5 | partial | True |
| Q07_consolidation_payment_settlement | relationship_consolidation | current | 5 | 0.80 | False | 1.000 | 0.830 | 0 | 1 | 5 | partial | True |
| Q08_distractor_resistance_current_control | distractor_resistance | current | 3 | 1.00 | True | 1.000 | 1.000 | 0 | 2 | 3 | solved | True |
| Q09_current_authority_app | current_authority_relationship_lookup | current | 3 | 1.00 | True | 1.000 | 1.000 | 0 | 1 | 3 | solved | True |
| Q10_historical_procedure_of_obligation | historical_comparison | as_of | 4 | 1.00 | True | 1.000 | 0.906 | 0 | 2 | 4 | solved | True |
| Q11_historical_app_of_service | historical_comparison | as_of | 3 | 1.00 | True | 1.000 | 1.000 | 0 | 1 | 3 | solved | True |
| Q12_draft_proposed_control | draft_lookup | draft | 3 | 1.00 | True | 1.000 | 1.000 | 0 | 2 | 1 | solved | True |

- **Vector solved** (entire required chain retrieved within budget): `['Q01_direct_service_of_app', 'Q02_one_hop_control_of_obligation', 'Q03_two_hop_obligation_of_app', 'Q05_three_hop_procedure_of_obligation', 'Q08_distractor_resistance_current_control', 'Q09_current_authority_app', 'Q10_historical_procedure_of_obligation', 'Q11_historical_app_of_service', 'Q12_draft_proposed_control']`
- **Vector partial** (some but not all required facts retrieved): `['Q04_two_hop_control_of_service', 'Q06_four_hop_procedure_of_app', 'Q07_consolidation_payment_settlement']`
- **Vector failed** (no required facts retrieved): `[]`

## Question detail

### Q01_direct_service_of_app -- direct_semantic_lookup

> Which business service does application APP-224510 support?

- intent: `current`, as_of_date: `2026-06-01`, top_k: 3
- eligible revisions (cross-document union): `['adj_rev1', 'app_rev2', 'ctl_rev2', 'obl_rev2', 'prc_rev2', 'svc_rev1']`
- required facts: `['F_app_current']`
- forbidden facts: `['F_app_historical', 'F_adj_app']`
- authority-aware hits (ranked documents): `['APP-PORTFOLIO', 'ADJACENT-DOMAIN', 'SERVICE-CATALOGUE']`
- unfiltered hits (ranked documents): `['APP-PORTFOLIO', 'APP-PORTFOLIO', 'ADJACENT-DOMAIN']`
- required-fact coverage@3: **1.00** (ALL required retrieved)
- complete relationship chain represented: **True**
- MRR: 1.000, nDCG@3: 1.000
- authority leakage (authority-aware, must be 0): **0**
- forbidden facts appearing in authority-aware hits: `['F_adj_app']` (adjacent-domain lexical distractors are eligible and not an authority failure)
- unfiltered ineligible hits (removed by authority filtering): **1**
- evidence-document diversity (distinct docs in authority-aware top-K): **3**
- vector outcome: **solved**, authority correct: **True**
- latency: resolver 0.118901s, authority-aware 0.040282s, unfiltered 0.009359s, total 0.168541s


### Q02_one_hop_control_of_obligation -- one_hop_relationship_lookup

> Which control satisfies Obligation O-31?

- intent: `current`, as_of_date: `2026-06-01`, top_k: 3
- eligible revisions (cross-document union): `['adj_rev1', 'app_rev2', 'ctl_rev2', 'obl_rev2', 'prc_rev2', 'svc_rev1']`
- required facts: `['F_obl_current']`
- forbidden facts: `['F_obl_historical', 'F_ctl_draft', 'F_adj_obl']`
- authority-aware hits (ranked documents): `['OBLIGATION-REGISTER', 'SERVICE-CATALOGUE', 'CONTROL-LIBRARY']`
- unfiltered hits (ranked documents): `['OBLIGATION-REGISTER', 'OBLIGATION-REGISTER', 'SERVICE-CATALOGUE']`
- required-fact coverage@3: **1.00** (ALL required retrieved)
- complete relationship chain represented: **True**
- MRR: 1.000, nDCG@3: 1.000
- authority leakage (authority-aware, must be 0): **0**
- forbidden facts appearing in authority-aware hits: `[]` (adjacent-domain lexical distractors are eligible and not an authority failure)
- unfiltered ineligible hits (removed by authority filtering): **1**
- evidence-document diversity (distinct docs in authority-aware top-K): **3**
- vector outcome: **solved**, authority correct: **True**
- latency: resolver 0.109716s, authority-aware 0.009166s, unfiltered 0.008482s, total 0.127364s


### Q03_two_hop_obligation_of_app -- distributed_two_hop_lookup

> Which obligation governs the business service that application APP-224510 supports?

- intent: `current`, as_of_date: `2026-06-01`, top_k: 3
- eligible revisions (cross-document union): `['adj_rev1', 'app_rev2', 'ctl_rev2', 'obl_rev2', 'prc_rev2', 'svc_rev1']`
- required facts: `['F_app_current', 'F_svc']`
- forbidden facts: `['F_adj_app', 'F_adj_svc']`
- authority-aware hits (ranked documents): `['APP-PORTFOLIO', 'SERVICE-CATALOGUE', 'ADJACENT-DOMAIN']`
- unfiltered hits (ranked documents): `['APP-PORTFOLIO', 'APP-PORTFOLIO', 'SERVICE-CATALOGUE']`
- required-fact coverage@3: **1.00** (ALL required retrieved)
- complete relationship chain represented: **True**
- MRR: 1.000, nDCG@3: 1.000
- authority leakage (authority-aware, must be 0): **0**
- forbidden facts appearing in authority-aware hits: `['F_adj_svc']` (adjacent-domain lexical distractors are eligible and not an authority failure)
- unfiltered ineligible hits (removed by authority filtering): **1**
- evidence-document diversity (distinct docs in authority-aware top-K): **3**
- vector outcome: **solved**, authority correct: **True**
- latency: resolver 0.120769s, authority-aware 0.009393s, unfiltered 0.008537s, total 0.138699s


### Q04_two_hop_control_of_service -- distributed_two_hop_lookup

> Which control satisfies the obligation that governs the Payment Settlement business service?

- intent: `current`, as_of_date: `2026-06-01`, top_k: 3
- eligible revisions (cross-document union): `['adj_rev1', 'app_rev2', 'ctl_rev2', 'obl_rev2', 'prc_rev2', 'svc_rev1']`
- required facts: `['F_svc', 'F_obl_current']`
- forbidden facts: `['F_obl_historical', 'F_adj_svc', 'F_adj_obl']`
- authority-aware hits (ranked documents): `['SERVICE-CATALOGUE', 'ADJACENT-DOMAIN', 'APP-PORTFOLIO']`
- unfiltered hits (ranked documents): `['SERVICE-CATALOGUE', 'ADJACENT-DOMAIN', 'APP-PORTFOLIO']`
- required-fact coverage@3: **0.50** (PARTIAL / none)
- complete relationship chain represented: **False**
- MRR: 1.000, nDCG@3: 0.613
- authority leakage (authority-aware, must be 0): **0**
- forbidden facts appearing in authority-aware hits: `['F_adj_obl']` (adjacent-domain lexical distractors are eligible and not an authority failure)
- unfiltered ineligible hits (removed by authority filtering): **1**
- evidence-document diversity (distinct docs in authority-aware top-K): **3**
- vector outcome: **partial**, authority correct: **True**
- latency: resolver 0.119012s, authority-aware 0.008618s, unfiltered 0.008647s, total 0.136276s


### Q05_three_hop_procedure_of_obligation -- distributed_multi_hop_lookup

> Which currently effective operating procedure implements the control that satisfies Obligation O-31?

- intent: `current`, as_of_date: `2026-06-01`, top_k: 4
- eligible revisions (cross-document union): `['adj_rev1', 'app_rev2', 'ctl_rev2', 'obl_rev2', 'prc_rev2', 'svc_rev1']`
- required facts: `['F_obl_current', 'F_ctl_current', 'F_prc_current']`
- forbidden facts: `['F_obl_historical', 'F_ctl_historical', 'F_prc_historical', 'F_ctl_draft', 'F_adj_obl', 'F_adj_ctl', 'F_adj_prc']`
- authority-aware hits (ranked documents): `['OBLIGATION-REGISTER', 'CONTROL-LIBRARY', 'SERVICE-CATALOGUE', 'PROCEDURE-CATALOGUE']`
- unfiltered hits (ranked documents): `['OBLIGATION-REGISTER', 'OBLIGATION-REGISTER', 'CONTROL-LIBRARY', 'CONTROL-LIBRARY']`
- required-fact coverage@4: **1.00** (ALL required retrieved)
- complete relationship chain represented: **True**
- MRR: 1.000, nDCG@4: 0.967
- authority leakage (authority-aware, must be 0): **0**
- forbidden facts appearing in authority-aware hits: `[]` (adjacent-domain lexical distractors are eligible and not an authority failure)
- unfiltered ineligible hits (removed by authority filtering): **3**
- evidence-document diversity (distinct docs in authority-aware top-K): **4**
- vector outcome: **solved**, authority correct: **True**
- latency: resolver 0.113930s, authority-aware 0.009233s, unfiltered 0.009051s, total 0.132214s


### Q06_four_hop_procedure_of_app -- distributed_multi_hop_lookup

> Which operating procedure ultimately supports application APP-224510?

- intent: `current`, as_of_date: `2026-06-01`, top_k: 5
- eligible revisions (cross-document union): `['adj_rev1', 'app_rev2', 'ctl_rev2', 'obl_rev2', 'prc_rev2', 'svc_rev1']`
- required facts: `['F_app_current', 'F_svc', 'F_obl_current', 'F_ctl_current', 'F_prc_current']`
- forbidden facts: `['F_app_historical', 'F_obl_historical', 'F_ctl_historical', 'F_prc_historical', 'F_ctl_draft', 'F_adj_app', 'F_adj_svc', 'F_adj_obl', 'F_adj_ctl', 'F_adj_prc']`
- authority-aware hits (ranked documents): `['APP-PORTFOLIO', 'PROCEDURE-CATALOGUE', 'ADJACENT-DOMAIN', 'CONTROL-LIBRARY', 'SERVICE-CATALOGUE']`
- unfiltered hits (ranked documents): `['APP-PORTFOLIO', 'APP-PORTFOLIO', 'PROCEDURE-CATALOGUE', 'PROCEDURE-CATALOGUE', 'CONTROL-LIBRARY']`
- required-fact coverage@5: **0.80** (PARTIAL / none)
- complete relationship chain represented: **False**
- MRR: 1.000, nDCG@5: 0.830
- authority leakage (authority-aware, must be 0): **0**
- forbidden facts appearing in authority-aware hits: `['F_adj_prc']` (adjacent-domain lexical distractors are eligible and not an authority failure)
- unfiltered ineligible hits (removed by authority filtering): **3**
- evidence-document diversity (distinct docs in authority-aware top-K): **5**
- vector outcome: **partial**, authority correct: **True**
- latency: resolver 0.110955s, authority-aware 0.010611s, unfiltered 0.009460s, total 0.131026s


### Q07_consolidation_payment_settlement -- relationship_consolidation

> Which current applications, obligations, controls and procedures are connected to the Payment Settlement business service?

- intent: `current`, as_of_date: `2026-06-01`, top_k: 5
- eligible revisions (cross-document union): `['adj_rev1', 'app_rev2', 'ctl_rev2', 'obl_rev2', 'prc_rev2', 'svc_rev1']`
- required facts: `['F_app_current', 'F_svc', 'F_obl_current', 'F_ctl_current', 'F_prc_current']`
- forbidden facts: `['F_app_historical', 'F_obl_historical', 'F_ctl_historical', 'F_prc_historical', 'F_ctl_draft', 'F_adj_app', 'F_adj_svc', 'F_adj_obl', 'F_adj_ctl', 'F_adj_prc']`
- authority-aware hits (ranked documents): `['SERVICE-CATALOGUE', 'APP-PORTFOLIO', 'ADJACENT-DOMAIN', 'OBLIGATION-REGISTER', 'PROCEDURE-CATALOGUE']`
- unfiltered hits (ranked documents): `['SERVICE-CATALOGUE', 'APP-PORTFOLIO', 'APP-PORTFOLIO', 'ADJACENT-DOMAIN', 'OBLIGATION-REGISTER']`
- required-fact coverage@5: **0.80** (PARTIAL / none)
- complete relationship chain represented: **False**
- MRR: 1.000, nDCG@5: 0.830
- authority leakage (authority-aware, must be 0): **0**
- forbidden facts appearing in authority-aware hits: `['F_adj_prc']` (adjacent-domain lexical distractors are eligible and not an authority failure)
- unfiltered ineligible hits (removed by authority filtering): **1**
- evidence-document diversity (distinct docs in authority-aware top-K): **5**
- vector outcome: **partial**, authority correct: **True**
- latency: resolver 0.101527s, authority-aware 0.008393s, unfiltered 0.008182s, total 0.118101s


### Q08_distractor_resistance_current_control -- distractor_resistance

> Which control currently satisfies Obligation O-31, excluding any superseded or proposed controls?

- intent: `current`, as_of_date: `2026-06-01`, top_k: 3
- eligible revisions (cross-document union): `['adj_rev1', 'app_rev2', 'ctl_rev2', 'obl_rev2', 'prc_rev2', 'svc_rev1']`
- required facts: `['F_obl_current']`
- forbidden facts: `['F_obl_historical', 'F_ctl_draft', 'F_adj_obl']`
- authority-aware hits (ranked documents): `['OBLIGATION-REGISTER', 'CONTROL-LIBRARY', 'SERVICE-CATALOGUE']`
- unfiltered hits (ranked documents): `['OBLIGATION-REGISTER', 'OBLIGATION-REGISTER', 'CONTROL-LIBRARY']`
- required-fact coverage@3: **1.00** (ALL required retrieved)
- complete relationship chain represented: **True**
- MRR: 1.000, nDCG@3: 1.000
- authority leakage (authority-aware, must be 0): **0**
- forbidden facts appearing in authority-aware hits: `[]` (adjacent-domain lexical distractors are eligible and not an authority failure)
- unfiltered ineligible hits (removed by authority filtering): **2**
- evidence-document diversity (distinct docs in authority-aware top-K): **3**
- vector outcome: **solved**, authority correct: **True**
- latency: resolver 0.106378s, authority-aware 0.007134s, unfiltered 0.007283s, total 0.120794s


### Q09_current_authority_app -- current_authority_relationship_lookup

> Which application currently supports the Payment Settlement business service?

- intent: `current`, as_of_date: `2026-06-01`, top_k: 3
- eligible revisions (cross-document union): `['adj_rev1', 'app_rev2', 'ctl_rev2', 'obl_rev2', 'prc_rev2', 'svc_rev1']`
- required facts: `['F_app_current']`
- forbidden facts: `['F_app_historical']`
- authority-aware hits (ranked documents): `['APP-PORTFOLIO', 'SERVICE-CATALOGUE', 'ADJACENT-DOMAIN']`
- unfiltered hits (ranked documents): `['APP-PORTFOLIO', 'APP-PORTFOLIO', 'SERVICE-CATALOGUE']`
- required-fact coverage@3: **1.00** (ALL required retrieved)
- complete relationship chain represented: **True**
- MRR: 1.000, nDCG@3: 1.000
- authority leakage (authority-aware, must be 0): **0**
- forbidden facts appearing in authority-aware hits: `[]` (adjacent-domain lexical distractors are eligible and not an authority failure)
- unfiltered ineligible hits (removed by authority filtering): **1**
- evidence-document diversity (distinct docs in authority-aware top-K): **3**
- vector outcome: **solved**, authority correct: **True**
- latency: resolver 0.105558s, authority-aware 0.008530s, unfiltered 0.007420s, total 0.121508s


### Q10_historical_procedure_of_obligation -- historical_comparison

> As of 2021, which operating procedure implemented the control that satisfied Obligation O-31?

- intent: `as_of`, as_of_date: `2021-06-01`, top_k: 4
- eligible revisions (cross-document union): `['adj_rev1', 'app_rev1', 'ctl_rev1', 'obl_rev1', 'prc_rev1', 'svc_rev1']`
- required facts: `['F_obl_historical', 'F_ctl_historical', 'F_prc_historical']`
- forbidden facts: `['F_obl_current', 'F_ctl_current', 'F_prc_current']`
- authority-aware hits (ranked documents): `['OBLIGATION-REGISTER', 'SERVICE-CATALOGUE', 'PROCEDURE-CATALOGUE', 'CONTROL-LIBRARY']`
- unfiltered hits (ranked documents): `['OBLIGATION-REGISTER', 'OBLIGATION-REGISTER', 'SERVICE-CATALOGUE', 'PROCEDURE-CATALOGUE']`
- required-fact coverage@4: **1.00** (ALL required retrieved)
- complete relationship chain represented: **True**
- MRR: 1.000, nDCG@4: 0.906
- authority leakage (authority-aware, must be 0): **0**
- forbidden facts appearing in authority-aware hits: `[]` (adjacent-domain lexical distractors are eligible and not an authority failure)
- unfiltered ineligible hits (removed by authority filtering): **2**
- evidence-document diversity (distinct docs in authority-aware top-K): **4**
- vector outcome: **solved**, authority correct: **True**
- latency: resolver 0.096839s, authority-aware 0.008086s, unfiltered 0.007944s, total 0.112869s


### Q11_historical_app_of_service -- historical_comparison

> As of 2021, which application supported the Payment Settlement business service?

- intent: `as_of`, as_of_date: `2021-06-01`, top_k: 3
- eligible revisions (cross-document union): `['adj_rev1', 'app_rev1', 'ctl_rev1', 'obl_rev1', 'prc_rev1', 'svc_rev1']`
- required facts: `['F_app_historical']`
- forbidden facts: `['F_app_current']`
- authority-aware hits (ranked documents): `['APP-PORTFOLIO', 'SERVICE-CATALOGUE', 'ADJACENT-DOMAIN']`
- unfiltered hits (ranked documents): `['APP-PORTFOLIO', 'APP-PORTFOLIO', 'SERVICE-CATALOGUE']`
- required-fact coverage@3: **1.00** (ALL required retrieved)
- complete relationship chain represented: **True**
- MRR: 1.000, nDCG@3: 1.000
- authority leakage (authority-aware, must be 0): **0**
- forbidden facts appearing in authority-aware hits: `[]` (adjacent-domain lexical distractors are eligible and not an authority failure)
- unfiltered ineligible hits (removed by authority filtering): **1**
- evidence-document diversity (distinct docs in authority-aware top-K): **3**
- vector outcome: **solved**, authority correct: **True**
- latency: resolver 0.111495s, authority-aware 0.008288s, unfiltered 0.007913s, total 0.127697s


### Q12_draft_proposed_control -- draft_lookup

> Which proposed draft control is under consideration in the Control Library?

- intent: `draft`, as_of_date: `2026-06-01`, top_k: 3
- eligible revisions (cross-document union): `['ctl_rev3']`
- required facts: `['F_ctl_draft']`
- forbidden facts: `['F_ctl_current']`
- authority-aware hits (ranked documents): `['CONTROL-LIBRARY']`
- unfiltered hits (ranked documents): `['CONTROL-LIBRARY', 'CONTROL-LIBRARY', 'CONTROL-LIBRARY']`
- required-fact coverage@3: **1.00** (ALL required retrieved)
- complete relationship chain represented: **True**
- MRR: 1.000, nDCG@3: 1.000
- authority leakage (authority-aware, must be 0): **0**
- forbidden facts appearing in authority-aware hits: `[]` (adjacent-domain lexical distractors are eligible and not an authority failure)
- unfiltered ineligible hits (removed by authority filtering): **2**
- evidence-document diversity (distinct docs in authority-aware top-K): **1**
- vector outcome: **solved**, authority correct: **True**
- latency: resolver 0.024154s, authority-aware 0.007301s, unfiltered 0.008186s, total 0.039641s


## What this benchmark proves / does not prove

- **Proves**: the corpus genuinely distributes each multi-hop relationship
  across separate documents (no chunk holds a pre-assembled answer);
  authority filtering (current/historical/draft) happens BEFORE vector
  ranking; and it measures exactly how much of each distributed chain a
  Vector baseline recovers within a fixed evidence budget.
- **Does not prove** that a graph projection is better -- no graph is
  built here. It only qualifies a fair, frozen comparison harness (see
  the contract's `fairness_contract`) and records the Vector baseline a
  future graph must be measured against under identical conditions.
- This is a small, controlled corpus: with only a handful of
  authority-eligible chunks per query, the vector recall ceiling is
  easy to reach, so absolute scores overstate what Vector would achieve
  on a large corpus. The value is the methodology and the honest
  per-question breakdown, not the headline numbers.
