# Stage 7A.2 -- Auditable Vector-RAG Answer Baseline: Scorecard

Generated from a single in-memory `AnswerEvaluationRun` -- this Markdown
and `reports/stage7a2_vector_answer_results.json` come from the SAME
execution, never two separate runs.

`answer_model`: `gpt-4o-mini`
`generated_at`: `2026-08-01T19:16:53.495446+00:00`
`retrieval_source`: `C:\Users\Admin\dev\er-lab\reports\stage7a_vector_retrieval_results.json` (Stage 7A.1's own frozen,
committed output -- retrieval was never re-run for this stage)
`retrieval_corpus_profile`: `baseline_demo`
`retrieval_embedding_model`: `sentence-transformers/all-MiniLM-L6-v2`

This report validates citations MECHANICALLY -- exact chunk_id set
membership against the Stage 7A.1 retrieval context and the Stage 6A/6B
gold evidence catalog. No LLM or semantic judge scores anything here.
Answer-TEXT correctness is a separate, explicitly human-review field on
every question result (`answer_text_correctness_human_review`,
currently `"not_reviewed"` for all 12 questions in this baseline run) --
never silently assumed or auto-graded.

## Aggregate scorecard (across 12 questions)

| Metric | Value |
|---|---:|
| Total invalid citations | 0 |
| Total unresolved-provenance citations | 0 |
| Mean required-fact citation coverage rate | 95.8% |
| Mean forbidden-fact citation rate | 54.2% |
| Uncited / total claims | 0 / 26 |
| Mean citation completeness | 100.0% |
| Evidence-sufficiency accuracy (scored questions) | 100.0% (1 of 12 questions had incomplete retrieval, the only case this accuracy is scored) |
| Total input tokens | 18143 |
| Total output tokens | 2243 |
| Total estimated cost (USD) | $0.004067 |
| Mean answer latency | 2.386s |

`n/a` means no applicable denominator (e.g. a question with zero
available required facts to score coverage against), never a misleading
0%/0 value.

## Per-question summary

★ marks the 7 questions Stage 7A.2's own spec calls out as exposing
the two real Stage 7A.1 findings (required/forbidden evidence
co-located in the same chunk; the RTO/RPO table chunk absent from top-5
for the consolidation question).

| Question | Difficulty | Evidence sufficient | Req. fact coverage | Forbidden cited | Invalid citations | Uncited/total claims | Sufficiency accuracy | Latency |
|---|---|---|---:|---:|---:|---:|---|---:|
| Q_DIRECT_001 ★ | direct | yes | 100.0% | 100.0% | 0 | 0/1 | n/a | 2.939s |
| Q_DIRECT_002 | direct | yes | 100.0% | 0.0% | 0 | 0/2 | n/a | 1.538s |
| Q_DIRECT_003 ★ | direct | yes | 100.0% | 100.0% | 0 | 0/1 | n/a | 1.852s |
| Q_DIRECT_004 | direct | yes | 100.0% | 0.0% | 0 | 0/1 | n/a | 1.230s |
| Q_DISTRACTOR_001 ★ | distractor_sensitive | yes | 100.0% | 100.0% | 0 | 0/2 | n/a | 2.517s |
| Q_DISTRACTOR_002 ★ | distractor_sensitive | yes | 100.0% | 100.0% | 0 | 0/2 | n/a | 2.061s |
| Q_DISTRACTOR_003 ★ | distractor_sensitive | yes | 100.0% | 100.0% | 0 | 0/1 | n/a | 1.252s |
| Q_RELATIONAL_001 | relational | yes | 100.0% | 0.0% | 0 | 0/2 | n/a | 1.803s |
| Q_RELATIONAL_002 | relational | yes | 100.0% | 0.0% | 0 | 0/2 | n/a | 2.131s |
| Q_MULTIHOP_001 ★ | multi_hop | yes | 100.0% | 100.0% | 0 | 0/5 | n/a | 4.145s |
| Q_MULTIHOP_002 | multi_hop | yes | 100.0% | 0.0% | 0 | 0/2 | n/a | 2.473s |
| Q_CONSOLIDATION_001 ★ | consolidation | no | 50.0% | 50.0% | 0 | 0/5 | yes | 4.693s |

