"""Stage 7R.2: deterministic, idempotent index building for the
POLICY-RETENTION-001 revision-search benchmark.

Embeds ONLY CanonicalChunk.retrieval_text (never source_text or
model_derived_text directly), mirroring Stage 7A.1's own indexer.py
convention (read-only reference, never imported/modified). Never touches
CanonicalDocument/CanonicalChunk, and never attaches any authority label
to an indexed record -- authority is resolved separately, at query time,
by Stage 7R.1's own resolver."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict

from ingestion_bench.retrieval_baseline.embeddings import EmbeddingProvider
from ingestion_bench.revision_search_benchmark.fixtures import RevisionFixture
from ingestion_bench.revision_search_benchmark.store import RevisionVectorRecord, RevisionVectorStore


class IndexBuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedding_model: str
    revision_symbols: list[str]

    candidate_chunk_count: int
    empty_retrieval_text_skipped_count: int
    indexed_count: int
    skipped_unchanged_count: int
    embedded_count: int

    build_latency_seconds: float
    embedding_elapsed_seconds: float
    embedding_cost_usd: float | None

    index_hash: str
    total_record_count: int
    generated_at: str


def _vector_record_from_chunk(chunk, embedding_model: str, embedding: list[float]) -> RevisionVectorRecord:
    return RevisionVectorRecord(
        embedding_model=embedding_model,
        logical_document_id=chunk.logical_document_id,
        document_revision_id=chunk.document_revision_id,
        version_label=chunk.version_label,
        revision_number=chunk.revision_number,
        source_document_sha256=chunk.source_document_sha256,
        chunk_id=chunk.chunk_id,
        content_sha256=chunk.content_sha256,
        retrieval_text=chunk.retrieval_text,
        chunk_type=chunk.chunk_type,
        heading_path=list(chunk.heading_path),
        source_element_ids=list(chunk.source_element_ids),
        embedding=embedding,
    )


def build_index(
    revision_fixtures: dict[str, RevisionFixture],
    embedding_provider: EmbeddingProvider,
    vector_store: RevisionVectorStore,
) -> IndexBuildResult:
    """Deterministic and idempotent: re-running with unchanged fixtures
    re-embeds nothing (every chunk is skipped as unchanged) and writes
    nothing new. This is the SAME idempotency contract
    retrieval_baseline/indexer.py's build_index proves for Stage 7A.1 --
    see Stage 7R.2 scenario E, which depends on it: registering/
    activating a revision that is ALREADY indexed must never re-embed."""
    start = time.perf_counter()

    all_chunks = [chunk for fixture in revision_fixtures.values() for chunk in fixture.chunks]
    candidate_count = len(all_chunks)

    embeddable = [c for c in all_chunks if c.retrieval_text.strip()]
    empty_skipped = candidate_count - len(embeddable)

    existing_hashes = vector_store.existing_content_hashes(embedding_provider.model_identity)

    to_embed = [c for c in embeddable if existing_hashes.get(c.chunk_id) != c.content_sha256]
    skipped_unchanged = len(embeddable) - len(to_embed)

    if to_embed:
        embed_result = embedding_provider.embed([c.retrieval_text for c in to_embed])
        records = [_vector_record_from_chunk(c, embedding_provider.model_identity, v) for c, v in zip(to_embed, embed_result.vectors)]
        vector_store.upsert(records)
    else:
        embed_result = None

    index_hash = vector_store.index_hash(embedding_provider.model_identity)
    total_records = vector_store.record_count(embedding_provider.model_identity)
    latency = time.perf_counter() - start

    return IndexBuildResult(
        embedding_model=embedding_provider.model_identity,
        revision_symbols=sorted(revision_fixtures),
        candidate_chunk_count=candidate_count,
        empty_retrieval_text_skipped_count=empty_skipped,
        indexed_count=len(to_embed),
        skipped_unchanged_count=skipped_unchanged,
        embedded_count=embed_result.call_count if embed_result is not None else 0,
        build_latency_seconds=latency,
        embedding_elapsed_seconds=embed_result.elapsed_seconds if embed_result is not None else 0.0,
        embedding_cost_usd=embed_result.cost_usd if embed_result is not None else 0.0,
        index_hash=index_hash,
        total_record_count=total_records,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
