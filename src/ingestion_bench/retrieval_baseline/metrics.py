"""Stage 7A.1: deterministic retrieval metrics.

No LLM, no semantic judge, no fuzzy scoring anywhere in this module. A
retrieved chunk is "relevant" to a required fact ONLY when its chunk_id
is a member of that fact's resolved gold chunk_ids (gold.py) -- exact
set membership, nothing else.

Every metric follows the same "never silently 0%" discipline the Stage
6A evaluator established (see docs/POC_DECISION_LOG.md): a metric with
no applicable denominator (e.g. a question with zero AVAILABLE required
facts in this corpus) is None, never a misleading 0.0.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ingestion_bench.retrieval_baseline.gold import ScopedFactEvidence, gold_chunk_ids
from ingestion_bench.retrieval_baseline.retrieval import RetrievalResult


class QuestionMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    ks: list[int]

    # keyed by str(k) -- JSON object keys must be strings.
    coverage_at_k: dict[str, float | None] = Field(default_factory=dict)
    recall_at_k: dict[str, float | None] = Field(default_factory=dict)
    all_required_retrieved_at_k: dict[str, bool | None] = Field(default_factory=dict)
    forbidden_hit_rate_at_k: dict[str, float] = Field(default_factory=dict)
    retrieved_chunk_count_at_k: dict[str, int] = Field(default_factory=dict)

    reciprocal_rank: float

    available_required_fact_count: int
    excluded_required_fact_count: int
    available_forbidden_fact_count: int

    retrieval_latency_seconds: float


def _required_gold_by_fact(required_evidence: dict[str, list[ScopedFactEvidence]]) -> dict[str, set[str]]:
    by_fact: dict[str, set[str]] = {}
    for fact_id, entries in required_evidence.items():
        chunk_ids = gold_chunk_ids(entries)
        if chunk_ids:
            by_fact[fact_id] = chunk_ids
    return by_fact


def compute_question_metrics(
    question_id: str,
    required_evidence: dict[str, list[ScopedFactEvidence]],
    forbidden_evidence: dict[str, list[ScopedFactEvidence]],
    ranked_results: list[RetrievalResult],
    ks: list[int],
    retrieval_latency_seconds: float,
) -> QuestionMetrics:
    required_gold_by_fact = _required_gold_by_fact(required_evidence)
    all_required_gold_chunk_ids = {cid for chunk_ids in required_gold_by_fact.values() for cid in chunk_ids}
    forbidden_gold_chunk_ids = {
        cid for entries in forbidden_evidence.values() for cid in gold_chunk_ids(entries)
    }

    # A required fact_id is "excluded" from retrieval scoring entirely
    # when NONE of its (possibly multi-fixture) entries resolved to
    # available_with_chunks -- missing_from_ingestion/not_applicable/
    # ingested_without_chunks, in any combination, all count as excluded,
    # never as a retrieval miss (task requirement: only category 4 --
    # retrieval failing to return AVAILABLE evidence -- is a miss).
    excluded_required = len(required_evidence) - len(required_gold_by_fact)
    available_forbidden = len({fact_id for fact_id, entries in forbidden_evidence.items() if gold_chunk_ids(entries)})

    retrieved_ids_ranked = [r.chunk_id for r in ranked_results]

    coverage_at_k: dict[str, float | None] = {}
    recall_at_k: dict[str, float | None] = {}
    all_required_at_k: dict[str, bool | None] = {}
    forbidden_hit_at_k: dict[str, float] = {}
    retrieved_count_at_k: dict[str, int] = {}

    for k in ks:
        key = str(k)
        top_k_ids = set(retrieved_ids_ranked[:k])
        retrieved_count_at_k[key] = min(k, len(retrieved_ids_ranked))

        if required_gold_by_fact:
            covered = sum(1 for chunk_ids in required_gold_by_fact.values() if chunk_ids & top_k_ids)
            coverage_at_k[key] = covered / len(required_gold_by_fact)
            all_required_at_k[key] = covered == len(required_gold_by_fact)
        else:
            coverage_at_k[key] = None
            all_required_at_k[key] = None

        if all_required_gold_chunk_ids:
            recall_at_k[key] = len(all_required_gold_chunk_ids & top_k_ids) / len(all_required_gold_chunk_ids)
        else:
            recall_at_k[key] = None

        if forbidden_gold_chunk_ids:
            forbidden_hit_at_k[key] = len(forbidden_gold_chunk_ids & top_k_ids) / len(forbidden_gold_chunk_ids)
        else:
            # No forbidden evidence is even available in this corpus to
            # leak -- trivially 0.0 (a real, meaningful zero, not a
            # missing-denominator case: "did not leak anything" is true
            # regardless of K here).
            forbidden_hit_at_k[key] = 0.0

    reciprocal_rank = 0.0
    for rank, chunk_id in enumerate(retrieved_ids_ranked, start=1):
        if chunk_id in all_required_gold_chunk_ids:
            reciprocal_rank = 1.0 / rank
            break

    return QuestionMetrics(
        question_id=question_id,
        ks=ks,
        coverage_at_k=coverage_at_k,
        recall_at_k=recall_at_k,
        all_required_retrieved_at_k=all_required_at_k,
        forbidden_hit_rate_at_k=forbidden_hit_at_k,
        retrieved_chunk_count_at_k=retrieved_count_at_k,
        reciprocal_rank=reciprocal_rank,
        available_required_fact_count=len(required_gold_by_fact),
        excluded_required_fact_count=excluded_required,
        available_forbidden_fact_count=available_forbidden,
        retrieval_latency_seconds=retrieval_latency_seconds,
    )
