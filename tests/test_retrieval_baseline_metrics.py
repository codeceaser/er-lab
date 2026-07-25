"""Stage 7A.1: retrieval-metrics tests.

No LLM, no semantic judge -- pure deterministic set-membership
arithmetic, exercised entirely with hand-built data (no real artifacts
needed).
"""

from __future__ import annotations

from ingestion_bench.retrieval_baseline.gold import ScopedFactEvidence
from ingestion_bench.retrieval_baseline.metrics import compute_question_metrics
from ingestion_bench.retrieval_baseline.retrieval import RetrievalResult


def _result(rank: int, chunk_id: str, score: float = 0.5) -> RetrievalResult:
    return RetrievalResult(
        rank=rank, score=score, chunk_id=chunk_id, content_sha256="a" * 64, retrieval_text="t",
        fixture="x/y", doc_id="D", source_format="pdf", unit_indices=[0], source_element_ids=[],
        heading_source_element_ids=[], annotation_ids=[], source_refs=[], heading_path=[],
    )


def test_required_fact_coverage_at_k_counts_facts_not_chunks():
    """Two required facts share ONE gold chunk -- coverage counts FACTS
    (both count as covered once that one chunk is retrieved), while
    recall counts the underlying CHUNK set (size 1)."""
    required = {
        "F1": [ScopedFactEvidence(fixture="x", fact_id="F1", status="available_with_chunks", chunk_ids=["c1"])],
        "F2": [ScopedFactEvidence(fixture="x", fact_id="F2", status="available_with_chunks", chunk_ids=["c1"])],
    }
    results = [_result(1, "c1")]
    metrics = compute_question_metrics("Q", required, {}, results, [1, 3], 0.01)
    assert metrics.coverage_at_k["1"] == 1.0  # both facts covered by the one retrieved chunk
    assert metrics.recall_at_k["1"] == 1.0  # the only gold chunk was retrieved
    assert metrics.available_required_fact_count == 2


def test_required_fact_coverage_partial_when_only_some_facts_hit():
    required = {
        "F1": [ScopedFactEvidence(fixture="x", fact_id="F1", status="available_with_chunks", chunk_ids=["c1"])],
        "F2": [ScopedFactEvidence(fixture="x", fact_id="F2", status="available_with_chunks", chunk_ids=["c2"])],
    }
    results = [_result(1, "c1"), _result(2, "cX")]
    metrics = compute_question_metrics("Q", required, {}, results, [1, 2], 0.01)
    assert metrics.coverage_at_k["2"] == 0.5
    assert metrics.all_required_retrieved_at_k["2"] is False


def test_missing_from_ingestion_facts_excluded_never_a_retrieval_failure():
    """A fact that is missing_from_ingestion or not_applicable must be
    EXCLUDED from coverage's denominator entirely -- not counted as a
    covered fact, and not counted as a failed one either. Only a fact
    that IS available_with_chunks but wasn't retrieved counts against
    coverage."""
    required = {
        "F1": [ScopedFactEvidence(fixture="x", fact_id="F1", status="available_with_chunks", chunk_ids=["c1"])],
        "F2": [ScopedFactEvidence(fixture="x", fact_id="F2", status="missing_from_ingestion")],
        "F3": [ScopedFactEvidence(fixture="x", fact_id="F3", status="not_applicable")],
        "F4": [ScopedFactEvidence(fixture="x", fact_id="F4", status="ingested_without_chunks")],
    }
    results = [_result(1, "c1")]
    metrics = compute_question_metrics("Q", required, {}, results, [1], 0.01)
    # F1 is the only available fact and it WAS retrieved -> perfect coverage.
    assert metrics.coverage_at_k["1"] == 1.0
    assert metrics.all_required_retrieved_at_k["1"] is True
    assert metrics.available_required_fact_count == 1
    assert metrics.excluded_required_fact_count == 3


def test_coverage_is_none_when_zero_required_facts_are_available():
    """A question entirely unresolvable in this corpus (e.g. every
    required fact excluded from this profile) must report None, never a
    misleading 0% -- same "never silently 0%" discipline as Stage 6A."""
    required = {"F1": [ScopedFactEvidence(fixture="x", fact_id="F1", status="missing_from_ingestion")]}
    results = [_result(1, "c1")]
    metrics = compute_question_metrics("Q", required, {}, results, [1], 0.01)
    assert metrics.coverage_at_k["1"] is None
    assert metrics.recall_at_k["1"] is None
    assert metrics.all_required_retrieved_at_k["1"] is None


def test_forbidden_fact_hit_rate_detects_leaked_forbidden_evidence():
    forbidden = {"D1": [ScopedFactEvidence(fixture="x", fact_id="D1", status="available_with_chunks", chunk_ids=["cbad"])]}
    results_with_leak = [_result(1, "cbad")]
    results_without_leak = [_result(1, "cgood")]

    leaked = compute_question_metrics("Q", {}, forbidden, results_with_leak, [1], 0.01)
    clean = compute_question_metrics("Q", {}, forbidden, results_without_leak, [1], 0.01)

    assert leaked.forbidden_hit_rate_at_k["1"] == 1.0
    assert clean.forbidden_hit_rate_at_k["1"] == 0.0


def test_forbidden_hit_rate_is_trivially_zero_when_no_forbidden_evidence_available():
    forbidden = {"D1": [ScopedFactEvidence(fixture="x", fact_id="D1", status="missing_from_ingestion")]}
    metrics = compute_question_metrics("Q", {}, forbidden, [_result(1, "c1")], [1], 0.01)
    assert metrics.forbidden_hit_rate_at_k["1"] == 0.0
    assert metrics.available_forbidden_fact_count == 0


def test_reciprocal_rank_of_first_relevant_chunk():
    required = {"F1": [ScopedFactEvidence(fixture="x", fact_id="F1", status="available_with_chunks", chunk_ids=["c3"])]}
    results = [_result(1, "c1"), _result(2, "c2"), _result(3, "c3")]
    metrics = compute_question_metrics("Q", required, {}, results, [5], 0.01)
    assert metrics.reciprocal_rank == 1 / 3


def test_reciprocal_rank_is_zero_when_nothing_relevant_retrieved():
    required = {"F1": [ScopedFactEvidence(fixture="x", fact_id="F1", status="available_with_chunks", chunk_ids=["cX"])]}
    results = [_result(1, "c1"), _result(2, "c2")]
    metrics = compute_question_metrics("Q", required, {}, results, [5], 0.01)
    assert metrics.reciprocal_rank == 0.0


def test_retrieved_chunk_count_at_k_never_exceeds_actual_results():
    metrics = compute_question_metrics("Q", {}, {}, [_result(1, "c1"), _result(2, "c2")], [1, 3, 5], 0.01)
    assert metrics.retrieved_chunk_count_at_k == {"1": 1, "3": 2, "5": 2}
