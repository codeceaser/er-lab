# Stage 7R.1 -- Revision Authority Scenario Scorecard

Generated from a single in-memory `ScenarioRunResult` -- this Markdown
and `reports/stage7r1_revision_authority_results.json` come from the
SAME execution, replaying `contracts/revision_authority_scenarios_v1.json`
against `InMemoryRevisionAuthorityRepository` (never Postgres -- this
report never requires a database).

`contract_version`: `revision_authority_scenarios_v1`
`generated_at`: `2026-08-01T22:23:38.743476+00:00`
`registration_checks`: 12/12 passed
`query_scenarios`: 13/13 passed
`all_passed`: **True**

## Registration checks (exact-duplicate / new-candidate behavior)

| Step | Scenario | Symbol | Logical document | Expected new | Actual new | Result |
|---|---|---|---|---|---|---|
| reg_v1 | B_changed_content | v1 | POLICY-RESILIENCE-001 | True | True | PASS |
| reg_v2 | B_changed_content | v2 | POLICY-RESILIENCE-001 | True | True | PASS |
| reg_v3 | — | v3 | POLICY-RESILIENCE-001 | True | True | PASS |
| reg_v3_dup | A_exact_duplicate_upload | v3_duplicate | POLICY-RESILIENCE-001 | False | False | PASS |
| reg_v4 | C_newer_draft_does_not_replace | v4 | POLICY-RESILIENCE-001 | True | True | PASS |
| reg_v5 | — | v5 | POLICY-RESILIENCE-001 | True | True | PASS |
| reg_v0 | F_late_upload_old_revision | v0_late_upload | POLICY-RESILIENCE-001 | True | True | PASS |
| reg_v6 | — | v6_rollback_demo | POLICY-RESILIENCE-001 | True | True | PASS |
| reg_w1 | — | w1 | POLICY-WITHDRAWN-DEMO-001 | True | True | PASS |
| reg_c1 | — | c1 | POLICY-CONFLICT-DEMO-001 | True | True | PASS |
| reg_c2 | — | c2 | POLICY-CONFLICT-DEMO-001 | True | True | PASS |
| reg_n1 | N_same_text_different_identity | n1_shares_v2_text | POLICY-SHARED-TEXT-DEMO-001 | True | True | PASS |

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
| I_explicit_comparison_query | comparison | 2025-06-01 | v1, v3, v5 | no | PASS |
| J_explicit_draft_query | draft | 2025-06-01 | v4 | no | PASS |
| K_withdrawn_no_replacement | current | 2025-06-01 | (none) | yes | PASS |
| L_overlapping_effective_revisions | current | 2025-06-01 | (none) | yes | PASS |
| M_authority_correction_rollback | comparison | 2025-06-01 | v3, v5, v6_rollback_demo | no | PASS |
| N_same_text_different_identity | draft | 2019-06-02 | n1_shares_v2_text | no | PASS |

## Scenario detail

### C_newer_draft_does_not_replace

A newer draft (v4) exists but must not replace the current effective revision (v3).

- query_intent: `current`, as_of_date: `2025-06-01`
- requested: `[]`
- expected eligible: `['v3']` / actual: `['v3']`
- expected states: `{'v1': 'superseded', 'v2': 'superseded', 'v3': 'effective', 'v4': 'draft', 'v5': 'approved_future', 'v0_late_upload': 'draft', 'v6_rollback_demo': 'draft'}` / actual: `{'v4': 'draft', 'v0_late_upload': 'draft', 'v6_rollback_demo': 'draft', 'v5': 'approved_future', 'v1': 'superseded', 'v2': 'superseded', 'v3': 'effective'}`
- integrity_error expected: `False` / actual: `None`
- resolution_explanation: current query for 'POLICY-RESILIENCE-001' as of 2025-06-01: 1 of 7 revision(s) effective -- d89ce8672548142297bc4a32c8860385de97871af5687744ab8d74b5d166f498
- registry_snapshot_hash: `8b0a481c2269c38eee52ca6189ecfa9f3bb4f26213c35eabee3b6da06085afad`
- **PASS**

