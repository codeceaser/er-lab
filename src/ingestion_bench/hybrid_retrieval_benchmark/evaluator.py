"""Stage 7B.2: scoring (via the FROZEN Stage 7B.0 scorer) and the
deterministic decision gates.

Every mode (V/G/H0/H1/H2), for both graph conditions, is scored by the
SAME frozen Stage 7B.0 `_evaluate_question` over the SAME
`build_evidence_alignment` -- no reimplemented or modified scoring. The
mode's ranked chunks are adapted into the Stage 7B.0 result shape purely
to feed that shared scorer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict

from ingestion_bench.cross_document_benchmark.benchmark_runner import FactEvidence, _evaluate_question
from ingestion_bench.cross_document_benchmark.retriever import CrossDocumentRetrievalHit, CrossDocumentSearchResult, PerDocumentResolution
from ingestion_bench.hybrid_retrieval_benchmark.model import FusedChunk


@dataclass
class ResolutionBundle:
    resolutions: list[PerDocumentResolution]
    eligible_union: list[str]
    snapshot_hash: str
    integrity_errors: list[str]
    failed_closed: bool
    requested_by_document: dict[str, list[str]]
    query_intent: str
    as_of_date: date


class FrozenScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_fact_coverage_at_k: float
    all_required_facts_retrieved_at_k: bool
    complete_chain_represented: bool
    mrr: float
    ndcg_at_k: float
    forbidden_fact_hit_ids: list[str]
    authority_leakage_count: int
    evidence_document_diversity: int
    outcome: str
    authority_correct: bool
    hit_chunk_ids: list[str]
    hit_documents: list[str]


def _fused_to_hit(fc: FusedChunk, rank: int) -> CrossDocumentRetrievalHit:
    return CrossDocumentRetrievalHit(
        rank=rank, similarity_score=fc.rrf_score, logical_document_id=fc.logical_document_id,
        document_revision_id=fc.document_revision_id, version_label=fc.version_label, revision_number=fc.revision_number,
        authority_label=fc.authority_label, source_relative_path=fc.source_relative_path,
        source_document_sha256=fc.source_document_sha256, chunk_id=fc.chunk_id, content_sha256=fc.content_sha256,
        retrieval_text=fc.retrieval_text, chunk_type=fc.chunk_type, unit_indices=fc.unit_indices,
        heading_path=fc.heading_path, source_element_ids=fc.source_element_ids, source_refs=fc.source_refs,
    )


def score_mode(
    question: dict[str, Any], fused_chunks: list[FusedChunk], bundle: ResolutionBundle,
    evidence: dict[str, FactEvidence], id_to_symbol: dict[str, str], total_latency: float,
) -> FrozenScore:
    hits = [_fused_to_hit(fc, i) for i, fc in enumerate(fused_chunks, start=1)]
    synthetic = CrossDocumentSearchResult(
        query_intent=bundle.query_intent, as_of_date=bundle.as_of_date, requested_revision_ids_by_document=bundle.requested_by_document,
        per_document_resolutions=bundle.resolutions, eligible_revision_ids_union=bundle.eligible_union,
        corpus_registry_snapshot_hash=bundle.snapshot_hash, failed_closed=bundle.failed_closed, integrity_errors=bundle.integrity_errors,
        resolver_latency_seconds=total_latency, authority_aware_vector_search_latency_seconds=0.0,
        unfiltered_vector_search_latency_seconds=0.0, hits=hits, unfiltered_hits=[],
    )
    scored = _evaluate_question(question, synthetic, evidence, id_to_symbol)
    return FrozenScore(
        required_fact_coverage_at_k=scored.required_fact_coverage_at_k, all_required_facts_retrieved_at_k=scored.all_required_facts_retrieved_at_k,
        complete_chain_represented=scored.complete_chain_represented, mrr=scored.mrr, ndcg_at_k=scored.ndcg_at_k,
        forbidden_fact_hit_ids=scored.forbidden_fact_hit_ids, authority_leakage_count=scored.authority_leakage_count,
        evidence_document_diversity=scored.evidence_document_diversity, outcome=scored.vector_outcome, authority_correct=scored.authority_correct,
        hit_chunk_ids=scored.authority_aware_hit_chunk_ids, hit_documents=scored.authority_aware_hit_documents,
    )


# --- decision gates ---------------------------------------------------------

TARGET_QUESTIONS = ("Q04_two_hop_control_of_service", "Q06_four_hop_procedure_of_app", "Q07_consolidation_payment_settlement")
Q12 = "Q12_draft_proposed_control"


class GateInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # per-question, for H2 of a graph condition vs the frozen Vector baseline
    target_complete_chain_improvements: int  # of Q04/Q06/Q07, how many became complete-chain where Vector was not
    regressions_vs_vector: list[str]         # questions where H2 coverage < Vector coverage
    q12_regressed: bool
    total_authority_leakage: int
    same_final_k: bool
    uses_query_time_llm: bool
    mean_latency_ratio_vs_vector: float


def meets_gate_a(g: GateInputs) -> bool:
    return (
        g.target_complete_chain_improvements >= 2
        and len(g.regressions_vs_vector) == 0
        and not g.q12_regressed
        and g.total_authority_leakage == 0
        and g.same_final_k
        and not g.uses_query_time_llm
        and g.mean_latency_ratio_vs_vector <= 2.0
    )


def decide(real: GateInputs, perfect: GateInputs, real_improves_any_target: bool, perfect_improves_any_target: bool) -> tuple[str, str, str]:
    """Returns (gate_id, decision, rationale). Gates evaluated in the
    fixed order A, D, B, C."""
    if meets_gate_a(real):
        return ("A", "Retain Hybrid Graph experimentally/selectively",
                "Real-graph H2 improved complete-chain on >=2 of Q04/Q06/Q07 with zero regressions, no Q12 regression, zero authority "
                "leakage, the same final K, no query-time LLM, and mean latency <= 2x Vector.")
    if len(real.regressions_vs_vector) == 0 and not real.q12_regressed and real.target_complete_chain_improvements < 2:
        return ("D", "Keep Vector; use Graph only for navigation/offline analysis",
                f"Real-graph H2 removed Graph regressions (no regression vs Vector) but improved only "
                f"{real.target_complete_chain_improvements} of the three target questions (< 2).")
    if meets_gate_a(perfect) and not meets_gate_a(real):
        return ("B", "Defer until reliable structured relationships exist",
                "Perfect-graph H2 meets the retain gate but real-graph H2 does not -- the benefit is contingent on structured-relationship "
                "quality that the real extractor does not deliver.")
    return ("C", "Close Graph exploration for this architecture",
            f"Neither real-graph nor perfect-graph hybrid materially improves Vector (real target improvements "
            f"{real.target_complete_chain_improvements}, perfect {perfect.target_complete_chain_improvements}; "
            f"real regressions {len(real.regressions_vs_vector)}).")
