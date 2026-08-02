"""Stage 7R.1/7R.1a: model-layer tests -- revision identity reuse,
authority metadata, authority periods, and derived-authority-state
rules.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from ingestion_bench.chunking import DocumentRevisionContext, compute_document_revision_id
from ingestion_bench.revision_authority.model import (
    AuthorityMetadata,
    AuthorityPeriod,
    RevisionIdentity,
    derive_authority_state,
    validate_own_periods_non_overlapping,
)


def _metadata(**overrides) -> AuthorityMetadata:
    defaults = dict(
        publication_status="approved",
        authority_source="governance-system",
        authority_reference="REF-1",
        authority_recorded_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
        authority_recorded_by="alice",
    )
    defaults.update(overrides)
    return AuthorityMetadata(**defaults)


def _period(**overrides) -> AuthorityPeriod:
    defaults = dict(
        authority_period_id=1, logical_document_id="DOC-1", document_revision_id="rev-1",
        effective_from=date(2023, 1, 1), effective_to=None, predecessor_revision_id=None,
        opening_event_id=1, authority_source="governance-system", authority_reference="REF-1",
        recorded_at=datetime(2023, 1, 1, tzinfo=timezone.utc), recorded_by="alice",
    )
    defaults.update(overrides)
    return AuthorityPeriod(**defaults)


def test_revision_identity_is_the_same_type_as_chunking_document_revision_context():
    """Stage 7R.1 must reuse the existing chunk lineage fields, never
    reinvent a parallel identity concept. Failure mode this guards
    against: a second, independently-computed 'revision id' scheme that
    silently diverges from the id real CanonicalChunk rows already carry
    -- which would make this whole registry unable to actually scope any
    real chunk. Affects: current search, historical search, and
    auditability equally, since ALL of them depend on this id matching
    real ingested data."""
    assert RevisionIdentity is DocumentRevisionContext


def test_document_revision_id_is_deterministic_not_freely_chosen():
    """Business nuance: two independent registration attempts for the
    identical revision must compute the IDENTICAL id without any
    lookup/coordination step. Failure this guards against: a random or
    caller-supplied id would make 'exact duplicate reuses the existing
    document_revision_id' impossible to satisfy deterministically.
    Affects: auditability (duplicate detection) and benchmark fairness."""
    id_a = compute_document_revision_id("DOC-1", "a" * 64, "v1", 1)
    id_b = compute_document_revision_id("DOC-1", "a" * 64, "v1", 1)
    assert id_a == id_b
    id_different = compute_document_revision_id("DOC-1", "b" * 64, "v1", 1)
    assert id_different != id_a


def test_authority_metadata_no_longer_carries_effective_dates_or_supersession_links():
    """Business nuance (Stage 7R.1a item 1): AuthorityMetadata is now a
    PURE governance-status record -- effective dates and supersession
    links live SOLELY in AuthorityPeriod. Failure this guards against:
    two competing authoritative copies of an effective interval (one on
    the revision row, one in the period table) silently disagreeing.
    Affects: current search (an authority source of truth must be
    singular) and auditability."""
    metadata = _metadata()
    assert not hasattr(metadata, "effective_from")
    assert not hasattr(metadata, "effective_to")
    assert not hasattr(metadata, "supersedes_revision_id")
    assert not hasattr(metadata, "superseded_by_revision_id")


def test_authority_period_rejects_effective_to_before_effective_from():
    """Business nuance: effective_to must never be BEFORE effective_from
    -- a genuinely inverted interval is always a data-entry bug, unlike
    a ZERO-WIDTH interval (effective_to == effective_from), which is a
    deliberate, valid representation of pre_effective_authority_correction
    (see test below). Failure this guards against: a silently-inverted
    window masquerading as a valid period. Affects: current search and
    auditability (fail closed by refusing to even construct it)."""
    with pytest.raises(ValidationError):
        _period(effective_from=date(2023, 1, 1), effective_to=date(2022, 1, 1))


def test_authority_period_allows_zero_width_interval_for_pre_effective_correction():
    """Business nuance: effective_to == effective_from represents a
    period that was scheduled but retracted before it ever took effect
    -- the interval [X, X) matches NO as_of_date at all (start-inclusive,
    end-exclusive), which is exactly the desired "this never actually
    became effective" behavior, and is exactly how
    pre_effective_authority_correction is represented. Affects:
    auditability (the correction is visible in the period's own
    zero-width interval, not just in prose)."""
    period = _period(effective_from=date(2029, 1, 1), effective_to=date(2029, 1, 1), closing_event_id=2, closure_reason="correction")
    assert period.effective_to == period.effective_from


def test_authority_period_requires_closure_reason_and_closing_event_id_together():
    """Business nuance: closure_reason and closing_event_id must be
    populated TOGETHER or not at all -- a period cannot be "half closed"
    (a reason with no linking event, or an event with no stated reason).
    Failure this guards against: an unauditable closure (WHY did this
    period end, with no traceable decision behind it). Affects:
    auditability directly."""
    with pytest.raises(ValidationError):
        _period(effective_to=date(2024, 1, 1), closing_event_id=2, closure_reason=None)
    with pytest.raises(ValidationError):
        _period(effective_to=date(2024, 1, 1), closing_event_id=None, closure_reason="withdrawn")


def test_authority_period_open_period_must_not_have_a_closure_reason():
    with pytest.raises(ValidationError):
        _period(effective_to=None, closure_reason="withdrawn", closing_event_id=2)


def test_validate_own_periods_non_overlapping_detects_overlap():
    """Business nuance: multiple periods for the SAME revision are
    explicitly permitted (item 1) but must never overlap each other.
    Failure this guards against: two periods both claiming authority
    over the same date, which is exactly as ambiguous for one revision
    as Scenario L is across two revisions. Affects: current search and
    historical search (an as_of query inside the overlap would be
    genuinely ambiguous)."""
    overlapping = [
        _period(authority_period_id=1, effective_from=date(2020, 1, 1), effective_to=date(2023, 1, 1), closing_event_id=2, closure_reason="superseded"),
        _period(authority_period_id=2, effective_from=date(2022, 1, 1), effective_to=None, opening_event_id=3),
    ]
    assert validate_own_periods_non_overlapping(overlapping) is not None


def test_validate_own_periods_non_overlapping_allows_disjoint_periods():
    """Business nuance: a revision reinstated after a rollback has TWO
    disjoint (non-overlapping) periods -- this must be accepted, never
    flagged as an error, or the post-effective rollback scenario (item
    3) would be structurally impossible to represent."""
    disjoint = [
        _period(authority_period_id=1, effective_from=date(2023, 1, 1), effective_to=date(2028, 1, 1), closing_event_id=2, closure_reason="superseded"),
        _period(authority_period_id=2, effective_from=date(2028, 6, 1), effective_to=None, opening_event_id=3),
    ]
    assert validate_own_periods_non_overlapping(disjoint) is None


def test_draft_state_derived_regardless_of_as_of_date_when_no_real_period():
    """Business nuance: a draft with NO real (non-zero-width) period has
    NO effective window at all -- its state must not depend on which
    date you ask about. Failure this guards against: a draft accidentally
    treated as effective for some date range. Affects: current search
    directly."""
    metadata = _metadata(publication_status="draft")
    state, error = derive_authority_state("draft", [], date(1999, 1, 1))
    assert state == "draft" and error is None
    state, error = derive_authority_state("draft", [], date(2999, 1, 1))
    assert state == "draft" and error is None


def test_draft_with_a_zero_width_period_is_still_draft_not_an_error():
    """Business nuance (the real bug found and fixed during development):
    a zero-width period (pre_effective_authority_correction) on a draft
    revision is a LEGITIMATE historical artifact, never itself the
    'effective revision is not approved' violation -- a zero-width
    period grants no authority for any date, so it is harmless. Failure
    this guards against: wrongly flagging every corrected revision as
    permanently malformed. Affects: auditability (a corrected revision
    must remain normally queryable, not stuck in an error state
    forever)."""
    zero_width = _period(effective_from=date(2029, 1, 1), effective_to=date(2029, 1, 1), closing_event_id=2, closure_reason="correction")
    state, error = derive_authority_state("draft", [zero_width], date(2025, 1, 1))
    assert state == "draft"
    assert error is None


def test_withdrawn_state_derived_regardless_of_prior_effective_window():
    """Business nuance: withdrawal is a TERMINAL, explicit fact once
    as_of_date reaches the closing date -- but (Stage 7R.1a's core
    correction) it must NOT override dates that fall WITHIN the
    now-closed period. Affects: current search (must never be withdrawn
    for a date it was genuinely effective) and historical search."""
    closed = _period(effective_from=date(2020, 1, 1), effective_to=date(2024, 1, 1), closing_event_id=2, closure_reason="withdrawn")
    state, error = derive_authority_state("withdrawn", [closed], date(2025, 1, 1))
    assert state == "withdrawn" and error is None
    state, error = derive_authority_state("withdrawn", [closed], date(2022, 1, 1))
    assert state == "effective" and error is None  # Stage 7R.1a's core fix


def test_approved_future_before_effective_from():
    """Business nuance: an approved revision with a future effective_from
    must read as 'approved_future', distinct from 'effective' -- Scenario
    D's core rule. Affects: current search directly."""
    future = _period(effective_from=date(2028, 1, 1), effective_to=None)
    state, error = derive_authority_state("approved", [future], date(2027, 12, 31))
    assert state == "approved_future" and error is None