### D_approved_future_not_early

v5 is approved with a future effective_from (2028-01-01); as of 2027-12-31 it must NOT be current.

- query_intent: `current`, as_of_date: `2027-12-31`
- requested: `[]`
- expected eligible: `['v3']` / actual: `['v3']`
- expected states: `{'v3': 'effective', 'v5': 'approved_future'}` / actual: `{'v5': 'approved_future', 'v3': 'effective'}`
- integrity_error expected: `False` / actual: `None`
- resolution_explanation: current query for 'POLICY-RESILIENCE-001' as of 2027-12-31: 1 of 7 revision(s) effective -- d89ce8672548142297bc4a32c8860385de97871af5687744ab8d74b5d166f498
- registry_snapshot_hash: `8b0a481c2269c38eee52ca6189ecfa9f3bb4f26213c35eabee3b6da06085afad`
- **PASS**

### E_supersession_boundary_on

On the exact effective_from boundary (2028-01-01), v5 becomes effective and v3 becomes superseded in the SAME atomic transition (effective_from <= as_of_date < effective_to).

- query_intent: `current`, as_of_date: `2028-01-01`
- requested: `[]`
- expected eligible: `['v5']` / actual: `['v5']`
- expected states: `{'v3': 'superseded', 'v5': 'effective'}` / actual: `{'v5': 'effective', 'v3': 'superseded'}`
- integrity_error expected: `False` / actual: `None`
- resolution_explanation: current query for 'POLICY-RESILIENCE-001' as of 2028-01-01: 1 of 7 revision(s) effective -- 6ddd50a3ef42a863eb506129a5a9952ae42e1d7d9afb5d7ce619485bf6140a31
- registry_snapshot_hash: `8b0a481c2269c38eee52ca6189ecfa9f3bb4f26213c35eabee3b6da06085afad`
- **PASS**

### O_boundary_day_before

One day before the boundary (2027-12-31), the OLD revision (v3) is still effective -- end-exclusive interval semantics.

- query_intent: `current`, as_of_date: `2027-12-31`
- requested: `[]`
- expected eligible: `['v3']` / actual: `['v3']`
- expected states: `{'v3': 'effective', 'v5': 'approved_future'}` / actual: `{'v5': 'approved_future', 'v3': 'effective'}`
- integrity_error expected: `False` / actual: `None`
- resolution_explanation: current query for 'POLICY-RESILIENCE-001' as of 2027-12-31: 1 of 7 revision(s) effective -- d89ce8672548142297bc4a32c8860385de97871af5687744ab8d74b5d166f498
- registry_snapshot_hash: `8b0a481c2269c38eee52ca6189ecfa9f3bb4f26213c35eabee3b6da06085afad`
- **PASS**

### F_late_upload_old_revision

v0 is registered very late (2026) but never approved/activated -- late upload alone must never grant currency.

- query_intent: `current`, as_of_date: `2026-06-02`
- requested: `[]`
- expected eligible: `['v3']` / actual: `['v3']`
- expected states: `{'v3': 'effective', 'v0_late_upload': 'draft'}` / actual: `{'v0_late_upload': 'draft', 'v3': 'effective'}`
- integrity_error expected: `False` / actual: `None`
- resolution_explanation: current query for 'POLICY-RESILIENCE-001' as of 2026-06-02: 1 of 7 revision(s) effective -- d89ce8672548142297bc4a32c8860385de97871af5687744ab8d74b5d166f498
- registry_snapshot_hash: `8b0a481c2269c38eee52ca6189ecfa9f3bb4f26213c35eabee3b6da06085afad`
- **PASS**

### G_current_authoritative_query

Plain current-authoritative query -- exactly one eligible revision.

