"""Stage 7A.1: full-benchmark evaluation orchestration.

Runs every Stage 6B question against ONE built corpus index, resolves
gold evidence at the corpus-level (fixture + fact_id + chunk_id scoped,
gold.py), retrieves at max(ks), and computes deterministic metrics for
every K. Never an LLM judge, never fuzzy scoring.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict

from ingestion_bench.retrieval_baseline.embeddings import EmbeddingProvider
from ingestion_bench.retrieval_baseline.gold import ScopedFactEvidence, gold_chunk_ids, resolve_corpus_gold_evidence
from ingestion_bench.retrieval_baseline.indexer import IndexBuildResult
from ingestion_bench.retrieval_baseline.metrics import QuestionMetrics, compute_question_metrics
from ingestion_bench.retrieval_baseline.retrieval import RetrievalResult, SearchMeta, search
from ingestion_bench.retrieval_baseline.vector_store import VectorStore
from ingestion_bench.retrieval_benchmark.model import BenchmarkQuestion, RetrievalBenchmarkContract
from ingestion_bench.evaluation.model import EvidenceAlignment


class QuestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    question: str
    difficulty: str
    citation_required: bool
    answer_rubric: str

    required_fact_ids: list[str]
    forbidden_fact_ids: list[str]
    required_fact_evidence: dict[str, list[ScopedFactEvidence]]
    forbidden_fact_evidence: dict[str, list[ScopedFactEvidence]]

    top_k_results: list[RetrievalResult]
    matched_required_fact_ids_at_k: dict[str, list[str]]
    forbidden_fact_ids_retrieved_at_k: dict[str, list[str]]

    search_meta: SearchMeta
    metrics: QuestionMetrics


def _matched_and_leaked_fact_ids(
    required_evidence: dict[str, list[ScopedFactEvidence]],
    forbidden_evidence: dict[str, list[ScopedFactEvidence]],
    ranked_results: list[RetrievalResult],
    ks: list[int],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    retrieved_ids_ranked = [r.chunk_id for r in ranked_results]
    matched_at_k: dict[str, list[str]] = {}
    leaked_at_k: dict[str, list[str]] = {}
    for k in ks:
        top_k_ids = set(retrieved_ids_ranked[:k])
        matched_at_k[str(k)] = sorted(
            fact_id for fact_id, entries in required_evidence.items() if gold_chunk_ids(entries) & top_k_ids
        )
        leaked_at_k[str(k)] = sorted(
            fact_id for fact_id, entries in forbidden_evidence.items() if gold_chunk_ids(entries) & top_k_ids
        )
    return matched_at_k, leaked_at_k


def evaluate_question(
    question: BenchmarkQuestion,
    corpus_profile: str,
    fixtures: list[str],
    catalog: list[EvidenceAlignment],
    indexed_chunk_ids: set[str],
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStore,
    ks: list[int],
) -> QuestionResult:
    required_evidence = resolve_corpus_gold_evidence(question.required_fact_ids, fixtures, catalog, indexed_chunk_ids)
    forbidden_evidence = resolve_corpus_gold_evidence(question.forbidden_fact_ids, fixtures, catalog, indexed_chunk_ids)

    max_k = max(ks)
    results, search_meta = search(question.question, corpus_profile, embedding_provider, vector_store, max_k)

    metrics = compute_question_metrics(
        question.question_id, required_evidence, forbidden_evidence, results, ks, search_meta.total_latency_seconds
    )
    matched_at_k, leaked_at_k = _matched_and_leaked_fact_ids(required_evidence, forbidden_evidence, results, ks)

    return QuestionResult(
        question_id=question.question_id,
        question=question.question,
        difficulty=question.difficulty,
        citation_required=question.citation_required,
        answer_rubric=question.answer_rubric,
        required_fact_ids=question.required_fact_ids,
        forbidden_fact_ids=question.forbidden_fact_ids,
        required_fact_evidence=required_evidence,
        forbidden_fact_evidence=forbidden_evidence,
        top_k_results=results,
        matched_required_fact_ids_at_k=matched_at_k,
        forbidden_fact_ids_retrieved_at_k=leaked_at_k,
        search_meta=search_meta,
        metrics=metrics,
    )


class AggregateMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ks: list[int]
    mean_coverage_at_k: dict[str, float | None]
    mean_recall_at_k: dict[str, float | None]
    all_required_retrieved_rate_at_k: dict[str, float | None]
    mean_forbidden_hit_rate_at_k: dict[str, float]
    mean_reciprocal_rank: float
    mean_retrieval_latency_seconds: float
    question_count: int


def _mean_or_none(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _rate_or_none(values: list[bool | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(1 for v in present if v) / len(present)


def build_aggregate_metrics(question_results: list[QuestionResult], ks: list[int]) -> AggregateMetrics:
    mean_coverage: dict[str, float | None] = {}
    mean_recall: dict[str, float | None] = {}
    all_required_rate: dict[str, float | None] = {}
    mean_forbidden: dict[str, float] = {}
    for k in ks:
        key = str(k)
        mean_coverage[key] = _mean_or_none([qr.metrics.coverage_at_k[key] for qr in question_results])
        mean_recall[key] = _mean_or_none([qr.metrics.recall_at_k[key] for qr in question_results])
        all_required_rate[key] = _rate_or_none([qr.metrics.all_required_retrieved_at_k[key] for qr in question_results])
        forbidden_values = [qr.metrics.forbidden_hit_rate_at_k[key] for qr in question_results]
        mean_forbidden[key] = sum(forbidden_values) / len(forbidden_values) if forbidden_values else 0.0

    reciprocal_ranks = [qr.metrics.reciprocal_rank for qr in question_results]
    latencies = [qr.metrics.retrieval_latency_seconds for qr in question_results]

    return AggregateMetrics(
        ks=ks,
        mean_coverage_at_k=mean_coverage,
        mean_recall_at_k=mean_recall,
        all_required_retrieved_rate_at_k=all_required_rate,
        mean_forbidden_hit_rate_at_k=mean_forbidden,
        mean_reciprocal_rank=(sum(reciprocal_ranks) / len(reciprocal_ranks)) if reciprocal_ranks else 0.0,
        mean_retrieval_latency_seconds=(sum(latencies) / len(latencies)) if latencies else 0.0,
        question_count=len(question_results),
    )


class RetrievalEvaluationRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus_profile: str
    embedding_model: str
    ks: list[int]
    generated_at: str
    index_build: IndexBuildResult
    question_results: list[QuestionResult]
    aggregate: AggregateMetrics


def run_evaluation(
    contract: RetrievalBenchmarkContract,
    corpus_profile: str,
    fixtures: list[str],
    catalog: list[EvidenceAlignment],
    indexed_chunk_ids: set[str],
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStore,
    index_build: IndexBuildResult,
    ks: list[int],
) -> RetrievalEvaluationRun:
    question_results = [
        evaluate_question(
            question, corpus_profile, fixtures, catalog, indexed_chunk_ids, embedding_provider, vector_store, ks
        )
        for question in contract.questions
    ]
    aggregate = build_aggregate_metrics(question_results, ks)
    return RetrievalEvaluationRun(
        corpus_profile=corpus_profile,
        embedding_model=embedding_provider.model_identity,
        ks=ks,
        generated_at=datetime.now(timezone.utc).isoformat(),
        index_build=index_build,
        question_results=question_results,
        aggregate=aggregate,
    )
