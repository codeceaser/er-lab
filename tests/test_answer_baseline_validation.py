"""Stage 7A.2: deterministic citation validator tests.

Pure, hand-built data -- no real artifacts, no network, no LLM.
"""

from __future__ import annotations

from ingestion_bench.answer_baseline.model import AnswerResult, CitedChunkProvenance, ClaimCitation
from ingestion_bench.answer_baseline.validation import validate_answer
from ingestion_bench.retrieval_baseline.gold import ScopedFactEvidence


def _provenance(chunk_id: str) -> CitedChunkProvenance:
    return CitedChunkProvenance(
        chunk_id=chunk_id, fixture="x/y", doc_id="D", source_format="pdf",
        unit_indices=[0], source_element_ids=[], heading_source_element_ids=[],
        annotation_ids=[], source_refs=[],
    )


def _answer(
    *, evidence_sufficient: bool = True, claims: list[ClaimCitation] | None = None, retrieved_chunk_ids: list[str] | None = None
) -> AnswerResult:
    claims = claims if claims is not None else []
    cited = sorted({cid for c in claims for cid in c.cited_chunk_ids})
    return AnswerResult(
        question_id="Q1", question="q", answer_text="a", evidence_sufficient=evidence_sufficient,
        cited_chunks=cited, claim_citations=claims, retrieved_chunk_ids=retrieved_chunk_ids or ["c1", "c2"],
        model_identity="m", answer_latency_seconds=0.1,
    )


def test_citation_to_unretrieved_chunk_is_counted_invalid():
    claims = [ClaimCitation(claim_text="a", cited_chunk_ids=["c_never_retrieved"], cited_chunk_provenance=[])]
    answer = _answer(claims=claims, retrieved_chunk_ids=["c1", "c2"])
    result = validate_answer(answer, {}, {}, all_required_retrieved_at_max_k=True)
    assert result.invalid_citation_count == 1
    assert result.invalid_cited_chunk_ids == ["c_never_retrieved"]


def test_valid_citation_to_retrieved_chunk_is_not_invalid():
    claims = [ClaimCitation(claim_text="a", cited_chunk_ids=["c1"], cited_chunk_provenance=[_provenance("c1")])]
    answer = _answer(claims=claims, retrieved_chunk_ids=["c1", "c2"])
    result = validate_answer(answer, {}, {}, all_required_retrieved_at_max_k=True)
    assert result.invalid_citation_count == 0


def test_valid_citation_missing_provenance_is_flagged_unresolved():
    """A citation to a chunk that WAS retrieved but has no matching
    provenance entry on its own claim -- should never happen given how
    answer_generator.py constructs results, but validated mechanically
    rather than assumed (item 4 requirement 2)."""
    claims = [ClaimCitation(claim_text="a", cited_chunk_ids=["c1"], cited_chunk_provenance=[])]
    answer = _answer(claims=claims, retrieved_chunk_ids=["c1", "c2"])
    result = validate_answer(answer, {}, {}, all_required_retrieved_at_max_k=True)
    assert result.unresolved_provenance_citation_count == 1
    assert result.unresolved_provenance_chunk_ids == ["c1"]
    assert result.invalid_citation_count == 0  # it WAS retrieved -- a distinct failure class


def test_required_fact_citation_coverage_credits_fact_only_when_gold_chunk_cited():
    required = {"F1": [ScopedFactEvidence(fixture="x", fact_id="F1", status="available_with_chunks", chunk_ids=["c1"])]}
    covered = _answer(claims=[ClaimCitation(claim_text="a", cited_chunk_ids=["c1"], cited_chunk_provenance=[_provenance("c1")])])
    uncovered = _answer(claims=[ClaimCitation(claim_text="a", cited_chunk_ids=["c2"], cited_chunk_provenance=[_provenance("c2")])])

    covered_result = validate_answer(covered, required, {}, all_required_retrieved_at_max_k=True)
    uncovered_result = validate_answer(uncovered, required, {}, all_required_retrieved_at_max_k=True)

    assert covered_result.required_fact_citation_coverage == {"F1": True}
    assert covered_result.required_fact_citation_coverage_rate == 1.0
    assert uncovered_result.required_fact_citation_coverage == {"F1": False}
    assert uncovered_result.required_fact_citation_coverage_rate == 0.0


def test_required_fact_citation_coverage_rate_is_none_with_no_available_required_facts():
    required = {"F1": [ScopedFactEvidence(fixture="x", fact_id="F1", status="missing_from_ingestion")]}
    answer = _answer(claims=[])
    result = validate_answer(answer, required, {}, all_required_retrieved_at_max_k=None)
    assert result.required_fact_citation_coverage_rate is None


