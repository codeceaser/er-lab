"""Stage 7A.2: evaluation-orchestration tests.

Hand-built RetrievalEvaluationRun data (never the real, committed Stage
7A.1 report -- that is exercised separately by the integration test) plus
the deterministic FakeAnswerGenerator.
"""

from __future__ import annotations

from ingestion_bench.answer_baseline.answer_generator import FakeAnswerClaim, FakeAnswerGenerator, FakeAnswerResponse
from ingestion_bench.answer_baseline.evaluation import build_aggregate_answer_metrics, run_answer_evaluation
from ingestion_bench.retrieval_baseline.evaluation import AggregateMetrics, QuestionResult, RetrievalEvaluationRun
from ingestion_bench.retrieval_baseline.indexer import IndexBuildResult
from ingestion_bench.retrieval_baseline.metrics import QuestionMetrics
from ingestion_bench.retrieval_baseline.retrieval import RetrievalResult, SearchMeta


def _retrieval_result(chunk_id: str) -> RetrievalResult:
    return RetrievalResult(
        rank=1, score=0.9, chunk_id=chunk_id, content_sha256="a" * 64, retrieval_text="text",
        fixture="x/y", doc_id="D", source_format="pdf", unit_indices=[0], source_element_ids=[],
        heading_source_element_ids=[], annotation_ids=[], source_refs=[], heading_path=[],
    )


def _question_result(question_id: str, *, all_required_retrieved: bool | None, top_k_results: list[RetrievalResult]) -> QuestionResult:
    metrics = QuestionMetrics(
        question_id=question_id, ks=[5], coverage_at_k={"5": 1.0}, recall_at_k={"5": 1.0},
        all_required_retrieved_at_k={"5": all_required_retrieved}, forbidden_hit_rate_at_k={"5": 0.0},
        retrieved_chunk_count_at_k={"5": len(top_k_results)}, reciprocal_rank=1.0,
        available_required_fact_count=1, excluded_required_fact_count=0, available_forbidden_fact_count=0,
        retrieval_latency_seconds=0.01,
    )
    search_meta = SearchMeta(
        corpus_profile="baseline_demo", embedding_model="fake", query="q", top_k=5,
        retrieved_count=len(top_k_results), embedding_elapsed_seconds=0.001,
        search_elapsed_seconds=0.001, total_latency_seconds=0.01,
    )
    return QuestionResult(
        question_id=question_id, question="What is X?", difficulty="direct", citation_required=True,
        answer_rubric="rubric", required_fact_ids=["F1"], forbidden_fact_ids=[],
        required_fact_evidence={}, forbidden_fact_evidence={}, top_k_results=top_k_results,
        matched_required_fact_ids_at_k={"5": []}, forbidden_fact_ids_retrieved_at_k={"5": []},
        search_meta=search_meta, metrics=metrics,
    )


def _retrieval_run(question_results: list[QuestionResult]) -> RetrievalEvaluationRun:
    index_build = IndexBuildResult(
        corpus_profile="baseline_demo", embedding_model="fake", fixtures=["x/y"], candidate_chunk_count=1,
        empty_retrieval_text_skipped_count=0, indexed_count=1, skipped_unchanged_count=0, embedded_count=1,
        total_record_count=1, build_latency_seconds=0.01, embedding_elapsed_seconds=0.01,
        embedding_cost_usd=None, index_hash="deadbeef", generated_at="2026-01-01T00:00:00+00:00",
    )
    aggregate = AggregateMetrics(
        ks=[5], mean_coverage_at_k={"5": 1.0}, mean_recall_at_k={"5": 1.0},
        all_required_retrieved_rate_at_k={"5": 1.0}, mean_forbidden_hit_rate_at_k={"5": 0.0},
        mean_reciprocal_rank=1.0, mean_retrieval_latency_seconds=0.01, question_count=len(question_results),
    )
    return RetrievalEvaluationRun(
        corpus_profile="baseline_demo", embedding_model="fake", ks=[5], generated_at="2026-01-01T00:00:00+00:00",
        index_build=index_build, question_results=question_results, aggregate=aggregate,
    )


def test_run_answer_evaluation_produces_one_result_per_question():
    run = _retrieval_run(
        [
            _question_result("Q1", all_required_retrieved=True, top_k_results=[_retrieval_result("c1")]),
            _question_result("Q2", all_required_retrieved=True, top_k_results=[_retrieval_result("c2")]),
        ]
    )
    generator = FakeAnswerGenerator()
    result = run_answer_evaluation(run, generator)
    assert len(result.question_results) == 2
    assert result.answer_model == FakeAnswerGenerator.model_identity
    assert result.retrieval_corpus_profile == "baseline_demo"


def test_incomplete_retrieval_causes_evidence_sufficient_false_is_scored_correctly():
    """When Stage 7A.1's own retrieval did NOT return all required facts,
    an honest answer must set evidence_sufficient=False -- validated
    mechanically, never assumed."""
    honest_response = {
        "Q1": FakeAnswerResponse(evidence_sufficient=False, answer_text="insufficient evidence", claims=[])
    }
    overclaiming_response = {
        "Q1": FakeAnswerResponse(evidence_sufficient=True, answer_text="a confident but wrong answer", claims=[])
    }
    run = _retrieval_run([_question_result("Q1", all_required_retrieved=False, top_k_results=[_retrieval_result("c1")])])

    honest_result = run_answer_evaluation(run, FakeAnswerGenerator(honest_response))
    overclaiming_result = run_answer_evaluation(run, FakeAnswerGenerator(overclaiming_response))

    assert honest_result.question_results[0].validation.evidence_sufficiency_accuracy is True
    assert overclaiming_result.question_results[0].validation.evidence_sufficiency_accuracy is False


def test_aggregate_metrics_sum_and_average_across_questions():
    results = [
        _question_result("Q1", all_required_retrieved=True, top_k_results=[_retrieval_result("c1")]),
        _question_result("Q2", all_required_retrieved=True, top_k_results=[_retrieval_result("c2")]),
    ]
    run = _retrieval_run(results)
    from ingestion_bench.answer_baseline.evaluation import answer_question

    generator = FakeAnswerGenerator()
    question_answers = [answer_question(qr, generator) for qr in run.question_results]
    aggregate = build_aggregate_answer_metrics(question_answers)
    assert aggregate.question_count == 2
    assert aggregate.total_input_tokens is None  # fake generator reports no token usage
    assert aggregate.total_estimated_cost_usd is None


def test_question_answer_result_defaults_to_not_reviewed_human_field():
    run = _retrieval_run([_question_result("Q1", all_required_retrieved=True, top_k_results=[_retrieval_result("c1")])])
    result = run_answer_evaluation(run, FakeAnswerGenerator())
    assert result.question_results[0].answer_text_correctness_human_review == "not_reviewed"
