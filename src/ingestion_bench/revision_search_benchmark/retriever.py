"""Stage 7R.2/7R.2a: the narrow authority-aware retriever.

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

The SAME function also runs the unfiltered comparison search (item 5's
own requirement), so both ranked lists come from ONE call, never two
independently-drifting code paths.

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
    # None exactly when the resolver never labeled this revision in this
    # query's scope -- e.g. an UNFILTERED hit belonging to a revision
    # that comparison/draft never requested, so resolve_query_scope()
    # never produced a label for it at all (Stage 7R.2a item 2: "authority
    # label, when applicable").
    authority_label: RevisionAuthorityLabel | None

    source_relative_path: str
    source_document_sha256: str
    chunk_id: str
    content_sha256: str
    retrieval_text: str
    chunk_type: str
    unit_indices: list[int]
    heading_path: list[str]
    source_element_ids: list[str]
    source_refs: list[dict]


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
    authority_aware_vector_search_latency_seconds: float
    unfiltered_vector_search_latency_seconds: float

    # Stage 7R.2a item 2: BOTH ranked lists are persisted on the SAME
    # result object -- never discarded after metric calculation, never
    # recomputed separately for the report vs. the artifact.
    hits: list[RetrievalHit]
    unfiltered_hits: list[RetrievalHit]


def _hit_from_search(hit: SearchHit, rank: int, label: RevisionAuthorityLabel | None) -> RetrievalHit:
    record = hit.record
    return RetrievalHit(
        rank=rank,
        similarity_score=hit.score,
        logical_document_id=record.logical_document_id,
        document_revision_id=record.document_revision_id,
        version_label=record.version_label,
        revision_number=record.revision_number,
        authority_label=label,
        source_relative_path=record.source_relative_path,
        source_document_sha256=record.source_document_sha256,
        chunk_id=record.chunk_id,
        content_sha256=record.content_sha256,
        retrieval_text=record.retrieval_text,
        chunk_type=record.chunk_type,
        unit_indices=list(record.unit_indices),
        heading_path=list(record.heading_path),
        source_element_ids=list(record.source_element_ids),
        source_refs=list(record.source_refs),
    )


def _hits_from_search(search_hits: list[SearchHit], authority_labels: dict[str, RevisionAuthorityLabel]) -> list[RetrievalHit]:
    return [
        _hit_from_search(hit, rank, authority_labels.get(hit.record.document_revision_id))
        for rank, hit in enumerate(search_hits, start=1)
    ]


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
    aware_latency = 0.0
    unfiltered_latency = 0.0
    hits: list[RetrievalHit] = []
    unfiltered_hits: list[RetrievalHit] = []
    # When the resolver fails closed, the vector store is NEVER called at
    # all -- neither the authority-aware search nor the unfiltered
    # comparison. The registry is untrustworthy, so there is nothing
    # meaningful to compare either, and a failed-closed query must cost
    # zero vector-search work, not just zero authority-aware hits.
    if not failed_closed:
        vector_start = time.perf_counter()
        search_hits = store.search_eligible(
            logical_document_id=logical_document_id,
            embedding_model=embedding_model,
            query_vector=query_vector,
            eligible_revision_ids=resolution.eligible_revision_ids,
            top_k=top_k,
        )
        aware_latency = time.perf_counter() - vector_start
        hits = _hits_from_search(search_hits, resolution.authority_labels)

        unfiltered_start = time.perf_counter()
        unfiltered_search_hits = store.search_unfiltered(
            logical_document_id=logical_document_id, embedding_model=embedding_model, query_vector=query_vector, top_k=top_k
        )
        unfiltered_latency = time.perf_counter() - unfiltered_start
        unfiltered_hits = _hits_from_search(unfiltered_search_hits, resolution.authority_labels)

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
        authority_aware_vector_search_latency_seconds=aware_latency,
        unfiltered_vector_search_latency_seconds=unfiltered_latency,
        hits=hits,
        unfiltered_hits=unfiltered_hits,
    )
