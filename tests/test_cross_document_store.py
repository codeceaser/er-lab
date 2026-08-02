"""Stage 7B.0: InMemoryCrossDocumentVectorStore unit tests -- proves the
cross-document eligibility-filtering contract in isolation."""

from __future__ import annotations

from ingestion_bench.cross_document_benchmark.store import InMemoryCrossDocumentVectorStore, RevisionVectorRecord


def _record(logical_document_id: str, document_revision_id: str, chunk_id: str, embedding: list[float]) -> RevisionVectorRecord:
    return RevisionVectorRecord(
        embedding_model="fake-v1", logical_document_id=logical_document_id, document_revision_id=document_revision_id,
        version_label=None, revision_number=1, source_document_sha256="a" * 64,
        source_relative_path="generated/fake.docx", chunk_id=chunk_id, content_sha256="b" * 64,
        retrieval_text=f"text for {chunk_id}", chunk_type="text", embedding=embedding,
    )


def test_ineligible_revision_strongest_match_never_leaks_into_eligible_search():
    """Business nuance: the ADVERSARIAL proof that cross-document
    filtering happens BEFORE ranking. An ineligible (e.g. historical)
    chunk whose embedding is IDENTICAL to the query (similarity 1.0, the
    strongest possible unfiltered match) must NEVER appear in
    search_eligible() when its revision is outside the cross-document
    eligible union, even though it wins the unfiltered search. Affects:
    every current-intent relationship query -- a historical/draft edge
    must never be surfaced as current."""
    store = InMemoryCrossDocumentVectorStore()
    query = [1.0, 0.0, 0.0]
    ineligible = _record("OBLIGATION-REGISTER", "hist-rev", "hist-chunk", [1.0, 0.0, 0.0])   # identical -> 1.0
    eligible = _record("OBLIGATION-REGISTER", "cur-rev", "cur-chunk", [0.0, 1.0, 0.0])       # orthogonal -> 0.0
    store.upsert([ineligible, eligible])

    unfiltered = store.search_unfiltered(embedding_model="fake-v1", query_vector=query, top_k=1)
    assert unfiltered[0].record.document_revision_id == "hist-rev"  # confirms adversarial setup

    eligible_only = store.search_eligible(embedding_model="fake-v1", query_vector=query, eligible_revision_ids=["cur-rev"], top_k=1)
    assert [h.record.document_revision_id for h in eligible_only] == ["cur-rev"]
    assert all(h.record.document_revision_id != "hist-rev" for h in eligible_only)


def test_empty_eligible_union_returns_zero_hits_never_searches_everything():
    store = InMemoryCrossDocumentVectorStore()
    store.upsert([_record("DOC-A", "rev-a", "chunk-a", [1.0, 0.0])])
    assert store.search_eligible(embedding_model="fake-v1", query_vector=[1.0, 0.0], eligible_revision_ids=[], top_k=5) == []


def test_search_eligible_spans_multiple_documents():
    """Cross-document: a single eligible search returns chunks from
    DIFFERENT logical documents when their revisions are all in the
    eligible union -- this is the whole point of cross-document
    retrieval."""
    store = InMemoryCrossDocumentVectorStore()
    store.upsert([
        _record("APP-PORTFOLIO", "app-rev2", "app-chunk", [1.0, 0.0, 0.0]),
        _record("SERVICE-CATALOGUE", "svc-rev1", "svc-chunk", [0.9, 0.1, 0.0]),
        _record("OBLIGATION-REGISTER", "obl-rev1-hist", "obl-hist-chunk", [1.0, 0.0, 0.0]),
    ])
    hits = store.search_eligible(
        embedding_model="fake-v1", query_vector=[1.0, 0.0, 0.0],
        eligible_revision_ids=["app-rev2", "svc-rev1"], top_k=5,
    )
    docs = {h.record.logical_document_id for h in hits}
    assert docs == {"APP-PORTFOLIO", "SERVICE-CATALOGUE"}
    assert all(h.record.document_revision_id != "obl-rev1-hist" for h in hits)


def test_deterministic_tie_break_by_chunk_id():
    store = InMemoryCrossDocumentVectorStore()
    store.upsert([
        _record("DOC-A", "rev-a", "zzz-chunk", [1.0, 0.0]),
        _record("DOC-B", "rev-b", "aaa-chunk", [1.0, 0.0]),
    ])
    hits = store.search_eligible(embedding_model="fake-v1", query_vector=[1.0, 0.0], eligible_revision_ids=["rev-a", "rev-b"], top_k=5)
    assert [h.record.chunk_id for h in hits] == ["aaa-chunk", "zzz-chunk"]  # equal score -> chunk_id ascending
