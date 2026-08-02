# Revision Authority Scenarios — Stage 7R.1 / 7R.1a

## What this document is

This document defines the business behavior of the Stage 7R.1/7R.1a
revision-authority registry and resolver (`src/ingestion_bench/revision_authority/`),
and how that behavior will later be consumed by each retrieval projection
(Regular Vector RAG, Graph RAG, wiki retrieval). It is corrected to
match the ACTUAL implemented behavior exactly (Stage 7R.1a item 9) —
where Stage 7R.1's original design turned out to be wrong (most notably:
withdrawal was a status short-circuit that ignored real history), this
document describes the CORRECTED, implemented behavior, not the
original intent.

**This is NOT a document-management/version-control system.** It does not
store or edit document binaries, provide check-in/check-out, manage approval
workflows, replace Documentum or a policy-governance platform, or infer
authority from filenames, upload time, or document text. It persists
authoritative revision metadata *supplied by a consumer or governance
source* and uses it to resolve which already-ingested document revisions
are eligible for a query.

Every scenario below is exercised for real by
`contracts/revision_authority_scenarios_v2.json` (`contract_version:
revision_authority_scenarios_v2`) and
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
towards the future until some later period closes it). A **zero-width**
interval (`effective_to == effective_from`) is a deliberate, valid
representation of a period that was scheduled but retracted before it
ever took effect — see `pre_effective_authority_correction` below; it
matches **no** `as_of_date` at all.

## Three-way model split (Stage 7R.1a)

Stage 7R.1's original design put a single `effective_from`/`effective_to`
pair directly on the revision's own row. That single pair could not
represent a historical revision before a later withdrawal, a revision
reinstated after a rollback, or multiple disjoint effective periods for
the same revision. Stage 7R.1a splits the model into three parts, with
**exactly one authoritative source for any given fact**:

1. **`RevisionIdentity`** (immutable) — reused verbatim from
   `ingestion_bench.chunking.DocumentRevisionContext` (Stage 4.1), never
   reinvented: `logical_document_id`, `document_revision_id`,
   `source_document_sha256`, `version_label`, `revision_number`.
2. **`AuthorityMetadata`** (mutable, one row per revision) — PURE
   governance status, never a date: `publication_status` (`draft` |
   `under_review` | `approved` | `withdrawn`), `approved_at`, plus
   governance provenance (`authority_source`, `authority_reference`,
   `authority_recorded_at`, `authority_recorded_by`). It carries **no**
   effective dates and **no** supersession links.
