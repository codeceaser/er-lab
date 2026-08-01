"""Stage 7A.2: deterministic (non-LLM) citation validation.

No second LLM ever grades an answer here. Every field on
`CitationValidationResult` is computed by exact set membership against
data already known: the Stage 7A.1 retrieval context an `AnswerResult`
was generated from, and the Stage 6A/6B gold evidence catalog
(`retrieval_baseline.gold`) -- same "never silently 0%/None-vs-False"
discipline as Stage 6A/7A.1's own metrics.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ingestion_bench.answer_baseline.model import AnswerResult
from ingestion_bench.retrieval_baseline.gold import ScopedFactEvidence, gold_chunk_ids


class CitationValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str

    # Every cited chunk was retrieved (item 4, requirement 1). A cited
    # chunk_id NOT present in answer.retrieved_chunk_ids is invalid --
    # the answer model cited evidence outside the retrieval context.
    invalid_citation_count: int
    invalid_cited_chunk_ids: list[str] = Field(default_factory=list)

    # Every citation resolves to stored provenance (item 4, requirement
    # 2). A VALID citation (chunk_id that WAS retrieved) that somehow has
    # no matching CitedChunkProvenance entry on its own claim is a
    # resolution failure -- should never happen given how
    # answer_generator.py constructs a ClaimCitation, but validated
    # mechanically here rather than merely assumed.
    unresolved_provenance_citation_count: int
    unresolved_provenance_chunk_ids: list[str] = Field(default_factory=list)

    # Required-fact citation coverage (item 4, requirement 3): a required
    # fact receives citation credit only when at least one VALIDLY cited
    # chunk (retrieved AND cited) belongs to its gold chunk set. Keyed by
    # fact_id, restricted to facts with at least one available (indexed)
    # gold chunk in this corpus -- a fact excluded from retrieval
    # scoring entirely contributes no entry here, never a misleading
    # False.
    required_fact_citation_coverage: dict[str, bool] = Field(default_factory=dict)
    required_fact_citation_coverage_rate: float | None = None

    # Forbidden-fact citation rate (item 4, requirement 4): same validly-
    # cited-chunk membership test against forbidden gold chunk sets. 0.0
    # when there is no available forbidden evidence in this corpus to
    # leak is a real, meaningful zero (same precedent as
    # retrieval_baseline.metrics.forbidden_hit_rate_at_k), never None.
    forbidden_fact_citation_count: int
    forbidden_cited_fact_ids: list[str] = Field(default_factory=list)
    forbidden_fact_citation_rate: float

    # Uncited substantive claim count, "where structurally detectable"
    # (item 4, requirement 5): a claim_citations entry with an EMPTY
    # cited_chunk_ids list is the only structurally detectable case --
    # this cannot detect a substantive statement embedded in answer_text
    # that the model never turned into a claims[] entry at all; that
    # residual gap is exactly why answer-text correctness stays a
    # human-review field (item 4's own explicit carve-out), never
    # silently claimed as fully covered by this count.
    uncited_claim_count: int
    total_claim_count: int
    citation_completeness: float | None

    # Evidence-sufficiency accuracy (item 4, requirement 7): ONLY scored
    # in the direction the task spec actually defines -- when retrieval
    # did NOT return all required facts, the answer should not claim
    # evidence_sufficient=True. None (not True, not False) whenever
    # retrieval WAS complete, or had no available required facts at all
    # (nothing incomplete to have been honest about) -- never a fabricated
    # score in a direction the task never asked this baseline to grade.
    evidence_sufficiency_expected_false: bool
    evidence_sufficiency_accuracy: bool | None

    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None
    answer_latency_seconds: float


def validate_answer(
    answer: AnswerResult,
    required_fact_evidence: dict[str, list[ScopedFactEvidence]],
    forbidden_fact_evidence: dict[str, list[ScopedFactEvidence]],
    all_required_retrieved_at_max_k: bool | None,
) -> CitationValidationResult:
    retrieved_ids = set(answer.retrieved_chunk_ids)
    cited_ids = set(answer.cited_chunks)
    valid_cited_ids = cited_ids & retrieved_ids
    invalid_cited_ids = sorted(cited_ids - retrieved_ids)

    unresolved_provenance_ids: set[str] = set()
    for claim in answer.claim_citations:
        valid_ids_in_claim = set(claim.cited_chunk_ids) & retrieved_ids
        provenance_ids_in_claim = {p.chunk_id for p in claim.cited_chunk_provenance}
        unresolved_provenance_ids |= valid_ids_in_claim - provenance_ids_in_claim

    required_gold_by_fact = {
        fact_id: gold_chunk_ids(entries) for fact_id, entries in required_fact_evidence.items() if gold_chunk_ids(entries)
    }
    coverage = {fact_id: bool(valid_cited_ids & gold) for fact_id, gold in required_gold_by_fact.items()}
    coverage_rate = (sum(1 for covered in coverage.values() if covered) / len(coverage)) if coverage else None

    forbidden_gold_by_fact = {
        fact_id: gold_chunk_ids(entries) for fact_id, entries in forbidden_fact_evidence.items() if gold_chunk_ids(entries)
    }
    forbidden_cited_fact_ids = sorted(
        fact_id for fact_id, gold in forbidden_gold_by_fact.items() if valid_cited_ids & gold
    )
    forbidden_rate = (
        len(forbidden_cited_fact_ids) / len(forbidden_gold_by_fact) if forbidden_gold_by_fact else 0.0
    )

    total_claims = len(answer.claim_citations)
    uncited_claims = sum(1 for claim in answer.claim_citations if not claim.cited_chunk_ids)
    completeness = ((total_claims - uncited_claims) / total_claims) if total_claims else None

    expect_insufficient = all_required_retrieved_at_max_k is False
    accuracy: bool | None = (answer.evidence_sufficient is False) if expect_insufficient else None

    return CitationValidationResult(
        question_id=answer.question_id,
        invalid_citation_count=len(invalid_cited_ids),
        invalid_cited_chunk_ids=invalid_cited_ids,
        unresolved_provenance_citation_count=len(unresolved_provenance_ids),
        unresolved_provenance_chunk_ids=sorted(unresolved_provenance_ids),
        required_fact_citation_coverage=coverage,
        required_fact_citation_coverage_rate=coverage_rate,
        forbidden_fact_citation_count=len(forbidden_cited_fact_ids),
        forbidden_cited_fact_ids=forbidden_cited_fact_ids,
        forbidden_fact_citation_rate=forbidden_rate,
        uncited_claim_count=uncited_claims,
        total_claim_count=total_claims,
        citation_completeness=completeness,
        evidence_sufficiency_expected_false=expect_insufficient,
        evidence_sufficiency_accuracy=accuracy,
        input_tokens=answer.input_tokens,
        output_tokens=answer.output_tokens,
        estimated_cost_usd=answer.estimated_cost_usd,
        answer_latency_seconds=answer.answer_latency_seconds,
    )
