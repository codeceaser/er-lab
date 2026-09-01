# Stage 7C.2 — Wiki hub retrieval / navigation qualification

> **Read-only measurement over the frozen Stage 7C.0 + 7C.1 artifacts.** Zero compiler or
> extractor calls; the 22 frozen facet vectors were loaded, never regenerated; nothing in
> Stage 7C.0 or 7C.1 was written.
>
> **Gate A: UNREACHABLE -- Gate Q = FAIL (Q-5, Q-7, Q-8).** Every W1-D / W1-FULL / N_advisory result below
> carries **`NON-QUALIFYING / DIAGNOSTIC ONLY`**. **D0 is NOT labelled** — it consumes no W1-derived
> model output, so Gate Q's failure does not reach it.

| Frozen identity | Value |
|---|---|
| projection_hash | `4162fa515cf29d09391c0d963b76c7e6…` |
| verdict_set_sha256 | `d49cc8643388f830ffbcf5097faa8335…` |
| compiler_contract_sha256 | `35ccad855b10e6e8c08f6699136dff59…` |
| embedding_set_sha256 | `bbc233f68a6b7ccdbdebabf9dfe6e35f…` |
| facets / pages / links / vectors | 22 / 13 / 30 / 22 |
| scorer (imported by identity) | `ingestion_bench.cross_document_benchmark.benchmark_runner._evaluate_question` |

## 1. Outcomes per arm

| Arm | solved | partial | failed | Label |
|---|---|---|---|---|
| V | 9 | 3 | 0 | — |
| W0 | 9 | 3 | 0 | — |
| D0 | 7 | 5 | 0 | — |
| W1-D | 6 | 5 | 1 | `NON-QUALIFYING / DIAGNOSTIC ONLY` |
| W1-FULL | 6 | 5 | 1 | `NON-QUALIFYING / DIAGNOSTIC ONLY` |
| N_advisory | 6 | 5 | 1 | `NON-QUALIFYING / DIAGNOSTIC ONLY` |

**Authority leakage across every arm and question: 0** (any nonzero value is a hard-safety failure).

## 2. Per-question, per-arm

| Question | K | V | W0 | D0 | W1-D | W1-FULL |
|---|---|---|---|---|---|---|
| Q01_direct_service_of_app | 3 | solved 1.00 | solved 1.00 | solved 1.00 | solved 1.00 | solved 1.00 |
| Q02_one_hop_control_of_obligation | 3 | solved 1.00 | solved 1.00 | solved 1.00 | solved 1.00 | solved 1.00 |
| Q03_two_hop_obligation_of_app | 3 | solved 1.00 | solved 1.00 | solved 1.00 | solved 1.00 | solved 1.00 |
| Q04_two_hop_control_of_service | 3 | partial 0.50 | partial 0.50 | partial 0.50 | partial 0.50 | partial 0.50 |
| Q05_three_hop_procedure_of_obligation | 4 | solved 1.00 | solved 1.00 | partial 0.33 | partial 0.33 | partial 0.33 |
| Q06_four_hop_procedure_of_app | 5 | partial 0.80 | partial 0.80 | partial 0.40 | partial 0.40 | partial 0.40 |
| Q07_consolidation_payment_settlement | 5 | partial 0.80 | partial 0.80 | partial 0.60 | partial 0.60 | partial 0.60 |
| Q08_distractor_resistance_current_control | 3 | solved 1.00 | solved 1.00 | solved 1.00 | failed 0.00 | failed 0.00 |
| Q09_current_authority_app | 3 | solved 1.00 | solved 1.00 | solved 1.00 | solved 1.00 | solved 1.00 |
| Q10_historical_procedure_of_obligation | 4 | solved 1.00 | solved 1.00 | partial 0.33 | partial 0.33 | partial 0.33 |
| Q11_historical_app_of_service | 3 | solved 1.00 | solved 1.00 | solved 1.00 | solved 1.00 | solved 1.00 |
| Q12_draft_proposed_control | 3 | solved 1.00 | solved 1.00 | solved 1.00 | solved 1.00 | solved 1.00 |

*Cell format: outcome + required-fact coverage@K.*

## 3. Attribution — the three required deltas

### W1-D vs D0

*marginal value of W1 semantic seed enrichment*

**W1-D is WORSE than D0 on 1 question(s)**

- improved: none
- regressed: ['Q08_distractor_resistance_current_control']
- identical on every axis: 11/12

### W1-FULL vs W1-D

*marginal value of claim-derived routing*

**W1-FULL and W1-D are MATERIALLY EQUIVALENT (identical on every axis, every question)**

- improved: none
- regressed: none
- identical on every axis: 12/12

### W1-FULL vs D0

*TOTAL marginal value of the LLM-assisted Wiki over the deterministic Wiki*

**W1-FULL is WORSE than D0 on 1 question(s)**

- improved: none
- regressed: ['Q08_distractor_resistance_current_control']
- identical on every axis: 11/12

**D0 vs V** — *marginal value of deterministic Wiki structure over Vector*: D0 is WORSE than V on 4 question(s)

