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
