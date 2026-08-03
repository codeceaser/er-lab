"""Stage 7B.2: three deterministic seed sources.

A. ExplicitAliasSeed   -- the frozen Stage 7B.1 exact/normalized alias
                          matching (reused unchanged).
B. VectorChunkSeed     -- an authority-aware Vector search over a fixed
                          internal candidate pool; for each candidate
                          chunk, the subject/object nodes of the eligible
                          edge assertions ALREADY supported by that chunk
                          become seeds. Never infers an entity when no
                          graph assertion links the chunk to it.
C. SemanticEdgeSeed    -- the top-N authority-eligible semantically
                          matched edge assertions; their subject/object
                          nodes become seeds.

None of these reads evaluation truth. Seeds are deduped by node_id while
ALL origins are preserved. Multiple seeds are supported.
"""

from __future__ import annotations

from ingestion_bench.graph_retrieval_benchmark.model import GraphEdgeAssertion, GraphNode
from ingestion_bench.graph_retrieval_benchmark.retriever import _match_seeds  # frozen explicit-alias matcher
from ingestion_bench.hybrid_retrieval_benchmark.edge_index import EdgeSemanticIndex
from ingestion_bench.hybrid_retrieval_benchmark.model import HybridSeed, SeedOrigin
from ingestion_bench.revision_search_benchmark.store import RevisionVectorRecord, cosine_similarity


def explicit_alias_seed_origins(query: str, nodes: list[GraphNode]) -> dict[str, tuple[GraphNode, SeedOrigin]]:
    out: dict[str, tuple[GraphNode, SeedOrigin]] = {}
    node_by_id = {n.node_id: n for n in nodes}
    for rank, seed in enumerate(_match_seeds(query, nodes), start=1):
        node = node_by_id[seed.matched_node_id]
        out[node.node_id] = (node, SeedOrigin(seed_source="explicit_alias", matched_ref=seed.matched_alias, source_rank=rank))
    return out


def _authority_aware_vector_pool(
    *, query_vector: list[float], chunk_evidence: dict[str, RevisionVectorRecord], eligible_revision_ids: list[str], pool_size: int
) -> list[tuple[str, float]]:
    """Authority-eligible chunks ranked by similarity, filtered BEFORE
    ranking. Returns (chunk_id, similarity) up to pool_size."""
    if not eligible_revision_ids:
        return []
    eligible = set(eligible_revision_ids)
    pool = [r for r in chunk_evidence.values() if r.document_revision_id in eligible]
    scored = [(r.chunk_id, cosine_similarity(query_vector, r.embedding)) for r in pool]
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return scored[:pool_size]


def vector_chunk_seed_origins(
    *, query_vector: list[float], chunk_evidence: dict[str, RevisionVectorRecord], eligible_revision_ids: list[str],
    eligible_edges: list[GraphEdgeAssertion], node_by_id: dict[str, GraphNode], top_k: int,
    vector_candidate_multiplier: int, max_vector_seed_chunks: int,
) -> dict[str, tuple[GraphNode, SeedOrigin]]:
    pool_size = min(vector_candidate_multiplier * top_k, max_vector_seed_chunks)
    ranked = _authority_aware_vector_pool(query_vector=query_vector, chunk_evidence=chunk_evidence, eligible_revision_ids=eligible_revision_ids, pool_size=pool_size)
    edges_by_chunk: dict[str, list[GraphEdgeAssertion]] = {}
    for e in eligible_edges:
        edges_by_chunk.setdefault(e.supporting_chunk_id, []).append(e)

    out: dict[str, tuple[GraphNode, SeedOrigin]] = {}
    for chunk_rank, (chunk_id, score) in enumerate(ranked, start=1):
        for edge in edges_by_chunk.get(chunk_id, []):  # NEVER infer -- only nodes an existing edge links to this chunk
            for node_id in (edge.subject_node_id, edge.object_node_id):
                node = node_by_id.get(node_id)
                if node is None or node_id in out:
                    continue
                out[node_id] = (node, SeedOrigin(seed_source="vector_chunk", matched_ref=chunk_id, source_rank=chunk_rank, semantic_score=score, supporting_revision_ids=[edge.document_revision_id]))
    return out


def semantic_edge_seed_origins(
    *, query_vector: list[float], edge_index: EdgeSemanticIndex, eligible_revision_ids: list[str],
    node_by_id: dict[str, GraphNode], semantic_edge_candidate_count: int,
) -> dict[str, tuple[GraphNode, SeedOrigin]]:
    out: dict[str, tuple[GraphNode, SeedOrigin]] = {}
    matches = edge_index.semantic_search_eligible(query_vector=query_vector, eligible_revision_ids=eligible_revision_ids, top_n=semantic_edge_candidate_count)
    for rank, (edge_rec, score) in enumerate(matches, start=1):
        for node_id in (edge_rec.subject_node_id, edge_rec.object_node_id):
            node = node_by_id.get(node_id)
            if node is None or node_id in out:
                continue
            out[node_id] = (node, SeedOrigin(seed_source="semantic_edge", matched_ref=edge_rec.edge_assertion_id, source_rank=rank, semantic_score=score, supporting_revision_ids=[edge_rec.document_revision_id]))
    return out


def collect_hybrid_seeds(
    *, use_explicit: bool, use_vector: bool, use_semantic: bool,
    query: str, query_vector: list[float], nodes: list[GraphNode], node_by_id: dict[str, GraphNode],
    chunk_evidence: dict[str, RevisionVectorRecord], eligible_revision_ids: list[str], eligible_edges: list[GraphEdgeAssertion],
    edge_index: EdgeSemanticIndex, top_k: int, vector_candidate_multiplier: int, max_vector_seed_chunks: int,
    semantic_edge_candidate_count: int,
) -> list[HybridSeed]:
    origins_by_node: dict[str, tuple[GraphNode, list[SeedOrigin]]] = {}

    def _merge(source: dict[str, tuple[GraphNode, SeedOrigin]]) -> None:
        for node_id, (node, origin) in source.items():
            if node_id not in origins_by_node:
                origins_by_node[node_id] = (node, [])
            origins_by_node[node_id][1].append(origin)

    if use_explicit:
        _merge(explicit_alias_seed_origins(query, nodes))
    if use_vector:
        _merge(vector_chunk_seed_origins(
            query_vector=query_vector, chunk_evidence=chunk_evidence, eligible_revision_ids=eligible_revision_ids,
            eligible_edges=eligible_edges, node_by_id=node_by_id, top_k=top_k,
            vector_candidate_multiplier=vector_candidate_multiplier, max_vector_seed_chunks=max_vector_seed_chunks,
        ))
    if use_semantic:
        _merge(semantic_edge_seed_origins(
            query_vector=query_vector, edge_index=edge_index, eligible_revision_ids=eligible_revision_ids,
            node_by_id=node_by_id, semantic_edge_candidate_count=semantic_edge_candidate_count,
        ))

    return [
        HybridSeed(node_id=node_id, canonical_name=node.canonical_name, entity_type=node.entity_type, origins=origins)
        for node_id, (node, origins) in sorted(origins_by_node.items())
    ]
