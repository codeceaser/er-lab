"""Stage 7B.2 / 7B.2a: deterministic seed sources with a supplemental-seed
cap to prevent graph saturation.

- ExplicitAliasSeed  -- frozen Stage 7B.1 exact/normalized alias matching.
  ALWAYS retained (never capped).
- VectorChunkSeed    -- authority-aware Vector search over a fixed
  candidate pool (eligibility filtered before ranking); the subject/object
  nodes of the eligible edges already supported by each candidate chunk.
- SemanticEdgeSeed   -- the top-N authority-eligible semantically matched
  edges; their subject/object nodes.

Vector-chunk and semantic-edge seeds are SUPPLEMENTAL: their candidate
nodes are ranked deterministically by RRF over their Vector-chunk source
rank and semantic-edge source rank, deduped by node id (all origins
preserved), and only the global top `max_supplemental_seed_nodes` are
kept. None of this reads evaluation truth. Multiple seeds are supported.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ingestion_bench.graph_retrieval_benchmark.model import GraphEdgeAssertion, GraphNode
from ingestion_bench.graph_retrieval_benchmark.retriever import _match_seeds  # frozen explicit-alias matcher
from ingestion_bench.hybrid_retrieval_benchmark.edge_index import EdgeSemanticIndex
from ingestion_bench.hybrid_retrieval_benchmark.model import HybridSeed, SeedOrigin
from ingestion_bench.hybrid_retrieval_benchmark.vector_candidate_store import VectorCandidateStore


@dataclass
class SeedResult:
    seeds: list[HybridSeed]
    eligible_graph_node_count: int
    supplemental_seed_candidate_count: int
    selected_supplemental_seed_count: int
    explicit_seed_count: int
    total_seed_count: int
    seed_saturation_ratio: float
    seed_saturation_ok: bool
    eligible_semantic_edge_hits: int
    vector_candidate_store_latency_seconds: float
    semantic_edge_store_latency_seconds: float


def collect_hybrid_seeds(
    *,
    query: str,
    query_vector: list[float],
    nodes: list[GraphNode],
    node_by_id: dict[str, GraphNode],
    eligible_revision_ids: list[str],
    eligible_edges: list[GraphEdgeAssertion],
    vector_candidate_store: VectorCandidateStore,
    edge_index: EdgeSemanticIndex,
    top_k: int,
    vector_candidate_multiplier: int,
    max_vector_seed_chunks: int,
    semantic_edge_candidate_count: int,
    max_supplemental_seed_nodes: int,
    supplemental_seed_saturation_threshold: float,
    rrf_constant: int,
) -> SeedResult:
    eligible_graph_node_ids = {nid for e in eligible_edges for nid in (e.subject_node_id, e.object_node_id)}

    # --- explicit-alias seeds (always retained) ---
    explicit: dict[str, SeedOrigin] = {}
    for rank, seed in enumerate(_match_seeds(query, nodes), start=1):
        explicit[seed.matched_node_id] = SeedOrigin(seed_source="explicit_alias", matched_ref=seed.matched_alias, source_rank=rank)

    # --- Vector-chunk supplemental candidates ---
    pool_size = min(vector_candidate_multiplier * top_k, max_vector_seed_chunks)
    _vc_start = time.perf_counter()
    vector_pool = vector_candidate_store.search_eligible(query_vector=query_vector, eligible_revision_ids=eligible_revision_ids, pool_size=pool_size)
    vector_candidate_store_latency = time.perf_counter() - _vc_start
    edges_by_chunk: dict[str, list[GraphEdgeAssertion]] = {}
    for e in eligible_edges:
        edges_by_chunk.setdefault(e.supporting_chunk_id, []).append(e)
    vector_origin: dict[str, SeedOrigin] = {}
    vector_rank: dict[str, int] = {}
    for chunk_rank, (chunk_id, score) in enumerate(vector_pool, start=1):
        for edge in edges_by_chunk.get(chunk_id, []):  # NEVER infer -- only nodes an existing edge links to this chunk
            for node_id in (edge.subject_node_id, edge.object_node_id):
                if node_id not in node_by_id or node_id in vector_origin:
                    continue
                vector_origin[node_id] = SeedOrigin(seed_source="vector_chunk", matched_ref=chunk_id, source_rank=chunk_rank, semantic_score=score, supporting_revision_ids=[edge.document_revision_id])
                vector_rank[node_id] = chunk_rank

    # --- semantic-edge supplemental candidates ---
    _se_start = time.perf_counter()
    edge_matches = edge_index.semantic_search_eligible(query_vector=query_vector, eligible_revision_ids=eligible_revision_ids, top_n=semantic_edge_candidate_count)
    semantic_edge_store_latency = time.perf_counter() - _se_start
    semantic_origin: dict[str, SeedOrigin] = {}
    semantic_rank: dict[str, int] = {}
    for rank, (edge_rec, score) in enumerate(edge_matches, start=1):
        for node_id in (edge_rec.subject_node_id, edge_rec.object_node_id):
            if node_id not in node_by_id or node_id in semantic_origin:
                continue
            semantic_origin[node_id] = SeedOrigin(seed_source="semantic_edge", matched_ref=edge_rec.edge_assertion_id, source_rank=rank, semantic_score=score, supporting_revision_ids=[edge_rec.document_revision_id])
            semantic_rank[node_id] = rank

    # --- RRF-rank supplemental candidates (excluding explicit nodes), cap ---
    supplemental_candidate_ids = (set(vector_origin) | set(semantic_origin)) - set(explicit)

    def _rrf(node_id: str) -> float:
        s = 0.0
        if node_id in vector_rank:
            s += 1.0 / (rrf_constant + vector_rank[node_id])
        if node_id in semantic_rank:
            s += 1.0 / (rrf_constant + semantic_rank[node_id])
        return s

    ranked_supplemental = sorted(supplemental_candidate_ids, key=lambda nid: (-_rrf(nid), nid))
    selected_supplemental = ranked_supplemental[:max_supplemental_seed_nodes]

    # --- assemble seeds (all origins preserved) ---
    def _origins(node_id: str) -> list[SeedOrigin]:
        out: list[SeedOrigin] = []
        if node_id in explicit:
            out.append(explicit[node_id])
        if node_id in vector_origin:
            out.append(vector_origin[node_id])
        if node_id in semantic_origin:
            out.append(semantic_origin[node_id])
        return out

    final_node_ids = sorted(set(explicit) | set(selected_supplemental))
    seeds = [HybridSeed(node_id=nid, canonical_name=node_by_id[nid].canonical_name, entity_type=node_by_id[nid].entity_type, origins=_origins(nid)) for nid in final_node_ids]

    eligible_node_count = len(eligible_graph_node_ids)
    ratio = (len(selected_supplemental) / eligible_node_count) if eligible_node_count else 0.0
    # Saturation guard: only enforced when the eligible graph has > 4 nodes.
    saturation_ok = eligible_node_count <= 4 or ratio <= supplemental_seed_saturation_threshold

    return SeedResult(
        seeds=seeds, eligible_graph_node_count=eligible_node_count,
        supplemental_seed_candidate_count=len(supplemental_candidate_ids), selected_supplemental_seed_count=len(selected_supplemental),
        explicit_seed_count=len(explicit), total_seed_count=len(seeds), seed_saturation_ratio=ratio,
        seed_saturation_ok=saturation_ok, eligible_semantic_edge_hits=len(edge_matches),
        vector_candidate_store_latency_seconds=vector_candidate_store_latency,
        semantic_edge_store_latency_seconds=semantic_edge_store_latency,
    )