- query_intent: `current`, as_of_date: `2025-06-01`
- requested: `[]`
- expected eligible: `['v3']` / actual: `['v3']`
- expected states: `{'v3': 'effective'}` / actual: `{'v3': 'effective'}`
- integrity_error expected: `False` / actual: `None`
- resolution_explanation: current query for 'POLICY-RESILIENCE-001' as of 2025-06-01: 1 of 7 revision(s) effective -- d89ce8672548142297bc4a32c8860385de97871af5687744ab8d74b5d166f498
- registry_snapshot_hash: `8b0a481c2269c38eee52ca6189ecfa9f3bb4f26213c35eabee3b6da06085afad`
- **PASS**

### H_historical_as_of_query

Historical as-of query resolves the revision that was effective THEN, not now.

- query_intent: `as_of`, as_of_date: `2020-06-01`
- requested: `[]`
- expected eligible: `['v2']` / actual: `['v2']`
- expected states: `{'v1': 'superseded', 'v2': 'effective', 'v3': 'approved_future'}` / actual: `{'v1': 'superseded', 'v2': 'effective', 'v3': 'approved_future'}`
- integrity_error expected: `False` / actual: `None`
- resolution_explanation: as_of query for 'POLICY-RESILIENCE-001' as of 2020-06-01: 1 of 7 revision(s) effective -- a2c03a3cc2201265ab6516b900df77ba833e89079b9b3a34c30f78b101065699
- registry_snapshot_hash: `8b0a481c2269c38eee52ca6189ecfa9f3bb4f26213c35eabee3b6da06085afad`
- **PASS**

### I_explicit_comparison_query

Comparison permits superseded/current/future revisions together, retaining their own labels -- never silently picking one.

- query_intent: `comparison`, as_of_date: `2025-06-01`
- requested: `['v1', 'v3', 'v5']`
- expected eligible: `['v1', 'v3', 'v5']` / actual: `['v1', 'v3', 'v5']`
- expected states: `{'v1': 'superseded', 'v3': 'effective', 'v5': 'approved_future'}` / actual: `{'v1': 'superseded', 'v3': 'effective', 'v5': 'approved_future'}`
- integrity_error expected: `False` / actual: `None`
- resolution_explanation: comparison query for 'POLICY-RESILIENCE-001': 3 of 3 requested revision(s) found and returned with their own authority labels
- registry_snapshot_hash: `8b0a481c2269c38eee52ca6189ecfa9f3bb4f26213c35eabee3b6da06085afad`
- **PASS**

### J_explicit_draft_query

Draft intent returns only the explicitly requested draft/under_review revisions -- v3 (effective, not draft) is excluded even though explicitly requested, never silently mixed in.

- query_intent: `draft`, as_of_date: `2025-06-01`
- requested: `['v4', 'v3']`
- expected eligible: `['v4']` / actual: `['v4']`
- expected states: `{'v4': 'draft'}` / actual: `{'v4': 'draft'}`
- integrity_error expected: `False` / actual: `None`
- resolution_explanation: draft query for 'POLICY-RESILIENCE-001': 1 of 2 requested revision(s) are draft/under_review and eligible
- registry_snapshot_hash: `8b0a481c2269c38eee52ca6189ecfa9f3bb4f26213c35eabee3b6da06085afad`
- **PASS**

### K_withdrawn_no_replacement

The only revision was withdrawn and no replacement was ever activated -- fails closed, never silently returns nothing as if that were a normal empty result.

- query_intent: `current`, as_of_date: `2025-06-01`
- requested: `[]`
- expected eligible: `[]` / actual: `[]`
- expected states: `{'w1': 'withdrawn'}` / actual: `{'w1': 'withdrawn'}`
- integrity_error expected: `True` / actual: `logical_document_id='POLICY-WITHDRAWN-DEMO-001' has no authoritative effective revision as of 2025-06-01`
- resolution_explanation: logical_document_id='POLICY-WITHDRAWN-DEMO-001' has no authoritative effective revision as of 2025-06-01
- registry_snapshot_hash: `b9dc9fda21d3727efcb3d3962671a867a9640fd7685548eaeb2faf336b7c0812`
- **PASS**

