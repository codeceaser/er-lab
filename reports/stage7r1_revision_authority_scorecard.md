# Stage 7R.1/7R.1a -- Revision Authority Scenario Scorecard

Generated from a single in-memory `ScenarioRunResult` -- this Markdown
and `reports/stage7r1_revision_authority_results.json` come from the
SAME execution, replaying `contracts/revision_authority_scenarios_v1.json`
against `InMemoryRevisionAuthorityRepository` (never Postgres -- this
report never requires a database).

`contract_version`: `revision_authority_scenarios_v2`
`generated_at`: `2026-08-02T00:53:18.895854+00:00`
`registration_checks`: 17/17 passed
`transition_checks`: 2/2 passed
`query_scenarios`: 21/21 passed
`all_passed`: **True**

## Registration checks (exact-duplicate / new-candidate behavior)

| Step | Scenario | Symbol | Logical document | Expected new | Actual new | Result |
|---|---|---|---|---|---|---|
| reg_v1 | B_changed_content | v1 | POLICY-RESILIENCE-001 | True | True | PASS |
| reg_v2 | B_changed_content | v2 | POLICY-RESILIENCE-001 | True | True | PASS |
| reg_v3 | — | v3 | POLICY-RESILIENCE-001 | True | True | PASS |
| reg_v3_dup | A_exact_duplicate_upload | v3_duplicate | POLICY-RESILIENCE-001 | False | False | PASS |
| reg_v4 | C_newer_draft_does_not_replace | v4 | POLICY-RESILIENCE-001 | True | True | PASS |
| reg_v4ur | J2_under_review_via_draft_intent | v4_under_review | POLICY-RESILIENCE-001 | True | True | PASS |
| reg_v5 | — | v5 | POLICY-RESILIENCE-001 | True | True | PASS |
| reg_v0 | F_late_upload_old_revision | v0_late_upload | POLICY-RESILIENCE-001 | True | True | PASS |
| reg_w1 | — | w1 | POLICY-WITHDRAWN-DEMO-001 | True | True | PASS |
| reg_c1 | — | c1 | POLICY-CONFLICT-DEMO-001 | True | True | PASS |
| reg_c2 | — | c2 | POLICY-CONFLICT-DEMO-001 | True | True | PASS |
| reg_n1 | N_same_text_different_identity | n1_shares_v2_text | POLICY-SHARED-TEXT-DEMO-001 | True | True | PASS |
| reg_rv3 | — | rv3 | POLICY-ROLLBACK-DEMO-001 | True | True | PASS |
| reg_rv5 | — | rv5 | POLICY-ROLLBACK-DEMO-001 | True | True | PASS |
| reg_m1 | — | m1 | POLICY-MALFORMED-DEMO-001 | True | True | PASS |
| reg_val1 | — | val1 | POLICY-VALIDATION-DEMO-001 | True | True | PASS |
| reg_v6 | — | v6_rollback_demo | POLICY-CORRECTION-DEMO-001 | True | True | PASS |

## Transition checks (expected-to-fail validation)

| Step | Scenario | Op | Logical document | Raised | Error | Result |
|---|---|---|---|---|---|---|
| self_supersede_val1 | self_supersession_rejected | activate | POLICY-VALIDATION-DEMO-001 | True | revision '29752a46d104985101610c1c0d1ee160c3e21bab575c61d66dd1c7cfa5ec7fb0' cannot supersede itself (old_revision_id == new_revision_id) | PASS |
| cross_doc_val1 | cross_document_activation_rejected | activate | POLICY-VALIDATION-DEMO-001 | True | cannot activate '29752a46d104985101610c1c0d1ee160c3e21bab575c61d66dd1c7cfa5ec7fb0' (logical_document_id='POLICY-VALIDATION-DEMO-001') to supersede 'd89ce8672548142297bc4a32c8860385de97871af5687744ab8d74b5d166f498' (logical_document_id='POLICY-RESILIENCE-001') -- a revision may only be superseded by a revision of the SAME logical document | PASS |

