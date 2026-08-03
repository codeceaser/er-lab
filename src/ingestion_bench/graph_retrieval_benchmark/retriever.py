"""Stage 7B.1: the authority-aware graph retriever.

For every query:
    1. resolves EACH corpus logical document independently through the
       frozen Stage 7R resolver (identical to the Stage 7B.0 Vector
       retriever's authority scoping);
    2. fails closed on any document-level integrity error;
    3. unions the eligible document_revision_ids;
    4. loads ONLY edge assertions supported by an eligible revision
       (authority filtering BEFORE traversal -- a historical/draft-only
       assertion never enters a current traversal and gets discarded
       afterward; it is never loaded at all);
    5. seeds from graph nodes matched to the query by exact-identifier and
       normalized-alias matching (NEVER the expected chain);
    6. traverses the eligible subgraph both directions (preserving each
       edge's source->target direction) up to ONE fixed global hop limit
       (<= 5);
    7. ranks candidate SUPPORTING CHUNKS by (shortest graph distance from
       a seed, then supporting-chunk cosine similarity to the query using
       the same embedding model, then stable chunk-id tie-break) and
       returns at most the frozen per-question top-K UNIQUE chunks.

Graph paths are explanatory metadata. Only source chunks count as
retrieved evidence -- no bare edge is evidence. If no seed entity is
found, the result is an explicit `no_seed_entity` outcome; it NEVER
consults evaluation truth or a precomputed path.

The retriever NEVER reads required_fact_ids / forbidden_fact_ids /
expected_relationship_chain -- only query text/vector, intent, as_of,
requested revisions, and top-K.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import deque
from datetime import date

from pydantic import BaseModel, ConfigDict

from ingestion_bench.cross_document_benchmark.retriever import PerDocumentResolution
from ingestion_bench.graph_retrieval_benchmark.builder import GraphProjection
from ingestion_bench.graph_retrieval_benchmark.model import GraphEdgeAssertion, GraphNode, normalize_entity_name
from ingestion_bench.graph_retrieval_benchmark.store import GraphStore
from ingestion_bench.revision_authority.resolver import RevisionAuthorityLabel
from ingestion_bench.revision_authority.service import RevisionAuthorityService
from ingestion_bench.revision_search_benchmark.store import RevisionVectorRecord, cosine_similarity

# Node entity_types that are too generic to seed a traversal (a status
# object like "the current operating procedure" must not be a seed).
_NON_SEEDABLE_TYPES = {"status", "other"}
_IDENTIFIER_TOKEN_RE = re.compile(r"[A-Za-z]{1,6}-\d+[A-Za-z]?")


class GraphSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matched_node_id: str
    matched_alias: str
    canonical_name: str
    entity_type: str


class TraversedEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_assertion_id: str
    subject_name: str
    predicate: str
    object_name: str
    hop_distance: int
    supporting_chunk_id: str
    logical_document_id: str
    document_revision_id: str


class GraphEvidenceHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    hop_distance: int
    similarity_score: float

    logical_document_id: str
    document_revision_id: str
    version_label: str | None
    revision_number: int | None
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

    # The edge assertions (evidence-backed) that caused this chunk to be
    # retrieved -- every one cites this same chunk. No bare edge is
    # evidence; the chunk is.
    supporting_edge_assertion_ids: list[str]


class GraphQueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_intent: str
    as_of_date: date
    requested_revision_ids_by_document: dict[str, list[str]]

    per_document_resolutions: list[PerDocumentResolution]
    eligible_revision_ids_union: list[str]
    corpus_registry_snapshot_hash: str
    failed_closed: bool
    integrity_errors: list[str]

    outcome: str  # "ok" | "no_seed_entity" | "failed_closed"
    seeds: list[GraphSeed]
    traversed_edges: list[TraversedEdge]
    hits: list[GraphEvidenceHit]

    resolver_latency_seconds: float
    traversal_latency_seconds: float
    ranking_latency_seconds: float
    total_latency_seconds: float


def _corpus_registry_snapshot_hash(resolutions: list[PerDocumentResolution]) -> str:
    payload = {r.logical_document_id: r.registry_snapshot_hash for r in resolutions if r.registry_snapshot_hash}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _resolve_corpus(
    *, service: RevisionAuthorityService, corpus_logical_document_ids: list[str], query_intent: str, as_of_date: date,
    requested_revision_ids_by_document: dict[str, list[str]],
) -> tuple[list[PerDocumentResolution], dict[str, RevisionAuthorityLabel], list[str], list[str], str, float]:
    """Identical authority scoping to the Stage 7B.0 Vector retriever:
    resolve each document via the frozen resolver, union eligible ids,
    collect integrity errors. Returns (resolutions, merged_labels,
    eligible_union, integrity_errors, corpus_snapshot_hash, latency)."""
    start = time.perf_counter()
    resolutions: list[PerDocumentResolution] = []
    merged_labels: dict[str, RevisionAuthorityLabel] = {}
    integrity_errors: list[str] = []
    eligible_union: list[str] = []
    for logical_document_id in corpus_logical_document_ids:
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
            logical_document_id=logical_document_id, query_intent=query_intent, as_of_date=as_of_date,  # type: ignore[arg-type]
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
    return resolutions, merged_labels, eligible_union, integrity_errors, _corpus_registry_snapshot_hash(resolutions), time.perf_counter() - start


def _match_seeds(query: str, nodes: list[GraphNode]) -> list[GraphSeed]:
    """Seed on nodes whose identifier token appears in the query
    (word-exact -- so 'C-88' never seeds 'C-88a') or whose normalized
    multiword alias is a substring of the normalized query. Generic
    status/other nodes are never seeds."""
    normalized_query = normalize_entity_name(query)
    query_identifier_tokens = {t.upper() for t in _IDENTIFIER_TOKEN_RE.findall(query)}
    seeds: list[GraphSeed] = []
    seen: set[str] = set()
    for node in nodes:
        if node.entity_type in _NON_SEEDABLE_TYPES:
            continue
        for alias in [node.canonical_name, *node.aliases]:
            alias_ids = {t.upper() for t in _IDENTIFIER_TOKEN_RE.findall(alias)}
            matched = False
            matched_alias = alias
            if alias_ids:
                if alias_ids & query_identifier_tokens:
                    matched = True
            else:
                norm_alias = normalize_entity_name(alias)
                if len(norm_alias) >= 4 and norm_alias in normalized_query:
                    matched = True
            if matched and node.node_id not in seen:
                seen.add(node.node_id)
                seeds.append(GraphSeed(matched_node_id=node.node_id, matched_alias=matched_alias, canonical_name=node.canonical_name, entity_type=node.entity_type))
                break
    return seeds


def _traverse(seeds: list[GraphSeed], eligible_edges: list[GraphEdgeAssertion], max_hops: int) -> tuple[dict[str, int], list[tuple[GraphEdgeAssertion, int]]]:
    """BFS over the eligible subgraph from the seed nodes, both
    directions, bounded by max_hops. Returns node distances and the list
    of (edge, hop_distance) traversed, where hop_distance is the distance
    of the edge's NEARER (already-reached) endpoint from a seed."""
    adjacency: dict[str, list[GraphEdgeAssertion]] = {}
    for edge in eligible_edges:
        adjacency.setdefault(edge.subject_node_id, []).append(edge)
        adjacency.setdefault(edge.object_node_id, []).append(edge)

    distance: dict[str, int] = {s.matched_node_id: 0 for s in seeds}
    queue: deque[str] = deque(distance)
    while queue:
        node_id = queue.popleft()
        d = distance[node_id]
        if d >= max_hops:
            continue
        for edge in adjacency.get(node_id, []):
            other = edge.object_node_id if edge.subject_node_id == node_id else edge.subject_node_id
            if other not in distance:
                distance[other] = d + 1
                queue.append(other)

    traversed: list[tuple[GraphEdgeAssertion, int]] = []
    for edge in eligible_edges:
        ds = distance.get(edge.subject_node_id)
        do = distance.get(edge.object_node_id)
        reached = [x for x in (ds, do) if x is not None]
        if reached:
            traversed.append((edge, min(reached)))
    return distance, traversed


