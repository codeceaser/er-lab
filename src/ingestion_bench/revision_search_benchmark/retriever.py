"""Stage 7R.2: the narrow authority-aware retriever.

For every query:
    1. calls Stage 7R.1's resolve_query_scope() (read-only reuse, never
       reimplemented, never modified);
    2. fails closed on integrity_error -- zero hits, the integrity error
       surfaced on the result, never a silent fallback to "just search
       everything";
    3. receives eligible_revision_ids;
    4. restricts vector candidates to those ids BEFORE similarity ranking
       (see store.py/pgvector_store.py -- the restriction lives inside
       the ranking query itself);
    5. returns top-K provenance-rich results, each carrying its own
       authority label, document identity, chunk/source provenance, and
       similarity score/rank.

Never touches CanonicalDocument/CanonicalChunk, never calls an LLM, never
imports Graph RAG/wiki/ADK/vision code.
"""

from __future__ import annotations

import time
from datetime import date

from pydantic import BaseModel, ConfigDict

from ingestion_bench.revision_authority.resolver import ExclusionReason, RevisionAuthorityLabel
from ingestion_bench.revision_authority.service import RevisionAuthorityService
from ingestion_bench.revision_search_benchmark.store import RevisionVectorStore, SearchHit


class RetrievalHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    similarity_score: float

    logical_document_id: str
    document_revision_id: str
    version_label: str | None
    revision_number: int | None
    authority_label: RevisionAuthorityLabel

    chunk_id: str
    content_sha256: str
    retrieval_text: str
    source_document_sha256: str


class AuthorityAwareSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logical_document_id: str
    query_intent: str
    as_of_date: date
    requested_revision_ids: list[str]

    registry_snapshot_hash: str
    eligible_revision_ids: list[str]
    excluded: list[ExclusionReason]
    authority_labels: dict[str, RevisionAuthorityLabel]
    integrity_error: str | None
    integrity_error_code: str | None
    failed_closed: bool

    resolver_latency_seconds: float
    vector_search_latency_seconds: float

    hits: list[RetrievalHit]


def _hit_from_search(hit: SearchHit, rank: int, label: RevisionAuthorityLabel) -> RetrievalHit:
    record = hit.record
    return RetrievalHit(
        rank=rank,
        similarity_score=hit.score,
        logical_document_id=record.logical_document_id,
        document_revision_id=record.document_revision_id,
        version_label=record.version_label,
        revision_number=record.revision_number,
        authority_label=label,
        chunk_id=record.chunk_id,
        content_sha256=record.content_sha256,
        retrieval_text=record.retrieval_text,
        source_document_sha256=record.source_document_sha256,
    )


def authority_aware_search(
    *,
    service: RevisionAuthorityService,
    store: RevisionVectorStore,
    logical_document_id: str,
    query_intent: str,
    as_of_date: date,
    requested_revision_ids: list[str] | None,
    query_vector: list[float],
    embedding_model: str,
    top_k: int,
) -> AuthorityAwareSearchResult:
    resolver_start = time.perf_counter()
    resolution = service.resolve_query_scope(
        logical_document_id=logical_document_id,
        query_intent=query_intent,  # type: ignore[arg-type]
        as_of_date=as_of_date,
        requested_revision_ids=requested_revision_ids,
    )
    resolver_latency = time.perf_counter() - resolver_start

    failed_closed = resolution.integrity_error is not None
    vector_latency = 0.0
    hits: list[RetrievalHit] = []
    if not failed_closed:
        vector_start = time.perf_counter()
        search_hits = store.search_eligible(
            embedding_model=embedding_model,
            query_vector=query_vector,
            eligible_revision_ids=resolution.eligible_revision_ids,
            top_k=top_k,
        )
        vector_latency = time.perf_counter() - vector_start
        hits = [
            _hit_from_search(hit, rank, resolution.authority_labels[hit.record.document_revision_id])
            for rank, hit in enumerate(search_hits, start=1)
        ]

    return AuthorityAwareSearchResult(
        logical_document_id=logical_document_id,
        query_intent=query_intent,
        as_of_date=as_of_date,
        requested_revision_ids=requested_revision_ids or [],
        registry_snapshot_hash=resolution.registry_snapshot_hash,
        eligible_revision_ids=resolution.eligible_revision_ids,
        excluded=resolution.excluded,
        authority_labels=resolution.authority_labels,
        integrity_error=resolution.integrity_error,
        integrity_error_code=resolution.integrity_error_code,
        failed_closed=failed_closed,
        resolver_latency_seconds=resolver_latency,
        vector_search_latency_seconds=vector_latency,
        hits=hits,
    )


def unfiltered_search(
    *, store: RevisionVectorStore, query_vector: list[float], embedding_model: str, top_k: int
) -> tuple[list[SearchHit], float]:
    """NO revision restriction at all -- used only for the item 5
    unfiltered-vs-authority-aware comparison, never returned as an
    authority-aware result."""
    start = time.perf_counter()
    hits = store.search_unfiltered(embedding_model=embedding_model, query_vector=query_vector, top_k=top_k)
    return hits, time.perf_counter() - start