**W1-FULL vs V** — *headline W1 system comparison*: W1-FULL is WORSE than V on 5 question(s)

**W0 vs V** — *frozen control; expected equivalent*: W0 and V are MATERIALLY EQUIVALENT (identical on every axis, every question)

> Never conclude the compiler was unnecessary from a comparison that excludes D0: only W1-FULL vs D0 supports a statement about whether the W1-derived layer was needed.

## 4. Counterfactual suppression diagnostic (Q04 / Q06 / Q07)

**`TRUTH-INFORMED / DIAGNOSTIC ONLY / NOT GATE-A ADMISSIBLE`** — it replaces none of the three attribution deltas.

| Question | links suppressed | natural outcome | suppressed outcome | still reachable |
|---|---|---|---|---|
| Q04_two_hop_control_of_service | 4 | partial 0.50 | partial 0.50 | True |
| Q06_four_hop_procedure_of_app | 8 | partial 0.40 | partial 0.40 | True |
| Q07_consolidation_payment_settlement | 8 | partial 0.60 | partial 0.60 | True |

## 5. Navigation, branching and bounds

| Question | Arm | seeds | pages visited | hops | candidates | branching | page sat. | chunk sat. |
|---|---|---|---|---|---|---|---|---|
| Q01_direct_service_of_app | D0 | 3 | 6 | 4 | 14 | 2.33 | 0.67 | 1.00 |
| Q01_direct_service_of_app | W1-D | 3 | 6 | 4 | 14 | 2.33 | 0.67 | 1.00 |
| Q01_direct_service_of_app | W1-FULL | 3 | 6 | 4 | 22 | 3.67 | 0.67 | 1.00 |
| Q02_one_hop_control_of_obligation | D0 | 3 | 4 | 3 | 12 | 3.00 | 0.44 | 0.67 |
| Q02_one_hop_control_of_obligation | W1-D | 3 | 5 | 3 | 12 | 2.40 | 0.56 | 1.00 |
| Q02_one_hop_control_of_obligation | W1-FULL | 3 | 5 | 3 | 20 | 4.00 | 0.56 | 1.00 |
| Q03_two_hop_obligation_of_app | D0 | 3 | 5 | 4 | 14 | 2.80 | 0.56 | 0.83 |
| Q03_two_hop_obligation_of_app | W1-D | 3 | 5 | 4 | 14 | 2.80 | 0.56 | 0.83 |
| Q03_two_hop_obligation_of_app | W1-FULL | 3 | 5 | 4 | 22 | 4.40 | 0.56 | 0.83 |
| Q04_two_hop_control_of_service | D0 | 3 | 4 | 2 | 9 | 2.25 | 0.44 | 0.67 |
| Q04_two_hop_control_of_service | W1-D | 3 | 4 | 2 | 9 | 2.25 | 0.44 | 0.67 |
| Q04_two_hop_control_of_service | W1-FULL | 3 | 4 | 2 | 15 | 3.75 | 0.44 | 0.67 |
| Q05_three_hop_procedure_of_obligation | D0 | 4 | 4 | 2 | 12 | 3.00 | 0.44 | 0.83 |
| Q05_three_hop_procedure_of_obligation | W1-D | 4 | 5 | 4 | 14 | 2.80 | 0.56 | 0.83 |
| Q05_three_hop_procedure_of_obligation | W1-FULL | 4 | 5 | 4 | 22 | 4.40 | 0.56 | 0.83 |
| Q06_four_hop_procedure_of_app | D0 | 5 | 7 | 4 | 14 | 2.00 | 0.78 | 1.00 |
| Q06_four_hop_procedure_of_app | W1-D | 5 | 7 | 4 | 14 | 2.00 | 0.78 | 1.00 |
| Q06_four_hop_procedure_of_app | W1-FULL | 5 | 7 | 4 | 23 | 3.29 | 0.78 | 1.00 |
| Q07_consolidation_payment_settlement | D0 | 5 | 5 | 2 | 9 | 1.80 | 0.56 | 0.67 |
| Q07_consolidation_payment_settlement | W1-D | 5 | 5 | 2 | 9 | 1.80 | 0.56 | 0.67 |
| Q07_consolidation_payment_settlement | W1-FULL | 5 | 5 | 2 | 15 | 3.00 | 0.56 | 0.67 |
| Q08_distractor_resistance_current_control | D0 | 3 | 3 | 2 | 9 | 3.00 | 0.33 | 0.67 |
| Q08_distractor_resistance_current_control | W1-D | 3 | 5 | 4 | 14 | 2.80 | 0.56 | 0.83 |
| Q08_distractor_resistance_current_control | W1-FULL | 3 | 5 | 4 | 22 | 4.40 | 0.56 | 0.83 |
| Q09_current_authority_app | D0 | 3 | 5 | 4 | 14 | 2.80 | 0.56 | 0.83 |
| Q09_current_authority_app | W1-D | 3 | 5 | 4 | 14 | 2.80 | 0.56 | 0.83 |
| Q09_current_authority_app | W1-FULL | 3 | 5 | 4 | 22 | 4.40 | 0.56 | 0.83 |
| Q10_historical_procedure_of_obligation | D0 | 4 | 5 | 3 | 14 | 2.80 | 0.56 | 0.83 |
| Q10_historical_procedure_of_obligation | W1-D | 4 | 5 | 3 | 12 | 2.40 | 0.56 | 1.00 |
| Q10_historical_procedure_of_obligation | W1-FULL | 4 | 5 | 3 | 19 | 3.80 | 0.56 | 1.00 |
| Q11_historical_app_of_service | D0 | 3 | 5 | 4 | 14 | 2.80 | 0.56 | 0.83 |
| Q11_historical_app_of_service | W1-D | 3 | 5 | 4 | 14 | 2.80 | 0.56 | 0.83 |
| Q11_historical_app_of_service | W1-FULL | 3 | 5 | 4 | 20 | 4.00 | 0.56 | 0.83 |
| Q12_draft_proposed_control | D0 | 2 | 2 | 0 | 1 | 0.50 | 1.00 | 1.00 |
| Q12_draft_proposed_control | W1-D | 2 | 2 | 1 | 1 | 0.50 | 1.00 | 1.00 |
| Q12_draft_proposed_control | W1-FULL | 2 | 2 | 1 | 3 | 1.50 | 1.00 | 1.00 |