## Query scenarios

| Scenario | Intent | As of | Eligible | Integrity error | Result |
|---|---|---|---|---|---|
| C_newer_draft_does_not_replace | current | 2025-06-01 | v3 | no | PASS |
| D_approved_future_not_early | current | 2027-12-31 | v3 | no | PASS |
| E_supersession_boundary_on | current | 2028-01-01 | v5 | no | PASS |
| O_boundary_day_before | current | 2027-12-31 | v3 | no | PASS |
| F_late_upload_old_revision | current | 2026-06-02 | v3 | no | PASS |
| G_current_authoritative_query | current | 2025-06-01 | v3 | no | PASS |
| H_historical_as_of_query | as_of | 2020-06-01 | v2 | no | PASS |
| H2_historical_as_of_before_withdrawal | as_of | 2022-06-01 | w1 | no | PASS |
| I_explicit_comparison_query | comparison | 2025-06-01 | v1, v3, v5 | no | PASS |
| J_explicit_draft_query | draft | 2025-06-01 | v4 | no | PASS |
| J2_under_review_via_draft_intent | draft | 2025-06-01 | v4_under_review | no | PASS |
| K_withdrawn_no_replacement | current | 2025-06-01 | (none) | yes | PASS |
| L_overlapping_effective_revisions | current | 2025-06-01 | (none) | yes | PASS |
| M_pre_effective_authority_correction | comparison | 2025-06-01 | v6_rollback_demo | no | PASS |
| N_same_text_different_identity | draft | 2019-06-02 | n1_shares_v2_text | no | PASS |
| E2_post_effective_rollback_before | as_of | 2027-12-31 | rv3 | no | PASS |
| E2_post_effective_rollback_during | as_of | 2028-03-01 | rv5 | no | PASS |
| E2_post_effective_rollback_after | current | 2028-07-01 | rv3 | no | PASS |
| malformed_record_excluded_not_fatal_comparison | comparison | 2025-06-01 | (none) | no | PASS |
| malformed_record_excluded_not_fatal_draft | draft | 2025-06-01 | (none) | no | PASS |
| duplicate_requested_revision_ids_rejected | comparison | 2025-06-01 | v3 | no | PASS |

## Scenario detail

### C_newer_draft_does_not_replace

A newer draft (v4) exists but must not replace the current effective revision (v3).

- query_intent: `current`, as_of_date: `2025-06-01`
- requested: `[]`
- expected eligible: `['v3']` / actual: `['v3']`
- expected exclusions: `[('v1', 'not_effective_superseded'), ('v2', 'not_effective_superseded'), ('v4', 'not_effective_draft'), ('v4_under_review', 'not_effective_under_review'), ('v5', 'not_effective_approved_future'), ('v0_late_upload', 'not_effective_draft')]` / actual: `[('v1', 'not_effective_superseded'), ('v2', 'not_effective_superseded'), ('v4', 'not_effective_draft'), ('v4_under_review', 'not_effective_under_review'), ('v5', 'not_effective_approved_future'), ('v0_late_upload', 'not_effective_draft')]`
- expected states: `{'v1': 'superseded', 'v2': 'superseded', 'v3': 'effective', 'v4': 'draft', 'v4_under_review': 'under_review', 'v5': 'approved_future', 'v0_late_upload': 'draft'}` / actual: `{'v4': 'draft', 'v0_late_upload': 'draft', 'v5': 'approved_future', 'v1': 'superseded', 'v4_under_review': 'under_review', 'v2': 'superseded', 'v3': 'effective'}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: current query for 'POLICY-RESILIENCE-001' as of 2025-06-01: 1 of 7 revision(s) effective -- d89ce8672548142297bc4a32c8860385de97871af5687744ab8d74b5d166f498
- registry_snapshot_hash: `57bbb007d5c03ea68eb68598fd5e6b9ab1361f659346b3d573a91e7ba95f3e0d`
- **PASS**

### D_approved_future_not_early

v5 is approved with a future effective_from (2028-01-01); as of 2027-12-31 it must NOT be current.

- query_intent: `current`, as_of_date: `2027-12-31`
- requested: `[]`
- expected eligible: `['v3']` / actual: `['v3']`
- expected exclusions: `[('v5', 'not_effective_approved_future')]` / actual: `[('v5', 'not_effective_approved_future')]`
- expected states: `{'v3': 'effective', 'v5': 'approved_future'}` / actual: `{'v5': 'approved_future', 'v3': 'effective'}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: current query for 'POLICY-RESILIENCE-001' as of 2027-12-31: 1 of 7 revision(s) effective -- d89ce8672548142297bc4a32c8860385de97871af5687744ab8d74b5d166f498
- registry_snapshot_hash: `57bbb007d5c03ea68eb68598fd5e6b9ab1361f659346b3d573a91e7ba95f3e0d`
- **PASS**