def test_effective_on_and_after_effective_from_before_effective_to():
    """Business nuance: the interval is start-INCLUSIVE (Scenario O/E
    boundary). Affects: current search (a one-day gap where nothing is
    authoritative would be a real production bug)."""
    period = _period(effective_from=date(2028, 1, 1), effective_to=date(2029, 1, 1), closing_event_id=2, closure_reason="superseded")
    state, _ = derive_authority_state("approved", [period], date(2028, 1, 1))
    assert state == "effective"
    state, _ = derive_authority_state("approved", [period], date(2028, 12, 31))
    assert state == "effective"


def test_superseded_on_and_after_effective_to():
    """Business nuance: the interval is end-EXCLUSIVE -- the other side
    of the same boundary. Affects: current search directly (an overlap
    here is exactly the Scenario L failure mode)."""
    period = _period(effective_from=date(2023, 1, 1), effective_to=date(2028, 1, 1), closing_event_id=2, closure_reason="superseded")
    state, _ = derive_authority_state("approved", [period], date(2028, 1, 1))
    assert state == "superseded"


def test_effective_revision_must_be_approved_a_real_period_on_a_draft_is_an_integrity_error():
    """Business nuance: only an APPROVED revision may ever be 'effective'
    -- a REAL (non-zero-width) period on a draft/under_review record is
    a genuine data-integrity anomaly (never possible via normal
    service.py calls), flagged explicitly, never silently derived as
    'effective' or silently ignored. Affects: current search (would be a
    serious authority-bypass bug) and auditability."""
    real_period = _period(effective_from=date(2023, 1, 1), effective_to=None)
    state, error = derive_authority_state("draft", [real_period], date(2024, 1, 1))
    assert state is None
    assert error is not None
    assert "not approved" in error.lower()


