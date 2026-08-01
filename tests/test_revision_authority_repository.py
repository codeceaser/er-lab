"""Stage 7R.1: in-memory repository tests -- append-only event log."""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

from ingestion_bench.revision_authority.model import AuthorityDecisionEvent
from ingestion_bench.revision_authority.repository import InMemoryRevisionAuthorityRepository


def _event(**overrides) -> AuthorityDecisionEvent:
    defaults = dict(
        event_id=0,
        event_type="revision_registered",
        logical_document_id="DOC-1",
        revision_id="r1",
        recorded_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        authority_source="governance-system",
        authority_reference="REF-1",
        recorded_by="alice",
        detail="test event",
    )
    defaults.update(overrides)
    return AuthorityDecisionEvent(**defaults)


def test_authority_decision_events_are_append_only():
    """Business nuance: the audit trail must be an immutable, growing
    log -- every authority change (register/decide/activate/withdraw)
    is a permanent fact, never editable after the fact. Failure this
    guards against: a caller "fixing" history by mutating or deleting a
    past event, which would make the registry's own audit trail
    untrustworthy. Affects: auditability directly -- this is the
    single property the whole event log exists to guarantee."""
    repo = InMemoryRevisionAuthorityRepository()
    e1 = repo.append_event(_event(detail="first"))
    e2 = repo.append_event(_event(detail="second"))
    assert e1.event_id == 1
    assert e2.event_id == 2
    events = repo.list_events("DOC-1")
    assert [e.detail for e in events] == ["first", "second"]

    # No update/delete method exists anywhere on this repository's
    # public surface -- append-only by API-surface absence, not just by
    # convention a caller could bypass.
    public_methods = {name for name, _ in inspect.getmembers(repo, predicate=inspect.ismethod) if not name.startswith("_")}
    assert not any("update" in m or "delete" in m or "remove" in m for m in public_methods if "event" in m.lower())
    assert "append_event" in public_methods
    assert "list_events" in public_methods


def test_list_events_returns_a_copy_never_the_internal_list():
    """Business nuance: a caller mutating the LIST returned by
    list_events() must never corrupt the repository's own internal
    history. Failure this guards against: accidental external mutation
    silently rewriting audit history via a shared reference. Affects:
    auditability."""
    repo = InMemoryRevisionAuthorityRepository()
    repo.append_event(_event())
    events = repo.list_events("DOC-1")
    events.clear()
    assert len(repo.list_events("DOC-1")) == 1


def test_list_events_filters_by_logical_document_id():
    repo = InMemoryRevisionAuthorityRepository()
    repo.append_event(_event(logical_document_id="DOC-1"))
    repo.append_event(_event(logical_document_id="DOC-2"))
    assert len(repo.list_events("DOC-1")) == 1
    assert len(repo.list_events("DOC-2")) == 1
    assert len(repo.list_events()) == 2


def test_event_ids_are_assigned_monotonically_across_documents():
    """Business nuance: event_id ordering must be globally meaningful
    (a real timeline of registry changes), not per-document -- so an
    auditor can reconstruct the exact global sequence of authority
    decisions across the whole registry. Affects: auditability."""
    repo = InMemoryRevisionAuthorityRepository()
    e1 = repo.append_event(_event(logical_document_id="DOC-1"))
    e2 = repo.append_event(_event(logical_document_id="DOC-2"))
    e3 = repo.append_event(_event(logical_document_id="DOC-1"))
    assert [e1.event_id, e2.event_id, e3.event_id] == [1, 2, 3]