> **THIS CORPUS DOES NOT TEST ENTERPRISE-SCALE HUB FAN-OUT. With 6 documents, 11 single-chunk revisions, one cross-document phrase anchor and no structural bridge into the distractor domain, low branching factors are a property of the CORPUS, not evidence that Wiki navigation is well-behaved at scale. No claim about navigation cost at scale may be made from this stage.**

## 6. Branch attribution vs D0

| Question | Arm | seed overlap vs D0 | branch-order divergence vs D0 |
|---|---|---|---|
| Q01_direct_service_of_app | W1-D | 3/3 | 10 |
| Q01_direct_service_of_app | W1-FULL | 3/3 | 20 |
| Q02_one_hop_control_of_obligation | W1-D | 2/3 | 9 |
| Q02_one_hop_control_of_obligation | W1-FULL | 2/3 | 17 |
| Q03_two_hop_obligation_of_app | W1-D | 3/3 | 10 |
| Q03_two_hop_obligation_of_app | W1-FULL | 3/3 | 19 |
| Q04_two_hop_control_of_service | W1-D | 2/3 | 4 |
| Q04_two_hop_control_of_service | W1-FULL | 2/3 | 14 |
| Q05_three_hop_procedure_of_obligation | W1-D | 4/4 | 10 |
| Q05_three_hop_procedure_of_obligation | W1-FULL | 4/4 | 20 |
| Q06_four_hop_procedure_of_app | W1-D | 4/5 | 10 |
| Q06_four_hop_procedure_of_app | W1-FULL | 4/5 | 22 |
| Q07_consolidation_payment_settlement | W1-D | 5/5 | 4 |
| Q07_consolidation_payment_settlement | W1-FULL | 5/5 | 14 |
| Q08_distractor_resistance_current_control | W1-D | 3/3 | 12 |
| Q08_distractor_resistance_current_control | W1-FULL | 3/3 | 20 |
| Q09_current_authority_app | W1-D | 3/3 | 10 |
| Q09_current_authority_app | W1-FULL | 3/3 | 18 |
| Q10_historical_procedure_of_obligation | W1-D | 3/4 | 11 |
| Q10_historical_procedure_of_obligation | W1-FULL | 3/4 | 15 |
| Q11_historical_app_of_service | W1-D | 3/3 | 0 |
| Q11_historical_app_of_service | W1-FULL | 3/3 | 14 |
| Q12_draft_proposed_control | W1-D | 2/2 | 0 |
| Q12_draft_proposed_control | W1-FULL | 2/2 | 2 |

## 7. Frozen Graph attribution (read-only)

Graph was **not** rerun or modified.

| | Expected-fact recall | Precision |
|---|---|---|
| Frozen Stage 7B.1 Graph | 12/15 = 0.80 | 0.86 |
| Frozen Stage 7C.1 W1 | 13/15 = 0.8667 | 22/25 = 0.88 |

> Do NOT claim Wiki extraction is inherently more reliable than Graph extraction: one non-deterministic snapshot per side, one small corpus, no repeated Graph runs, and only approximately aligned recall/precision definitions.

- **Graph:** typed-edge precision; reachability SENSITIVE to a missing inferred edge
- **Wiki:** source-hub redundant connectivity; cost paid as branching ambiguity

## 8. Stop point

This stage stops at the **owner page-quality checkpoint**. Claude does not score page
quality (§8D); the blind six-page W0/W1 packet and its rubric are emitted separately, and
`docs/STAGE7C_WIKI_DECISION.md` is **not** finalized until the owner's ratings are supplied.

Gate A is unreachable. The final Stage 7C outcome will be **Gate B or Gate C** under the
frozen rules, and that selection is owner-dependent — it is not made here.

