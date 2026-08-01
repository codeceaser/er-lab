"""Stage 7A.2: full-benchmark answer evaluation orchestration.

Reads the frozen Stage 7A.1 `RetrievalEvaluationRun` JSON
(`reports/stage7a_vector_retrieval_results.json`) as the SOLE source of
retrieval context -- never re-invokes `retrieval_baseline.retrieval.search`,
never touches `indexer.py`/`metrics.py`. Runs one answer per question
through the configured `AnswerGenerator`, then deterministically validates
every answer (`validation.py`). Never an LLM judge.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ingestion_bench.answer_baseline import config
from ingestion_bench.answer_baseline.answer_generator import AnswerGenerator
from ingestion_bench.answer_baseline.model import AnswerResult
from ingestion_bench.answer_baseline.validation import CitationValidationResult, validate_answer
from ingestion_bench.retrieval_baseline.evaluation import QuestionResult, RetrievalEvaluationRun
from ingestion_bench.retrieval_baseline.retrieval import RetrievalResult


def load_retrieval_run(path: Path | None = None) -> RetrievalEvaluationRun:
    """The one, sole retrieval-context input for this whole package --
    Stage 7A.1's own committed output, read verbatim, never re-run."""
    resolved = path or config.STAGE7A_RETRIEVAL_RESULTS_PATH
    data = json.loads(Path(resolved).read_text(encoding="utf-8"))
    return RetrievalEvaluationRun.model_validate(data)


class QuestionAnswerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    question: str
    difficulty: str
    answer_rubric: str

    top_k_results: list[RetrievalResult]

    answer: AnswerResult
    validation: CitationValidationResult

    # Answer-TEXT correctness (as opposed to the mechanically validated
    # citation/coverage fields above) is intentionally left for a human
    # to fill in for this first 12-question baseline -- never computed by
    # a second LLM acting as judge. "not_reviewed" until a human sets it.
    answer_text_correctness_human_review: Literal["not_reviewed", "correct", "partially_correct", "incorrect"] = (
        "not_reviewed"
    )
    answer_text_correctness_notes: str | None = None


def answer_question(question_result: QuestionResult, generator: AnswerGenerator) -> QuestionAnswerResult:
    retrieved = question_result.top_k_results
    answer = generator.generate(question_result.question_id, question_result.question, retrieved)

    max_k_key = str(max(question_result.metrics.ks))
    all_required_retrieved = question_result.metrics.all_required_retrieved_at_k[max_k_key]
    validation = validate_answer(
        answer, question_result.required_fact_evidence, question_result.forbidden_fact_evidence, all_required_retrieved
    )

    return QuestionAnswerResult(
        question_id=question_result.question_id,
        question=question_result.question,
        difficulty=question_result.difficulty,
        answer_rubric=question_result.answer_rubric,
        top_k_results=retrieved,
        answer=answer,
        validation=validation,
    )


class AggregateAnswerMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_count: int

    total_invalid_citations: int
    total_unresolved_provenance_citations: int

    mean_required_fact_citation_coverage_rate: float | None
    mean_forbidden_fact_citation_rate: float

    total_claims: int
    total_uncited_claims: int
    mean_citation_completeness: float | None

    evidence_sufficiency_scored_question_count: int
    evidence_sufficiency_accuracy_rate: float | None

    total_input_tokens: int | None
    total_output_tokens: int | None
    total_estimated_cost_usd: float | None
    mean_answer_latency_seconds: float


def _mean_or_none(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _sum_or_none(values: list[int | None]) -> int | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present)


def _sum_or_none_float(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present)


def build_aggregate_answer_metrics(results: list[QuestionAnswerResult]) -> AggregateAnswerMetrics:
    validations = [r.validation for r in results]

    scored_accuracy = [v.evidence_sufficiency_accuracy for v in validations if v.evidence_sufficiency_accuracy is not None]

    total_claims = sum(v.total_claim_count for v in validations)
    total_uncited = sum(v.uncited_claim_count for v in validations)
    latencies = [v.answer_latency_seconds for v in validations]

    return AggregateAnswerMetrics(
        question_count=len(results),
        total_invalid_citations=sum(v.invalid_citation_count for v in validations),
        total_unresolved_provenance_citations=sum(v.unresolved_provenance_citation_count for v in validations),
        mean_required_fact_citation_coverage_rate=_mean_or_none(
            [v.required_fact_citation_coverage_rate for v in validations]
        ),
        mean_forbidden_fact_citation_rate=(
            sum(v.forbidden_fact_citation_rate for v in validations) / len(validations) if validations else 0.0
        ),
        total_claims=total_claims,
        total_uncited_claims=total_uncited,
        mean_citation_completeness=_mean_or_none([v.citation_completeness for v in validations]),
        evidence_sufficiency_scored_question_count=len(scored_accuracy),
        evidence_sufficiency_accuracy_rate=(
            (sum(1 for a in scored_accuracy if a) / len(scored_accuracy)) if scored_accuracy else None
        ),
        total_input_tokens=_sum_or_none([v.input_tokens for v in validations]),
        total_output_tokens=_sum_or_none([v.output_tokens for v in validations]),
        total_estimated_cost_usd=_sum_or_none_float([v.estimated_cost_usd for v in validations]),
        mean_answer_latency_seconds=(sum(latencies) / len(latencies)) if latencies else 0.0,
    )


class AnswerEvaluationRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_model: str
    generated_at: str
    retrieval_source: str
    retrieval_corpus_profile: str
    retrieval_embedding_model: str
    question_results: list[QuestionAnswerResult]
    aggregate: AggregateAnswerMetrics


def run_answer_evaluation(
    retrieval_run: RetrievalEvaluationRun, generator: AnswerGenerator, retrieval_source: str | None = None
) -> AnswerEvaluationRun:
    question_results = [answer_question(qr, generator) for qr in retrieval_run.question_results]
    aggregate = build_aggregate_answer_metrics(question_results)
    return AnswerEvaluationRun(
        answer_model=generator.model_identity,
        generated_at=datetime.now(timezone.utc).isoformat(),
        retrieval_source=retrieval_source or str(config.STAGE7A_RETRIEVAL_RESULTS_PATH),
        retrieval_corpus_profile=retrieval_run.corpus_profile,
        retrieval_embedding_model=retrieval_run.embedding_model,
        question_results=question_results,
        aggregate=aggregate,
    )
