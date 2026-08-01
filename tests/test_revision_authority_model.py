"""Stage 7R.1: model-layer tests -- revision identity reuse, authority
metadata validation, and derived-authority-state rules.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from ingestion_bench.chunking import DocumentRevisionContext, compute_document_revision_id
from ingestion_bench.revision_authority.model import AuthorityMetadata, RevisionIdentity, derive_authority_state


def _metadata(**overrides) -> AuthorityMetadata:
    defaults = dict(
        publication_status="approved",
        effective_from=date(2023, 1, 1),
        effective_to=None,
        authority_source="governance-system",
        authority_reference="REF-1",
        authority_recorded_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
        authority_recorded_by="alice",
    )
    defaults.update(overrides)
    return AuthorityMetadata(**defaults)


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
    Affects: auditability (duplicate detection) and benchmark fairness
    (two benchmark runs registering the same fixture must agree)."""
    id_a = compute_document_revision_id("DOC-1", "a" * 64, "v1", 1)
    id_b = compute_document_revision_id("DOC-1", "a" * 64, "v1", 1)
    assert id_a == id_b
    id_different = compute_document_revision_id("DOC-1", "b" * 64, "v1", 1)
    assert id_different != id_a


def test_authority_metadata_rejects_effective_to_at_or_before_effective_from():
    """Business nuance: an effective window must have positive width --
    effective_to == effective_from would mean the revision is NEVER
    actually effective for any as_of_date (start-inclusive/end-exclusive
    means the interval would be empty). Failure this guards against: a
    silently-empty effective window masquerading as a valid revision.
    Affects: current search (a revision that can never be current is a
    data-entry bug, not a legitimate state) and auditability (fail
    closed by refusing to even construct it)."""
    with pytest.raises(ValidationError):
        _metadata(effective_from=date(2023, 1, 1), effective_to=date(2023, 1, 1))
    with pytest.raises(ValidationError):
        _metadata(effective_from=date(2023, 1, 1), effective_to=date(2022, 1, 1))


def test_authority_metadata_allows_valid_ordering_and_open_ended_interval():
    _metadata(effective_from=date(2023, 1, 1), effective_to=date(2024, 1, 1))
    _metadata(effective_from=date(2023, 1, 1), effective_to=None)


def test_draft_state_derived_regardless_of_as_of_date():
    """Business nuance: a draft has NO effective window at all -- its
    state must not depend on which date you ask about. Failure this
    guards against: a draft accidentally treated as effective for some
    date range because effective_from happened to be populated. Affects:
    current search directly (drafts must never leak into default
    results) -- see test_effective_revision_must_be_approved for the
    companion integrity check."""
    metadata = _metadata(publication_status="draft", effective_from=None, effective_to=None)
    state, error = derive_authority_state(metadata, date(1999, 1, 1))
    assert state == "draft" and error is None
    state, error = derive_authority_state(metadata, date(2999, 1, 1))
    assert state == "draft" and error is None


def test_withdrawn_state_derived_regardless_of_prior_effective_window():
    """Business nuance: withdrawal is a TERMINAL, explicit fact -- it
    must dominate over whatever effective_from/effective_to the revision
    had before withdrawal (Scenario K). Failure this guards against: a
    withdrawn revision's stale effective dates making it look 'still
    effective' to a naive date-only check. Affects: current search (a
    withdrawn revision must never be served) and auditability (the
    withdrawal itself must be unambiguous in derived state, not just in
    an event log a caller might not consult)."""
    metadata = _metadata(publication_status="withdrawn", effective_from=date(2020, 1, 1), effective_to=None)
    state, error = derive_authority_state(metadata, date(2025, 1, 1))
    assert state == "withdrawn" and error is None


def test_approved_future_before_effective_from():
    """Business nuance: an approved revision with a future effective_from
    must read as 'approved_future', distinct from 'effective' -- this is
    Scenario D's core rule. Failure this guards against: an off-by-one or
    inverted comparison letting a future revision leak into current
    results early. Affects: current search directly."""
    metadata = _metadata(effective_from=date(2028, 1, 1), effective_to=None)
    state, error = derive_authority_state(metadata, date(2027, 12, 31))
    assert state == "approved_future" and error is None


