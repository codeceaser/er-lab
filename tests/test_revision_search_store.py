"""Stage 7R.2: InMemoryRevisionVectorStore unit tests -- proves the
store's OWN eligibility-filtering contract in isolation, before any
resolver/service involvement."""

from __future__ import annotations

from ingestion_bench.revision_search_benchmark.store import InMemoryRevisionVectorStore, RevisionVectorRecord


def _record(document_revision_id: str, chunk_id: str, embedding: list[float]) -> RevisionVectorRecord:
    return RevisionVectorRecord(
        embedding_model="fake-v1",
        logical_document_id="POLICY-RETENTION-001",
        document_revision_id=document_revision_id,
        version_label=None,
        revision_number=1,
        source_document_sha256="a" * 64,
        chunk_id=chunk_id,
        content_sha256="b" * 64,
        retrieval_text=f"text for {chunk_id}",
        chunk_type="text",
        embedding=embedding,
    )


def test_ineligible_draft_strongest_match_never_appears_in_eligible_search():
    """Business nuance: this is the ADVERSARIAL proof that filtering
    happens BEFORE ranking, not after -- an ineligible (draft) chunk
    whose embedding is IDENTICAL to the query vector (cosine similarity
    1.0, the strongest possible unfiltered match) must NEVER appear in
    search_eligible()'s results when its revision is excluded from
    eligible_revision_ids, even though it would rank #1 in an unfiltered
    search. Failure this guards against: a 'fetch top-K unfiltered, then
    discard ineligible hits' implementation, which would be
    indistinguishable from correct filtering on most inputs but would
    leak an ineligible result whenever top_k is smaller than the number
    of ineligible candidates ranked above the first eligible one --
    exactly what this test constructs. Affects: current search directly
    (this is THE property Stage 7R.2 exists to prove)."""
    store = InMemoryRevisionVectorStore()
    query_vector = [1.0, 0.0, 0.0]
    ineligible_draft = _record("draft-rev", "draft-chunk-1", [1.0, 0.0, 0.0])  # identical to query -- similarity 1.0
    eligible_effective = _record("effective-rev", "effective-chunk-1", [0.0, 1.0, 0.0])  # orthogonal -- similarity 0.0
    store.upsert([ineligible_draft, eligible_effective])

    unfiltered = store.search_unfiltered(embedding_model="fake-v1", query_vector=query_vector, top_k=1)
    assert unfiltered[0].record.document_revision_id == "draft-rev"  # confirms the adversarial setup: draft WOULD win unfiltered

    eligible_only = store.search_eligible(
        embedding_model="fake-v1", query_vector=query_vector, eligible_revision_ids=["effective-rev"], top_k=1
    )
    assert len(eligible_only) == 1
    assert eligible_only[0].record.document_revision_id == "effective-rev"
    assert all(hit.record.document_revision_id != "draft-rev" for hit in eligible_only)


def test_empty_eligible_revision_ids_returns_zero_hits_never_falls_back_to_unfiltered():
    """Business nuance: an empty eligible_revision_ids list (e.g. because
    the resolver found no effective revision) must yield ZERO hits, never
    silently fall back to searching everything. Failure this guards
    against: a defensive-coding bug ('if eligible list is empty, just
    search all') that would defeat authority-aware filtering exactly when
    it matters most (no authoritative revision exists). Affects: current
    search directly."""
    store = InMemoryRevisionVectorStore()
    store.upsert([_record("rev-1", "chunk-1", [1.0, 0.0])])
    hits = store.search_eligible(embedding_model="fake-v1", query_vector=[1.0, 0.0], eligible_revision_ids=[], top_k=5)
    assert hits == []


def test_upsert_is_idempotent_by_chunk_id_and_embedding_model():
    store = InMemoryRevisionVectorStore()
    record = _record("rev-1", "chunk-1", [1.0, 0.0])
    store.upsert([record])
    store.upsert([record.model_copy(update={"content_sha256": "c" * 64})])
    assert store.record_count("fake-v1") == 1
    assert store.existing_content_hashes("fake-v1")["chunk-1"] == "c" * 64


def test_index_hash_depends_only_on_chunk_id_and_content_hash_not_embedding_values():
    """Business nuance: index_hash must be reproducible across platforms
    even when floating-point embedding values differ slightly (e.g.
    different BLAS backends) -- it hashes (chunk_id, content_sha256)
    pairs only. Affects: the authority-switch proof (Scenario E), which
    depends on index_hash being a reliable 'did the index change'
    signal, not a false positive from embedding-library nondeterminism."""
    store_a = InMemoryRevisionVectorStore()
    store_b = InMemoryRevisionVectorStore()
    store_a.upsert([_record("rev-1", "chunk-1", [1.0, 0.0])])
    store_b.upsert([_record("rev-1", "chunk-1", [0.999999, 0.0001])])  # different embedding, same identity
    assert store_a.index_hash("fake-v1") == store_b.index_hash("fake-v1")