def graph_search(
    *,
    service: RevisionAuthorityService,
    store: GraphStore,
    projection: GraphProjection,
    corpus_logical_document_ids: list[str],
    query: str,
    query_intent: str,
    as_of_date: date,
    requested_revision_ids_by_document: dict[str, list[str]],
    query_vector: list[float],
    top_k: int,
    max_hops: int,
) -> GraphQueryResult:
    resolutions, merged_labels, eligible_union, integrity_errors, snapshot_hash, resolver_latency = _resolve_corpus(
        service=service, corpus_logical_document_ids=corpus_logical_document_ids, query_intent=query_intent,
        as_of_date=as_of_date, requested_revision_ids_by_document=requested_revision_ids_by_document,
    )
    failed_closed = bool(integrity_errors)

    def _empty(outcome: str, seeds: list[GraphSeed], traversal_latency: float, ranking_latency: float) -> GraphQueryResult:
        return GraphQueryResult(
            query_intent=query_intent, as_of_date=as_of_date, requested_revision_ids_by_document=requested_revision_ids_by_document,
            per_document_resolutions=resolutions, eligible_revision_ids_union=sorted(set(eligible_union)),
            corpus_registry_snapshot_hash=snapshot_hash, failed_closed=failed_closed, integrity_errors=integrity_errors,
            outcome=outcome, seeds=seeds, traversed_edges=[], hits=[],
            resolver_latency_seconds=resolver_latency, traversal_latency_seconds=traversal_latency,
            ranking_latency_seconds=ranking_latency, total_latency_seconds=resolver_latency + traversal_latency + ranking_latency,
        )

    if failed_closed:
        return _empty("failed_closed", [], 0.0, 0.0)

    # Authority filtering BEFORE traversal: only eligible edge assertions
    # are ever loaded.
    eligible_edges = store.edge_assertions_for_revisions(sorted(set(eligible_union)))
    node_by_id = {n.node_id: n for n in projection.nodes.values()}

    seeds = _match_seeds(query, list(projection.nodes.values()))
    if not seeds:
        return _empty("no_seed_entity", [], 0.0, 0.0)

    traversal_start = time.perf_counter()
    _distance, traversed = _traverse(seeds, eligible_edges, max_hops)
    traversal_latency = time.perf_counter() - traversal_start

    ranking_start = time.perf_counter()
    # Best (smallest) hop distance and the edges backing each chunk.
    best_hop: dict[str, int] = {}
    edges_for_chunk: dict[str, list[str]] = {}
    for edge, hop in traversed:
        cid = edge.supporting_chunk_id
        best_hop[cid] = min(hop, best_hop.get(cid, hop))
        edges_for_chunk.setdefault(cid, []).append(edge.edge_assertion_id)

    def _similarity(chunk_id: str) -> float:
        record = projection.chunk_evidence.get(chunk_id)
        return cosine_similarity(query_vector, record.embedding) if record is not None else 0.0

    ranked_chunk_ids = sorted(best_hop, key=lambda cid: (best_hop[cid], -_similarity(cid), cid))[:top_k]
    ranking_latency = time.perf_counter() - ranking_start

    hits: list[GraphEvidenceHit] = []
    for rank, chunk_id in enumerate(ranked_chunk_ids, start=1):
        record: RevisionVectorRecord = projection.chunk_evidence[chunk_id]
        hits.append(GraphEvidenceHit(
            rank=rank, hop_distance=best_hop[chunk_id], similarity_score=_similarity(chunk_id),
            logical_document_id=record.logical_document_id, document_revision_id=record.document_revision_id,
            version_label=record.version_label, revision_number=record.revision_number,
            authority_label=merged_labels.get(record.document_revision_id),
            source_relative_path=record.source_relative_path, source_document_sha256=record.source_document_sha256,
            chunk_id=chunk_id, content_sha256=record.content_sha256, retrieval_text=record.retrieval_text,
            chunk_type=record.chunk_type, unit_indices=list(record.unit_indices), heading_path=list(record.heading_path),
            source_element_ids=list(record.source_element_ids), source_refs=list(record.source_refs),
            supporting_edge_assertion_ids=sorted(edges_for_chunk[chunk_id]),
        ))

    traversed_meta = [
        TraversedEdge(
            edge_assertion_id=edge.edge_assertion_id,
            subject_name=node_by_id[edge.subject_node_id].canonical_name if edge.subject_node_id in node_by_id else edge.subject_node_id,
            predicate=edge.predicate,
            object_name=node_by_id[edge.object_node_id].canonical_name if edge.object_node_id in node_by_id else edge.object_node_id,
            hop_distance=hop, supporting_chunk_id=edge.supporting_chunk_id,
            logical_document_id=edge.logical_document_id, document_revision_id=edge.document_revision_id,
        )
        for edge, hop in sorted(traversed, key=lambda pair: (pair[1], pair[0].edge_assertion_id))
    ]

    return GraphQueryResult(
        query_intent=query_intent, as_of_date=as_of_date, requested_revision_ids_by_document=requested_revision_ids_by_document,
        per_document_resolutions=resolutions, eligible_revision_ids_union=sorted(set(eligible_union)),
        corpus_registry_snapshot_hash=snapshot_hash, failed_closed=False, integrity_errors=[],
        outcome="ok", seeds=seeds, traversed_edges=traversed_meta, hits=hits,
        resolver_latency_seconds=resolver_latency, traversal_latency_seconds=traversal_latency,
        ranking_latency_seconds=ranking_latency, total_latency_seconds=resolver_latency + traversal_latency + ranking_latency,
    )