### E_supersession_boundary_on

On the exact effective_from boundary (2028-01-01), v5 becomes effective and v3 becomes superseded in the SAME atomic transition.

- query_intent: `current`, as_of_date: `2028-01-01`
- requested: `[]`
- expected eligible: `['v5']` / actual: `['v5']`
- expected exclusions: `[('v3', 'not_effective_superseded')]` / actual: `[('v3', 'not_effective_superseded')]`
- expected states: `{'v3': 'superseded', 'v5': 'effective'}` / actual: `{'v5': 'effective', 'v3': 'superseded'}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: current query for 'POLICY-RESILIENCE-001' as of 2028-01-01: 1 of 7 revision(s) effective -- 6ddd50a3ef42a863eb506129a5a9952ae42e1d7d9afb5d7ce619485bf6140a31
- registry_snapshot_hash: `57bbb007d5c03ea68eb68598fd5e6b9ab1361f659346b3d573a91e7ba95f3e0d`
- **PASS**

### O_boundary_day_before

One day before the boundary (2027-12-31), the OLD revision (v3) is still effective -- end-exclusive interval semantics.

- query_intent: `current`, as_of_date: `2027-12-31`
- requested: `[]`
- expected eligible: `['v3']` / actual: `['v3']`
- expected exclusions: `[('v5', 'not_effective_approved_future')]` / actual: `[('v5', 'not_effective_approved_future')]`
- expected states: `{'v3': 'effective', 'v5': 'approved_future'}` / actual: `{'v5': 'approved_future', 'v3': 'effective'}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: current query for 'POLICY-RESILIENCE-001' as of 2027-12-31: 1 of 7 revision(s) effective -- d89ce8672548142297bc4a32c8860385de97871af5687744ab8d74b5d166f498
- registry_snapshot_hash: `57bbb007d5c03ea68eb68598fd5e6b9ab1361f659346b3d573a91e7ba95f3e0d`
- **PASS**

### F_late_upload_old_revision

v0 is registered very late (2026) but never approved/activated -- late upload alone must never grant currency.

