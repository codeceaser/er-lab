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

from ingestion_bench.revision_authority.model import AuthorityMetadata, RevisionIdentity
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
    service.withdraw_revision(document_revision_id=only.document_revision_id, authority_source="gov", authority_reference="W1", authority_recorded_by="alice", recorded_at=NOW)

    result = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2024, 1, 1))
    assert result.eligible_revision_ids == []
    assert result.integrity_error is not None
    assert "no authoritative effective revision" in result.integrity_error


def test_overlapping_effective_revisions_fail_closed():
    """Business nuance: two revisions of ONE logical document must never
    both be 'effective' at once -- if the registry ends up in that state
    (a real operator-misuse case: activating two revisions independently
    with old=None), the resolver must refuse to guess which one is
    right. Failure this guards against: silently picking the
    higher-hashed / most-recently-written / arbitrary revision, which
    would make search results non-deterministic and unauditable. Affects:
    current search directly -- this is Scenario L."""
    service, _ = _service()
    a = _register(service, "a" * 64, revision_number=1)
    b = _register(service, "b" * 64, revision_number=2)
    service.activate_revision(new_revision_id=a.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    service.activate_revision(new_revision_id=b.document_revision_id, old_revision_id=None, effective_from=date(2021, 1, 1), authority_source="gov", authority_reference="A2", authority_recorded_by="alice", recorded_at=NOW)

    result = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2024, 1, 1))
    assert result.eligible_revision_ids == []
    assert result.integrity_error is not None
    assert "simultaneously effective" in result.integrity_error


def test_inconsistent_supersession_links_fail_closed():
    """Business nuance: supersedes_revision_id/superseded_by_revision_id
    must always be mutual and point at a revision that actually exists
    -- this can never happen via activate_revision's own atomic
    transition, so this test constructs a corrupted state directly via
    the repository's low-level save_metadata (simulating a bad manual
    edit or a bug elsewhere) to prove the RESOLVER, not just the
    service, is the real safety net. Failure this guards against: a
    broken link silently being ignored, which could hide a genuine
    registry corruption from an auditor. Affects: current search
    (refuses to resolve at all) and auditability (surfaces the exact
    inconsistency)."""
    service, repo = _service()
    a = _register(service, "a" * 64, revision_number=1)
    b = _register(service, "b" * 64, revision_number=2)
    # a claims to be superseded by b, but b does NOT claim to supersede a.
    repo.save_metadata(a.document_revision_id, AuthorityMetadata(
        publication_status="approved", effective_from=date(2020, 1, 1), effective_to=date(2023, 1, 1),
        superseded_by_revision_id=b.document_revision_id,
        authority_source="gov", authority_reference="R1", authority_recorded_at=NOW, authority_recorded_by="alice",
    ))
    repo.save_metadata(b.document_revision_id, AuthorityMetadata(
        publication_status="approved", effective_from=date(2023, 1, 1), effective_to=None,
        authority_source="gov", authority_reference="R2", authority_recorded_at=NOW, authority_recorded_by="alice",
    ))

    result = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2024, 1, 1))
    assert result.eligible_revision_ids == []
    assert result.integrity_error is not None
    assert "supersession" in result.integrity_error


def test_effective_revision_must_be_approved():
    """Business nuance: only publication_status='approved' may ever
    resolve to derived state 'effective' -- constructed here via a
    direct repository write (a draft record with effective_from
    populated, impossible through normal service calls) to prove the
    resolver treats this as a hard integrity error, never as a silently
    'effective' or silently 'draft' outcome. Failure this guards
    against: an authority-bypass bug granting current status to
    unreviewed content. Affects: current search (a serious authority
    violation if it ever happened for real) and auditability."""
    service, repo = _service()
    corrupted = _register(service, "a" * 64)
    repo.save_metadata(corrupted.document_revision_id, AuthorityMetadata(
        publication_status="draft", effective_from=date(2020, 1, 1), effective_to=None,
        authority_source="gov", authority_reference="R1", authority_recorded_at=NOW, authority_recorded_by="alice",
    ))

    result = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2024, 1, 1))
    assert result.eligible_revision_ids == []
    assert result.integrity_error is not None
    assert "not approved" in result.integrity_error.lower()


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
