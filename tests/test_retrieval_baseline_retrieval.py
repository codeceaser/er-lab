"""Stage 7A.1: retrieval-result provenance and determinism tests.

Uses the deterministic FakeEmbeddingProvider and the in-memory
VectorStore -- no network, no database.
"""

from __future__ import annotations

from ingestion_bench.retrieval_baseline.embeddings import FakeEmbeddingProvider
from ingestion_bench.retrieval_baseline.retrieval import search
from ingestion_bench.retrieval_baseline.vector_store import InMemoryVectorStore, VectorRecord


def _seed_store() -> tuple[InMemoryVectorStore, FakeEmbeddingProvider]:
    embedder = FakeEmbeddingProvider(dimension=16)
    store = InMemoryVectorStore()
    texts = {
        "c1": "Application APP-224510 supports the Payment Settlement business service.",
        "c2": "Unrelated text about quarterly recovery-test pass rates.",
        "c3": "Control C-88 mandates Recovery Procedure P-205.",
    }
    for chunk_id, text in texts.items():
        vector = embedder.embed([text]).vectors[0]
        store.upsert(
            [
                VectorRecord(
                    corpus_profile="p", embedding_model=embedder.model_identity, chunk_id=chunk_id,
                    content_sha256="a" * 63 + chunk_id[-1], retrieval_text=text, fixture="parity/PARITY_001.pdf",
                    doc_id="PARITY_001", source_format="pdf", source_element_ids=[f"el_{chunk_id}"],
                    heading_source_element_ids=[f"h_{chunk_id}"], annotation_ids=[], unit_indices=[0],
                    source_refs=[{"element_id": f"el_{chunk_id}", "unit_index": 0, "element_type": "paragraph"}],
                    heading_path=["Some Heading"], contains_model_derived=False, embedding=vector,
                )
            ]
        )
    return store, embedder


def test_retrieval_result_carries_full_provenance():
    store, embedder = _seed_store()
    results, meta = search("Application APP-224510 supports the Payment Settlement business service.", "p", embedder, store, top_k=1)
    assert len(results) == 1
    r = results[0]
    assert r.rank == 1
    assert 0.99 <= r.score <= 1.0000001
    assert r.chunk_id == "c1"
    assert r.content_sha256
    assert r.retrieval_text
    assert r.fixture == "parity/PARITY_001.pdf"
    assert r.doc_id == "PARITY_001"
    assert r.source_format == "pdf"
    assert r.unit_indices == [0]
    assert r.source_element_ids == ["el_c1"]
    assert r.heading_source_element_ids == ["h_c1"]
    assert r.annotation_ids == []
    assert r.source_refs and r.source_refs[0]["element_id"] == "el_c1"
    assert r.heading_path == ["Some Heading"]
    assert meta.retrieved_count == 1
    assert meta.corpus_profile == "p"
    assert meta.embedding_model == embedder.model_identity


def test_exact_text_match_ranks_first():
    store, embedder = _seed_store()
    results, _meta = search("Control C-88 mandates Recovery Procedure P-205.", "p", embedder, store, top_k=3)
    assert results[0].chunk_id == "c3"
    assert results[0].score == max(r.score for r in results)


def test_ranking_is_deterministic_across_repeated_calls():
    store, embedder = _seed_store()
    query = "Application APP-224510 supports the Payment Settlement business service."
    runs = [search(query, "p", embedder, store, top_k=3)[0] for _ in range(5)]
    first_order = [r.chunk_id for r in runs[0]]
    for run in runs[1:]:
        assert [r.chunk_id for r in run] == first_order
        assert [r.score for r in run] == [r.score for r in runs[0]]


def test_top_k_is_respected_and_never_exceeds_available_records():
    store, embedder = _seed_store()
    results, meta = search("anything", "p", embedder, store, top_k=100)
    assert len(results) == 3  # only 3 records exist
    assert meta.retrieved_count == 3
    assert [r.rank for r in results] == [1, 2, 3]