## Highlighted questions (detail)

### Q_DIRECT_001 (direct)

**Question:** Which application supports the Payment Settlement business service?

**Answer rubric:** Correct answer names APP-224510 as the supporting application, sourced from P_001. The decommissioned predecessor APP-224499, mentioned only in distractor paragraph D_001, must not be cited as the answer.

**Generated answer:** The application that supports the Payment Settlement business service is APP-224510.

**Evidence sufficient (model-reported):** yes

**Required facts cited:** P_001

**Required facts NOT cited:** (none)

**Forbidden facts cited (should be empty):** D_001

**Invalid citations:** 0

**Evidence-sufficiency accuracy:** n/a (scored only when retrieval did not return all required facts)

### Q_DIRECT_003 (direct)

**Question:** What Recovery Time Objective (RTO) is documented for Payment Settlement?

**Answer rubric:** Correct answer states 4 hours, sourced from the RTO row of T_001 (row 1). The retired/legacy distractor row (T_001 row 3, tied to C-88a) must not be cited as a current RTO/RPO value.

**Generated answer:** The Recovery Time Objective (RTO) for Payment Settlement is documented as 4 hours.

**Evidence sufficient (model-reported):** yes

**Required facts cited:** T_001_r1c0, T_001_r1c1

**Required facts NOT cited:** (none)

**Forbidden facts cited (should be empty):** T_001_r3c0, T_001_r3c1

**Invalid citations:** 0

**Evidence-sufficiency accuracy:** n/a (scored only when retrieval did not return all required facts)

### Q_DISTRACTOR_001 (distractor_sensitive)

**Question:** Which application is currently in scope for Regulatory Obligation O-31: APP-224510 or APP-224499?

**Answer rubric:** Correct answer is APP-224510 (P_001/P_002), the current in-scope application. APP-224499 is the decommissioned predecessor named only in distractor paragraph D_001 and must not be cited as the in-scope application.

**Generated answer:** The application currently in scope for Regulatory Obligation O-31 is APP-224510. APP-224499 was the predecessor system for payment settlement and has been decommissioned.

**Evidence sufficient (model-reported):** yes

**Required facts cited:** P_001, P_002

**Required facts NOT cited:** (none)

**Forbidden facts cited (should be empty):** D_001

**Invalid citations:** 0

**Evidence-sufficiency accuracy:** n/a (scored only when retrieval did not return all required facts)

### Q_DISTRACTOR_002 (distractor_sensitive)

**Question:** Which control currently satisfies Regulatory Obligation O-31: C-88 or C-88a?

**Answer rubric:** Correct answer is Control C-88 (P_003), the current control. C-88a is retired/historical per distractor paragraph D_002 and must not be cited as the current control, despite sharing 'C-88' as a substring.

**Generated answer:** Control C-88 currently satisfies Regulatory Obligation O-31. Control C-88a has been retired and replaced by Control C-88.

**Evidence sufficient (model-reported):** yes

**Required facts cited:** P_003

**Required facts NOT cited:** (none)

**Forbidden facts cited (should be empty):** D_002

**Invalid citations:** 0

**Evidence-sufficiency accuracy:** n/a (scored only when retrieval did not return all required facts)

### Q_DISTRACTOR_003 (distractor_sensitive)

**Question:** In the overlapping-annotation stress fixture, which RTO annotation is the current, primary value: 4h or 6h?

**Answer rubric:** Correct answer cites the 4h RTO annotation (SB_001, labeled 'Primary annotation'). SB_002 ('Superseded annotation... draft, do not use') must not be cited as the current value.

**Generated answer:** The current, primary RTO annotation is 4 hours.

**Evidence sufficient (model-reported):** yes