- query_intent: `current`, as_of_date: `2026-06-02`
- requested: `[]`
- expected eligible: `['v3']` / actual: `['v3']`
- expected exclusions: `[('v0_late_upload', 'not_effective_draft')]` / actual: `[('v0_late_upload', 'not_effective_draft')]`
- expected states: `{'v3': 'effective', 'v0_late_upload': 'draft'}` / actual: `{'v0_late_upload': 'draft', 'v3': 'effective'}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: current query for 'POLICY-RESILIENCE-001' as of 2026-06-02: 1 of 7 revision(s) effective -- d89ce8672548142297bc4a32c8860385de97871af5687744ab8d74b5d166f498
- registry_snapshot_hash: `57bbb007d5c03ea68eb68598fd5e6b9ab1361f659346b3d573a91e7ba95f3e0d`
- **PASS**

### G_current_authoritative_query

Plain current-authoritative query -- exactly one eligible revision.

- query_intent: `current`, as_of_date: `2025-06-01`
- requested: `[]`
- expected eligible: `['v3']` / actual: `['v3']`
- expected exclusions: `[('v1', 'not_effective_superseded'), ('v2', 'not_effective_superseded'), ('v4', 'not_effective_draft'), ('v4_under_review', 'not_effective_under_review'), ('v5', 'not_effective_approved_future'), ('v0_late_upload', 'not_effective_draft')]` / actual: `[('v1', 'not_effective_superseded'), ('v2', 'not_effective_superseded'), ('v4', 'not_effective_draft'), ('v4_under_review', 'not_effective_under_review'), ('v5', 'not_effective_approved_future'), ('v0_late_upload', 'not_effective_draft')]`
- expected states: `{'v3': 'effective'}` / actual: `{'v3': 'effective'}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: current query for 'POLICY-RESILIENCE-001' as of 2025-06-01: 1 of 7 revision(s) effective -- d89ce8672548142297bc4a32c8860385de97871af5687744ab8d74b5d166f498
- registry_snapshot_hash: `57bbb007d5c03ea68eb68598fd5e6b9ab1361f659346b3d573a91e7ba95f3e0d`
- **PASS**

### H_historical_as_of_query

Historical as-of query resolves the revision that was effective THEN, not now.

- query_intent: `as_of`, as_of_date: `2020-06-01`
- requested: `[]`
- expected eligible: `['v2']` / actual: `['v2']`
- expected exclusions: `[('v1', 'not_effective_superseded'), ('v3', 'not_effective_approved_future')]` / actual: `[('v1', 'not_effective_superseded'), ('v3', 'not_effective_approved_future')]`
- expected states: `{'v1': 'superseded', 'v2': 'effective', 'v3': 'approved_future'}` / actual: `{'v1': 'superseded', 'v2': 'effective', 'v3': 'approved_future'}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: as_of query for 'POLICY-RESILIENCE-001' as of 2020-06-01: 1 of 7 revision(s) effective -- a2c03a3cc2201265ab6516b900df77ba833e89079b9b3a34c30f78b101065699
- registry_snapshot_hash: `57bbb007d5c03ea68eb68598fd5e6b9ab1361f659346b3d573a91e7ba95f3e0d`
- **PASS**

### H2_historical_as_of_before_withdrawal

Item 2: as_of BEFORE the withdrawal date, within the old (now-closed) period, must still resolve effective.

- query_intent: `as_of`, as_of_date: `2022-06-01`
- requested: `[]`
- expected eligible: `['w1']` / actual: `['w1']`
- expected exclusions: `[]` / actual: `[]`
- expected states: `{'w1': 'effective'}` / actual: `{'w1': 'effective'}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: as_of query for 'POLICY-WITHDRAWN-DEMO-001' as of 2022-06-01: 1 of 1 revision(s) effective -- 58baa48e37a0a7dcf1f209ee3fef45b34c95e6c8259f24ca0158c459b0ed41aa
- registry_snapshot_hash: `52aa4edf200c483a6c804c88a2c7536ae755d55926b3977d0b143b6cd9e617bb`
- **PASS**

### I_explicit_comparison_query

Comparison permits superseded/current/future revisions together, retaining their own labels -- never silently picking one.

