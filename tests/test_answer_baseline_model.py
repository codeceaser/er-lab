"""Stage 7A.2: strict model tests for AnswerResult/ClaimCitation/CitedChunkProvenance."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ingestion_bench.answer_baseline.model import AnswerResult, CitedChunkProvenance, ClaimCitation


def _provenance(chunk_id: str = "c1") -> CitedChunkProvenance:
    return CitedChunkProvenance(
        chunk_id=chunk_id, fixture="x/y", doc_id="D", source_format="pdf",
        unit_indices=[0], source_element_ids=[], heading_source_element_ids=[],
        annotation_ids=[], source_refs=[],
    )


def test_claim_citation_allows_provenance_as_proper_subset_of_cited_ids():
    """A citation to a chunk_id that was never retrieved legitimately has
    NO provenance entry -- this must not raise; it is exactly the
    "invalid citation" case validation.py is responsible for detecting."""
    claim = ClaimCitation(claim_text="x", cited_chunk_ids=["c1", "c_unretrieved"], cited_chunk_provenance=[_provenance("c1")])
    assert claim.cited_chunk_ids == ["c1", "c_unretrieved"]
    assert [p.chunk_id for p in claim.cited_chunk_provenance] == ["c1"]


def test_claim_citation_rejects_provenance_for_an_id_never_cited():
    with pytest.raises(ValidationError):
        ClaimCitation(claim_text="x", cited_chunk_ids=["c1"], cited_chunk_provenance=[_provenance("c1"), _provenance("c2")])


def test_answer_result_requires_cited_chunks_to_equal_union_of_claims():
    claims = [ClaimCitation(claim_text="a", cited_chunk_ids=["c1"], cited_chunk_provenance=[_provenance("c1")])]
    with pytest.raises(ValidationError):
        AnswerResult(
            question_id="Q1", question="q", answer_text="a", evidence_sufficient=True,
            cited_chunks=["c1", "c2"], claim_citations=claims, retrieved_chunk_ids=["c1"],
            model_identity="m", answer_latency_seconds=0.1,
        )


def test_answer_result_accepts_consistent_cited_chunks():
    claims = [ClaimCitation(claim_text="a", cited_chunk_ids=["c1"], cited_chunk_provenance=[_provenance("c1")])]
    result = AnswerResult(
        question_id="Q1", question="q", answer_text="a", evidence_sufficient=True,
        cited_chunks=["c1"], claim_citations=claims, retrieved_chunk_ids=["c1"],
        model_identity="m", answer_latency_seconds=0.1,
    )
    assert result.cited_chunks == ["c1"]


def test_answer_result_permits_a_cited_chunk_never_present_in_retrieved_chunk_ids():
    """Structurally allowed at the model level -- this is data an invalid
    real-world model response could produce; validation.py, not model.py,
    is responsible for flagging it."""
    claims = [ClaimCitation(claim_text="a", cited_chunk_ids=["c_bad"], cited_chunk_provenance=[])]
    result = AnswerResult(
        question_id="Q1", question="q", answer_text="a", evidence_sufficient=True,
        cited_chunks=["c_bad"], claim_citations=claims, retrieved_chunk_ids=["c1"],
        model_identity="m", answer_latency_seconds=0.1,
    )
    assert result.cited_chunks == ["c_bad"]
    assert "c_bad" not in result.retrieved_chunk_ids


def test_answer_result_rejects_extra_fields():
    with pytest.raises(ValidationError):
        AnswerResult(
            question_id="Q1", question="q", answer_text="a", evidence_sufficient=True,
            cited_chunks=[], claim_citations=[], retrieved_chunk_ids=[],
            model_identity="m", answer_latency_seconds=0.1, unexpected_field="nope",
        )