def test_approved_with_no_period_at_all_is_an_integrity_error():
    """Business nuance: an 'approved' revision that was never actually
    activated (no period recorded at all) cannot be resolved to any
    state -- the resolver must not silently guess. Affects: current
    search and auditability."""
    state, error = derive_authority_state("approved", [], date(2024, 1, 1))
    assert state is None
    assert error is not None


def test_upload_timestamp_never_selects_authority():
    """Business nuance: authority_recorded_at/recorded_at (when a fact
    was RECORDED) must have zero influence on the derived authority
    state -- only publication_status + period effective_from/effective_to
    + as_of_date do. Failure this guards against: a 'most recently
    touched wins' bug (Stage 7R.1 objective: 'Do not determine authority
    from upload timestamp'). Affects: current search and benchmark
    fairness."""
    early = _period(recorded_at=datetime(2000, 1, 1, tzinfo=timezone.utc), effective_from=date(2020, 1, 1))
    late = _period(recorded_at=datetime(2099, 1, 1, tzinfo=timezone.utc), effective_from=date(2020, 1, 1))
    state_early, _ = derive_authority_state("approved", [early], date(2024, 1, 1))
    state_late, _ = derive_authority_state("approved", [late], date(2024, 1, 1))
    assert state_early == state_late == "effective"


def test_highest_revision_number_never_selects_authority_by_itself():
    """Business nuance: revision_number is part of IDENTITY only, never
    an authority signal -- it does not even appear anywhere in
    AuthorityMetadata, AuthorityPeriod, or derive_authority_state's own
    signature, so there is no code path by which it COULD influence the
    result (Stage 7R.1 objective: 'Do not determine authority from...
    greatest revision number'). Affects: current search directly."""
    low_number_effective = _period(effective_from=date(2020, 1, 1))
    state_low, _ = derive_authority_state("approved", [low_number_effective], date(2024, 1, 1))
    state_high, _ = derive_authority_state("draft", [], date(2024, 1, 1))
    assert state_low == "effective"
    assert state_high == "draft"
