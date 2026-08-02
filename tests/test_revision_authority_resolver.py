"""Stage 7R.1: resolver tests -- the four query intents, fail-closed
integrity checks, determinism, and the registry snapshot hash.

Several tests write directly to the repository's low-level
save_identity/save_metadata methods (bypassing service.py's own business
rules) to simulate a genuinely corrupted/inconsistent registry state --
the resolver is the safety net for exactly that, never something that
merely trusts the service layer never misbehaves.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from ingestion_bench.revision_authority.model import AuthorityMetadata, AuthorityPeriod
from ingestion_bench.revision_authority.repository import InMemoryRevisionAuthorityRepository
from ingestion_bench.revision_authority.resolver import resolve_query_scope
from ingestion_bench.revision_authority.service import RevisionAuthorityService

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _service() -> tuple[RevisionAuthorityService, InMemoryRevisionAuthorityRepository]:
    repo = InMemoryRevisionAuthorityRepository()
    return RevisionAuthorityService(repo), repo


def _register(service, sha, **overrides):
    defaults = dict(
        logical_document_id="DOC-1", source_document_sha256=sha, version_label=None, revision_number=1,
        authority_source="gov", authority_reference="REF", authority_recorded_by="alice", recorded_at=NOW,
    )
    defaults.update(overrides)
    return service.register_revision(**defaults).identity


def test_current_query_returns_only_effective_revision():
    """Business nuance: 'current' must return EXACTLY the one revision
    whose effective window covers as_of_date -- never zero when one
    legitimately exists, never the draft/superseded siblings alongside
    it. Failure this guards against: a default search silently including
    stale or unreviewed content. Affects: current search directly."""
    service, _ = _service()
    old = _register(service, "a" * 64, revision_number=1)
    new = _register(service, "b" * 64, revision_number=2)
    service.activate_revision(new_revision_id=old.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    service.activate_revision(new_revision_id=new.document_revision_id, old_revision_id=old.document_revision_id, effective_from=date(2023, 1, 1), authority_source="gov", authority_reference="A2", authority_recorded_by="alice", recorded_at=NOW)

    result = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2024, 1, 1))
    assert result.eligible_revision_ids == [new.document_revision_id]
    assert result.integrity_error is None


def test_as_of_query_returns_historical_effective_revision():
    """Business nuance: 'as_of' with a PAST date must return whichever
    revision was actually effective THEN, not whatever is current now.
    Failure this guards against: a historical/audit query silently
    reflecting present-day state instead of the requested point in time.
    Affects: historical search directly, and auditability (a legal-hold
    or compliance query must be trustworthy)."""
    service, _ = _service()
    old = _register(service, "a" * 64, revision_number=1)
    new = _register(service, "b" * 64, revision_number=2)
    service.activate_revision(new_revision_id=old.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    service.activate_revision(new_revision_id=new.document_revision_id, old_revision_id=old.document_revision_id, effective_from=date(2023, 1, 1), authority_source="gov", authority_reference="A2", authority_recorded_by="alice", recorded_at=NOW)

    result = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="as_of", as_of_date=date(2021, 6, 1))
    assert result.eligible_revision_ids == [old.document_revision_id]


def test_comparison_query_allows_explicit_superseded_revisions():
    """Business nuance: comparison intent must permit BOTH a superseded
    and a current revision in the same result, each keeping its own
    label -- current/as_of intents would never do this (they pick
    exactly one). Failure this guards against: a comparison UI/API
    unable to show history because the resolver forces a single
    'winner'. Affects: auditability and historical search (side-by-side
    revision comparison is impossible otherwise)."""
    service, _ = _service()
    old = _register(service, "a" * 64, revision_number=1)
    new = _register(service, "b" * 64, revision_number=2)
    service.activate_revision(new_revision_id=old.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    service.activate_revision(new_revision_id=new.document_revision_id, old_revision_id=old.document_revision_id, effective_from=date(2023, 1, 1), authority_source="gov", authority_reference="A2", authority_recorded_by="alice", recorded_at=NOW)

    result = service.resolve_query_scope(
        logical_document_id="DOC-1", query_intent="comparison", as_of_date=date(2024, 1, 1),
        requested_revision_ids=[old.document_revision_id, new.document_revision_id],
    )
    assert set(result.eligible_revision_ids) == {old.document_revision_id, new.document_revision_id}
    assert result.authority_labels[old.document_revision_id].derived_state == "superseded"
    assert result.authority_labels[new.document_revision_id].derived_state == "effective"


def test_draft_query_requires_explicit_draft_intent():
    """Business nuance: a draft is only ever visible through the
    dedicated 'draft' intent with its id explicitly requested -- it must
    never appear in a 'current'/'as_of' result, and a NON-draft revision
    requested under 'draft' intent must be excluded, never silently
    included. Failure this guards against: unreviewed content leaking
    into an ordinary search result set. Affects: current search
    (drafts must never appear there) and auditability (a reviewer's
    draft-only view must be trustworthy)."""
    service, _ = _service()
    draft = _register(service, "a" * 64, revision_number=1)
    effective = _register(service, "b" * 64, revision_number=2)
    service.activate_revision(new_revision_id=effective.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)

    current_result = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2024, 1, 1))
    assert draft.document_revision_id not in current_result.eligible_revision_ids

    draft_result = service.resolve_query_scope(
        logical_document_id="DOC-1", query_intent="draft", as_of_date=date(2024, 1, 1),
        requested_revision_ids=[draft.document_revision_id, effective.document_revision_id],
    )
    assert draft_result.eligible_revision_ids == [draft.document_revision_id]
    excluded_ids = {e.revision_id for e in draft_result.excluded}
    assert effective.document_revision_id in excluded_ids


def test_withdrawn_current_without_replacement_fails_closed():
    """Business nuance: a document whose only revision was withdrawn,
    with nothing yet approved to replace it, must FAIL CLOSED -- an
    empty eligible list alone would be indistinguishable from 'this
    document doesn't exist' or 'no results matched'. Failure this
    guards against: silently returning zero results as if that were a
    normal, healthy outcome. Affects: current search (must surface the
    integrity_error to the caller) and auditability."""
    service, _ = _service()
    only = _register(service, "a" * 64)
    service.activate_revision(new_revision_id=only.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    service.withdraw_revision(document_revision_id=only.document_revision_id, withdrawal_effective_date=date(2023, 1, 1), authority_source="gov", authority_reference="W1", authority_recorded_by="alice", recorded_at=NOW)

    result = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2024, 1, 1))
    assert result.eligible_revision_ids == []
    assert result.integrity_error is not None
    assert result.integrity_error_code == "no_effective_revision"
    assert "no authoritative effective revision" in result.integrity_error


def test_withdrawal_before_and_after_date_resolves_differently():
    """Business nuance (Stage 7R.1a item 2's core fix): withdrawal takes
    effect on withdrawal_effective_date, never recorded_at -- an as_of
    date BEFORE withdrawal, still within the old (now-closed) period,
    must resolve effective; on/after withdrawal, ineligible. Failure
    this guards against: conflating 'when the decision was recorded'
    with 'when it takes effect', which would corrupt every historical
    query touching a withdrawn revision. Affects: historical search
    directly."""
    service, _ = _service()
    only = _register(service, "a" * 64)
    service.activate_revision(new_revision_id=only.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    # Recorded in 2025, but takes effect 2023-01-01 -- recorded_at must
    # never be consulted for date resolution.
    service.withdraw_revision(
        document_revision_id=only.document_revision_id, withdrawal_effective_date=date(2023, 1, 1),
        authority_source="gov", authority_reference="W1", authority_recorded_by="alice",
        recorded_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
    )

    before = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="as_of", as_of_date=date(2021, 1, 1))
    after = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="as_of", as_of_date=date(2023, 1, 1))
    assert before.eligible_revision_ids == [only.document_revision_id]
    assert after.eligible_revision_ids == []
    assert after.integrity_error_code == "no_effective_revision"


def test_overlapping_effective_revisions_fail_closed():
    """Business nuance: two revisions of ONE logical document must never
    both be 'effective' at once. This precondition can no longer be
    reached through ordinary service usage (Stage 7R.1a's own
    pre-activation overlap validation rejects a second independent
    activate_revision(old=None) call while a first period is still
    open) -- so it is constructed here the same way the contract's own
    Scenario L does: one legitimate activation plus one raw,
    low-level repository write, simulating pre-existing inconsistent
    data. Failure this guards against: silently picking the
    higher-hashed / most-recently-written / arbitrary revision, which
    would make search results non-deterministic and unauditable.
    Affects: current search directly -- this is Scenario L."""
    service, repo = _service()
    a = _register(service, "a" * 64, revision_number=1)
    b = _register(service, "b" * 64, revision_number=2)
    service.activate_revision(new_revision_id=a.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    repo.save_metadata(b.document_revision_id, AuthorityMetadata(
        publication_status="approved", authority_source="gov", authority_reference="R2",
        authority_recorded_at=NOW, authority_recorded_by="alice",
    ))
    repo.save_period(AuthorityPeriod(
        authority_period_id=0, logical_document_id="DOC-1", document_revision_id=b.document_revision_id,
        effective_from=date(2021, 1, 1), effective_to=None, opening_event_id=1,
        authority_source="gov", authority_reference="RAW", recorded_at=NOW, recorded_by="alice",
    ))

    result = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2024, 1, 1))
    assert result.eligible_revision_ids == []
    assert result.integrity_error is not None
    # Stage 7R.1b item 3: the central, date-independent
    # cross_revision_period_overlap check now catches this (and any
    # other) case of two revisions' periods overlapping ANYWHERE in
    # history -- a strictly broader, more precise classification than
    # the old as_of-date-scoped "overlapping_effective_revisions" check,
    # which is now unreachable (any two periods simultaneously
    # "effective" at one date necessarily also overlap structurally).
    assert result.integrity_error_code == "cross_revision_period_overlap"
    assert "overlaps" in result.integrity_error


def test_inconsistent_supersession_links_fail_closed():
    """Business nuance: a period closed as 'superseded'/'rollback' must
    always have a matching successor period (predecessor_revision_id
    pointing back, effective_from matching the closed period's own
    effective_to) -- this can never happen via activate_revision's own
    atomic transition, so this test constructs a corrupted state
    directly via the repository's low-level save_period (simulating a
    bad manual edit or a bug elsewhere) to prove the RESOLVER, not just
    the service, is the real safety net. Failure this guards against: a
    broken link silently being ignored, which could hide a genuine
    registry corruption from an auditor. Affects: current search
    (refuses to resolve at all) and auditability (surfaces the exact
    inconsistency)."""
    service, repo = _service()
    a = _register(service, "a" * 64, revision_number=1)
    repo.save_metadata(a.document_revision_id, AuthorityMetadata(
        publication_status="approved", authority_source="gov", authority_reference="R1",
        authority_recorded_at=NOW, authority_recorded_by="alice",
    ))
    # a's period claims to have been superseded (closed) but NO other
    # revision's period has a matching predecessor_revision_id/effective_from.
    repo.save_period(AuthorityPeriod(
        authority_period_id=0, logical_document_id="DOC-1", document_revision_id=a.document_revision_id,
        effective_from=date(2020, 1, 1), effective_to=date(2023, 1, 1), opening_event_id=1,
        closing_event_id=2, closure_reason="superseded",
        authority_source="gov", authority_reference="RAW", recorded_at=NOW, recorded_by="alice",
    ))

    result = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2024, 1, 1))
    assert result.eligible_revision_ids == []
    assert result.integrity_error is not None
    assert result.integrity_error_code == "missing_successor"
    assert "successor" in result.integrity_error


def test_effective_revision_must_be_approved():
    """Business nuance: only publication_status='approved' may ever
    resolve to derived state 'effective' -- constructed here via a
    direct repository write (a draft record with a REAL, non-zero-width
    period, impossible through normal service calls) to prove the
    resolver treats this as a hard integrity error, never as a silently
    'effective' or silently 'draft' outcome. Failure this guards
    against: an authority-bypass bug granting current status to
    unreviewed content. Affects: current search (a serious authority
    violation if it ever happened for real) and auditability."""
    service, repo = _service()
    corrupted = _register(service, "a" * 64)
    repo.save_period(AuthorityPeriod(
        authority_period_id=0, logical_document_id="DOC-1", document_revision_id=corrupted.document_revision_id,
        effective_from=date(2020, 1, 1), effective_to=None, opening_event_id=1,
        authority_source="gov", authority_reference="R1", recorded_at=NOW, recorded_by="alice",
    ))

    result = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2024, 1, 1))
    assert result.eligible_revision_ids == []
    assert result.integrity_error is not None
    # Sourced from the central validator (item 3) -- specific, not a generic
    # bucket code, consistent with the rest of the package's reason_code style.
    assert result.integrity_error_code == "unapproved_with_real_period"
    assert "not approved" in result.integrity_error.lower()


def test_malformed_record_excluded_individually_under_comparison_never_fatal():
    """Business nuance (item 3/6): comparison/draft intents must NEVER
    hard-fail the whole query because ONE requested revision's record is
    malformed IN A WAY THAT IS SPECIFIC TO ITSELF (a REVISION-scoped
    problem, e.g. a draft revision with a real period) -- it is excluded
    individually, with the integrity error as its own exclusion reason.
    `bad`'s period is deliberately NON-overlapping with `good`'s so this
    test isolates the revision-scoped case from the DOCUMENT-scoped
    cross_revision_period_overlap case (which correctly fails the whole
    query -- see test_malformed_comparison_document_scoped_problem_fails_whole_query).
    Failure this guards against: one bad record silently making an
    entire comparison/audit view unusable. Affects: auditability
    directly (comparison mode exists precisely to inspect a registry,
    including a broken one)."""
    service, repo = _service()
    good = _register(service, "a" * 64, revision_number=1)
    service.activate_revision(new_revision_id=good.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    bad = _register(service, "b" * 64, revision_number=2)
    # bad stays "draft" (never approved) but gets a REAL period anyway --
    # a revision-scoped problem. good's period is OPEN-ENDED from 2020
    # onward, so bad's spurious period must be fully BOUNDED and entirely
    # BEFORE 2020 to be disjoint -- anything from 2020 onward would also
    # trip the document-scoped cross_revision_period_overlap check.
    repo.save_period(AuthorityPeriod(
        authority_period_id=0, logical_document_id="DOC-1", document_revision_id=bad.document_revision_id,
        effective_from=date(2010, 1, 1), effective_to=date(2015, 1, 1), opening_event_id=1,
        authority_source="gov", authority_reference="RAW", recorded_at=NOW, recorded_by="alice",
    ))

    result = service.resolve_query_scope(
        logical_document_id="DOC-1", query_intent="comparison", as_of_date=date(2024, 1, 1),
        requested_revision_ids=[good.document_revision_id, bad.document_revision_id],
    )
    assert result.integrity_error is None
    assert result.eligible_revision_ids == [good.document_revision_id]
    excluded = {e.revision_id: e.reason_code for e in result.excluded}
    assert excluded[bad.document_revision_id] == "malformed_authority_record"


def test_document_scoped_overlap_fails_the_whole_comparison_query():
    """Business nuance (item 3): unlike a REVISION-scoped problem (which
    only excludes the one bad revision), a DOCUMENT-scoped problem --
    here, two DIFFERENT revisions' periods genuinely overlapping in the
    shared timeline -- makes the whole document untrustworthy, so it
    fails the WHOLE comparison query closed, never just excluding one
    side of the overlap. Failure this guards against: a comparison view
    silently showing two overlapping "effective" periods as if the
    timeline were coherent. Affects: auditability (comparison exists to
    audit a registry -- it must say so plainly when the registry itself
    is broken, not paper over it)."""
    service, repo = _service()
    a = _register(service, "a" * 64, revision_number=1)
    b = _register(service, "b" * 64, revision_number=2)
    service.activate_revision(new_revision_id=a.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    repo.save_metadata(b.document_revision_id, AuthorityMetadata(
        publication_status="approved", authority_source="gov", authority_reference="R2",
        authority_recorded_at=NOW, authority_recorded_by="alice",
    ))
    repo.save_period(AuthorityPeriod(
        authority_period_id=0, logical_document_id="DOC-1", document_revision_id=b.document_revision_id,
        effective_from=date(2021, 1, 1), effective_to=None, opening_event_id=1,
        authority_source="gov", authority_reference="RAW", recorded_at=NOW, recorded_by="alice",
    ))

    result = service.resolve_query_scope(
        logical_document_id="DOC-1", query_intent="comparison", as_of_date=date(2024, 1, 1),
        requested_revision_ids=[a.document_revision_id, b.document_revision_id],
    )
    assert result.eligible_revision_ids == []
    assert result.integrity_error is not None
    assert result.integrity_error_code == "cross_revision_period_overlap"


def test_document_scoped_broken_link_fails_the_whole_draft_query():
    """Business nuance (item 3): a DOCUMENT-scoped broken supersession
    link fails the whole `draft` query closed too, not just current/
    as_of/comparison -- the same "the shared timeline itself cannot be
    trusted" reasoning applies regardless of which intent asked.
    Affects: auditability."""
    service, repo = _service()
    a = _register(service, "a" * 64, revision_number=1)
    draft_candidate = _register(service, "b" * 64, revision_number=2)
    repo.save_metadata(a.document_revision_id, AuthorityMetadata(
        publication_status="approved", authority_source="gov", authority_reference="R1",
        authority_recorded_at=NOW, authority_recorded_by="alice",
    ))
    # a's period claims to have been superseded but nothing picks up --
    # a broken, document-scoped link.
    repo.save_period(AuthorityPeriod(
        authority_period_id=0, logical_document_id="DOC-1", document_revision_id=a.document_revision_id,
        effective_from=date(2020, 1, 1), effective_to=date(2023, 1, 1), opening_event_id=1,
        closing_event_id=2, closure_reason="superseded",
        authority_source="gov", authority_reference="RAW", recorded_at=NOW, recorded_by="alice",
    ))

    result = service.resolve_query_scope(
        logical_document_id="DOC-1", query_intent="draft", as_of_date=date(2024, 1, 1),
        requested_revision_ids=[draft_candidate.document_revision_id],
    )
    assert result.eligible_revision_ids == []
    assert result.integrity_error is not None
    assert result.integrity_error_code == "missing_successor"


def test_duplicate_requested_revision_ids_deduplicated_not_doubled():
    """Business nuance (item 6): requesting the same revision id twice
    must never produce two eligible entries -- the second occurrence is
    rejected deterministically (an explicit duplicate_request exclusion)
    rather than silently ignored or silently duplicated. Affects:
    auditability (a caller bug must be visible, not silently
    absorbed)."""
    service, _ = _service()
    a = _register(service, "a" * 64, revision_number=1)
    service.activate_revision(new_revision_id=a.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)

    result = service.resolve_query_scope(
        logical_document_id="DOC-1", query_intent="comparison", as_of_date=date(2024, 1, 1),
        requested_revision_ids=[a.document_revision_id, a.document_revision_id],
    )
    assert result.eligible_revision_ids == [a.document_revision_id]
    duplicate_exclusions = [e for e in result.excluded if e.reason_code == "duplicate_request"]
    assert len(duplicate_exclusions) == 1
    assert duplicate_exclusions[0].revision_id == a.document_revision_id


def test_effective_interval_is_start_inclusive_end_exclusive():
    """Business nuance: effective_from <= as_of_date < effective_to --
    the exact boundary day belongs to the NEW revision, not the old one
    (Scenario O/E). Failure this guards against: an off-by-one either
    creating a one-day gap (neither revision effective) or a one-day
    overlap (both effective, triggering the Scenario L failure).
    Affects: current search directly, on exactly the day authority
    changes hands."""
    service, _ = _service()
    old = _register(service, "a" * 64, revision_number=1)
    new = _register(service, "b" * 64, revision_number=2)
    service.activate_revision(new_revision_id=old.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    service.activate_revision(new_revision_id=new.document_revision_id, old_revision_id=old.document_revision_id, effective_from=date(2023, 6, 1), authority_source="gov", authority_reference="A2", authority_recorded_by="alice", recorded_at=NOW)

    day_before = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2023, 5, 31))
    boundary_day = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2023, 6, 1))
    assert day_before.eligible_revision_ids == [old.document_revision_id]
    assert boundary_day.eligible_revision_ids == [new.document_revision_id]


def test_resolver_is_deterministic():
    """Business nuance: calling resolve_query_scope multiple times with
    the SAME registry state and SAME arguments must always return the
    same eligible_revision_ids, excluded reasons, and
    registry_snapshot_hash. Failure this guards against: any hidden
    nondeterminism (unsorted dict/set iteration, wall-clock dependence)
    silently making two runs of the same benchmark disagree. Affects:
    benchmark fairness directly, and auditability (a resolution must be
    reproducible after the fact)."""
    service, _ = _service()
    a = _register(service, "a" * 64, revision_number=1)
    service.activate_revision(new_revision_id=a.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)

    results = [
        service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2024, 1, 1))
        for _ in range(5)
    ]
    assert len({r.model_dump_json() for r in results}) == 1


def test_registry_snapshot_hash_changes_when_authority_changes():
    """Business nuance: registry_snapshot_hash must change whenever ANY
    authority fact for the queried document changes (new revision,
    decision, activation, withdrawal) -- it is the mechanism an auditor
    or a caching layer uses to detect 'did anything change since I last
    looked'. Failure this guards against: a stale/insensitive hash that
    never changes, silently hiding real registry mutations. Affects:
    auditability directly."""
    service, _ = _service()
    a = _register(service, "a" * 64, revision_number=1)
    before = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2024, 1, 1))
    service.activate_revision(new_revision_id=a.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    after = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2024, 1, 1))
    assert before.registry_snapshot_hash != after.registry_snapshot_hash


def test_registry_snapshot_hash_is_stable_when_nothing_changes():
    service, _ = _service()
    _register(service, "a" * 64, revision_number=1)
    r1 = resolve_query_scope(
        InMemoryRevisionAuthorityRepository(), "DOC-EMPTY", "current", date(2024, 1, 1)
    )
    r2 = resolve_query_scope(
        InMemoryRevisionAuthorityRepository(), "DOC-EMPTY", "current", date(2024, 1, 1)
    )
    assert r1.registry_snapshot_hash == r2.registry_snapshot_hash