3. **`AuthorityPeriod`** (mutable, MULTIPLE rows per revision permitted)
   — the **sole authoritative source for effective-date resolution**.
   Each row: `effective_from`, `effective_to`, `predecessor_revision_id`
   (which revision this period's opening followed, if any),
   `opening_event_id`/`closing_event_id` (links into the append-only
   event log — never a free-text reference alone), `closure_reason`
   (`superseded` | `withdrawn` | `rollback` | `correction`), plus its
   own governance provenance. Multiple **non-overlapping** periods for
   the same revision are explicitly permitted — this is exactly what
   makes reinstatement (Scenario `E2`) representable.

**Derived authority state** (computed at query time from
`AuthorityMetadata.publication_status` + ALL of a revision's own
`AuthorityPeriod` rows, never stored): `draft` | `under_review` |
`approved_future` | `effective` | `superseded` | `withdrawn`. An old
revision may remain historically `approved` (`publication_status`)
forever while its derived *current* authority state is `superseded` —
these are deliberately different things. `is_latest` is never stored as
an authoritative fact; authority is never derived from upload timestamp,
highest revision number, version label, filename, or embedding
similarity.

---

## A. Exact duplicate upload

- **Business situation:** the same governance system (or a retry, or an
  operator) re-submits the identical document a second time.
- **Registry precondition:** revision `v3` of `POLICY-RESILIENCE-001` is
  already registered.
- **Event:** `register_revision()` is called again with identical
  `logical_document_id` + `source_document_sha256` + `version_label` +
  `revision_number` (contract step `reg_v3_dup`, symbol `v3_duplicate`).
- **Resulting registry state:** no new row. `document_revision_id` is
  recomputed and is byte-identical to `v3`'s — the lookup finds the
  existing identity and returns it. `is_new_revision=False`.
- **Default-current/as-of/comparison query behavior:** all unaffected —
  `v3`'s own authority state is unchanged.
- **Expected index behavior:** no re-chunking, no re-embedding — the
  service has no chunking/embedding dependency at all.
- **Audit evidence:** one `duplicate_registration_attempt` event
  (scenario `A_exact_duplicate_upload`).
- **What this scenario does NOT imply:** it does not imply the second
  submission's own request metadata is discarded — it lives on the
  audit event's own fields, distinct from the revision's identity.

## B. Changed content for the same logical document

- **Business situation:** the same logical policy document is revised —
  the text actually changed.
- **Event:** `register_revision()` with the same `logical_document_id`
  but a *different* `source_document_sha256` (`v2`, step `reg_v2`).
- **Resulting registry state:** a brand-new revision row, its own
  `document_revision_id`, `publication_status="draft"` by default, no
  authority period at all yet. `v1`'s own row is untouched.
- **What this scenario does NOT imply:** it does not imply the new
  revision is now current — a registered draft has no period until
  explicitly activated (Scenario C).

## C. Newer draft does not replace current effective revision

- **Business situation:** a draft (`v4`, 10-year retention) exists for
  review while `v3` (7-year retention) stays authoritative.
- **Registry precondition:** `v3` has an open period
  `[2023-01-01, None)`; `v4` is `draft`, no period.
- **Default-current query behavior:** `current` as of `2025-06-01`
  (scenario `C_newer_draft_does_not_replace`) returns exactly `v3`; `v4`
  excluded with `reason_code=not_effective_draft`.
- **Comparison-query behavior:** `v4` CAN be explicitly compared
  (comparison permits drafts) — an explicit, differently-labeled
  request, never the default.
- **What this scenario does NOT imply:** it does not imply drafts are
  hidden — they remain fully visible to `draft`/`comparison` intents;
  only the default current/as_of path excludes them.

## D. Approved future revision does not become current early

- **Business situation:** `v5` (8-year retention) has been activated
  with a FUTURE `effective_from`, and must not leak into current-
  authority results before that date arrives.
- **Registry precondition:** `activate_revision(new=v5, old=v3,
  effective_from=2028-01-01)` has run — `v5`'s period is
  `[2028-01-01, None)`, `v3`'s period is unchanged (still open,
  `[2023-01-01, None)`) until that same call closes it (Scenario E — the
  SAME single call governs both "not yet" and "now", see below).
- **Default-current query behavior:** `current` as of `2027-12-31`
  (scenario `D_approved_future_not_early`) returns `v3`; `v5` excluded
  with `reason_code=not_effective_approved_future`.
- **What this scenario does NOT imply:** it does not imply a future
  activation must be re-run once the date arrives — see Scenario E.

## E. New effective revision supersedes the old revision

- **Business situation:** `v5`'s effective date arrives; it must become
  current in the exact same atomic moment `v3` stops being current.
- **Event:** a `current` query exactly ON the boundary date (scenario
  `E_supersession_boundary_on`, `as_of_date=2028-01-01`).
- **Default-current query behavior:** returns `v5` (`effective_from
  <= as_of_date`); `v3` excluded (`not_effective_superseded`, its
  `effective_to=2028-01-01 <= as_of_date`).
- **Atomic supersession behavior (item 4):** `activate_revision` closes
  `v3`'s period (`effective_to=2028-01-01`, `closure_reason=superseded`,
  `closing_event_id=<E>`) and opens `v5`'s period
  (`effective_from=2028-01-01`, `opening_event_id=<E>`,
  `predecessor_revision_id=v3`) using the SAME single event `<E>` —
  "the corresponding authority decision event" (singular) covers the
  whole transition. Before any write, `_validate_activation` confirms:
  both revisions exist, they share one `logical_document_id`,
  `old_revision_id != new_revision_id`, `v3` has exactly one OPEN
  period to close, the new period does not overlap any other
  revision's period of this document (nor `v5`'s own prior periods),
  and the transition date is not before `v3`'s own period start. Only
  after every check passes does the transaction begin.
