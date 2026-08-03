"""Stage 7B.1: graph-build accuracy evaluation and Vector-vs-Graph
comparison.

Graph CONSTRUCTION never reads evaluation truth. This evaluator runs
AFTER construction and is the only place the Stage 7B.0 fact contract is
read. It NEVER silently repairs an extracted edge using benchmark truth
-- it only measures.

Crucially, per-question Graph metrics are computed by the FROZEN Stage
7B.0 `_evaluate_question` function over the SAME `build_evidence_alignment`
fact->chunk mapping -- so Vector and Graph are scored by literally the
same code and the same fact alignment. The graph hits are adapted into
the Stage 7B.0 result shape purely to feed that shared scorer.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict

# Read-only reuse of the FROZEN Stage 7B.0 scorer + fact alignment.
from ingestion_bench.cross_document_benchmark.benchmark_runner import FactEvidence, _evaluate_question
from ingestion_bench.cross_document_benchmark.retriever import CrossDocumentRetrievalHit, CrossDocumentSearchResult
from ingestion_bench.graph_retrieval_benchmark.builder import GraphProjection
from ingestion_bench.graph_retrieval_benchmark.model import identifiers_in, normalize_entity_name
from ingestion_bench.graph_retrieval_benchmark.retriever import GraphQueryResult


# --- graph build accuracy ---------------------------------------------------


class GraphBuildEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_count: int
    edge_assertion_count: int
    evidence_count: int

    expected_fact_count: int
    covered_expected_fact_count: int
    expected_fact_edge_recall: float
    missing_expected_fact_ids: list[str]

    extracted_edge_precision: float
    unsupported_extracted_edge_count: int
    unsupported_extracted_edges: list[str]

    duplicate_assertion_count: int
    provenance_complete_edge_count: int
    provenance_completeness: float
    edges_with_invalid_or_missing_supporting_chunk: int

    entity_normalization_collision_count: int
    entity_normalization_collisions: list[str]

    rejected_relationship_count: int


def _entity_matches(fact_side: str, node_canonical: str) -> bool:
    fact_ids = identifiers_in(fact_side)
    node_ids = identifiers_in(node_canonical)
    if fact_ids:
        return fact_ids <= node_ids
    return normalize_entity_name(fact_side) == normalize_entity_name(node_canonical)


def evaluate_graph_build(
    projection: GraphProjection, contract: dict[str, Any], evidence: dict[str, FactEvidence], valid_chunk_ids: set[str]
) -> GraphBuildEvaluation:
    nodes = projection.nodes
    edges = projection.edge_assertions

    # Expected-fact edge recall: an expected fact is covered iff some edge
    # is backed by the fact's supporting chunk AND its subject/object
    # correspond to the fact's subject/object.
    covered: set[str] = set()
    edge_matches_a_fact: dict[str, bool] = {e.edge_assertion_id: False for e in edges}
    for fact in contract["facts"]:
        fid = fact["fact_id"]
        chunk_id = evidence[fid].supporting_chunk_id
        for e in edges:
            if e.supporting_chunk_id != chunk_id:
                continue
            subj = nodes[e.subject_node_id].canonical_name if e.subject_node_id in nodes else ""
            obj = nodes[e.object_node_id].canonical_name if e.object_node_id in nodes else ""
            if _entity_matches(fact["subject"], subj) and _entity_matches(fact["object"], obj):
                covered.add(fid)
                edge_matches_a_fact[e.edge_assertion_id] = True
    missing = sorted({f["fact_id"] for f in contract["facts"]} - covered)

    unsupported = [e.edge_assertion_id for e in edges if not edge_matches_a_fact[e.edge_assertion_id]]
    precision = (len(edges) - len(unsupported)) / len(edges) if edges else 1.0

    provenance_complete = sum(
        1 for e in edges
        if len(e.supporting_content_sha256) == 64 and len(e.source_document_sha256) == 64
        and e.source_relative_path and e.source_refs
    )
    invalid_chunk_edges = sum(1 for e in edges if e.supporting_chunk_id not in valid_chunk_ids)

    # Entity normalization collisions: a node whose merged surface forms
    # carry MORE THAN ONE distinct enterprise identifier (e.g. C-88 and
    # C-88a wrongly merged).
    collisions: list[str] = []
    for node in nodes.values():
        ids = set()
        for name in [node.canonical_name, *node.aliases]:
            ids |= identifiers_in(name)
        if len(ids) > 1:
            collisions.append(f"{node.node_id}: {sorted(ids)}")

    return GraphBuildEvaluation(
        node_count=len(nodes), edge_assertion_count=len(edges), evidence_count=len({e.supporting_chunk_id for e in edges}),
        expected_fact_count=len(contract["facts"]), covered_expected_fact_count=len(covered),
        expected_fact_edge_recall=len(covered) / len(contract["facts"]) if contract["facts"] else 1.0,
        missing_expected_fact_ids=missing,
        extracted_edge_precision=precision, unsupported_extracted_edge_count=len(unsupported), unsupported_extracted_edges=unsupported,
        duplicate_assertion_count=projection.duplicate_assertion_count,
        provenance_complete_edge_count=provenance_complete,
        provenance_completeness=provenance_complete / len(edges) if edges else 1.0,
        edges_with_invalid_or_missing_supporting_chunk=invalid_chunk_edges,
        entity_normalization_collision_count=len(collisions), entity_normalization_collisions=collisions,
        rejected_relationship_count=projection.rejected_relationship_count,
    )


# --- per-question Graph metrics via the FROZEN Stage 7B.0 scorer ------------


def _graph_result_to_cross_document_result(graph_result: GraphQueryResult) -> CrossDocumentSearchResult:
    """Adapt a GraphQueryResult into the Stage 7B.0 result shape so the
    FROZEN `_evaluate_question` scores Graph exactly as it scored Vector.
    unfiltered_hits is empty (Graph has no unfiltered baseline); the
    graph's traversal+ranking time stands in for the authority-aware
    search latency."""
    hits = [
        CrossDocumentRetrievalHit(
            rank=h.rank, similarity_score=h.similarity_score, logical_document_id=h.logical_document_id,
            document_revision_id=h.document_revision_id, version_label=h.version_label, revision_number=h.revision_number,
            authority_label=h.authority_label, source_relative_path=h.source_relative_path,
            source_document_sha256=h.source_document_sha256, chunk_id=h.chunk_id, content_sha256=h.content_sha256,
            retrieval_text=h.retrieval_text, chunk_type=h.chunk_type, unit_indices=h.unit_indices,
            heading_path=h.heading_path, source_element_ids=h.source_element_ids, source_refs=h.source_refs,
        )
        for h in graph_result.hits
    ]
    return CrossDocumentSearchResult(
        query_intent=graph_result.query_intent, as_of_date=graph_result.as_of_date,
        requested_revision_ids_by_document=graph_result.requested_revision_ids_by_document,
        per_document_resolutions=graph_result.per_document_resolutions,
        eligible_revision_ids_union=graph_result.eligible_revision_ids_union,
        corpus_registry_snapshot_hash=graph_result.corpus_registry_snapshot_hash,
        failed_closed=graph_result.failed_closed, integrity_errors=graph_result.integrity_errors,
        resolver_latency_seconds=graph_result.resolver_latency_seconds,
        authority_aware_vector_search_latency_seconds=graph_result.traversal_latency_seconds + graph_result.ranking_latency_seconds,
        unfiltered_vector_search_latency_seconds=0.0, hits=hits, unfiltered_hits=[],
    )


class GraphQuestionMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    question_type: str
    query_intent: str
    top_k: int

    required_fact_coverage_at_k: float
    all_required_facts_retrieved_at_k: bool
    complete_chain_represented: bool
    mrr: float
    ndcg_at_k: float
    authority_leakage_count: int
    forbidden_fact_hit_ids: list[str]
    evidence_document_diversity: int
    graph_outcome: str
    authority_correct: bool
    failure_reasons: list[str]

    graph_hit_chunk_ids: list[str]
    graph_hit_documents: list[str]
    seed_entities: list[str]
    total_latency_seconds: float

    # Full graph query result (seeds, paths, edges, provenance) for audit.
    graph_result: GraphQueryResult


def evaluate_graph_question(
    question: dict[str, Any], graph_result: GraphQueryResult, evidence: dict[str, FactEvidence], id_to_symbol: dict[str, str]
) -> GraphQuestionMetrics:
    synthetic = _graph_result_to_cross_document_result(graph_result)
    scored = _evaluate_question(question, synthetic, evidence, id_to_symbol)  # FROZEN Stage 7B.0 scorer
    return GraphQuestionMetrics(
        question_id=scored.question_id, question_type=scored.question_type, query_intent=scored.query_intent, top_k=scored.top_k,
        required_fact_coverage_at_k=scored.required_fact_coverage_at_k,
        all_required_facts_retrieved_at_k=scored.all_required_facts_retrieved_at_k,
        complete_chain_represented=scored.complete_chain_represented, mrr=scored.mrr, ndcg_at_k=scored.ndcg_at_k,
        authority_leakage_count=scored.authority_leakage_count, forbidden_fact_hit_ids=scored.forbidden_fact_hit_ids,
        evidence_document_diversity=scored.evidence_document_diversity, graph_outcome=scored.vector_outcome,
        authority_correct=scored.authority_correct, failure_reasons=scored.failure_reasons,
        graph_hit_chunk_ids=scored.authority_aware_hit_chunk_ids, graph_hit_documents=scored.authority_aware_hit_documents,
        seed_entities=[s.canonical_name for s in graph_result.seeds], total_latency_seconds=graph_result.total_latency_seconds,
        graph_result=graph_result,
    )


# --- Vector-vs-Graph comparison --------------------------------------------


class QuestionComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    question_type: str
    query_intent: str
    top_k: int

    vector_coverage_at_k: float
    graph_coverage_at_k: float
    coverage_delta: float

    vector_all_required: bool
    graph_all_required: bool
    vector_complete_chain: bool
    graph_complete_chain: bool

    vector_mrr: float
    graph_mrr: float
    vector_ndcg_at_k: float
    graph_ndcg_at_k: float

    vector_evidence_document_diversity: int
    graph_evidence_document_diversity: int
    vector_authority_leakage_count: int
    graph_authority_leakage_count: int

    vector_total_latency_seconds: float
    graph_total_latency_seconds: float

    outcome_change: str  # "improved" | "unchanged" | "regressed"


def compare_vector_and_graph(
    vector_results: dict[str, Any], graph_metrics: list[GraphQuestionMetrics]
) -> list[QuestionComparison]:
    vector_by_id = {q["question_id"]: q for q in vector_results["question_results"]}
    comparisons: list[QuestionComparison] = []
    for g in graph_metrics:
        v = vector_by_id[g.question_id]
        v_cov = v["required_fact_coverage_at_k"]
        if g.required_fact_coverage_at_k > v_cov + 1e-9:
            change = "improved"
        elif g.required_fact_coverage_at_k < v_cov - 1e-9:
            change = "regressed"
        else:
            change = "unchanged"
        comparisons.append(QuestionComparison(
            question_id=g.question_id, question_type=g.question_type, query_intent=g.query_intent, top_k=g.top_k,
            vector_coverage_at_k=v_cov, graph_coverage_at_k=g.required_fact_coverage_at_k,
            coverage_delta=g.required_fact_coverage_at_k - v_cov,
            vector_all_required=v["all_required_facts_retrieved_at_k"], graph_all_required=g.all_required_facts_retrieved_at_k,
            vector_complete_chain=v["complete_chain_represented"], graph_complete_chain=g.complete_chain_represented,
            vector_mrr=v["mrr"], graph_mrr=g.mrr, vector_ndcg_at_k=v["ndcg_at_k"], graph_ndcg_at_k=g.ndcg_at_k,
            vector_evidence_document_diversity=v["evidence_document_diversity"], graph_evidence_document_diversity=g.evidence_document_diversity,
            vector_authority_leakage_count=v["authority_leakage_count"], graph_authority_leakage_count=g.authority_leakage_count,
            vector_total_latency_seconds=v["total_latency_seconds"], graph_total_latency_seconds=g.total_latency_seconds,
            outcome_change=change,
        ))
    return comparisons