def test_effective_on_and_after_effective_from_before_effective_to():
    """Business nuance: the interval is start-INCLUSIVE -- the exact
    effective_from date itself must already read as effective (Scenario
    O/E boundary). Failure this guards against: an off-by-one that
    delays currency by one day. Affects: current search (a one-day gap
    where nothing is authoritative would be a real production bug)."""
    metadata = _metadata(effective_from=date(2028, 1, 1), effective_to=date(2029, 1, 1))
    state, error = derive_authority_state(metadata, date(2028, 1, 1))
    assert state == "effective" and error is None
    state, error = derive_authority_state(metadata, date(2028, 12, 31))
    assert state == "effective" and error is None


def test_superseded_on_and_after_effective_to():
    """Business nuance: the interval is end-EXCLUSIVE -- effective_to
    itself must already read as superseded, not effective (Scenario
    O/E boundary, the OTHER side of the same day). Failure this guards
    against: a one-day OVERLAP where both the old and new revision would
    read as effective simultaneously. Affects: current search directly
    (an overlap here is exactly the Scenario L failure mode)."""
    metadata = _metadata(effective_from=date(2023, 1, 1), effective_to=date(2028, 1, 1))
    state, error = derive_authority_state(metadata, date(2028, 1, 1))
    assert state == "superseded" and error is None


def test_effective_revision_must_be_approved_draft_with_effective_from_is_an_integrity_error():
    """Business nuance: only an APPROVED revision may ever be 'effective'
    -- if a draft/under_review record somehow has effective_from
    populated (a data-integrity anomaly, e.g. a bypassed/corrupted write,
    never possible via normal service.py calls), that must be flagged as
    an explicit error, never silently derived as 'effective' or silently
    coerced back to 'draft' as if nothing were wrong. Failure this
    guards against: a corrupted registry row silently granting authority
    to an unapproved revision. Affects: current search (would be a
    serious authority-bypass bug) and auditability (must be visible as
    an explicit error, not swallowed)."""
    metadata = _metadata(publication_status="draft", effective_from=date(2023, 1, 1), effective_to=None)
    state, error = derive_authority_state(metadata, date(2024, 1, 1))
    assert state is None
    assert error is not None
    assert "not approved" in error.lower()


def test_approved_missing_effective_from_is_an_integrity_error():
    """Business nuance: an 'approved' revision that was never given an
    effective_from cannot be resolved to any state -- this should never
    happen via record_authority_decision/activate_revision's own
    contracts, but the resolver must not silently guess (e.g. defaulting
    to 'approved_future' or 'effective'). Affects: current search
    (refusing to guess is exactly the 'fail closed' discipline) and
    auditability."""
    metadata = _metadata(publication_status="approved", effective_from=None, effective_to=None)
    state, error = derive_authority_state(metadata, date(2024, 1, 1))
    assert state is None
    assert error is not None


def test_upload_timestamp_never_selects_authority():
    """Business nuance: authority_recorded_at (when a fact was RECORDED)
    must have zero influence on the derived authority state -- only
    publication_status + effective_from/effective_to + as_of_date do.
    Failure this guards against: a 'most recently touched wins' bug,
    exactly the anti-pattern this whole stage exists to prevent (Stage
    7R.1 objective: 'Do not determine authority from upload timestamp').
    Affects: current search (would silently prefer freshness over actual
    governance decisions) and benchmark fairness (a late re-run touching
    a record's timestamp must never change which revision is authoritative)."""
    early = _metadata(authority_recorded_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
    late = _metadata(authority_recorded_at=datetime(2099, 1, 1, tzinfo=timezone.utc))
    state_early, _ = derive_authority_state(early, date(2024, 1, 1))
    state_late, _ = derive_authority_state(late, date(2024, 1, 1))
    assert state_early == state_late == "effective"


def test_highest_revision_number_never_selects_authority_by_itself():
    """Business nuance: revision_number is part of IDENTITY only, never
    an authority signal -- a revision_number=99 draft must not outrank a
    revision_number=1 effective revision. Failure this guards against a
    'highest number wins' heuristic silently substituting for an actual
    governance decision (Stage 7R.1 objective: 'Do not determine
    authority from... greatest revision number'). Affects: current
    search directly."""
    low_number_effective = _metadata(publication_status="approved", effective_from=date(2020, 1, 1))
    high_number_draft = _metadata(publication_status="draft", effective_from=None)
    # revision_number itself never even appears in AuthorityMetadata or
    # derive_authority_state's signature -- there is no code path by
    # which it COULD influence the result.
    state_low, _ = derive_authority_state(low_number_effective, date(2024, 1, 1))
    state_high, _ = derive_authority_state(high_number_draft, date(2024, 1, 1))
    assert state_low == "effective"
    assert state_high == "draft"
