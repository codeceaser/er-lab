"""Stage 7R.1a: atomicity, fault-injection, and cross-document/self-
transition rejection tests.

FaultInjectingRepository wraps a real InMemoryRevisionAuthorityRepository
and raises at a precisely chosen point during activate_revision's
multi-step write, so the test can inspect the WRAPPED repository's own
state afterward and prove the transaction rolled back completely --
never a mock standing in for real behavior.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from ingestion_bench.revision_authority.model import AuthorityPeriod
from ingestion_bench.revision_authority.repository import InMemoryRevisionAuthorityRepository
from ingestion_bench.revision_authority.service import ActivationValidationError, RevisionAuthorityService

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


class FaultInjectingRepository:
    """Test-only wrapper: raises at one of three precise points during a
    multi-step write, delegating everything else (including
    transaction(), which governs the REAL inner repository's own
    snapshot/restore) to the wrapped InMemoryRevisionAuthorityRepository."""

    def __init__(self, inner: InMemoryRevisionAuthorityRepository, fault: str) -> None:
        self._inner = inner
        self._fault = fault
        self._save_period_calls = 0

    def append_event(self, event):
        if self._fault == "before_event_append":
            raise RuntimeError("injected fault: before event append")
        if self._fault == "during_event_append":
            raise RuntimeError("injected fault: during event append")
        return self._inner.append_event(event)

    def save_period(self, period):
        self._save_period_calls += 1
        result = self._inner.save_period(period)  # the write itself succeeds...
        if self._fault == "after_new_period_before_old_close" and self._save_period_calls == 1:
            raise RuntimeError("injected fault: after new-period write, before old-period close")  # ...then the fault fires
        return result

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _service(inner: InMemoryRevisionAuthorityRepository) -> RevisionAuthorityService:
    return RevisionAuthorityService(inner)


def _register_and_activate_first(service: RevisionAuthorityService, sha: str, revision_number: int) -> str:
    result = service.register_revision(
        logical_document_id="DOC-1", source_document_sha256=sha, version_label=None, revision_number=revision_number,
        authority_source="gov", authority_reference="REF", authority_recorded_by="alice", recorded_at=NOW,
    )
    service.activate_revision(
        new_revision_id=result.identity.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1),
        authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW,
    )
    return result.identity.document_revision_id


@pytest.mark.parametrize(
    "fault",
    ["after_new_period_before_old_close", "before_event_append", "during_event_append"],
)
def test_failed_activation_leaves_no_partial_registry_period_or_event_mutation(fault: str):
    """Business nuance: activate_revision writes to THREE places
    (metadata, an event, and one or two periods) -- if anything fails
    partway through (a real crash, an unexpected exception), NONE of
    those writes may remain, or the registry could end up with a period
    that references a nonexistent event, two revisions simultaneously
    effective, or a revision silently "approved" with no period backing
    it. Failure this guards against: a torn write corrupting the
    registry in a way ordinary queries might not even detect until much
    later. Affects: current search (a torn write could easily produce
    Scenario L's overlapping-effective failure mode for real, not just
    as a hypothetical) and auditability (a partial event/period pair
    would be unexplainable during a later audit)."""
    inner = InMemoryRevisionAuthorityRepository()
    service = _service(inner)
    old_id = _register_and_activate_first(service, "a" * 64, 1)

    new_result = service.register_revision(
        logical_document_id="DOC-1", source_document_sha256="b" * 64, version_label=None, revision_number=2,
        authority_source="gov", authority_reference="REF2", authority_recorded_by="alice", recorded_at=NOW,
    )
    new_id = new_result.identity.document_revision_id

    events_before = inner.list_events("DOC-1")
    old_metadata_before = inner.get_metadata(old_id)
    old_periods_before = inner.list_periods_for_revision(old_id)
    new_metadata_before = inner.get_metadata(new_id)
    new_periods_before = inner.list_periods_for_revision(new_id)

    faulty_service = RevisionAuthorityService(FaultInjectingRepository(inner, fault=fault))
    with pytest.raises(RuntimeError, match="injected fault"):
        faulty_service.activate_revision(
            new_revision_id=new_id, old_revision_id=old_id, effective_from=date(2023, 1, 1),
            authority_source="gov", authority_reference="A2", authority_recorded_by="alice", recorded_at=NOW,
        )

    assert inner.list_events("DOC-1") == events_before
    assert inner.get_metadata(old_id) == old_metadata_before
    assert inner.list_periods_for_revision(old_id) == old_periods_before
    assert inner.get_metadata(new_id) == new_metadata_before
    assert inner.list_periods_for_revision(new_id) == new_periods_before

    # And the registry is still perfectly resolvable afterward -- proving
    # the rollback didn't just avoid a crash, it left a CONSISTENT state.
    result = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2024, 1, 1))
    assert result.eligible_revision_ids == [old_id]
    assert result.integrity_error is None


def test_activation_cannot_supersede_a_revision_belonging_to_another_logical_document():
    """Business nuance: old_revision_id and new_revision_id must belong
    to the SAME logical_document_id -- activation is a within-document
    concept. Failure this guards against: a copy-paste bug or a
    cross-tenant mixup accidentally linking two unrelated documents'
    revision histories together. Affects: current search (a cross-
    document link would make "which document is this chunk scoped to"
    ambiguous) and auditability."""
    inner = InMemoryRevisionAuthorityRepository()
    service = _service(inner)
    doc_a_id = _register_and_activate_first(service, "a" * 64, 1)
    doc_b_result = service.register_revision(
        logical_document_id="DOC-B", source_document_sha256="c" * 64, version_label=None, revision_number=1,
        authority_source="gov", authority_reference="REF", authority_recorded_by="alice", recorded_at=NOW,
    )

    with pytest.raises(ActivationValidationError, match="SAME logical document"):
        service.activate_revision(
            new_revision_id=doc_b_result.identity.document_revision_id, old_revision_id=doc_a_id,
            effective_from=date(2023, 1, 1), authority_source="gov", authority_reference="X",
            authority_recorded_by="alice", recorded_at=NOW,
        )


def test_a_revision_cannot_supersede_itself():
    """Business nuance: old_revision_id must never equal
    new_revision_id -- a revision cannot be its own predecessor.
    Failure this guards against: a caller bug passing the same id twice,
    which would otherwise try to open a second period for a revision
    while simultaneously claiming to close its own still-open one in the
    SAME transition -- an incoherent state. Affects: current search and
    auditability (a self-referential supersession chain would be
    nonsensical to audit)."""
    inner = InMemoryRevisionAuthorityRepository()
    service = _service(inner)
    revision_id = _register_and_activate_first(service, "a" * 64, 1)

    with pytest.raises(ActivationValidationError, match="cannot supersede itself"):
        service.activate_revision(
            new_revision_id=revision_id, old_revision_id=revision_id, effective_from=date(2023, 1, 1),
            authority_source="gov", authority_reference="X", authority_recorded_by="alice", recorded_at=NOW,
        )


def test_a_failed_validation_leaves_both_revisions_unchanged():
    """Business nuance: when pre-activation validation fails (any of the
    structural checks in item 4), NEITHER revision's metadata/periods
    may be touched -- validation runs entirely BEFORE the repository's
    transaction() is even entered. Failure this guards against: a
    "validate as you go" implementation that mutates the new revision
    before discovering the old revision is invalid, leaving an orphaned
    half-applied change. Affects: current search and benchmark fairness
    (a rejected activation attempt must be a true no-op, safe to retry)."""
    inner = InMemoryRevisionAuthorityRepository()
    service = _service(inner)
    revision_id = _register_and_activate_first(service, "a" * 64, 1)
    metadata_before = inner.get_metadata(revision_id)
    periods_before = inner.list_periods_for_revision(revision_id)

    with pytest.raises(ActivationValidationError):
        service.activate_revision(
            new_revision_id=revision_id, old_revision_id="nonexistent-old-id", effective_from=date(2023, 1, 1),
            authority_source="gov", authority_reference="X", authority_recorded_by="alice", recorded_at=NOW,
        )

    assert inner.get_metadata(revision_id) == metadata_before
    assert inner.list_periods_for_revision(revision_id) == periods_before


def test_no_event_is_appended_for_a_failed_transition():
    """Business nuance: a rejected activate_revision() call must leave
    the append-only event log completely unchanged -- an audit trail
    must never record a transition that never actually happened.
    Failure this guards against: a "log the attempt anyway" pattern that
    would make the event log an unreliable record of ACTUAL registry
    changes. Affects: auditability directly."""
    inner = InMemoryRevisionAuthorityRepository()
    service = _service(inner)
    revision_id = _register_and_activate_first(service, "a" * 64, 1)
    events_before = inner.list_events()

    with pytest.raises(ActivationValidationError):
        service.activate_revision(
            new_revision_id=revision_id, old_revision_id=revision_id, effective_from=date(2023, 1, 1),
            authority_source="gov", authority_reference="X", authority_recorded_by="alice", recorded_at=NOW,
        )

    assert inner.list_events() == events_before


def test_activation_requires_old_revision_to_have_exactly_one_open_period():
    """Business nuance: supersession only makes sense against a revision
    that currently HAS an open (uncledosed) authority period -- a
    revision that was never activated, or one already fully closed with
    no open period, has nothing valid to supersede. Failure this guards
    against: superseding a revision that is already superseded/withdrawn,
    which would silently fabricate a supersession chain that never
    reflected real authority. Affects: current search and auditability."""
    inner = InMemoryRevisionAuthorityRepository()
    service = _service(inner)
    never_activated = service.register_revision(
        logical_document_id="DOC-1", source_document_sha256="a" * 64, version_label=None, revision_number=1,
        authority_source="gov", authority_reference="REF", authority_recorded_by="alice", recorded_at=NOW,
    )
    new_result = service.register_revision(
        logical_document_id="DOC-1", source_document_sha256="b" * 64, version_label=None, revision_number=2,
        authority_source="gov", authority_reference="REF2", authority_recorded_by="alice", recorded_at=NOW,
    )

    with pytest.raises(ActivationValidationError, match="open authority period"):
        service.activate_revision(
            new_revision_id=new_result.identity.document_revision_id,
            old_revision_id=never_activated.identity.document_revision_id,
            effective_from=date(2023, 1, 1), authority_source="gov", authority_reference="X",
            authority_recorded_by="alice", recorded_at=NOW,
        )


def test_activation_rejects_a_new_period_overlapping_a_third_revisions_open_period():
    """Business nuance: even when old_revision_id correctly names the
    revision being superseded, the new period must not ALSO collide with
    some OTHER, unrelated revision's own open period. Note this specific
    conflicting precondition can no longer be reached through ordinary
    (even careless) service usage -- item 4's own validation already
    rejects a second independent `activate_revision(old=None)` call
    while a first one's period is still open (see
    test_overlapping_effective_revisions_scenario_fails_closed's
    contract-level construction, which uses a raw repository write for
    exactly this reason) -- so this test constructs the precondition the
    same way: a direct, low-level repository write simulating
    pre-existing inconsistent data (e.g. from before this validation
    existed, or a manual data fix gone wrong), then proves a NEW,
    otherwise-valid activation still correctly detects and rejects the
    conflict. Failure this guards against: a normal-looking activation
    silently creating a second conflict even while correctly closing the
    first one. Affects: current search directly."""
    inner = InMemoryRevisionAuthorityRepository()
    service = _service(inner)
    old_id = _register_and_activate_first(service, "a" * 64, 1)

    third_result = service.register_revision(
        logical_document_id="DOC-1", source_document_sha256="c" * 64, version_label=None, revision_number=3,
        authority_source="gov", authority_reference="REF3", authority_recorded_by="alice", recorded_at=NOW,
    )
    third_id = third_result.identity.document_revision_id
    # Bypasses service.py's own validation entirely -- simulates
    # pre-existing inconsistent data, not a mistake the service itself
    # could still be tricked into making.
    inner.save_period(AuthorityPeriod(
        authority_period_id=0, logical_document_id="DOC-1", document_revision_id=third_id,
        effective_from=date(2021, 1, 1), effective_to=None, predecessor_revision_id=None,
        opening_event_id=1, authority_source="gov", authority_reference="RAW", recorded_at=NOW, recorded_by="alice",
    ))

    new_result = service.register_revision(
        logical_document_id="DOC-1", source_document_sha256="d" * 64, version_label=None, revision_number=4,
        authority_source="gov", authority_reference="REF4", authority_recorded_by="alice", recorded_at=NOW,
    )
    with pytest.raises(ActivationValidationError, match="overlap"):
        service.activate_revision(
            new_revision_id=new_result.identity.document_revision_id, old_revision_id=old_id,
            effective_from=date(2023, 1, 1), authority_source="gov", authority_reference="X",
            authority_recorded_by="alice", recorded_at=NOW,
        )
