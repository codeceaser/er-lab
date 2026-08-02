"""Stage 7B.0: the cross-document authority-aware retriever.

For every query:
    1. resolves EACH corpus logical document independently through Stage
       7R.1's own resolve_query_scope() (read-only reuse) at the query's
       intent + as_of_date;
    2. fails closed if ANY document reports an integrity_error -- the
       shared corpus is untrustworthy, so nothing is retrieved;
    3. unions the per-document eligible_revision_ids into ONE
       cross-document eligibility set;
    4. runs ONE cross-document vector search restricted to that union
       BEFORE ranking/LIMIT (store.search_eligible);
    5. returns provenance-rich hits, each carrying the resolver's own
       authority label for its revision (when that revision's document
       was resolved in this query).

The retriever NEVER reads a question's required_fact_ids,
forbidden_fact_ids, or expected_relationship_chain -- those are
evaluation truth, consumed only by the evaluator (benchmark_runner). This
module's inputs are strictly the query text/vector, intent, as_of_date,
requested revisions, and top-K budget.

It also runs the unfiltered comparison search from the SAME call, so both
ranked lists derive from one code path.
"""

from __future__ import annotations

import time
from datetime import date

from pydantic import BaseModel, ConfigDict

from ingestion_bench.cross_document_benchmark.store import CrossDocumentVectorStore, SearchHit
from ingestion_bench.revision_authority.resolver import ExclusionReason, RevisionAuthorityLabel
from ingestion_bench.revision_authority.service import RevisionAuthorityService


class PerDocumentResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logical_document_id: str
    resolved: bool  # False for draft/comparison intents when no revision of this document was requested
    query_intent: str
    eligible_revision_ids: list[str]
    excluded: list[ExclusionReason]
    authority_labels: dict[str, RevisionAuthorityLabel]
    registry_snapshot_hash: str | None
    integrity_error: str | None
    integrity_error_code: str | None


class CrossDocumentRetrievalHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    similarity_score: float

    logical_document_id: str
    document_revision_id: str
    version_label: str | None
    revision_number: int | None
    # None when this revision's document was not resolved in this query
    # (e.g. an unfiltered hit from a document outside a draft query's
    # requested set) -- "authority label, when applicable".
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


class CrossDocumentSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_intent: str
    as_of_date: date
    requested_revision_ids_by_document: dict[str, list[str]]

    per_document_resolutions: list[PerDocumentResolution]
    eligible_revision_ids_union: list[str]
    corpus_registry_snapshot_hash: str
    failed_closed: bool
    integrity_errors: list[str]

    resolver_latency_seconds: float
    authority_aware_vector_search_latency_seconds: float
    unfiltered_vector_search_latency_seconds: float

    hits: list[CrossDocumentRetrievalHit]
    unfiltered_hits: list[CrossDocumentRetrievalHit]