### L_overlapping_effective_revisions

Two revisions independently activated with old=None end up simultaneously effective -- fails closed rather than silently choosing one.

- query_intent: `current`, as_of_date: `2025-06-01`
- requested: `[]`
- expected eligible: `[]` / actual: `[]`
- expected states: `{'c1': 'effective', 'c2': 'effective'}` / actual: `{'c1': 'effective', 'c2': 'effective'}`
- integrity_error expected: `True` / actual: `2 revisions of 'POLICY-CONFLICT-DEMO-001' are simultaneously effective as of 2025-06-01: ['59cfbadb767dfef58bd35636f2eb3b70515a62f9e717f1269a0afad3ce0ed1fd', 'eb3d8cbb2b37f0503ba851becefcc9a5e7eb0ce1bff7494d7772d8b86c6fd124'] -- refusing to silently choose one`
- resolution_explanation: 2 revisions of 'POLICY-CONFLICT-DEMO-001' are simultaneously effective as of 2025-06-01: ['59cfbadb767dfef58bd35636f2eb3b70515a62f9e717f1269a0afad3ce0ed1fd', 'eb3d8cbb2b37f0503ba851becefcc9a5e7eb0ce1bff7494d7772d8b86c6fd124'] -- refusing to silently choose one
- registry_snapshot_hash: `5187522806733f2264885b362798df126c0cf00d60680ad53af9550d38c271c0`
- **PASS**

### M_authority_correction_rollback

v6 was approved-future then rolled back to draft via a second authority decision -- the correction is visible in the audit trail and never touches v3/v5's own effective windows.

- query_intent: `comparison`, as_of_date: `2025-06-01`
- requested: `['v6_rollback_demo', 'v3', 'v5']`
- expected eligible: `['v3', 'v5', 'v6_rollback_demo']` / actual: `['v3', 'v5', 'v6_rollback_demo']`
- expected states: `{'v6_rollback_demo': 'draft', 'v3': 'effective', 'v5': 'approved_future'}` / actual: `{'v6_rollback_demo': 'draft', 'v3': 'effective', 'v5': 'approved_future'}`
- integrity_error expected: `False` / actual: `None`
- resolution_explanation: comparison query for 'POLICY-RESILIENCE-001': 3 of 3 requested revision(s) found and returned with their own authority labels
- registry_snapshot_hash: `8b0a481c2269c38eee52ca6189ecfa9f3bb4f26213c35eabee3b6da06085afad`
- **PASS**

### N_same_text_different_identity

Byte-identical content under a DIFFERENT logical_document_id gets a fully independent revision identity -- proven by resolving it on its own document, unaffected by POLICY-RESILIENCE-001's v2 authority.

- query_intent: `draft`, as_of_date: `2019-06-02`
- requested: `['n1_shares_v2_text']`
- expected eligible: `['n1_shares_v2_text']` / actual: `['n1_shares_v2_text']`
- expected states: `{'n1_shares_v2_text': 'draft'}` / actual: `{'n1_shares_v2_text': 'draft'}`
- integrity_error expected: `False` / actual: `None`
- resolution_explanation: draft query for 'POLICY-SHARED-TEXT-DEMO-001': 1 of 1 requested revision(s) are draft/under_review and eligible
- registry_snapshot_hash: `6b65c1b387f5b866903e8bd441dfb013b33bc4587c0f0bf095b9b11bfdefb11c`
- **PASS**

## What this report does NOT establish

- Any wiring into Stage 7A.1 retrieval -- this stage never filters or
  reranks a real search result; that is Stage 7R.2, after review.
- Real Postgres persistence -- see the separate, skippable
  `test_real_postgres_revision_authority_repository` integration test
  for that (not exercised by this report).
