# Revision Authority Scenarios — Stage 7R.1

## What this document is

This document defines the business behavior of the Stage 7R.1 revision-authority
registry and resolver (`src/ingestion_bench/revision_authority/`), and how
that behavior will later be consumed by each retrieval projection
(Regular Vector RAG, Graph RAG, wiki retrieval).

**This is NOT a document-management/version-control system.** It does not
store or edit document binaries, provide check-in/check-out, manage approval
workflows, replace Documentum or a policy-governance platform, or infer
authority from filenames, upload time, or document text. It persists
authoritative revision metadata *supplied by a consumer or governance
source* and uses it to resolve which already-ingested document revisions
are eligible for a query.

Every scenario below is exercised for real by
`contracts/revision_authority_scenarios_v1.json` and
`scripts/run_stage7r1_revision_scenarios.py` — see
`reports/stage7r1_revision_authority_scorecard.md` for the measured,
passing result, and `tests/test_revision_authority_*.py` for one or more
named pytest tests per scenario. Scenario IDs below match the contract's
own `scenario_id` values exactly.

## Effective interval convention

```
effective_from <= as_of_date < effective_to
```

`effective_from` is inclusive; `effective_to` is exclusive. When
`effective_to` is `null`, the interval has no declared upper bound (open
towards the future until some later revision closes it via
`activate_revision`'s atomic supersession).

## Revision identity vs. authority metadata

**Revision identity is immutable** and reused verbatim from
`ingestion_bench.chunking.DocumentRevisionContext` (Stage 4.1) — never
reinvented by this package:

- `logical_document_id`
- `document_revision_id` (always `compute_document_revision_id(logical_document_id, source_document_sha256, version_label, revision_number)` — a deterministic SHA-256, never freely chosen)
- `source_document_sha256`
- `version_label`
- `revision_number`

**Authority metadata is mutable** and lives *only* in this new registry,
never on `CanonicalChunk`:

- `publication_status`: `draft` | `under_review` | `approved` | `withdrawn` (the only facts a governance source may assert directly)
- `approved_at`, `effective_from`, `effective_to`
- `supersedes_revision_id`, `superseded_by_revision_id` (set only by `activate_revision`'s atomic transition)
- `authority_source`, `authority_reference`, `authority_recorded_at`, `authority_recorded_by`

**Derived authority state** (computed at query time, never stored):
`draft` | `under_review` | `approved_future` | `effective` | `superseded` | `withdrawn`.
An old revision may remain historically `approved` (`publication_status`)
forever while its derived *current* authority state is `superseded` — these
are deliberately different things. `is_latest` is never stored as an
authoritative fact; authority is never derived from upload timestamp,
highest revision number, version label, filename, or embedding similarity.

---

## A. Exact duplicate upload

- **Business situation:** the same governance system (or a retry, or an
  operator) re-submits the identical document a second time — same logical
  document, same bytes, same version label, same revision number.
- **Registry precondition:** revision `v3` of `POLICY-RESILIENCE-001`
  (`source_document_sha256` for "Resilience Policy v3 -- retention period 7
  years", `revision_number=3`) is already registered.
- **Event:** `register_revision()` is called again with identical
  `logical_document_id` + `source_document_sha256` + `version_label` +
  `revision_number` (contract step `reg_v3_dup`, symbol `v3_duplicate`).
- **Resulting registry state:** no new row. `document_revision_id` is
  recomputed and is byte-identical to `v3`'s — the lookup finds the
  existing identity and returns it. `is_new_revision=False`.
- **Default-current query behavior:** unaffected — `v3`'s own authority
  state (whatever it already was) is unchanged.
- **As-of query behavior:** unaffected, same reason.
- **Comparison-query behavior:** there is nothing new to compare; a
  comparison request for `v3` still resolves to exactly one revision.
- **Expected index behavior:** no re-chunking, no re-embedding — the
  service has no chunking/embedding dependency at all, so there is nothing
  to trigger.
- **Audit evidence:** one `duplicate_registration_attempt` event is
  appended (contract scenario `A_exact_duplicate_upload`), recording the
  repeated attempt without creating a duplicate revision row.
- **What this scenario does NOT imply:** it does not imply the *second*
  submission's metadata (upload time, submitting user, request id) is
  discarded — that context lives in the audit event's own
  `authority_reference`/`recorded_by`/`recorded_at` fields, distinct from
  the *revision's* own immutable identity, which never changes.

## B. Changed content for the same logical document

- **Business situation:** the same logical policy document is revised —
  the text actually changed.
- **Registry precondition:** `v1` of `POLICY-RESILIENCE-001` is registered.
- **Event:** `register_revision()` is called with the same
  `logical_document_id` but a *different* `source_document_sha256` (`v2`,
  contract step `reg_v2`).
- **Resulting registry state:** a brand-new revision row, its own
  `document_revision_id` (the hash differs because `source_document_sha256`
  differs), `publication_status="draft"` by default. `v1`'s own row is
  completely untouched.
- **Default-current query behavior:** still resolves to whatever was
  effective before this registration — a new draft registration alone
  never changes what is current (see Scenario C).
- **As-of query behavior:** unaffected for any date before `v2` is later
  activated.
- **Comparison-query behavior:** `v1` and `v2` can now both be requested
  explicitly and compared side by side, each retaining its own label.
- **Expected index behavior:** this registry never triggers chunking or
  embedding itself — those remain the caller's own responsibility,
  entirely outside this package (Stage 5A ingestion is untouched by Stage
  7R.1).
- **Audit evidence:** a `revision_registered` event for the new revision
  (contract scenario tag `B_changed_content` on both `reg_v1` and
  `reg_v2`).
- **What this scenario does NOT imply:** it does not imply the new
  revision is now current, nor that it will ever become current — a
  registered draft can sit unreviewed indefinitely (Scenario C).

## C. Newer draft does not replace current effective revision

- **Business situation:** a draft revision (`v4`, proposing a 10-year
  retention period) exists for review, but the currently authoritative
  revision (`v3`, 7-year retention) must keep serving current-authority
  queries throughout the review.
- **Registry precondition:** `v3` is `effective` (activated with
  `effective_from=2023-01-01`, superseding `v2`); `v4` is registered but
  never approved (`publication_status="draft"`).
- **Event:** none beyond registration — this scenario is about the
  *absence* of an event making `v4` authoritative.
- **Resulting registry state:** `v3.publication_status="approved"`,
  effective; `v4.publication_status="draft"`, no effective dates at all.
- **Default-current query behavior:** `current` intent as of `2025-06-01`
  (contract scenario `C_newer_draft_does_not_replace`) returns exactly
  `v3`; `v4` is excluded with reason `draft_not_eligible_for_intent`.
- **As-of query behavior:** any historical date also resolves to whichever
  revision was actually effective then — `v4` is never eligible for
  `as_of` either, for the same reason.
- **Comparison-query behavior:** `v4` CAN be explicitly compared against
  `v3` (comparison permits drafts) — but that is an explicit,
  intentional, differently-labeled request, never the default.
- **Expected index behavior:** `v4`'s chunks (if `v4` were ever ingested)
  would exist in the corpus but must never be returned by a default
  current-authority retrieval query once Stage 7R.2 wires this resolver
  into retrieval.
- **Audit evidence:** `v4`'s own `revision_registered` event exists; no
  `revision_activated` event exists for it, which is itself the evidence
  that it was never made current.
- **What this scenario does NOT imply:** it does not imply drafts are
  hidden or deleted — they remain fully visible to `draft`-intent and
  `comparison`-intent queries; only the *default* current/as_of path
  excludes them.

## D. Approved future revision does not become current early

- **Business situation:** a new revision (`v5`, 8-year retention) has been
  formally approved and given a *future* effective date, but must not
  leak into current-authority results before that date arrives.
- **Registry precondition:** `v5` is activated (`activate_revision(new=v5,
  old=v3, effective_from=2028-01-01)`), so
  `v5.publication_status="approved"`, `v5.effective_from=2028-01-01`.
- **Event:** a `current` query as of a date still before `2028-01-01`
  (contract scenario `D_approved_future_not_early`, `as_of_date=2027-12-31`).
- **Resulting registry state:** unchanged by the query itself (queries are
  read-only).
- **Default-current query behavior:** returns `v3` (still effective);
  `v5` is excluded with reason `not_effective_approved_future` and detail
  `effective_from=2028-01-01 is after as_of_date=2027-12-31`.
- **As-of query behavior:** identical mechanics for any historical or
  present date before `2028-01-01`.
- **Comparison-query behavior:** `v5` can be explicitly compared even
  though it isn't current yet — its `approved_future` label is preserved,
  never silently upgraded to `effective`.
- **Expected index behavior:** once Stage 7R.2 exists, a default retrieval
  query as of `2027-12-31` must never surface `v5`-scoped chunks as
  current evidence.
- **Audit evidence:** the single `revision_activated` event for `v5`
  (recorded at registration/approval time, `2024-10-15`) already carries
  the future `effective_from` — there is no separate "become current"
  event that fires later; the derived state changes purely as a function
  of `as_of_date`, never a background job.
- **What this scenario does NOT imply:** it does not imply a future
  activation requires re-running `activate_revision` again once the date
  arrives — see Scenario E, the SAME activation event already governs
  both "not yet" and "now" outcomes.

## E. New effective revision supersedes the old revision

- **Business situation:** `v5`'s effective date arrives; it must become
  current in the exact same atomic moment `v3` stops being current.
- **Registry precondition:** same as Scenario D.
- **Event:** a `current` query exactly ON the boundary date (contract
  scenario `E_supersession_boundary_on`, `as_of_date=2028-01-01`).
- **Resulting registry state:** unchanged by the query (the actual
  supersession was already recorded atomically by the single
  `activate_revision` call in Scenario D's setup — see "Atomic
  supersession behavior" below).
- **Default-current query behavior:** returns `v5` (now effective, since
  `effective_from(2028-01-01) <= as_of_date(2028-01-01)`); `v3` is
  excluded with reason `not_effective_superseded` (its `effective_to`,
  `2028-01-01`, is now `<= as_of_date`).
- **As-of query behavior:** identical mechanics for any date on or after
  `2028-01-01` (until a further supersession, if any).
- **Comparison-query behavior:** both `v3` and `v5` remain independently
  requestable, `v3` now labeled `superseded`, `v5` now labeled
  `effective`.
- **Expected index behavior:** the retrieval-eligible revision for
  `POLICY-RESILIENCE-001` flips from `v3`-scoped chunks to `v5`-scoped
  chunks at exactly this boundary, once Stage 7R.2 exists — no
  in-between state where both or neither are eligible.
- **Audit evidence:** the same single `revision_activated` event from
  Scenario D's setup (`related_revision_id=v3`) is the complete audit
  trail for this transition — there is no second event.
- **What this scenario does NOT imply:** it does not imply `v3`'s
  canonical chunks are deleted, rechunked, or re-embedded — they remain
  exactly as ingested, simply no longer the *default* eligible revision.

## F. Late upload of an older approved revision

- **Business situation:** an older, already-superseded-in-spirit document
  copy is registered very late (long after newer revisions already
  exist) — this must never let it leapfrog into currency merely because
  it was just uploaded.
- **Registry precondition:** `v3` is effective; `v0_late_upload` (a
  distinct, older-content revision) is registered on `2026-06-01` —
  chronologically *after* `v3` became effective (`2023-01-01`).
- **Event:** `register_revision()` for `v0_late_upload`, with no further
  authority decision (contract scenario `F_late_upload_old_revision`).
- **Resulting registry state:** `v0_late_upload.publication_status="draft"`
  — registration alone NEVER assigns any authority, regardless of how
  late (or early) the upload timestamp is.
- **Default-current query behavior:** `current` as of `2026-06-02` still
  returns `v3`; `v0_late_upload` is excluded as `draft`.
- **As-of query behavior:** identical — `v0_late_upload` has no effective
  window at all, so it is never eligible for any date.
- **Comparison-query behavior:** `v0_late_upload` can be explicitly
  compared, retaining its `draft` label.
- **Expected index behavior:** no retrieval-eligibility change results
  from this registration alone.
- **Audit evidence:** one `revision_registered` event, timestamped
  `2026-06-01`, is the only record — its lateness relative to `v3`'s own
  `2023-01-01` activation is visible directly in the audit trail, never
  hidden.
- **What this scenario does NOT imply:** it does not imply upload
  timestamp is tracked as a *ranking* signal anywhere in this package —
  `authority_recorded_at` is audit provenance only, never an input to
  `derive_authority_state`.

## G. Current-authoritative query

- **Business situation:** the ordinary case — "what does this policy say
  right now?"
- **Registry precondition:** `POLICY-RESILIENCE-001` has a normal
  revision history (`v1` → `v2` → `v3`, `v3` effective).
- **Event:** `resolve_query_scope(query_intent="current", as_of_date=<today>)`
  (contract scenario `G_current_authoritative_query`, `as_of_date=2025-06-01`
  standing in for "today" — the pure resolver never defaults this itself).
- **Resulting registry state:** unchanged (read-only).
- **Default-current query behavior:** exactly one eligible revision,
  `v3`.
- **As-of query behavior:** N/A — this IS the current-intent case.
- **Comparison-query behavior:** N/A for this scenario.
- **Expected index behavior:** once Stage 7R.2 exists, this is the
  default filter every ordinary Vector RAG query applies before
  similarity ranking.
- **Audit evidence:** none generated by a read-only query — the resolver
  never appends an event.
- **What this scenario does NOT imply:** it does not imply "today" is
  computed anywhere inside this package — the caller (a future outer
  application layer, never this stage) supplies `as_of_date` explicitly,
  always.

## H. Historical as-of query

- **Business situation:** "what did this policy say on 2020-06-01?" — an
  audit, a legal hold, or a historical-comparison need.
- **Registry precondition:** same history as Scenario G.
- **Event:** `resolve_query_scope(query_intent="as_of", as_of_date=2020-06-01)`
  (contract scenario `H_historical_as_of_query`).
- **Resulting registry state:** unchanged.
- **Default-current query behavior:** N/A for this scenario.
- **As-of query behavior:** returns `v2` (effective `[2019-01-01,
  2023-01-01)`, which covers `2020-06-01`); `v1` is excluded as
  `superseded`, `v3` is excluded as `approved_future` (relative to
  `2020-06-01`, `v3` had not yet begun).
- **Comparison-query behavior:** N/A for this scenario.
- **Expected index behavior:** once Stage 7R.2 exists, a historical
  retrieval query scoped to `2020-06-01` must resolve `v2`-scoped
  chunks, never `v3`'s.
- **Audit evidence:** none generated (read-only).
- **What this scenario does NOT imply:** it does not imply `as_of` and
  `current` are different code paths — both call the exact same interval
  test; only the caller's own stated intent (and, in a future outer
  layer, whether `as_of_date` happens to equal "today") differs.

## I. Explicit revision-comparison query

- **Business situation:** "show me the superseded, current, and
  not-yet-effective versions of this policy side by side."
- **Registry precondition:** same history as Scenario G, plus `v5`
  approved-future.
- **Event:** `resolve_query_scope(query_intent="comparison",
  requested_revision_ids=[v1, v3, v5], as_of_date=2025-06-01)` (contract
  scenario `I_explicit_comparison_query`).
- **Resulting registry state:** unchanged.
- **Default-current query behavior:** N/A — comparison never silently
  narrows to one revision.
- **As-of query behavior:** N/A for this scenario.
- **Comparison-query behavior:** all three requested revisions are
  returned, each retaining its own derived label (`v1`→`superseded`,
  `v3`→`effective`, `v5`→`approved_future`) — nothing is excluded, nothing
  is silently promoted or demoted.
- **Expected index behavior:** a future comparison-oriented UI/API (Stage
  7A.3-like, or a later stage) would show all three revisions' own
  chunks side by side, each correctly labeled.
- **Audit evidence:** none generated (read-only).
- **What this scenario does NOT imply:** it does not imply comparison
  mode bypasses registry integrity checks universally — supersession-link
  consistency is still real data, just not used to "pick one" the way
  current/as_of intents do.

## J. Explicit draft-awareness query

- **Business situation:** "show me the drafts under review for this
  policy" — a reviewer's own dashboard, never mixed into a normal search.
- **Registry precondition:** `v4` is `draft`; `v3` is `effective`.
- **Event:** `resolve_query_scope(query_intent="draft",
  requested_revision_ids=[v4, v3], as_of_date=2025-06-01)` (contract
  scenario `J_explicit_draft_query` — `v3` requested too, deliberately,
  to prove it gets excluded).
- **Resulting registry state:** unchanged.
- **Default-current query behavior:** N/A for this scenario.
- **As-of query behavior:** N/A for this scenario.
- **Comparison-query behavior:** N/A for this scenario (draft intent is
  its own thing, not comparison).
- **Expected index behavior:** a reviewer-only draft-preview surface (not
  built in Stage 7R.1) would show only `v4`'s chunks, clearly labeled
  DRAFT, never blended into a current-authority result set.
- **Audit evidence:** none generated (read-only).
- **What this scenario does NOT imply:** it does not imply requesting a
  non-draft revision under `draft` intent is an error — it is simply
  excluded, with an explicit reason (`not_draft_or_under_review`), never
  silently included and never a hard failure.

## K. Current revision withdrawn with no replacement

- **Business situation:** the only effective revision of a document is
  formally withdrawn (e.g. a policy is retracted) and nothing has been
  approved to replace it yet.
- **Registry precondition:** `POLICY-WITHDRAWN-DEMO-001`'s only revision,
  `w1`, was activated (`effective_from=2020-01-01`).
- **Event:** `withdraw_revision(w1)` (contract step `withdraw_w1`,
  scenario `K_withdrawn_no_replacement`).
- **Resulting registry state:** `w1.publication_status="withdrawn"` —
  its prior `effective_from`/`effective_to` are left untouched for
  historical record, but `derive_authority_state` short-circuits to
  `withdrawn` regardless of those dates.
- **Default-current query behavior:** `current` as of `2025-06-01`
  returns **zero** eligible revisions and an `integrity_error`
  (`"...has no authoritative effective revision as of 2025-06-01"`) —
  never a silent empty success.
- **As-of query behavior:** any date after the withdrawal behaves
  identically; a date *before* the withdrawal (but on/after
  `2020-01-01`) would still resolve `w1` as `effective` — withdrawal is
  not retroactive.
- **Comparison-query behavior:** `w1` can still be explicitly compared,
  correctly labeled `withdrawn`.
- **Expected index behavior:** once Stage 7R.2 exists, a default query
  against this document must FAIL CLOSED (surface the integrity error to
  the caller), never silently return zero results indistinguishable from
  "this document doesn't exist."
- **Audit evidence:** one `revision_withdrawn` event, distinct from
  `authority_decision_recorded`, makes the withdrawal itself
  independently auditable.
- **What this scenario does NOT imply:** it does not imply the resolver
  auto-selects the most-recently-superseded revision as a fallback — no
  fallback of any kind exists; a human/governance decision
  (`activate_revision` for a real replacement) is required.

## L. Conflicting overlapping effective revisions

- **Business situation:** operator error — two revisions of the same
  document both get activated independently (each with `old=None`
  instead of properly superseding one another), leaving two
  simultaneously "effective" revisions.
- **Registry precondition:** `POLICY-CONFLICT-DEMO-001` has `c1`
  activated `old=None, effective_from=2020-01-01` and `c2` ALSO activated
  `old=None, effective_from=2021-01-01` (contract scenario
  `L_overlapping_effective_revisions`) — a real, plausible misuse of the
  service API, not a hand-corrupted database row.
- **Event:** a `current` query as of `2025-06-01`.
- **Resulting registry state:** both `c1` and `c2` are independently
  `publication_status="approved"` with open (`None`) `effective_to` —
  neither was ever told about the other.
- **Default-current query behavior:** **fails closed** — `integrity_error`
  names both conflicting revision ids and states
  `"refusing to silently choose one"`; `eligible_revision_ids=[]`.
- **As-of query behavior:** identical failure for any date on/after
  `2021-01-01` (both effective); a date before `2021-01-01` would
  resolve only `c1`, no conflict.
- **Comparison-query behavior:** comparison is UNAFFECTED — both can
  still be explicitly compared (comparison never "picks one", so the
  conflict is not a comparison-blocking condition).
- **Expected index behavior:** once Stage 7R.2 exists, a default query
  against this document must refuse to serve ANY revision-scoped result
  rather than guess — this is exactly the "fail closed" contract
  Vector/Graph/wiki retrieval will all depend on.
- **Audit evidence:** both revisions' own `revision_activated` events
  exist independently — there is no single event that "caused" the
  conflict; the conflict is a property of the accumulated state, which
  is exactly what the resolver's integrity scan is for.
- **What this scenario does NOT imply:** it does not imply the resolver
  attempts any automatic reconciliation (e.g. "prefer the later
  effective_from") — silently picking one, by any rule, is exactly what
  Stage 7R.1 refuses to do.

## M. Authority correction or rollback

- **Business situation:** a governance decision is corrected before it
  ever took effect — e.g. a proposed 12-year retention period revision is
  approved-future, then withdrawn from consideration and rolled back to
  draft.
- **Registry precondition:** `v6_rollback_demo` is registered, then
  `record_authority_decision(publication_status="approved",
  effective_from=2029-01-01)`.
- **Event:** a second `record_authority_decision(publication_status="draft",
  effective_from=None, effective_to=None)` on the SAME revision (contract
  steps `decide_v6_approve` then `decide_v6_rollback`, scenario
  `M_authority_correction_rollback`).
- **Resulting registry state:** `v6_rollback_demo` is back to `draft`,
  with no effective dates — `record_authority_decision` never touches
  supersession links, and since `v6_rollback_demo` was never
  `activate_revision`'d, `v3`/`v5`'s own effective windows are completely
  untouched by this correction.
- **Default-current query behavior:** `v6_rollback_demo` is excluded
  (`draft`) both before and after the correction — from the outside, a
  current-authority query never saw a difference.
- **As-of query behavior:** identical — `v6_rollback_demo` was never
  eligible for any date.
- **Comparison-query behavior:** requesting `v6_rollback_demo` alongside
  `v3`/`v5` (contract scenario `M_authority_correction_rollback` itself
  does exactly this) shows its CURRENT label (`draft`, post-rollback) —
  comparison always reflects present registry state, not a frozen
  snapshot from before the correction.
- **Expected index behavior:** no retrieval-eligibility change results
  from either the original approval or the rollback, since the revision
  was never activated.
- **Audit evidence:** TWO `authority_decision_recorded` events exist for
  `v6_rollback_demo` (the approval, then the rollback) — the full
  correction history is reconstructable from the append-only event log,
  never overwritten or deleted.
- **What this scenario does NOT imply:** it does not imply correcting an
  ALREADY-ACTIVATED supersession is this simple — rolling back a
  revision that already closed another one's `effective_to` via
  `activate_revision` would require a second, explicit correction on the
  other side too (out of scope for this narrow example; the general
  problem is why `activate_revision` keeps both sides atomic in the
  first place).

## N. Same textual content across different revision identities

- **Business situation:** the exact same paragraph/boilerplate text is
  legitimately reused across two UNRELATED logical documents (e.g. a
  shared legal clause) — this must never be treated as "the same
  revision" just because the bytes match.
- **Registry precondition:** `POLICY-SHARED-TEXT-DEMO-001`'s revision
  `n1_shares_v2_text` has the byte-identical `source_document_sha256` as
  `POLICY-RESILIENCE-001`'s `v2` — but a different `logical_document_id`.
- **Event:** `register_revision()` for `n1_shares_v2_text` (contract
  scenario `N_same_text_different_identity`).
- **Resulting registry state:** a completely independent revision row,
  its own `document_revision_id` (the hash differs because
  `logical_document_id` differs, even though `source_document_sha256` is
  identical) — proven directly by `compute_document_revision_id`'s own
  hash inputs, not asserted separately.
- **Default-current query behavior:** querying `POLICY-SHARED-TEXT-DEMO-001`
  and querying `POLICY-RESILIENCE-001` are two entirely independent
  resolutions; nothing about `v2`'s authority (superseded, in this case)
  leaks into `n1_shares_v2_text`'s own (draft) state, or vice versa.
- **As-of query behavior:** identical independence.
- **Comparison-query behavior:** `n1_shares_v2_text` can be compared only
  within its own document's revision set — this package never compares
  across `logical_document_id` boundaries.
- **Expected index behavior:** once Stage 7R.2 exists, chunk-level
  content-hash-based embedding REUSE (a Stage 4.1/7A.1 concept,
  `embedding_input_sha256`) can still legitimately apply across these two
  revisions (identical text costs nothing extra to embed twice) even
  though their AUTHORITY is completely independent — these are
  deliberately orthogonal concerns.
- **Audit evidence:** `n1_shares_v2_text`'s own `revision_registered`
  event, entirely separate from `v2`'s.
- **What this scenario does NOT imply:** it does not imply
  `source_document_sha256` alone is ever used as a revision's identity —
  identity is always the FULL tuple (`logical_document_id` +
  `source_document_sha256` + `version_label` + `revision_number`).

## O. Effective-date boundary behavior

- **Business situation:** precise handling of the exact day authority
  changes hands — off-by-one errors here would either double-serve or
  gap-serve a policy for one day.
- **Registry precondition:** same `v3`/`v5` supersession as Scenario E
  (`v3.effective_to = v5.effective_from = 2028-01-01`).
- **Event:** two queries one day apart — `as_of_date=2027-12-31`
  (contract scenario `O_boundary_day_before`) and `as_of_date=2028-01-01`
  (Scenario E's `E_supersession_boundary_on`).
- **Resulting registry state:** unchanged by either query.
- **Default-current query behavior:** `2027-12-31` → `v3` (still
  effective: `effective_from(2023-01-01) <= 2027-12-31 <
  effective_to(2028-01-01)`); `2028-01-01` → `v5` (now effective:
  `effective_from(2028-01-01) <= 2028-01-01`, and `v3` now excluded:
  `effective_to(2028-01-01) <= 2028-01-01`).
- **As-of query behavior:** identical mechanics — the boundary rule is
  intent-independent.
- **Comparison-query behavior:** N/A for this scenario.
- **Expected index behavior:** exactly one revision is eligible on
  either side of the boundary, never zero (a gap) and never two (an
  overlap) — this is the same property Scenario L's failure mode
  violates when the registry itself is inconsistent; here the registry
  IS consistent, so the boundary behaves cleanly.
- **Audit evidence:** none generated by either read-only query; the
  boundary's correctness is a property of the single `activate_revision`
  event from Scenario D/E's setup.
- **What this scenario does NOT imply:** it does not imply `effective_to`
  is ever treated as inclusive anywhere in this package — the
  `effective_from <= as_of_date < effective_to` convention is applied
  uniformly, with no per-call override.

---

## Projection-use-case documentation

The SAME resolver (`resolver.resolve_query_scope` /
`RevisionAuthorityService.resolve_query_scope`) is designed to later serve
every retrieval projection identically — **none of the following is
implemented in Stage 7R.1**; this section documents the intended Stage
7R.2+ wiring only.

### Regular Vector RAG (Stage 7A.1, Stage 7R.2)

Before similarity ranking, filter the candidate chunk set down to only
those chunks whose `document_revision_id` is in
`eligible_revision_ids` for the query's own `(logical_document_id,
query_intent, as_of_date)`. A `current`-intent search never ranks a
draft's or a superseded revision's chunks alongside the effective
revision's — the filter happens BEFORE ranking, never as a post-hoc
re-sort. This is the entire scope of Stage 7R.2; nothing about
`retrieval_baseline`'s own indexing, embedding, or scoring logic changes.

### Graph RAG (Stage 7B)

Select revision-scoped nodes and edges before traversal — a graph query
must resolve its own eligible revision set first (same resolver call),
then traverse only edges/nodes belonging to those revisions. **Never
merge superseded and current edges into one timeless fact** — e.g. "Control
C-88 satisfies Obligation O-31" (current, from `v3`-equivalent data) and
"Control C-88a satisfied Obligation O-31" (historical/retired) must
remain two distinct, revision-scoped edges, never collapsed into a
single "C-88(a) satisfies O-31" fact that erases which one is current.
A comparison-intent graph query can legitimately traverse both revisions'
subgraphs side by side, exactly like Scenario I above, each edge
retaining its own revision's authority label.

### Wiki retrieval (Stage 7C)

The current page for a logical document resolves from whichever
revision the resolver returns for `current` intent — never a
freshly-computed "most recent" heuristic. Revision history remains
separately navigable (an `as_of`/`comparison`-intent view over the same
resolver, driving a "view as of this date" or "compare revisions" page).
Every wiki statement stays linked to its own revision-scoped chunks
(via `source_element_ids`/`source_refs`, already on `CanonicalChunk`) so
a historical page view can still show exactly which chunk each
statement came from, even for a long-superseded revision.
