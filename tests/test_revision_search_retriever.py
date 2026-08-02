"""Stage 7R.2: authority_aware_search() tests -- fail-closed behavior,
provenance completeness, and that filtering happens before ranking/LIMIT
at the retriever level (composing the real Stage 7R.1 resolver with the
in-memory store)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from ingestion_bench.revision_authority.model import AuthorityPeriod
from ingestion_bench.revision_authority.repository import InMemoryRevisionAuthorityRepository
from ingestion_bench.revision_authority.service import RevisionAuthorityService
from ingestion_bench.revision_search_benchmark.retriever import authority_aware_search
from ingestion_bench.revision_search_benchmark.store import InMemoryRevisionVectorStore, RevisionVectorRecord

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
DOC = "POLICY-RETENTION-001"


def _record(document_revision_id: str, chunk_id: str, embedding: list[float]) -> RevisionVectorRecord:
    return RevisionVectorRecord(
        embedding_model="fake-v1", logical_document_id=DOC, document_revision_id=document_revision_id,
        version_label=None, revision_number=1, source_document_sha256="a" * 64,
        source_relative_path="generated/fake.docx", chunk_id=chunk_id,
        content_sha256="b" * 64, retrieval_text=f"text for {chunk_id}", chunk_type="text", embedding=embedding,
    )


def _service_with_one_effective_revision():
    repository = InMemoryRevisionAuthorityRepository()
    service = RevisionAuthorityService(repository)
    result = service.register_revision(
        logical_document_id=DOC, source_document_sha256="a" * 64, version_label=None, revision_number=1,
        authority_source="gov", authority_reference="REF", authority_recorded_by="alice", recorded_at=NOW,
    )
    service.activate_revision(
        new_revision_id=result.identity.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1),
        authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW,
    )
    return service, repository, result.identity.document_revision_id


def test_registry_integrity_error_fails_closed_before_any_vector_search():
    """Business nuance: when Stage 7R.1's resolver reports an
    integrity_error (e.g. two revisions simultaneously effective), the
    retriever must return ZERO hits and must NEVER call the vector store
    at all -- not 'search everything and return nothing', but 'never
    search'. Failure this guards against: a partially-filtered result
    slipping through when the registry itself cannot be trusted, or
    wasted vector-search latency on a query that was always going to
    fail closed. Affects: current search directly."""
    repository = InMemoryRevisionAuthorityRepository()
    service = RevisionAuthorityService(repository)
    a = service.register_revision(logical_document_id=DOC, source_document_sha256="a" * 64, version_label=None, revision_number=1, authority_source="gov", authority_reference="R1", authority_recorded_by="alice", recorded_at=NOW)
    b = service.register_revision(logical_document_id=DOC, source_document_sha256="b" * 64, version_label=None, revision_number=2, authority_source="gov", authority_reference="R2", authority_recorded_by="alice", recorded_at=NOW)
    service.activate_revision(new_revision_id=a.identity.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1), authority_source="gov", authority_reference="A1", authority_recorded_by="alice", recorded_at=NOW)
    # Raw, low-level write constructing a genuine cross-revision overlap
    # -- bypasses service.py's own validation, simulating pre-existing
    # inconsistent data (matches the pattern used throughout
    # test_revision_authority_resolver.py for the same reason).
    repository.save_period(AuthorityPeriod(
        authority_period_id=0, logical_document_id=DOC, document_revision_id=b.identity.document_revision_id,
        effective_from=date(2020, 6, 1), effective_to=None, opening_event_id=1,
        authority_source="gov", authority_reference="RAW", recorded_at=NOW, recorded_by="alice",
    ))
    repository.save_metadata(b.identity.document_revision_id, repository.get_metadata(b.identity.document_revision_id).model_copy(update={"publication_status": "approved"}))

    class _ExplodingStore(InMemoryRevisionVectorStore):
        def search_eligible(self, **kwargs):
            raise AssertionError("search_eligible() must never be called when the resolver fails closed")

        def search_unfiltered(self, **kwargs):
            raise AssertionError("search_unfiltered() must never be called when the resolver fails closed either")

    result = authority_aware_search(
        service=service, store=_ExplodingStore(), logical_document_id=DOC, query_intent="current",
        as_of_date=date(2024, 1, 1), requested_revision_ids=None, query_vector=[1.0, 0.0],
        embedding_model="fake-v1", top_k=5,
    )
    assert result.failed_closed is True
    assert result.integrity_error is not None
    assert result.hits == []


def test_current_intent_returns_only_the_effective_revision_with_full_provenance():
    """Business nuance: every RetrievalHit must carry its own authority
    label, document identity, and chunk/source provenance -- never a bare
    similarity score. Affects: auditability (a result with no provenance
    is unusable as evidence)."""
    service, repository, revision_id = _service_with_one_effective_revision()
    store = InMemoryRevisionVectorStore()
    store.upsert([_record(revision_id, "chunk-1", [1.0, 0.0])])

    result = authority_aware_search(
        service=service, store=store, logical_document_id=DOC, query_intent="current", as_of_date=date(2024, 1, 1),
        requested_revision_ids=None, query_vector=[1.0, 0.0], embedding_model="fake-v1", top_k=5,
    )
    assert result.failed_closed is False
    assert len(result.hits) == 1
    hit = result.hits[0]
    assert hit.document_revision_id == revision_id
    assert hit.logical_document_id == DOC
    assert hit.authority_label.derived_state == "effective"
    assert hit.chunk_id == "chunk-1"
    assert hit.content_sha256 == "b" * 64
    assert hit.source_document_sha256 == "a" * 64
    assert hit.source_relative_path == "generated/fake.docx"
    assert hit.rank == 1
    assert hit.similarity_score == 1.0
    # The unfiltered comparison ran too, from the SAME call.
    assert len(result.unfiltered_hits) == 1
    assert result.unfiltered_hits[0].document_revision_id == revision_id


def test_draft_intent_labels_the_result_draft_never_as_current_authority():
    repository = InMemoryRevisionAuthorityRepository()
    service = RevisionAuthorityService(repository)
    result = service.register_revision(
        logical_document_id=DOC, source_document_sha256="a" * 64, version_label=None, revision_number=1,
        authority_source="gov", authority_reference="REF", authority_recorded_by="alice", recorded_at=NOW,
    )
    store = InMemoryRevisionVectorStore()
    store.upsert([_record(result.identity.document_revision_id, "chunk-1", [1.0, 0.0])])

    search_result = authority_aware_search(
        service=service, store=store, logical_document_id=DOC, query_intent="draft", as_of_date=date(2024, 1, 1),
        requested_revision_ids=[result.identity.document_revision_id], query_vector=[1.0, 0.0],
        embedding_model="fake-v1", top_k=5,
    )
    assert [h.document_revision_id for h in search_result.hits] == [result.identity.document_revision_id]
    assert search_result.hits[0].authority_label.derived_state == "draft"
