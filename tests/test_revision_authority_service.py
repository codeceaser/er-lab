"""Stage 7R.1: authority transition service tests."""

from __future__ import annotations

import ast
from datetime import date, datetime, timezone
from pathlib import Path

from ingestion_bench.revision_authority.repository import InMemoryRevisionAuthorityRepository
from ingestion_bench.revision_authority.service import RevisionAuthorityService

REPO_ROOT = Path(__file__).resolve().parent.parent
REVISION_AUTHORITY_ROOT = REPO_ROOT / "src" / "ingestion_bench" / "revision_authority"

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _service() -> RevisionAuthorityService:
    return RevisionAuthorityService(InMemoryRevisionAuthorityRepository())


def _register(service, **overrides):
    defaults = dict(
        logical_document_id="DOC-1", source_document_sha256="a" * 64, version_label="v1", revision_number=1,
        authority_source="governance-system", authority_reference="REF-1", authority_recorded_by="alice", recorded_at=NOW,
    )
    defaults.update(overrides)
    return service.register_revision(**defaults)


def test_exact_duplicate_reuses_revision_identity():
    """Business nuance: a second registration attempt with IDENTICAL
    logical_document_id + source_document_sha256 + version_label +
    revision_number must resolve to the SAME document_revision_id, never
    create a second row. Failure this guards against: a duplicate
    ingestion pipeline run (e.g. a retried upload) silently doubling a
    document's revision history, which would corrupt supersession
    chains and confuse every downstream authority query. Affects:
    auditability (duplicate rows would make 'how many revisions exist'
    meaningless) and benchmark fairness (a benchmark re-run must not
    accumulate phantom revisions)."""
    service = _service()
    first = _register(service)
    second = _register(service)
    assert first.is_new_revision is True
    assert second.is_new_revision is False
    assert first.identity.document_revision_id == second.identity.document_revision_id
    assert len(service._repository.list_revisions_for_document("DOC-1")) == 1


def test_exact_duplicate_does_not_request_rechunking_or_reembedding():
    """Business nuance: registering a duplicate must never trigger any
    ingestion-side work (chunking/embedding) -- this service has no
    dependency on either. Failure this guards against: a naive
    'reprocess on every upload' implementation wasting compute (and,
    worse, risking non-determinism) on data that hasn't actually
    changed. Affects: benchmark fairness (repeated registration must be
    free) -- verified structurally here (no chunking/embedding import
    anywhere in this package) rather than by mocking a call that
    shouldn't exist in the first place."""
    forbidden = ("chunker", "chunk_document", "embeddings", "sentence_transformers", "SentenceTransformer")
    for path in REVISION_AUTHORITY_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for name in forbidden:
                    assert name not in node.module, f"{path} imports {node.module!r} containing forbidden {name!r}"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "chunk_document", f"{path} calls chunk_document()"


def test_changed_content_registers_new_revision_candidate():
    """Business nuance: different bytes for the SAME logical document
    must always create a genuinely new revision candidate -- registered,
    but per item 6, never automatically current. Failure this guards
    against: a hash-based dedup that's too aggressive (silently merging
    genuinely different content) or too loose (never recognizing a real
    change). Affects: current search (a changed document must be
    trackable) and historical search (each real version must remain
    independently resolvable)."""
    service = _service()
    v1 = _register(service, source_document_sha256="a" * 64)
    v2 = _register(service, source_document_sha256="b" * 64)
    assert v1.is_new_revision and v2.is_new_revision
    assert v1.identity.document_revision_id != v2.identity.document_revision_id
    result = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2024, 6, 1))
    assert result.integrity_error is not None  # neither v1 nor v2 was ever activated -- no authoritative revision yet
    assert result.eligible_revision_ids == []