- query_intent: `comparison`, as_of_date: `2025-06-01`
- requested: `['v1', 'v3', 'v5']`
- expected eligible: `['v1', 'v3', 'v5']` / actual: `['v1', 'v3', 'v5']`
- expected exclusions: `[]` / actual: `[]`
- expected states: `{'v1': 'superseded', 'v3': 'effective', 'v5': 'approved_future'}` / actual: `{'v1': 'superseded', 'v3': 'effective', 'v5': 'approved_future'}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: comparison query for 'POLICY-RESILIENCE-001': 3 of 3 requested revision(s) eligible
- registry_snapshot_hash: `57bbb007d5c03ea68eb68598fd5e6b9ab1361f659346b3d573a91e7ba95f3e0d`
- **PASS**

### J_explicit_draft_query

Draft intent returns only the explicitly requested draft/under_review revisions -- v3 (effective, not draft) is excluded even though explicitly requested, never silently mixed in.

- query_intent: `draft`, as_of_date: `2025-06-01`
- requested: `['v4', 'v3']`
- expected eligible: `['v4']` / actual: `['v4']`
- expected exclusions: `[('v3', 'not_eligible_for_draft_intent')]` / actual: `[('v3', 'not_eligible_for_draft_intent')]`
- expected states: `{'v4': 'draft'}` / actual: `{'v4': 'draft'}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: draft query for 'POLICY-RESILIENCE-001': 1 of 2 requested revision(s) eligible
- registry_snapshot_hash: `57bbb007d5c03ea68eb68598fd5e6b9ab1361f659346b3d573a91e7ba95f3e0d`
- **PASS**

### J2_under_review_via_draft_intent

under_review is ALSO a legitimate draft-intent result -- v4_under_review must be eligible.

- query_intent: `draft`, as_of_date: `2025-06-01`
- requested: `['v4_under_review']`
- expected eligible: `['v4_under_review']` / actual: `['v4_under_review']`
- expected exclusions: `[]` / actual: `[]`
- expected states: `{'v4_under_review': 'under_review'}` / actual: `{'v4_under_review': 'under_review'}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: draft query for 'POLICY-RESILIENCE-001': 1 of 1 requested revision(s) eligible
- registry_snapshot_hash: `57bbb007d5c03ea68eb68598fd5e6b9ab1361f659346b3d573a91e7ba95f3e0d`
- **PASS**

### K_withdrawn_no_replacement

current/as_of ON/AFTER the withdrawal date: fails closed, never silently returns nothing as if that were a normal empty result.

- query_intent: `current`, as_of_date: `2025-06-01`
- requested: `[]`
- expected eligible: `[]` / actual: `[]`
- expected exclusions: `[]` / actual: `[]`
- expected states: `{'w1': 'withdrawn'}` / actual: `{'w1': 'withdrawn'}`
- integrity_error expected: `True` (code `no_effective_revision`) / actual: `logical_document_id='POLICY-WITHDRAWN-DEMO-001' has no authoritative effective revision as of 2025-06-01` (code `no_effective_revision`)
- resolution_explanation: logical_document_id='POLICY-WITHDRAWN-DEMO-001' has no authoritative effective revision as of 2025-06-01
- registry_snapshot_hash: `52aa4edf200c483a6c804c88a2c7536ae755d55926b3977d0b143b6cd9e617bb`
- **PASS**

### L_overlapping_effective_revisions

Two revisions simultaneously effective -- fails closed rather than silently choosing one.

- query_intent: `current`, as_of_date: `2025-06-01`
- requested: `[]`
- expected eligible: `[]` / actual: `[]`
- expected exclusions: `[]` / actual: `[]`
- expected states: `{'c1': 'effective', 'c2': 'effective'}` / actual: `{'c1': 'effective', 'c2': 'effective'}`
- integrity_error expected: `True` (code `overlapping_effective_revisions`) / actual: `2 revisions of 'POLICY-CONFLICT-DEMO-001' are simultaneously effective as of 2025-06-01: ['59cfbadb767dfef58bd35636f2eb3b70515a62f9e717f1269a0afad3ce0ed1fd', 'eb3d8cbb2b37f0503ba851becefcc9a5e7eb0ce1bff7494d7772d8b86c6fd124'] -- refusing to silently choose one` (code `overlapping_effective_revisions`)
- resolution_explanation: 2 revisions of 'POLICY-CONFLICT-DEMO-001' are simultaneously effective as of 2025-06-01: ['59cfbadb767dfef58bd35636f2eb3b70515a62f9e717f1269a0afad3ce0ed1fd', 'eb3d8cbb2b37f0503ba851becefcc9a5e7eb0ce1bff7494d7772d8b86c6fd124'] -- refusing to silently choose one
- registry_snapshot_hash: `86b931cb7cd0584a8e3eafd0494970c283e2f31c500c96febc1a59a736e5f6b0`
- **PASS**

### M_pre_effective_authority_correction

v6 was approved-future then RETRACTED (closure_reason=correction) before it ever took effect -- comparison shows it back in draft, and the correction never touches v3/v5's own effective windows.

- query_intent: `comparison`, as_of_date: `2025-06-01`
- requested: `['v6_rollback_demo']`
- expected eligible: `['v6_rollback_demo']` / actual: `['v6_rollback_demo']`
- expected exclusions: `[]` / actual: `[]`
- expected states: `{'v6_rollback_demo': 'draft'}` / actual: `{'v6_rollback_demo': 'draft'}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: comparison query for 'POLICY-CORRECTION-DEMO-001': 1 of 1 requested revision(s) eligible
- registry_snapshot_hash: `82cc422d574b3c0cd7316bfda6f440cfc9899ddd4524e234964376b29eba4273`
- **PASS**

