"""Stage 7B.2: deterministic Reciprocal Rank Fusion of a Vector ranking
and a Graph/path ranking, into the frozen per-question top-K unique
chunks. One fixed global RRF constant; no per-question tuning. Hybrid is
never given a larger final budget than Vector or Graph.
"""

from __future__ import annotations

from ingestion_bench.hybrid_retrieval_benchmark.model import FusedChunk, RankedChunk
from ingestion_bench.revision_authority.resolver import RevisionAuthorityLabel
from ingestion_bench.revision_search_benchmark.store import RevisionVectorRecord


def rrf_fuse(
    *,
    vector_ranked: list[RankedChunk],
    graph_ranked: list[RankedChunk],
    rrf_constant: int,
    top_k: int,
    chunk_evidence: dict[str, RevisionVectorRecord],
    authority_labels: dict[str, RevisionAuthorityLabel],
    graph_chunk_support: dict[str, tuple[list[str], list[str], list[str]]],
) -> list[FusedChunk]:
    vector_by_id = {r.chunk_id: r for r in vector_ranked}
    graph_by_id = {r.chunk_id: r for r in graph_ranked}

    scores: dict[str, float] = {}
    v_contrib: dict[str, float] = {}
    g_contrib: dict[str, float] = {}
    for r in vector_ranked:
        c = 1.0 / (rrf_constant + r.rank)
        scores[r.chunk_id] = scores.get(r.chunk_id, 0.0) + c
        v_contrib[r.chunk_id] = c
    for r in graph_ranked:
        c = 1.0 / (rrf_constant + r.rank)
        scores[r.chunk_id] = scores.get(r.chunk_id, 0.0) + c
        g_contrib[r.chunk_id] = c

    ordered = sorted(scores, key=lambda cid: (-scores[cid], cid))[:top_k]

    fused: list[FusedChunk] = []
    for final_rank, cid in enumerate(ordered, start=1):
        v = vector_by_id.get(cid)
        g = graph_by_id.get(cid)
        contributed_by = "both" if (v and g) else ("vector_only" if v else "graph_only")
        edge_ids, path_ids, seed_sources = graph_chunk_support.get(cid, ([], [], []))
        rec = chunk_evidence.get(cid)
        fused.append(FusedChunk(
            chunk_id=cid, final_rank=final_rank, rrf_score=scores[cid],
            vector_rank=v.rank if v else None, vector_score=v.score if v else None,
            graph_rank=g.rank if g else None, graph_score=g.score if g else None,
            vector_rrf_contribution=v_contrib.get(cid, 0.0), graph_rrf_contribution=g_contrib.get(cid, 0.0),
            contributed_by=contributed_by, seed_sources=seed_sources, supporting_path_ids=path_ids,
            supporting_edge_assertion_ids=edge_ids,
            logical_document_id=rec.logical_document_id if rec else "", document_revision_id=rec.document_revision_id if rec else "",
            version_label=rec.version_label if rec else None, revision_number=rec.revision_number if rec else None,
            source_relative_path=rec.source_relative_path if rec else "", source_document_sha256=rec.source_document_sha256 if rec else "",
            content_sha256=rec.content_sha256 if rec else "", retrieval_text=rec.retrieval_text if rec else "",
            chunk_type=rec.chunk_type if rec else "text", unit_indices=list(rec.unit_indices) if rec else [],
            heading_path=list(rec.heading_path) if rec else [], source_element_ids=list(rec.source_element_ids) if rec else [],
            source_refs=list(rec.source_refs) if rec else [], authority_label=authority_labels.get(rec.document_revision_id) if rec else None,
        ))
    return fused