def test_new_effective_revision_supersedes_old_atomically():
    """Business nuance: activating a new revision must, in ONE
    transition, close the OLD revision's window (effective_to,
    superseded_by_revision_id) AND open the NEW one's (publication_status,
    effective_from, supersedes_revision_id) -- never a state where only
    one side has been updated. Failure this guards against: a
    half-applied transition (e.g. a crash between two separate writes)
    leaving the registry with either two effective revisions (Scenario
    L) or zero (a gap). Affects: current search directly -- this is the
    exact property that prevents both Scenario L's and Scenario K's
    failure modes from happening as a matter of course."""
    service = _service()
    old = _register(service, source_document_sha256="a" * 64)
    new = _register(service, source_document_sha256="b" * 64)
    service.activate_revision(
        new_revision_id=old.identity.document_revision_id, old_revision_id=None,
        effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="ACT-OLD",
        authority_recorded_by="alice", recorded_at=NOW,
    )
    service.activate_revision(
        new_revision_id=new.identity.document_revision_id, old_revision_id=old.identity.document_revision_id,
        effective_from=date(2023, 1, 1), authority_source="gov", authority_reference="ACT-NEW",
        authority_recorded_by="alice", recorded_at=NOW,
    )

    # Stage 7R.1a: effective dates/supersession links live in
    # AuthorityPeriod now, never AuthorityMetadata.
    old_period = service._repository.list_periods_for_revision(old.identity.document_revision_id)[0]
    new_period = service._repository.list_periods_for_revision(new.identity.document_revision_id)[0]
    new_metadata = service._repository.get_metadata(new.identity.document_revision_id)
    assert old_period.effective_to == date(2023, 1, 1)
    assert old_period.closure_reason == "superseded"
    assert new_metadata.publication_status == "approved"
    assert new_period.effective_from == date(2023, 1, 1)
    assert new_period.predecessor_revision_id == old.identity.document_revision_id
    # Both periods reference the SAME event -- "the corresponding
    # authority decision event" (singular) covers the whole transition.
    assert old_period.closing_event_id == new_period.opening_event_id

    before = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2021, 1, 1))
    after = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2023, 1, 1))
    assert before.eligible_revision_ids == [old.identity.document_revision_id]
    assert after.eligible_revision_ids == [new.identity.document_revision_id]


def test_activate_revision_first_ever_activation_allows_old_revision_id_none():
    service = _service()
    only = _register(service)
    service.activate_revision(
        new_revision_id=only.identity.document_revision_id, old_revision_id=None,
        effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="ACT-1",
        authority_recorded_by="alice", recorded_at=NOW,
    )
    result = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2021, 1, 1))
    assert result.eligible_revision_ids == [only.identity.document_revision_id]


# --- Stage 7R.1b item 1: restrict status mutation ---------------------------


def test_record_authority_decision_rejects_direct_approved_status():
    """Business nuance: 'approved' must always be created ALONGSIDE a
    real authority period (activate_revision/reinstate_revision) --
    never as a bare status flip. Failure this guards against: a caller
    marking a revision 'approved' with NO period at all, which the
    resolver would then have to treat as the 'effective revision is not
    approved' integrity violation (or, worse, some other silent
    misbehavior) rather than never being possible in the first place.
    Affects: current search (an 'approved' revision must always have
    real authority behind it) and auditability (the ONLY path to
    'approved' is now traceable to a period-opening event)."""
    service = _service()
    only = _register(service)
    try:
        service.record_authority_decision(
            document_revision_id=only.identity.document_revision_id, publication_status="approved",
            authority_source="gov", authority_reference="X", authority_recorded_by="alice", recorded_at=NOW,
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "draft" in str(exc) and "under_review" in str(exc)
    # No period was created, no metadata mutation occurred.
    assert service._repository.get_metadata(only.identity.document_revision_id).publication_status == "draft"
    assert service._repository.list_periods_for_revision(only.identity.document_revision_id) == []


def test_record_authority_decision_rejects_direct_withdrawn_status():
    """Business nuance: 'withdrawn' must always CLOSE a real open
    period (withdraw_revision) -- never as a bare status flip that
    leaves the period itself still open. Failure this guards against:
    a revision marked 'withdrawn' while its authority period remains
    open (effective_to=None) -- the resolver would then have to guess
    whether to trust the status or the period; instead this is
    structurally impossible to create. Affects: current search (an open
    period under a 'withdrawn' status would be a genuine ambiguity) and
    auditability."""
    service = _service()
    only = _register(service)
    service.activate_revision(
        new_revision_id=only.identity.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1),
        authority_source="gov", authority_reference="ACT", authority_recorded_by="alice", recorded_at=NOW,
    )
    try:
        service.record_authority_decision(
            document_revision_id=only.identity.document_revision_id, publication_status="withdrawn",
            authority_source="gov", authority_reference="X", authority_recorded_by="alice", recorded_at=NOW,
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "draft" in str(exc) and "under_review" in str(exc)
    # The period is still open and still resolves effective -- direct
    # "withdrawn" never got a chance to leave it in a contradictory state.
    period = service._repository.list_periods_for_revision(only.identity.document_revision_id)[0]
    assert period.is_open
    result = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="current", as_of_date=date(2021, 1, 1))
    assert result.eligible_revision_ids == [only.identity.document_revision_id]