### N_same_text_different_identity

Byte-identical content under a DIFFERENT logical_document_id gets a fully independent revision identity.

- query_intent: `draft`, as_of_date: `2019-06-02`
- requested: `['n1_shares_v2_text']`
- expected eligible: `['n1_shares_v2_text']` / actual: `['n1_shares_v2_text']`
- expected exclusions: `[]` / actual: `[]`
- expected states: `{'n1_shares_v2_text': 'draft'}` / actual: `{'n1_shares_v2_text': 'draft'}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: draft query for 'POLICY-SHARED-TEXT-DEMO-001': 1 of 1 requested revision(s) eligible
- registry_snapshot_hash: `1368272dd17be20bd62a0292ed894fb8c8b8a464ef08da54365b99cb298ed9d1`
- **PASS**

### E2_post_effective_rollback_before

Item 3: as_of 2027-12-31 (before rv5 ever existed) -> rv3.

- query_intent: `as_of`, as_of_date: `2027-12-31`
- requested: `[]`
- expected eligible: `['rv3']` / actual: `['rv3']`
- expected exclusions: `[('rv5', 'not_effective_approved_future')]` / actual: `[('rv5', 'not_effective_approved_future')]`
- expected states: `{'rv3': 'effective', 'rv5': 'approved_future'}` / actual: `{'rv5': 'approved_future', 'rv3': 'effective'}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: as_of query for 'POLICY-ROLLBACK-DEMO-001' as of 2027-12-31: 1 of 2 revision(s) effective -- c356a6494a3c204365334d4056a91c8614cdf98f95c55eaccd818eac34bd028f
- registry_snapshot_hash: `f4e011f4bdfc78f2692026eafb34d6e4f694c5054ffb9f07b33fa0f7c0c392b4`
- **PASS**

### E2_post_effective_rollback_during

