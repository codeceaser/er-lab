"""Stage 7B.2: authority-eligible graph traversal and path ranking.

Two Graph-side evidence producers, both traversing ONLY the
authority-eligible edge assertions and supporting multiple seeds:

- `hop_ranked_graph_evidence` (used by H1): BFS from the seeds, rank the
  supporting chunks by (hop distance, supporting-chunk similarity,
  chunk_id) -- the Stage 7B.1-style hop-first ranking, but from expanded
  seeds.

- `semantic_path_ranked_graph_evidence` (used by H2): enumerate bounded
  SIMPLE paths (no repeated node, <= max_hops edges, capped at a fixed
  global candidate limit), derive each path's representation from its
  OWN existing edges only ("subject predicate object\n..."), embed it,
  and rank paths by query<->path cosine similarity (NOT hop distance),
  then shorter path, then stable path id. Chunks are collected in
  path-rank order.

Only original source chunks count as retrieved evidence. No inferred or
repaired edge is ever added. Evaluation truth is never read.
"""

from __future__ import annotations

import hashlib
import time
from collections import deque
from dataclasses import dataclass, field

from ingestion_bench.graph_retrieval_benchmark.model import GraphEdgeAssertion, GraphNode
from ingestion_bench.hybrid_retrieval_benchmark.model import HybridSeed, PathCandidate, RankedChunk
from ingestion_bench.retrieval_baseline.embeddings import EmbeddingProvider
from ingestion_bench.revision_search_benchmark.store import RevisionVectorRecord, cosine_similarity


@dataclass
class GraphSideResult:
    ranked_chunks: list[RankedChunk]
    traversed_edge_ids: list[str]
    paths: list[PathCandidate]
    # chunk_id -> (supporting edge ids, supporting path ids, seed sources)
    chunk_support: dict[str, tuple[list[str], list[str], list[str]]]
    candidate_path_count: int
    embedding_calls: int
    latency_seconds: float


def _adjacency(eligible_edges: list[GraphEdgeAssertion]) -> dict[str, list[GraphEdgeAssertion]]:
    adj: dict[str, list[GraphEdgeAssertion]] = {}
    for edge in eligible_edges:
        adj.setdefault(edge.subject_node_id, []).append(edge)
        adj.setdefault(edge.object_node_id, []).append(edge)
    return adj


def _seed_sources_for_nodes(node_ids: set[str], seeds: list[HybridSeed]) -> list[str]:
    sources: set[str] = set()
    by_id = {s.node_id: s for s in seeds}
    for nid in node_ids:
        seed = by_id.get(nid)
        if seed:
            sources.update(o.seed_source for o in seed.origins)
    return sorted(sources)


def hop_ranked_graph_evidence(
    *, seeds: list[HybridSeed], eligible_edges: list[GraphEdgeAssertion], chunk_evidence: dict[str, RevisionVectorRecord],
    query_vector: list[float], max_hops: int,
) -> GraphSideResult:
    start = time.perf_counter()
    adj = _adjacency(eligible_edges)
    distance: dict[str, int] = {s.node_id: 0 for s in seeds}
    queue: deque[str] = deque(distance)
    while queue:
        node_id = queue.popleft()
        d = distance[node_id]
        if d >= max_hops:
            continue
        for edge in adj.get(node_id, []):
            other = edge.object_node_id if edge.subject_node_id == node_id else edge.subject_node_id
            if other not in distance:
                distance[other] = d + 1
                queue.append(other)

    best_hop: dict[str, int] = {}
    edges_for_chunk: dict[str, list[str]] = {}
    endpoints_for_chunk: dict[str, set[str]] = {}
    traversed: list[str] = []
    for edge in eligible_edges:
        ds = distance.get(edge.subject_node_id)
        do = distance.get(edge.object_node_id)
        reached = [x for x in (ds, do) if x is not None]
        if not reached:
            continue
        traversed.append(edge.edge_assertion_id)
        cid = edge.supporting_chunk_id
        best_hop[cid] = min(min(reached), best_hop.get(cid, min(reached)))
        edges_for_chunk.setdefault(cid, []).append(edge.edge_assertion_id)
        endpoints_for_chunk.setdefault(cid, set()).update({edge.subject_node_id, edge.object_node_id})

    def _sim(cid: str) -> float:
        rec = chunk_evidence.get(cid)
        return cosine_similarity(query_vector, rec.embedding) if rec else 0.0

    ranked_ids = sorted(best_hop, key=lambda cid: (best_hop[cid], -_sim(cid), cid))
    ranked = [RankedChunk(chunk_id=cid, rank=i, score=_sim(cid)) for i, cid in enumerate(ranked_ids, start=1)]
    chunk_support = {
        cid: (sorted(edges_for_chunk[cid]), [], _seed_sources_for_nodes(endpoints_for_chunk[cid], seeds))
        for cid in ranked_ids
    }
    return GraphSideResult(ranked_chunks=ranked, traversed_edge_ids=sorted(set(traversed)), paths=[], chunk_support=chunk_support, candidate_path_count=0, embedding_calls=0, latency_seconds=time.perf_counter() - start)