def _hit_from_search(hit: SearchHit, rank: int, label: RevisionAuthorityLabel | None) -> CrossDocumentRetrievalHit:
    record = hit.record
    return CrossDocumentRetrievalHit(
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


def _corpus_registry_snapshot_hash(resolutions: list[PerDocumentResolution]) -> str:
    """A deterministic digest over every resolved document's own registry
    snapshot hash -- changes whenever ANY document's authority state
    changes, so a single value summarizes the whole corpus's authority
    state for a query. Reuses the same SHA-256-over-canonical-JSON idiom
    the resolver uses per document."""
    import hashlib
    import json

    payload = {r.logical_document_id: r.registry_snapshot_hash for r in resolutions if r.registry_snapshot_hash}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def cross_document_search(
    *,
    service: RevisionAuthorityService,
    store: CrossDocumentVectorStore,
    corpus_logical_document_ids: list[str],
    query_intent: str,
    as_of_date: date,
    requested_revision_ids_by_document: dict[str, list[str]],
    query_vector: list[float],
    embedding_model: str,
    top_k: int,
) -> CrossDocumentSearchResult:
    resolver_start = time.perf_counter()
    resolutions: list[PerDocumentResolution] = []
    merged_labels: dict[str, RevisionAuthorityLabel] = {}
    integrity_errors: list[str] = []
    eligible_union: list[str] = []

    for logical_document_id in corpus_logical_document_ids:
        # For current/as_of, resolve EVERY document (no requested ids).
        # For draft/comparison, resolve ONLY documents with a requested
        # revision (the resolver's explicit intents require at least one).
        if query_intent in ("current", "as_of"):
            requested = None
            do_resolve = True
        else:
            requested = requested_revision_ids_by_document.get(logical_document_id)
            do_resolve = bool(requested)

        if not do_resolve:
            resolutions.append(PerDocumentResolution(
                logical_document_id=logical_document_id, resolved=False, query_intent=query_intent,
                eligible_revision_ids=[], excluded=[], authority_labels={}, registry_snapshot_hash=None,
                integrity_error=None, integrity_error_code=None,
            ))
            continue

        resolution = service.resolve_query_scope(
            logical_document_id=logical_document_id,
            query_intent=query_intent,  # type: ignore[arg-type]
            as_of_date=as_of_date,
            requested_revision_ids=requested,
        )
        resolutions.append(PerDocumentResolution(
            logical_document_id=logical_document_id, resolved=True, query_intent=query_intent,
            eligible_revision_ids=list(resolution.eligible_revision_ids), excluded=list(resolution.excluded),
            authority_labels=dict(resolution.authority_labels), registry_snapshot_hash=resolution.registry_snapshot_hash,
            integrity_error=resolution.integrity_error, integrity_error_code=resolution.integrity_error_code,
        ))
        merged_labels.update(resolution.authority_labels)
        if resolution.integrity_error is not None:
            integrity_errors.append(f"{logical_document_id}: {resolution.integrity_error}")
        else:
            eligible_union.extend(resolution.eligible_revision_ids)
    resolver_latency = time.perf_counter() - resolver_start

    corpus_snapshot_hash = _corpus_registry_snapshot_hash(resolutions)
    failed_closed = bool(integrity_errors)

    aware_latency = 0.0
    unfiltered_latency = 0.0
    hits: list[CrossDocumentRetrievalHit] = []
    unfiltered_hits: list[CrossDocumentRetrievalHit] = []
    # When any document fails closed, the vector store is NEVER queried --
    # the shared corpus cannot be trusted, so there is nothing to rank or
    # to compare against.
    if not failed_closed:
        aware_start = time.perf_counter()
        search_hits = store.search_eligible(
            embedding_model=embedding_model, query_vector=query_vector,
            eligible_revision_ids=eligible_union, top_k=top_k,
        )
        aware_latency = time.perf_counter() - aware_start
        hits = [_hit_from_search(h, rank, merged_labels.get(h.record.document_revision_id)) for rank, h in enumerate(search_hits, start=1)]

        unfiltered_start = time.perf_counter()
        unfiltered_search_hits = store.search_unfiltered(embedding_model=embedding_model, query_vector=query_vector, top_k=top_k)
        unfiltered_latency = time.perf_counter() - unfiltered_start
        unfiltered_hits = [_hit_from_search(h, rank, merged_labels.get(h.record.document_revision_id)) for rank, h in enumerate(unfiltered_search_hits, start=1)]

    return CrossDocumentSearchResult(
        query_intent=query_intent,
        as_of_date=as_of_date,
        requested_revision_ids_by_document=requested_revision_ids_by_document,
        per_document_resolutions=resolutions,
        eligible_revision_ids_union=sorted(set(eligible_union)),
        corpus_registry_snapshot_hash=corpus_snapshot_hash,
        failed_closed=failed_closed,
        integrity_errors=integrity_errors,
        resolver_latency_seconds=resolver_latency,
        authority_aware_vector_search_latency_seconds=aware_latency,
        unfiltered_vector_search_latency_seconds=unfiltered_latency,
        hits=hits,
        unfiltered_hits=unfiltered_hits,
    )