Item 3: as_of 2028-03-01 (rv5's own window, before rollback) -> rv5.

- query_intent: `as_of`, as_of_date: `2028-03-01`
- requested: `[]`
- expected eligible: `['rv5']` / actual: `['rv5']`
- expected exclusions: `[('rv3', 'not_effective_approved_future')]` / actual: `[('rv3', 'not_effective_approved_future')]`
- expected states: `{'rv3': 'approved_future', 'rv5': 'effective'}` / actual: `{'rv5': 'effective', 'rv3': 'approved_future'}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: as_of query for 'POLICY-ROLLBACK-DEMO-001' as of 2028-03-01: 1 of 2 revision(s) effective -- 998f28d599eab3274b6decc4ac53c82bd6e78e386f4fb6d1c91245e67f137903
- registry_snapshot_hash: `f4e011f4bdfc78f2692026eafb34d6e4f694c5054ffb9f07b33fa0f7c0c392b4`
- **PASS**

### E2_post_effective_rollback_after

Item 3: current/as_of 2028-07-01 (after rollback) -> REINSTATED rv3, rv3's own SECOND authority period.

- query_intent: `current`, as_of_date: `2028-07-01`
- requested: `[]`
- expected eligible: `['rv3']` / actual: `['rv3']`
- expected exclusions: `[('rv5', 'not_effective_superseded')]` / actual: `[('rv5', 'not_effective_superseded')]`
- expected states: `{'rv3': 'effective', 'rv5': 'superseded'}` / actual: `{'rv5': 'superseded', 'rv3': 'effective'}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: current query for 'POLICY-ROLLBACK-DEMO-001' as of 2028-07-01: 1 of 2 revision(s) effective -- c356a6494a3c204365334d4056a91c8614cdf98f95c55eaccd818eac34bd028f
- registry_snapshot_hash: `f4e011f4bdfc78f2692026eafb34d6e4f694c5054ffb9f07b33fa0f7c0c392b4`
- **PASS**

### malformed_record_excluded_not_fatal_comparison

A revision with a genuinely malformed record (draft status + a real, non-zero-width period -- 'effective revision is not approved') is EXCLUDED individually under comparison intent, never aborting the whole query.

- query_intent: `comparison`, as_of_date: `2025-06-01`
- requested: `['m1']`
- expected eligible: `[]` / actual: `[]`
- expected exclusions: `[('m1', 'malformed_authority_record')]` / actual: `[('m1', 'malformed_authority_record')]`
- expected states: `{}` / actual: `{}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: comparison query for 'POLICY-MALFORMED-DEMO-001': 0 of 1 requested revision(s) eligible
- registry_snapshot_hash: `614123fbd46de19bc5ce46f51dd6b9546080ae99b0c06aa55927e4dea0122f45`
- **PASS**

### malformed_record_excluded_not_fatal_draft

The SAME malformed revision is EXCLUDED individually under draft intent too, never aborting the whole query.

- query_intent: `draft`, as_of_date: `2025-06-01`
- requested: `['m1']`
- expected eligible: `[]` / actual: `[]`
- expected exclusions: `[('m1', 'malformed_authority_record')]` / actual: `[('m1', 'malformed_authority_record')]`
- expected states: `{}` / actual: `{}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: draft query for 'POLICY-MALFORMED-DEMO-001': 0 of 1 requested revision(s) eligible
- registry_snapshot_hash: `614123fbd46de19bc5ce46f51dd6b9546080ae99b0c06aa55927e4dea0122f45`
- **PASS**

### duplicate_requested_revision_ids_rejected

Item 6: requesting the same revision id twice under comparison intent deduplicates deterministically -- one eligible entry, one duplicate_request exclusion, never two eligible entries.

- query_intent: `comparison`, as_of_date: `2025-06-01`
- requested: `['v3', 'v3']`
- expected eligible: `['v3']` / actual: `['v3']`
- expected exclusions: `[('v3', 'duplicate_request')]` / actual: `[('v3', 'duplicate_request')]`
- expected states: `{'v3': 'effective'}` / actual: `{'v3': 'effective'}`
- integrity_error expected: `False` (code `None`) / actual: `None` (code `None`)
- resolution_explanation: comparison query for 'POLICY-RESILIENCE-001': 1 of 2 requested revision(s) eligible
- registry_snapshot_hash: `57bbb007d5c03ea68eb68598fd5e6b9ab1361f659346b3d573a91e7ba95f3e0d`
- **PASS**

## What this report does NOT establish

- Any wiring into Stage 7A.1 retrieval -- this stage never filters or
  reranks a real search result; that is Stage 7R.2, after review.
- Real Postgres persistence -- see the separate, skippable
  `test_real_postgres_revision_authority_repository` integration test
  for that (not exercised by this report).
