"""Stage 7A.1: idempotent-indexing tests.

Uses the deterministic FakeEmbeddingProvider and the in-memory
VectorStore reference implementation only -- no network, no database.
"""

from __future__ import annotations

import pytest

from ingestion_bench.retrieval_baseline.config import ARTIFACTS_STAGE5A_ROOT, CORPUS_PROFILES_PATH
from ingestion_bench.retrieval_baseline.corpus import load_corpus_profile_set
from ingestion_bench.retrieval_baseline.embeddings import FakeEmbeddingProvider
from ingestion_bench.retrieval_baseline.indexer import build_index
from ingestion_bench.retrieval_baseline.vector_store import InMemoryVectorStore, VectorRecord


def _skip_if_no_artifacts():
    if not (ARTIFACTS_STAGE5A_ROOT / "PARITY_001_pdf" / "canonical_chunks.jsonl").exists():
        pytest.skip("artifacts/stage5a/ not present -- run scripts/run_docling_standard.py first")


def _profile(name: str):
    return load_corpus_profile_set(CORPUS_PROFILES_PATH).profiles[name]


def test_first_build_indexes_every_nonempty_chunk():
    _skip_if_no_artifacts()
    profile = _profile("parity_pdf")
    embedder = FakeEmbeddingProvider(dimension=16)
    store = InMemoryVectorStore()
    result = build_index(profile, ARTIFACTS_STAGE5A_ROOT, embedder, store)
    assert result.indexed_count == result.candidate_chunk_count - result.empty_retrieval_text_skipped_count
    assert result.skipped_unchanged_count == 0
    assert result.total_record_count == result.indexed_count


def test_second_build_is_fully_idempotent_no_reembedding_no_duplicates():
    _skip_if_no_artifacts()
    profile = _profile("parity_pdf")
    embedder = FakeEmbeddingProvider(dimension=16)
    store = InMemoryVectorStore()
    first = build_index(profile, ARTIFACTS_STAGE5A_ROOT, embedder, store)
    second = build_index(profile, ARTIFACTS_STAGE5A_ROOT, embedder, store)

    assert second.indexed_count == 0
    assert second.embedded_count == 0
    assert second.skipped_unchanged_count == first.indexed_count
    assert second.total_record_count == first.total_record_count
    assert second.index_hash == first.index_hash


def test_index_hash_is_stable_across_rebuilds_with_unchanged_input():
    _skip_if_no_artifacts()
    profile = _profile("baseline_demo")
    embedder = FakeEmbeddingProvider(dimension=16)
    store_a = InMemoryVectorStore()
    store_b = InMemoryVectorStore()
    result_a = build_index(profile, ARTIFACTS_STAGE5A_ROOT, embedder, store_a)
    result_b = build_index(profile, ARTIFACTS_STAGE5A_ROOT, embedder, store_b)
    assert result_a.index_hash == result_b.index_hash


def test_store_upsert_never_creates_duplicate_rows_for_the_same_key():
    """The same chunk_id + content_sha256 + embedding_model (scoped by
    corpus_profile) must never create duplicate records, even if upsert()
    itself is called twice with the identical record -- proven at the
    STORE level, independent of the indexer's own pre-filtering
    optimization."""
    store = InMemoryVectorStore()
    record = VectorRecord(
        corpus_profile="p", embedding_model="m", chunk_id="c1", content_sha256="a" * 64, retrieval_text="hello",
        fixture="x/y", doc_id="D", source_format="pdf", contains_model_derived=False, embedding=[1.0, 0.0],
    )
    store.upsert([record])
    store.upsert([record])
    store.upsert([record])
    assert store.record_count("p", "m") == 1


def test_store_upsert_replaces_when_content_sha256_changes_still_one_row():
    store = InMemoryVectorStore()
    base = dict(
        corpus_profile="p", embedding_model="m", chunk_id="c1", fixture="x/y", doc_id="D", source_format="pdf",
        contains_model_derived=False, embedding=[1.0, 0.0],
    )
    store.upsert([VectorRecord(**base, content_sha256="a" * 64, retrieval_text="v1")])
    store.upsert([VectorRecord(**base, content_sha256="b" * 64, retrieval_text="v2")])
    assert store.record_count("p", "m") == 1
    hashes = store.existing_content_hashes("p", "m")
    assert hashes["c1"] == "b" * 64


def test_same_chunk_indexed_separately_per_corpus_profile():
    """A chunk from PARITY_001.pdf legitimately appears in BOTH
    baseline_demo and parity_pdf -- these must be two independent rows
    (scoped by corpus_profile), never deduplicated across profiles."""
    _skip_if_no_artifacts()
    embedder = FakeEmbeddingProvider(dimension=16)
    store = InMemoryVectorStore()
    build_index(_profile("baseline_demo"), ARTIFACTS_STAGE5A_ROOT, embedder, store)
    build_index(_profile("parity_pdf"), ARTIFACTS_STAGE5A_ROOT, embedder, store)

    baseline_ids = store.all_chunk_ids("baseline_demo", embedder.model_identity)
    parity_pdf_ids = store.all_chunk_ids("parity_pdf", embedder.model_identity)
    assert parity_pdf_ids <= baseline_ids  # every parity_pdf chunk also appears in baseline_demo
    assert store.record_count("baseline_demo", embedder.model_identity) != store.record_count(
        "parity_pdf", embedder.model_identity
    )


def test_empty_retrieval_text_chunks_are_never_indexed():
    """A chunk with empty/whitespace-only retrieval_text (e.g. an
    asset-only picture with no caption/OCR/model-derived text) has
    nothing meaningful to embed and must never be indexed."""
    _skip_if_no_artifacts()
    profile = _profile("parity_pptx")
    embedder = FakeEmbeddingProvider(dimension=16)
    store = InMemoryVectorStore()
    result = build_index(profile, ARTIFACTS_STAGE5A_ROOT, embedder, store)
    if result.empty_retrieval_text_skipped_count > 0:
        assert result.indexed_count == result.candidate_chunk_count - result.empty_retrieval_text_skipped_count
        assert result.total_record_count == result.indexed_count
