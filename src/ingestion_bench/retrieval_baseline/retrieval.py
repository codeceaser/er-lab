"""Stage 7A.1: provenance-rich retrieval.

A retrieval result is never just text and a similarity number -- every
result carries the full provenance chain back to the original
CanonicalDocument elements it came from.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict

from ingestion_bench.retrieval_baseline.embeddings import EmbeddingProvider
from ingestion_bench.retrieval_baseline.vector_store import VectorStore


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    score: float

    chunk_id: str
    content_sha256: str
    retrieval_text: str

    fixture: str
    doc_id: str
    source_format: str

    unit_indices: list[int]
    source_element_ids: list[str]
    heading_source_element_ids: list[str]
    annotation_ids: list[str]
    source_refs: list[dict]
    heading_path: list[str]


class SearchMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus_profile: str
    embedding_model: str
    query: str
    top_k: int
    retrieved_count: int
    embedding_elapsed_seconds: float
    search_elapsed_seconds: float
    total_latency_seconds: float


def search(
    query: str,
    corpus_profile: str,
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStore,
    top_k: int,
) -> tuple[list[RetrievalResult], SearchMeta]:
    start = time.perf_counter()
    embed_result = embedding_provider.embed([query])
    query_vector = embed_result.vectors[0]

    search_start = time.perf_counter()
    hits = vector_store.search(corpus_profile, embedding_provider.model_identity, query_vector, top_k)
    search_elapsed = time.perf_counter() - search_start

    results = [
        RetrievalResult(
            rank=index + 1,
            score=hit.score,
            chunk_id=hit.record.chunk_id,
            content_sha256=hit.record.content_sha256,
            retrieval_text=hit.record.retrieval_text,
            fixture=hit.record.fixture,
            doc_id=hit.record.doc_id,
            source_format=hit.record.source_format,
            unit_indices=hit.record.unit_indices,
            source_element_ids=hit.record.source_element_ids,
            heading_source_element_ids=hit.record.heading_source_element_ids,
            annotation_ids=hit.record.annotation_ids,
            source_refs=hit.record.source_refs,
            heading_path=hit.record.heading_path,
        )
        for index, hit in enumerate(hits)
    ]

    total_latency = time.perf_counter() - start
    meta = SearchMeta(
        corpus_profile=corpus_profile,
        embedding_model=embedding_provider.model_identity,
        query=query,
        top_k=top_k,
        retrieved_count=len(results),
        embedding_elapsed_seconds=embed_result.elapsed_seconds,
        search_elapsed_seconds=search_elapsed,
        total_latency_seconds=total_latency,
    )
    return results, meta