**Required facts cited:** SB_001

**Required facts NOT cited:** (none)

**Forbidden facts cited (should be empty):** SB_002

**Invalid citations:** 0

**Evidence-sufficiency accuracy:** n/a (scored only when retrieval did not return all required facts)

### Q_MULTIHOP_001 (multi_hop)

**Question:** Trace the full chain from the payment application to the recovery procedure it must follow: which application, which regulatory obligation, which control, and which recovery procedure?

**Answer rubric:** Correct answer chains all four hops: APP-224510 (P_001) -> in scope for O-31 (P_002) -> satisfied by Control C-88 (P_003) -> which mandates Recovery Procedure P-205 (P_004). The decommissioned APP-224499 (D_001) or retired C-88a (D_002) must not be substituted at any hop.

**Generated answer:** The full chain from the payment application to the recovery procedure is as follows: The application is APP-224510, which supports the Payment Settlement business service. It is in scope for Regulatory Obligation O-31, which is satisfied by Control C-88. Control C-88 mandates Recovery Procedure P-205 for critical payment-processing applications. Upon incident detection, Recovery Procedure P-205 must be activated.

**Evidence sufficient (model-reported):** yes

**Required facts cited:** P_001, P_002, P_003, P_004

**Required facts NOT cited:** (none)

**Forbidden facts cited (should be empty):** D_001, D_002

**Invalid citations:** 0

**Evidence-sufficiency accuracy:** n/a (scored only when retrieval did not return all required facts)

### Q_CONSOLIDATION_001 (consolidation)

**Question:** Summarize the Payment Settlement service's resilience posture: application identity, ownership, governing control/obligation, mandated recovery procedure, and documented RTO/RPO.

**Answer rubric:** Correct answer consolidates: APP-224510 (P_001), owned by the Resilience Engineering Team in EMEA (P_005), governed by Control C-88 satisfying O-31 (P_003), which mandates Recovery Procedure P-205 (P_004), with a documented RTO of 4 hours and RPO of 1 hour (T_001 rows 1-2). The decommissioned/retired distractors (D_001, D_002) and the legacy C-88a RPO row (T_001 row 3) must not appear as if they were current facts.

**Generated answer:** The Payment Settlement service's resilience posture includes the following elements: 
- **Application Identity**: The service is supported by application APP-224510.
- **Ownership**: It is owned by the Resilience Engineering Team and operates in EMEA.
- **Governing Control/Obligation**: The service is in scope for Regulatory Obligation O-31, satisfied by Control C-88.
- **Mandated Recovery Procedure**: Control C-88 mandates Recovery Procedure P-205 for critical payment-processing applications.
- **Documented RTO**: The documented RTO target is 4 hours. 

However, the evidence does not provide information about the RPO (Recovery Point Objective), making it insufficient for that part of the answer.

**Evidence sufficient (model-reported):** no

**Required facts cited:** P_001, P_005, P_003, P_004

**Required facts NOT cited:** T_001_r1c0, T_001_r1c1, T_001_r2c0, T_001_r2c1

**Forbidden facts cited (should be empty):** D_001, D_002

**Invalid citations:** 0

**Evidence-sufficiency accuracy:** yes (scored only when retrieval did not return all required facts)


## What this report does NOT establish

- Answer-text correctness of any kind -- see
  `answer_text_correctness_human_review` on each question result
  (`"not_reviewed"` for this baseline run); this report never invents a
  semantic judge for it.
- Any retrieval-quality claim beyond what `reports/stage7a_vector_retrieval_scorecard.md`
  already establishes -- retrieval itself was not re-run or re-scored here.
- Graph RAG, wiki retrieval, vision-enriched ingestion, reranking, hybrid
  retrieval, query decomposition, ADK orchestration -- none implemented
  or used anywhere in this stage.

Full per-question provenance (retrieved chunks, claim citations, raw
validation output) is in `artifacts/stage7a2/question_answers/` and
`reports/stage7a2_vector_answer_results.json`.
