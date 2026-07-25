"""Stage 7A.1: deterministic, idempotent index building.

Reads frozen Stage 5A CanonicalChunk artifacts (via corpus.py), embeds
ONLY CanonicalChunk.retrieval_text (never source_text or
model_derived_text directly), and upserts into the configured vector
store. Never modifies CanonicalDocument, CanonicalChunk, or any Stage 5A
artifact.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ingestion_bench.retrieval_baseline.corpus import CorpusProfile, TaggedChunk, load_corpus_chunks
from ingestion_bench.retrieval_baseline.embeddings import EmbeddingProvider
from ingestion_bench.retrieval_baseline.vector_store import VectorRecord, VectorStore


class IndexBuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus_profile: str
    embedding_model: str
    fixtures: list[str]

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


def _vector_record_from_chunk(tagged: TaggedChunk, corpus_profile: str, embedding_model: str, embedding: list[float]) -> VectorRecord:
    chunk = tagged.chunk
    return VectorRecord(
        corpus_profile=corpus_profile,
        embedding_model=embedding_model,
        chunk_id=chunk.chunk_id,
        content_sha256=chunk.content_sha256,
        retrieval_text=chunk.retrieval_text,
        fixture=tagged.fixture,
        doc_id=tagged.doc_id,
        source_format=tagged.source_format,
        source_element_ids=list(chunk.source_element_ids),
        heading_source_element_ids=list(chunk.heading_source_element_ids),
        annotation_ids=list(chunk.annotation_ids),
        unit_indices=list(chunk.unit_indices),
        source_refs=[ref.model_dump(mode="json") for ref in chunk.source_refs],
        heading_path=list(chunk.heading_path),
        contains_model_derived=chunk.contains_model_derived,
        embedding=embedding,
    )


def build_index(
    profile: CorpusProfile,
    artifacts_root: Path,
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStore,
) -> IndexBuildResult:
    """Deterministic and idempotent: re-running with unchanged Stage 5A
    artifacts re-embeds nothing (every chunk is skipped as unchanged) and
    writes nothing new -- indexed_count == 0, skipped_unchanged_count ==
    candidate_chunk_count (minus any empty-retrieval_text chunks, which
    are never indexed at all -- there is nothing meaningful to embed)."""
    start = time.perf_counter()

    tagged_chunks = load_corpus_chunks(profile, artifacts_root)
    candidate_count = len(tagged_chunks)

    embeddable = [tc for tc in tagged_chunks if tc.chunk.retrieval_text.strip()]
    empty_skipped = candidate_count - len(embeddable)

    existing_hashes = vector_store.existing_content_hashes(profile.name, embedding_provider.model_identity)

    to_embed: list[TaggedChunk] = []
    skipped_unchanged = 0
    for tc in embeddable:
        if existing_hashes.get(tc.chunk.chunk_id) == tc.chunk.content_sha256:
            skipped_unchanged += 1
        else:
            to_embed.append(tc)

    if to_embed:
        embed_result = embedding_provider.embed([tc.chunk.retrieval_text for tc in to_embed])
    else:
        embed_result = None

    if embed_result is not None:
        records = [
            _vector_record_from_chunk(tc, profile.name, embedding_provider.model_identity, vector)
            for tc, vector in zip(to_embed, embed_result.vectors)
        ]
        vector_store.upsert(records)

    index_hash = vector_store.index_hash(profile.name, embedding_provider.model_identity)
    total_records = vector_store.record_count(profile.name, embedding_provider.model_identity)
    latency = time.perf_counter() - start

    return IndexBuildResult(
        corpus_profile=profile.name,
        embedding_model=embedding_provider.model_identity,
        fixtures=list(profile.fixtures),
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