def test_record_authority_decision_still_supports_draft_and_under_review():
    """Business nuance: the restriction in item 1 must not break the
    LEGITIMATE pure-status-change use case -- draft <-> under_review
    transitions remain fully supported, with no period involved either
    way. Affects: auditability (a reviewer workflow must still work)."""
    service = _service()
    only = _register(service)
    updated = service.record_authority_decision(
        document_revision_id=only.identity.document_revision_id, publication_status="under_review",
        authority_source="gov", authority_reference="X", authority_recorded_by="alice", recorded_at=NOW,
    )
    assert updated.publication_status == "under_review"
    back_to_draft = service.record_authority_decision(
        document_revision_id=only.identity.document_revision_id, publication_status="draft",
        authority_source="gov", authority_reference="Y", authority_recorded_by="alice", recorded_at=NOW,
    )
    assert back_to_draft.publication_status == "draft"
    assert service._repository.list_periods_for_revision(only.identity.document_revision_id) == []


# --- Stage 7R.1b item 2: restrict closure reasons per operation -------------


def test_activate_revision_always_closes_old_period_as_superseded():
    """Business nuance: activate_revision's forward-progress supersession
    must always be recorded with closure_reason='superseded' -- there is
    no public parameter letting a caller relabel it. Affects:
    auditability (closure_reason is an audit-meaningful fact, not a free
    choice)."""
    service = _service()
    old = _register(service, source_document_sha256="a" * 64)
    new = _register(service, source_document_sha256="b" * 64)
    service.activate_revision(new_revision_id=old.identity.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    service.activate_revision(new_revision_id=new.identity.document_revision_id, old_revision_id=old.identity.document_revision_id, effective_from=date(2023, 1, 1), authority_source="gov", authority_reference="A2", authority_recorded_by="alice", recorded_at=NOW)
    old_period = service._repository.list_periods_for_revision(old.identity.document_revision_id)[0]
    assert old_period.closure_reason == "superseded"
    assert not hasattr(service.activate_revision, "__wrapped__")  # sanity: not dynamically patched
    import inspect
    assert "closure_reason" not in inspect.signature(service.activate_revision).parameters


def test_reinstate_revision_always_closes_old_period_as_rollback():
    """Business nuance: reinstate_revision's reversal must always be
    recorded with closure_reason='rollback', distinct from a forward
    supersession -- there is no public parameter letting a caller
    relabel it either. Affects: auditability (rollback vs. supersession
    is a real, meaningful distinction in the audit trail)."""
    import inspect

    service = _service()
    old = _register(service, source_document_sha256="a" * 64)
    new = _register(service, source_document_sha256="b" * 64)
    service.activate_revision(new_revision_id=old.identity.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    service.activate_revision(new_revision_id=new.identity.document_revision_id, old_revision_id=old.identity.document_revision_id, effective_from=date(2023, 1, 1), authority_source="gov", authority_reference="A2", authority_recorded_by="alice", recorded_at=NOW)
    service.reinstate_revision(new_revision_id=old.identity.document_revision_id, old_revision_id=new.identity.document_revision_id, effective_from=date(2024, 1, 1), authority_source="gov", authority_reference="R1", authority_recorded_by="alice", recorded_at=NOW)
    new_period = [p for p in service._repository.list_periods_for_revision(new.identity.document_revision_id) if not p.is_open][0]
    assert new_period.closure_reason == "rollback"
    assert "closure_reason" not in inspect.signature(service.reinstate_revision).parameters


# --- Stage 7R.1b hardening guard 1: no status mutation once real authority exists


def test_currently_effective_revision_cannot_be_changed_to_draft():
    """Business nuance: an OPEN, currently-effective period is the
    clearest possible case of real authority already granted -- a
    'draft' status here would directly contradict a still-open period
    (the resolver would have to choose which to believe). Failure this
    guards against: a governance UI accidentally 'un-reviewing' a
    revision that is live in production right now. Affects: current
    search directly."""
    service = _service()
    only = _register(service)
    service.activate_revision(new_revision_id=only.identity.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    metadata_before = service._repository.get_metadata(only.identity.document_revision_id)
    periods_before = service._repository.list_periods_for_revision(only.identity.document_revision_id)
    events_before = service._repository.list_events("DOC-1")
    try:
        service.record_authority_decision(document_revision_id=only.identity.document_revision_id, publication_status="draft", authority_source="gov", authority_reference="X", authority_recorded_by="alice", recorded_at=NOW)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "non-zero-width" in str(exc)
    assert service._repository.get_metadata(only.identity.document_revision_id) == metadata_before
    assert service._repository.list_periods_for_revision(only.identity.document_revision_id) == periods_before
    assert service._repository.list_events("DOC-1") == events_before


def test_currently_effective_revision_cannot_be_changed_to_under_review():
    """Business nuance: same as the draft case, for under_review --
    neither permitted status may ever be assigned once real authority
    exists. Affects: current search directly."""
    service = _service()
    only = _register(service)
    service.activate_revision(new_revision_id=only.identity.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    try:
        service.record_authority_decision(document_revision_id=only.identity.document_revision_id, publication_status="under_review", authority_source="gov", authority_reference="X", authority_recorded_by="alice", recorded_at=NOW)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "non-zero-width" in str(exc)


def test_historical_superseded_revision_cannot_be_changed_to_draft():
    """Business nuance: a revision's period being CLOSED (superseded)
    does not erase the fact that it once held real, historical authority
    -- as_of queries against that historical window still depend on it.
    Failure this guards against: 'cleaning up' an old revision's status
    in a way that would corrupt historical (as_of) resolution even
    though the revision is no longer current. Affects: historical search
    directly."""
    service = _service()
    old = _register(service, source_document_sha256="a" * 64)
    new = _register(service, source_document_sha256="b" * 64)
    service.activate_revision(new_revision_id=old.identity.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    service.activate_revision(new_revision_id=new.identity.document_revision_id, old_revision_id=old.identity.document_revision_id, effective_from=date(2023, 1, 1), authority_source="gov", authority_reference="A2", authority_recorded_by="alice", recorded_at=NOW)
    # old is now superseded (its own period is closed, non-zero-width).
    try:
        service.record_authority_decision(document_revision_id=old.identity.document_revision_id, publication_status="draft", authority_source="gov", authority_reference="X", authority_recorded_by="alice", recorded_at=NOW)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "non-zero-width" in str(exc)
    # Historical resolution is untouched by the rejected attempt.
    historical = service.resolve_query_scope(logical_document_id="DOC-1", query_intent="as_of", as_of_date=date(2021, 1, 1))
    assert historical.eligible_revision_ids == [old.identity.document_revision_id]


def test_future_approved_revision_cannot_be_changed_to_under_review():
    """Business nuance: an approved-future revision's period is real
    (non-zero-width) even though it hasn't started yet -- it is
    scheduled real authority, not a draft candidate. Failure this guards
    against: silently un-scheduling a future activation by flipping its
    status, which would leave a period on the books with NO matching
    'approved' status (a genuine integrity contradiction). Affects:
    current search (as of the future date, once it arrives)."""
    service = _service()
    only = _register(service)
    service.activate_revision(new_revision_id=only.identity.document_revision_id, old_revision_id=None, effective_from=date(2030, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    try:
        service.record_authority_decision(document_revision_id=only.identity.document_revision_id, publication_status="under_review", authority_source="gov", authority_reference="X", authority_recorded_by="alice", recorded_at=NOW)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "non-zero-width" in str(exc)


def test_reinstated_revision_with_prior_history_cannot_be_changed_to_draft():
    """Business nuance: a revision reinstated via reinstate_revision()
    carries an earlier, already-closed period PLUS a new open one -- any
    one of those being non-zero-width is enough to block a status
    mutation, not just the currently-open one. Affects: current and
    historical search."""
    service = _service()
    old = _register(service, source_document_sha256="a" * 64)
    new = _register(service, source_document_sha256="b" * 64)
    service.activate_revision(new_revision_id=old.identity.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    service.activate_revision(new_revision_id=new.identity.document_revision_id, old_revision_id=old.identity.document_revision_id, effective_from=date(2023, 1, 1), authority_source="gov", authority_reference="A2", authority_recorded_by="alice", recorded_at=NOW)
    service.reinstate_revision(new_revision_id=old.identity.document_revision_id, old_revision_id=new.identity.document_revision_id, effective_from=date(2024, 1, 1), authority_source="gov", authority_reference="R1", authority_recorded_by="alice", recorded_at=NOW)
    try:
        service.record_authority_decision(document_revision_id=old.identity.document_revision_id, publication_status="draft", authority_source="gov", authority_reference="X", authority_recorded_by="alice", recorded_at=NOW)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "non-zero-width" in str(exc)


def test_zero_width_corrected_candidate_may_still_move_draft_to_under_review():
    """Business nuance: a zero-width period (retracted via
    closure_reason='correction' before it ever took effect) never
    granted real authority -- item 1's restriction must NOT block this
    candidate's ordinary draft<->under_review review workflow. Affects:
    auditability (a correction must not accidentally freeze a
    revision's review status forever)."""
    service = _service()
    only = _register(service)
    service.activate_revision(new_revision_id=only.identity.document_revision_id, old_revision_id=None, effective_from=date(2025, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    service.withdraw_revision(document_revision_id=only.identity.document_revision_id, withdrawal_effective_date=date(2025, 1, 1), closure_reason="correction", authority_source="gov", authority_reference="C1", authority_recorded_by="alice", recorded_at=NOW)
    assert service._repository.get_metadata(only.identity.document_revision_id).publication_status == "draft"

    under_review = service.record_authority_decision(document_revision_id=only.identity.document_revision_id, publication_status="under_review", authority_source="gov", authority_reference="X", authority_recorded_by="alice", recorded_at=NOW)
    assert under_review.publication_status == "under_review"
    back_to_draft = service.record_authority_decision(document_revision_id=only.identity.document_revision_id, publication_status="draft", authority_source="gov", authority_reference="Y", authority_recorded_by="alice", recorded_at=NOW)
    assert back_to_draft.publication_status == "draft"


# --- Stage 7R.1b hardening guard 2: correction boundary ---------------------


def test_zero_width_pre_effective_correction_succeeds():
    """Business nuance: a correction exactly AT the open period's own
    effective_from -- retracting authority before it ever took effect --
    is the one legitimate use of closure_reason='correction'. Affects:
    auditability (this is the documented, intended path)."""
    service = _service()
    only = _register(service)
    service.activate_revision(new_revision_id=only.identity.document_revision_id, old_revision_id=None, effective_from=date(2028, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    service.withdraw_revision(document_revision_id=only.identity.document_revision_id, withdrawal_effective_date=date(2028, 1, 1), closure_reason="correction", authority_source="gov", authority_reference="C1", authority_recorded_by="alice", recorded_at=NOW)
    period = service._repository.list_periods_for_revision(only.identity.document_revision_id)[0]
    assert period.effective_from == period.effective_to == date(2028, 1, 1)
    assert service._repository.get_metadata(only.identity.document_revision_id).publication_status == "draft"


def test_correction_after_one_day_fails():
    """Business nuance: even ONE day past the period's own start means
    the period genuinely took effect -- 'correction' is no longer
    coherent, and the caller must use closure_reason='withdrawn'
    instead. Failure this guards against: a governance actor mislabeling
    a real, if brief, period of authority as if it never happened.
    Affects: auditability (a correction must never erase real history)."""
    service = _service()
    only = _register(service)
    service.activate_revision(new_revision_id=only.identity.document_revision_id, old_revision_id=None, effective_from=date(2028, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    try:
        service.withdraw_revision(document_revision_id=only.identity.document_revision_id, withdrawal_effective_date=date(2028, 1, 2), closure_reason="correction", authority_source="gov", authority_reference="C1", authority_recorded_by="alice", recorded_at=NOW)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "correction" in str(exc) and "withdrawn" in str(exc)


def test_correction_after_a_historical_effective_interval_fails():
    """Business nuance: attempting a 'correction' long after a period
    was genuinely effective (years, not a day) must be rejected exactly
    the same way as the one-day case -- there is no grace window.
    Affects: auditability."""
    service = _service()
    only = _register(service)
    service.activate_revision(new_revision_id=only.identity.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    try:
        service.withdraw_revision(document_revision_id=only.identity.document_revision_id, withdrawal_effective_date=date(2024, 6, 1), closure_reason="correction", authority_source="gov", authority_reference="C1", authority_recorded_by="alice", recorded_at=NOW)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "correction" in str(exc) and "withdrawn" in str(exc)


def test_failed_correction_leaves_metadata_period_and_events_unchanged():
    """Business nuance: a rejected correction attempt (item 2's boundary
    check) must be a true no-op -- the rejection happens BEFORE the
    repository's transaction() is even entered, so nothing partial can
    be left behind. Affects: auditability (a rejected request must never
    itself become a misleading audit trail)."""
    service = _service()
    only = _register(service)
    service.activate_revision(new_revision_id=only.identity.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    metadata_before = service._repository.get_metadata(only.identity.document_revision_id)
    periods_before = service._repository.list_periods_for_revision(only.identity.document_revision_id)
    events_before = service._repository.list_events("DOC-1")

    try:
        service.withdraw_revision(document_revision_id=only.identity.document_revision_id, withdrawal_effective_date=date(2024, 6, 1), closure_reason="correction", authority_source="gov", authority_reference="C1", authority_recorded_by="alice", recorded_at=NOW)
        assert False, "expected ValueError"
    except ValueError:
        pass

    assert service._repository.get_metadata(only.identity.document_revision_id) == metadata_before
    assert service._repository.list_periods_for_revision(only.identity.document_revision_id) == periods_before
    assert service._repository.list_events("DOC-1") == events_before


def test_withdraw_revision_rejects_superseded_and_rollback_as_closure_reason():
    """Business nuance: withdraw_revision must never accept
    'superseded'/'rollback' -- those are meaningful ONLY when a NEW
    revision is simultaneously taking over (activate_revision/
    reinstate_revision), which withdraw_revision never does. Failure
    this guards against: a semantically contradictory audit record
    ("withdrawn... for reason: superseded") with no actual successor.
    Affects: auditability directly."""
    service = _service()
    only = _register(service)
    service.activate_revision(new_revision_id=only.identity.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    for bad_reason in ("superseded", "rollback"):
        try:
            service.withdraw_revision(
                document_revision_id=only.identity.document_revision_id, withdrawal_effective_date=date(2023, 1, 1),
                closure_reason=bad_reason, authority_source="gov", authority_reference="X",
                authority_recorded_by="alice", recorded_at=NOW,
            )
            assert False, f"expected ValueError for closure_reason={bad_reason!r}"
        except ValueError as exc:
            assert "withdrawn" in str(exc) and "correction" in str(exc)