- **What this scenario does NOT imply:** it does not imply `v3`'s
  canonical chunks are deleted, rechunked, or re-embedded.

## F. Late upload of an older approved revision

- **Business situation:** an older document copy is registered very
  late — this must never let it leapfrog into currency merely because
  it was just uploaded.
- **Event:** `register_revision()` for `v0_late_upload` on `2026-06-01`
  (chronologically after `v3` became effective), with NO further
  authority decision (scenario `F_late_upload_old_revision`).
- **Default-current query behavior:** `current` as of `2026-06-02`
  still returns `v3`; `v0_late_upload` excluded as `draft`.
- **What this scenario does NOT imply:** it does not imply
  `authority_recorded_at`/`recorded_at` is ever consulted by
  `derive_authority_state` — it is audit provenance only.

## G. Current-authoritative query

- **Business situation:** the ordinary case — "what does this policy say
  right now?"
- **Event:** `resolve_query_scope(query_intent="current",
  as_of_date=<today>)` (scenario `G_current_authoritative_query`,
  `2025-06-01` standing in for "today" — the pure resolver never
  defaults this itself).
- **Default-current query behavior:** exactly one eligible revision,
  `v3`.
- **What this scenario does NOT imply:** "today" is never computed
  inside this package — the caller always supplies `as_of_date`
  explicitly.

## H. Historical as-of query

- **Business situation:** "what did this policy say on 2020-06-01?"
- **As-of query behavior:** `resolve_query_scope(query_intent="as_of",
  as_of_date=2020-06-01)` (scenario `H_historical_as_of_query`) returns
  `v2` (effective `[2019-01-01, 2023-01-01)`); `v1` excluded
  (`superseded`), `v3` excluded (`approved_future` relative to that
  date).
- **What this scenario does NOT imply:** it does not imply `as_of` and
  `current` are different code paths — both call the exact same
  interval test; only the caller's own stated intent differs.

## H2. Historical as-of BEFORE a withdrawal