def test_forbidden_fact_citation_detected_only_via_a_valid_citation():
    forbidden = {"D1": [ScopedFactEvidence(fixture="x", fact_id="D1", status="available_with_chunks", chunk_ids=["c2"])]}
    leaked = _answer(claims=[ClaimCitation(claim_text="a", cited_chunk_ids=["c2"], cited_chunk_provenance=[_provenance("c2")])])
    clean = _answer(claims=[ClaimCitation(claim_text="a", cited_chunk_ids=["c1"], cited_chunk_provenance=[_provenance("c1")])])

    leaked_result = validate_answer(leaked, {}, forbidden, all_required_retrieved_at_max_k=True)
    clean_result = validate_answer(clean, {}, forbidden, all_required_retrieved_at_max_k=True)

    assert leaked_result.forbidden_fact_citation_count == 1
    assert leaked_result.forbidden_cited_fact_ids == ["D1"]
    assert leaked_result.forbidden_fact_citation_rate == 1.0
    assert clean_result.forbidden_fact_citation_rate == 0.0


def test_forbidden_fact_citation_via_unretrieved_chunk_id_does_not_count_as_a_leak():
    """An invalid citation (to a chunk never retrieved) that happens to
    equal a forbidden fact's gold chunk_id is not a genuine leak from
    THIS retrieval -- it's caught separately as an invalid citation."""
    forbidden = {"D1": [ScopedFactEvidence(fixture="x", fact_id="D1", status="available_with_chunks", chunk_ids=["c_never_retrieved"])]}
    answer = _answer(claims=[ClaimCitation(claim_text="a", cited_chunk_ids=["c_never_retrieved"], cited_chunk_provenance=[])])
    result = validate_answer(answer, {}, forbidden, all_required_retrieved_at_max_k=True)
    assert result.forbidden_fact_citation_count == 0
    assert result.invalid_citation_count == 1


def test_forbidden_fact_citation_rate_is_zero_not_none_with_no_available_forbidden_evidence():
    forbidden = {"D1": [ScopedFactEvidence(fixture="x", fact_id="D1", status="not_applicable")]}
    answer = _answer(claims=[])
    result = validate_answer(answer, {}, forbidden, all_required_retrieved_at_max_k=True)
    assert result.forbidden_fact_citation_rate == 0.0


def test_uncited_claim_count_and_citation_completeness():
    claims = [
        ClaimCitation(claim_text="cited", cited_chunk_ids=["c1"], cited_chunk_provenance=[_provenance("c1")]),
        ClaimCitation(claim_text="uncited", cited_chunk_ids=[], cited_chunk_provenance=[]),
    ]
    answer = _answer(claims=claims)
    result = validate_answer(answer, {}, {}, all_required_retrieved_at_max_k=True)
    assert result.uncited_claim_count == 1
    assert result.total_claim_count == 2
    assert result.citation_completeness == 0.5


def test_citation_completeness_is_none_with_zero_claims():
    answer = _answer(claims=[])
    result = validate_answer(answer, {}, {}, all_required_retrieved_at_max_k=True)
    assert result.citation_completeness is None


def test_evidence_sufficiency_accuracy_scored_only_when_retrieval_incomplete():
    insufficient_answer = _answer(evidence_sufficient=False)
    overclaiming_answer = _answer(evidence_sufficient=True)

    correct = validate_answer(insufficient_answer, {}, {}, all_required_retrieved_at_max_k=False)
    wrong = validate_answer(overclaiming_answer, {}, {}, all_required_retrieved_at_max_k=False)
    not_scored_complete = validate_answer(overclaiming_answer, {}, {}, all_required_retrieved_at_max_k=True)
    not_scored_none = validate_answer(overclaiming_answer, {}, {}, all_required_retrieved_at_max_k=None)

    assert correct.evidence_sufficiency_expected_false is True
    assert correct.evidence_sufficiency_accuracy is True
    assert wrong.evidence_sufficiency_accuracy is False
    assert not_scored_complete.evidence_sufficiency_expected_false is False
    assert not_scored_complete.evidence_sufficiency_accuracy is None
    assert not_scored_none.evidence_sufficiency_accuracy is None


def test_token_cost_latency_pass_through_from_answer():
    answer = AnswerResult(
        question_id="Q1", question="q", answer_text="a", evidence_sufficient=True,
        cited_chunks=[], claim_citations=[], retrieved_chunk_ids=["c1"],
        model_identity="gpt-4o-mini", input_tokens=100, output_tokens=50,
        estimated_cost_usd=0.000045, answer_latency_seconds=1.234,
    )
    result = validate_answer(answer, {}, {}, all_required_retrieved_at_max_k=True)
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    assert result.estimated_cost_usd == 0.000045
    assert result.answer_latency_seconds == 1.234