def _enumerate_simple_paths(seeds: list[HybridSeed], adj: dict[str, list[GraphEdgeAssertion]], max_hops: int, max_paths: int) -> list[tuple[list[str], list[GraphEdgeAssertion]]]:
    """Bounded simple-path enumeration (no repeated node, <= max_hops
    edges), deterministic (edges expanded in edge_assertion_id order),
    capped at max_paths. Returns (node_path, edge_path) pairs -- the node
    path is tracked during traversal (never reconstructed from edges), so
    it is always a genuine simple chain in traversal order."""
    paths: list[tuple[list[str], list[GraphEdgeAssertion]]] = []
    seed_ids = sorted({s.node_id for s in seeds})

    def dfs(current: str, node_path: list[str], edges: list[GraphEdgeAssertion]) -> None:
        if edges:
            paths.append((list(node_path), list(edges)))
            if len(paths) >= max_paths:
                return
        if len(edges) >= max_hops:
            return
        for edge in sorted(adj.get(current, []), key=lambda e: e.edge_assertion_id):
            other = edge.object_node_id if edge.subject_node_id == current else edge.subject_node_id
            if other in node_path:
                continue
            node_path.append(other)
            edges.append(edge)
            dfs(other, node_path, edges)
            edges.pop()
            node_path.pop()
            if len(paths) >= max_paths:
                return

    for seed_id in seed_ids:
        if len(paths) >= max_paths:
            break
        dfs(seed_id, [seed_id], [])
    return paths[:max_paths]


def _path_representation(edges: list[GraphEdgeAssertion], node_by_id: dict[str, GraphNode]) -> str:
    lines = []
    for e in edges:
        subj = node_by_id[e.subject_node_id].canonical_name if e.subject_node_id in node_by_id else e.subject_node_id
        obj = node_by_id[e.object_node_id].canonical_name if e.object_node_id in node_by_id else e.object_node_id
        lines.append(f"{subj} {e.predicate} {obj}")
    return "\n".join(lines)


def _path_id(edges: list[GraphEdgeAssertion]) -> str:
    return "path_" + hashlib.sha256("|".join(e.edge_assertion_id for e in edges).encode("utf-8")).hexdigest()[:16]


def semantic_path_ranked_graph_evidence(
    *, seeds: list[HybridSeed], eligible_edges: list[GraphEdgeAssertion], node_by_id: dict[str, GraphNode],
    chunk_evidence: dict[str, RevisionVectorRecord], query_vector: list[float], embedding_provider: EmbeddingProvider,
    max_hops: int, max_candidate_paths: int,
) -> GraphSideResult:
    start = time.perf_counter()
    adj = _adjacency(eligible_edges)
    edge_paths = _enumerate_simple_paths(seeds, adj, max_hops, max_candidate_paths)

    reprs = [_path_representation(ep, node_by_id) for _np, ep in edge_paths]
    embeddings = embedding_provider.embed(reprs).vectors if reprs else []
    candidates: list[PathCandidate] = []
    for (node_seq, ep), representation, emb in zip(edge_paths, reprs, embeddings):
        candidates.append(PathCandidate(
            path_id=_path_id(ep), node_ids=list(node_seq), edge_assertion_ids=[e.edge_assertion_id for e in ep],
            representation=representation, hop_length=len(ep), semantic_score=cosine_similarity(query_vector, emb),
            supporting_chunk_ids=list(dict.fromkeys(e.supporting_chunk_id for e in ep)),
        ))
    # Rank paths by semantic similarity (NOT hop distance), then shorter, then id.
    candidates.sort(key=lambda p: (-p.semantic_score, p.hop_length, p.path_id))

    edge_by_id = {e.edge_assertion_id: e for e in eligible_edges}
    seen_chunks: dict[str, int] = {}
    chunk_support: dict[str, tuple[list[str], list[str], list[str]]] = {}
    ranked: list[RankedChunk] = []
    for path in candidates:
        for cid in path.supporting_chunk_ids:
            if cid not in seen_chunks:
                seen_chunks[cid] = len(ranked) + 1
                ranked.append(RankedChunk(chunk_id=cid, rank=len(ranked) + 1, score=path.semantic_score))
                endpoints = set()
                edge_ids = []
                for eid in path.edge_assertion_ids:
                    e = edge_by_id.get(eid)
                    if e and e.supporting_chunk_id == cid:
                        edge_ids.append(eid)
                        endpoints.update({e.subject_node_id, e.object_node_id})
                chunk_support[cid] = (sorted(set(edge_ids)), [path.path_id], _seed_sources_for_nodes(endpoints, seeds))
            else:
                edge_ids, path_ids, sources = chunk_support[cid]
                if path.path_id not in path_ids:
                    path_ids.append(path.path_id)

    traversed = sorted({eid for p in candidates for eid in p.edge_assertion_ids})
    return GraphSideResult(
        ranked_chunks=ranked, traversed_edge_ids=traversed, paths=candidates, chunk_support=chunk_support,
        candidate_path_count=len(candidates), embedding_calls=1 if reprs else 0, latency_seconds=time.perf_counter() - start,
    )