- **Business situation (item 2's core fix):** a document's only
  revision (`w1`) was later withdrawn — but a historical query for a
  date BEFORE the withdrawal must still see it as authoritative.
- **Registry precondition:** `w1` activated `[2020-01-01, None)`, then
  `withdraw_revision(w1, withdrawal_effective_date=2024-01-01)` closes
  it — recorded LATE, `2025-03-01`, to prove `recorded_at` is never
  consulted.
- **As-of query behavior:** `as_of_date=2022-06-01` (scenario
  `H2_historical_as_of_before_withdrawal`) resolves `w1` as `effective`
  — its now-closed period `[2020-01-01, 2024-01-01)` still covers that
  date.
- **What this scenario does NOT imply:** withdrawal is never
  retroactive — only dates on/after `withdrawal_effective_date` are
  affected (see Scenario K).

## I. Explicit revision-comparison query

- **Business situation:** "show me the superseded, current, and
  not-yet-effective versions of this policy side by side."
- **Comparison-query behavior:** `requested_revision_ids=[v1, v3, v5]`
  (scenario `I_explicit_comparison_query`) returns all three, each
  retaining its own derived label (`v1`→`superseded`, `v3`→`effective`,
  `v5`→`approved_future`) — nothing excluded, nothing silently promoted.
- **What this scenario does NOT imply:** comparison mode does not
  bypass ALL integrity checks universally — a genuinely MALFORMED
  individual record is still excluded (see the malformed-record
  scenarios below); only the "pick exactly one" registry-wide checks
  (overlap, no-effective-revision) don't apply, since comparison never
  picks anything.

## J. Explicit draft-awareness query

- **Business situation:** "show me the drafts under review" — a
  reviewer's own dashboard, never mixed into a normal search.
- **Draft-query behavior:** `requested_revision_ids=[v4, v3]` (scenario
  `J_explicit_draft_query`, `v3` requested deliberately to prove it gets
  excluded) returns only `v4`; `v3` excluded
  (`reason_code=not_eligible_for_draft_intent`).
- **What this scenario does NOT imply:** requesting a non-draft
  revision under `draft` intent is not an error — it is excluded with
  an explicit reason, never silently included and never a hard failure.

## J2. `under_review` requested through draft intent

- **Business situation:** `under_review` is ALSO a legitimate
  pre-approval governance state, not just `draft` — a reviewer's queue
  should show both.
- **Registry precondition:** `v4_under_review` registered then
  `record_authority_decision(publication_status="under_review")` — a
  PURE status change, no period involved.
- **Draft-query behavior:** `requested_revision_ids=[v4_under_review]`
  (scenario `J2_under_review_via_draft_intent`) returns it, labeled
  `under_review`.
- **What this scenario does NOT imply:** `draft` and `under_review` are
  not the same derived state — they are reported distinctly, both
  simply share the same *eligibility* rule for `draft` intent.

## K. Current revision withdrawn with no replacement

- **Business situation:** the only effective revision of a document is
  formally withdrawn and nothing has been approved to replace it yet.
- **Event (item 2):** `withdraw_revision(w1,
  withdrawal_effective_date=2024-01-01, closure_reason="withdrawn")` —
  closes the OPEN period at `withdrawal_effective_date` (never
  `recorded_at`), sets `publication_status="withdrawn"`, appends ONE
  `revision_withdrawn` event carrying `decision_effective_date` as a
  STRUCTURED field (never reconstructed by parsing `detail`'s prose).
- **Default-current query behavior:** `current` as of `2025-06-01`
  (scenario `K_withdrawn_no_replacement`) returns **zero** eligible
  revisions and `integrity_error_code=no_effective_revision` — never a
  silent empty success.
- **What this scenario does NOT imply:** the resolver never
  auto-selects a fallback — a human/governance decision
  (`activate_revision`/`reinstate_revision` for a real replacement) is
  required. See H2 above for the "before withdrawal" side of this same
  document.

## L. Conflicting overlapping effective revisions

- **Business situation:** operator error — two revisions of the same
  document both end up "effective" at once.
- **Registry precondition (item 4's own validation changed how this
  scenario must be constructed):** Stage 7R.1a's pre-activation overlap
  check now REJECTS a second independent
  `activate_revision(old=None)` call while a first period is still
  open — so this precondition can no longer arise from two ordinary
  service calls. The contract constructs it via one legitimate
  activation (`c1`) plus one raw, low-level repository write bypassing
  `service.py` entirely (`corrupt_metadata` + `corrupt_period` for
  `c2`), simulating pre-existing inconsistent data (e.g. from before
  this validation existed) rather than a mistake the service itself
  could still be tricked into making.
- **Default-current query behavior:** `current` as of `2025-06-01`
  (scenario `L_overlapping_effective_revisions`) fails closed:
  `integrity_error_code=cross_revision_period_overlap`,
  `eligible_revision_ids=[]`.
- **Comparison/draft-query behavior (Stage 7R.1b):** ALSO fails the
  whole query closed with the same `cross_revision_period_overlap`
  code. This is a document-SCOPED problem (the shared timeline between
  `c1` and `c2` is structurally broken, not a defect of either
  revision's own record alone), and Stage 7R.1b's central integrity
  validator (`integrity.py`) treats every document-scoped problem as a
  hard error for ALL FOUR intents, including comparison/draft — there
  is nothing trustworthy left to compare or browse. This differs from
  a REVISION-scoped problem (e.g. one draft revision with a spuriously
  real period), which comparison/draft still exclude individually
  without aborting the rest of the query.
- **What this scenario does NOT imply:** the resolver never attempts
  automatic reconciliation (e.g. "prefer the later effective_from") —
  silently picking one, by any rule, is exactly what this package
  refuses to do.

## M. `pre_effective_authority_correction` (renamed from Stage 7R.1's "M")

- **Business situation:** a proposed 12-year retention period revision
  is approved-future, then retracted BEFORE it ever took effect.
- **Registry precondition:** `activate_revision(v6, old=None,
  effective_from=2029-01-01)` opens `v6`'s period; then
  `withdraw_revision(v6, withdrawal_effective_date=2029-01-01,
  closure_reason="correction")` closes it — `withdrawal_effective_date`
  equals the period's own `effective_from`, producing a **zero-width**
  period `[2029-01-01, 2029-01-01)` that matches no `as_of_date` at all.
  `closure_reason="correction"` reverts `publication_status` to
  `"draft"` (distinct from `"withdrawn"`, which `closure_reason=
  "withdrawn"`/`"rollback"` produce).
- **Comparison-query behavior:** requesting `v6` (scenario
  `M_pre_effective_authority_correction`) shows it back in `draft`.
- **A real bug found and fixed during development:** a zero-width
  period on a `draft` revision was originally (wrongly) flagged as the
  "effective revision is not approved" integrity violation, since the
  naive rule was "draft revisions must have zero periods". Corrected to
  "draft revisions must have zero *real* (non-zero-width) periods" —
  see `derive_authority_state`'s own docstring and
  `test_draft_with_a_zero_width_period_is_still_draft_not_an_error`.
- **What this scenario does NOT imply:** it does not imply this
  revision interacts with any OTHER revision's own period at all — kept
  in its own isolated logical document (`POLICY-CORRECTION-DEMO-001`)
  in the contract precisely because a *pre-effective* correction never
  needs to.

## E2. Post-effective rollback and reinstatement (item 3)

- **Business situation:** `rv3` effective from 2023-01-01 is superseded
  by `rv5` from 2028-01-01 — but `rv5` is later rolled back
  (2028-06-01), and `rv3` is REINSTATED, effective again from that same
  date. Unlike Scenario M, `rv5` genuinely WAS effective for real dates
  (2028-01-01 through 2028-06-01) before being rolled back.
- **Event:** `reinstate_revision(new=rv3, old=rv5,
  effective_from=2028-06-01)` — a thin wrapper over the SAME validated,
  atomic `activate_revision` machinery, with `closure_reason_for_old=
  "rollback"` (vs. the default `"superseded"`) for audit clarity. This
  opens `rv3`'s SECOND, disjoint authority period
  (`[2028-06-01, None)`) without touching or destroying its FIRST
  period (`[2023-01-01, 2028-01-01)`, closed `superseded`) — `rv3` now
  has two periods on file, both preserved.
- **As-of query behavior:**
  - `as_of_date=2027-12-31` (scenario `E2_post_effective_rollback_before`)
    → `rv3` (its first period).
  - `as_of_date=2028-03-01` (scenario `E2_post_effective_rollback_during`)
    → `rv5` (its only period); `rv3` labeled `approved_future` at this
    date — see note below.
  - `as_of_date=2028-07-01`/`current` (scenario
    `E2_post_effective_rollback_after`) → `rv3` again, via its SECOND
    period; `rv5` now `superseded`.
- **A deliberate, documented design choice (not specified by the task,
  resolved during implementation):** at `2028-03-01`, `rv3`'s own label
  is `approved_future`, not `superseded` — mechanically, `rv3` HAS a
  scheduled future period (`2028-06-01`) as of that date, and
  `derive_authority_state` treats "has a period starting later" as
  `approved_future` regardless of whether the revision was ALSO
  effective in the past. This keeps the derivation rule uniform (never
  special-cased for "this revision has a history"), and is verified
  directly by `test_post_effective_rollback_before_during_after`.
- **Expected index behavior:** no chunks are changed, deleted,
  rechunked, or re-embedded at any point in this whole sequence —
  `rv3`'s canonical chunks (had this been a real ingested document)
  would be identical before the supersession, during `rv5`'s window,
  and after reinstatement.
- **What this scenario does NOT imply:** it does not imply
  `reinstate_revision` is a DIFFERENT operation from `activate_revision`
  at the data-model level — it is the exact same atomic transition,
  under a self-documenting name, with a different default
  `closure_reason_for_old`.

## N. Same textual content across different revision identities

- **Business situation:** the exact same paragraph/boilerplate text is
  legitimately reused across two UNRELATED logical documents.
- **Registry precondition:** `POLICY-SHARED-TEXT-DEMO-001`'s
  `n1_shares_v2_text` has the byte-identical `source_document_sha256`
  as `POLICY-RESILIENCE-001`'s `v2`, but a DIFFERENT
  `logical_document_id`.
- **Resulting registry state:** a completely independent
  `document_revision_id` (the hash differs because `logical_document_id`
  differs) — proven directly by `compute_document_revision_id`'s own
  hash inputs.
- **What this scenario does NOT imply:** `source_document_sha256` alone
  is never a revision's identity — identity is always the FULL tuple.

## O. Effective-date boundary behavior

- **Business situation:** precise handling of the exact day authority
  changes hands — an off-by-one here would either double-serve or
  gap-serve a policy for one day.
- **Default-current query behavior:** `2027-12-31`
  (`O_boundary_day_before`) → `v3` still effective; `2028-01-01`
  (`E_supersession_boundary_on`) → `v5` now effective, `v3` now
  superseded — exactly one revision eligible on either side, never zero
  (a gap) and never two (an overlap).
- **What this scenario does NOT imply:** `effective_to` is never
  treated as inclusive anywhere in this package.

---

## Malformed-record scenarios (item 6)

`POLICY-MALFORMED-DEMO-001`'s `m1` is left `publication_status="draft"`
but given a REAL (non-zero-width) authority period via a raw repository
write — the exact "effective revision is not approved" integrity
violation, constructed directly (never reachable via normal service
calls).

- **`malformed_record_excluded_not_fatal_comparison`**: `comparison`
  intent excludes `m1` individually (`reason_code=
  malformed_authority_record`), `integrity_error=None` — the query
  itself succeeds.
- **`malformed_record_excluded_not_fatal_draft`**: same, under `draft`
  intent.
- **What these do NOT imply:** a malformed record NEVER hard-fails a
  comparison/draft query — only current/as_of intents (which "pick" a
  revision) fail closed on registry-wide integrity problems; comparison/
  draft only exclude the SPECIFIC bad record.

## Duplicate requested revision IDs (item 6)

`duplicate_requested_revision_ids_rejected`: requesting `[v3, v3]`
under `comparison` intent yields ONE eligible entry plus one
`duplicate_request` exclusion for the repeat — never two eligible
entries. Rejected **deterministically** (first occurrence wins, always),
never silently absorbed or silently doubled.

## Cross-document and self-supersession rejection (item 5)

`POLICY-VALIDATION-DEMO-001` proves, directly against the service (both
as contract `expect_error` transition steps and as dedicated pytest
tests):

- `self_supersession_rejected`: `activate_revision(new=val1, old=val1,
  ...)` raises `ActivationValidationError` — "cannot supersede itself".
- `cross_document_activation_rejected`: `activate_revision(new=val1,
  old=v3, ...)` (where `v3` belongs to a DIFFERENT logical document)
  raises — "SAME logical document".

Both checks run in `_validate_activation`, entirely BEFORE any
repository write — a failed validation leaves both revisions completely
unchanged and appends NO event (proven by
`test_a_failed_validation_leaves_both_revisions_unchanged` and
`test_no_event_is_appended_for_a_failed_transition`).

## Atomic rollback (item 4)

`test_failed_activation_leaves_no_partial_registry_period_or_event_mutation`
(parametrized over three fault points: after the new-period write but
before the old-period close; before event append; during event append)
uses a test-only `FaultInjectingRepository` wrapper to raise at each
precise point during a REAL `activate_revision` call, then inspects the
WRAPPED, real `InMemoryRevisionAuthorityRepository`'s own state
afterward — proving `transaction()`'s snapshot-and-restore leaves
**zero** partial mutation, regardless of where the fault occurred.
`test_real_postgres_failed_activation_rolls_back_completely` proves the
same property against a REAL Postgres transaction (BEGIN/COMMIT/
ROLLBACK), not just the in-memory snapshot.

---

## Structured audit events (item 8)

Every `AuthorityDecisionEvent` carries `decision_effective_date` (when
the authority change TAKES EFFECT) as a distinct, structured field from
`recorded_at` (when the decision was RECORDED) — and, for
closure-type events, a structured `closure_reason`. Neither is ever
reconstructed by parsing `detail`'s free-text prose; `detail` is
human-readable context only, never a data source. The event API remains
strictly append-only: `repository.py`'s `RevisionAuthorityRepository`
Protocol exposes `append_event`/`list_events` and no update/delete
method of any kind for events, anywhere.

## What canonical chunks never receive (item 9)

- **Canonical chunks never receive mutable superseded/current flags of
  any kind.** `CanonicalChunk` (Stage 4/4.1) is immutable and untouched
  by this entire package — no field on it changes as authority periods
  open, close, get corrected, or get reinstated.
- **Historical evidence remains unchanged.** A chunk ingested under a
  now-superseded or now-withdrawn revision keeps the exact same
  `content_sha256`, `chunk_id`, and text forever — proven directly
  against the REAL `chunk_document()` pipeline by
  `test_old_canonical_chunk_content_and_hash_remain_unchanged`,
  `test_authority_correction_requires_no_chunk_mutation`.
- **Authority periods determine eligibility, not chunk-level state.**
  Whether a chunk is "in scope" for a query is entirely a function of
  its own `document_revision_id` being in a resolver's
  `eligible_revision_ids` — nothing about the chunk itself changes.
- **If a future retrieval-index authority field is ever added (Stage
  7R.2+), it must be a DERIVED CACHE only** — recomputed from this
  registry's own `AuthorityPeriod`/`AuthorityMetadata` tables, never a
  second authoritative copy an index could drift from. This package
  itself already follows that same discipline internally (`AuthorityPeriod`
  is the SOLE authoritative source for effective dates; nothing else
  duplicates it).
- **Authority changes require no rechunking or re-embedding.** Verified
  structurally (`test_exact_duplicate_does_not_request_rechunking_or_reembedding`,
  `test_authority_correction_requires_no_reembedding`): this package has
  no import of `chunk_document`, any chunking module, or any embedding
  provider anywhere in its own source.

---

## Projection-use-case documentation

The SAME resolver (`resolver.resolve_query_scope` /
`RevisionAuthorityService.resolve_query_scope`) is designed to later serve
every retrieval projection identically — **none of the following is
implemented in Stage 7R.1/7R.1a**; this section documents the intended
Stage 7R.2+ wiring only.

### Regular Vector RAG (Stage 7A.1, Stage 7R.2)

Before similarity ranking, filter the candidate chunk set down to only
those chunks whose `document_revision_id` is in `eligible_revision_ids`
for the query's own `(logical_document_id, query_intent, as_of_date)`.
A `current`-intent search never ranks a draft's or a superseded
revision's chunks alongside the effective revision's — the filter
happens BEFORE ranking, never as a post-hoc re-sort. Any index-side
authority field this wiring introduces must be a derived cache of this
registry's own periods, per the rule above — never a second source of
truth.

### Graph RAG (Stage 7B)

Select revision-scoped nodes and edges before traversal — a graph query
must resolve its own eligible revision set first (same resolver call),
then traverse only edges/nodes belonging to those revisions. **Never
merge superseded and current edges into one timeless fact.** A
comparison-intent graph query can legitimately traverse both revisions'
subgraphs side by side, each edge retaining its own revision's authority
label — exactly like Scenario I/E2 above.

### Wiki retrieval (Stage 7C)

The current page for a logical document resolves from whichever
revision the resolver returns for `current` intent — never a
freshly-computed "most recent" heuristic. Revision history remains
separately navigable (an `as_of`/`comparison`-intent view over the same
resolver, driving a "view as of this date" or "compare revisions" page
— including a revision with MULTIPLE periods, like `rv3` in Scenario
E2). Every wiki statement stays linked to its own revision-scoped
chunks (via `source_element_ids`/`source_refs`, already on
`CanonicalChunk`).
