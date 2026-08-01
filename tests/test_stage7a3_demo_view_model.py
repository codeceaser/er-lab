"""Stage 7A.3: view-model construction tests.

Hand-built data proves the mechanics (unresolved citations, cross-doc
warnings, explicit-label detection); a real-data test against the
actual committed Stage 7A.2/7A.2a answer run proves the Q_CONSOLIDATION_001
finding surfaces correctly end to end.
"""

from __future__ import annotations

import json
from pathlib import Path

from ingestion_bench.answer_baseline import config
from ingestion_bench.answer_baseline.evaluation import AnswerEvaluationRun, QuestionAnswerResult
from ingestion_bench.answer_baseline.model import AnswerResult, CitedChunkProvenance, ClaimCitation
from ingestion_bench.answer_baseline.validation import CitationValidationResult
from ingestion_bench.demo.status_labels import detect_explicit_status_labels
from ingestion_bench.demo.view_model import build_question_view
from ingestion_bench.retrieval_baseline.retrieval import RetrievalResult

REPO_ROOT = Path(__file__).resolve().parent.parent


def _retrieval_result(chunk_id: str, rank: int, fixture: str, text: str) -> RetrievalResult:
    return RetrievalResult(
        rank=rank, score=0.9, chunk_id=chunk_id, content_sha256="a" * 64, retrieval_text=text,
        fixture=fixture, doc_id=fixture.split("/")[-1], source_format="pdf", unit_indices=[0],
        source_element_ids=[f"el_{chunk_id}"], heading_source_element_ids=[], annotation_ids=[],
        source_refs=[{"page": rank}], heading_path=[],
    )


def _provenance(chunk_id: str, fixture: str) -> CitedChunkProvenance:
    return CitedChunkProvenance(
        chunk_id=chunk_id, fixture=fixture, doc_id=fixture.split("/")[-1], source_format="pdf",
        unit_indices=[0], source_element_ids=[f"el_{chunk_id}"], heading_source_element_ids=[],
        annotation_ids=[], source_refs=[{"page": 1}],
    )


def _validation_stub(question_id: str) -> CitationValidationResult:
    return CitationValidationResult(
        question_id=question_id, invalid_citation_count=0, unresolved_provenance_citation_count=0,
        required_fact_citation_coverage={}, required_fact_citation_coverage_rate=None,
        forbidden_fact_citation_count=0, cited_chunk_forbidden_evidence_exposure_rate=0.0,
        uncited_claim_count=0, total_claim_count=1, citation_completeness=1.0,
        evidence_sufficiency_expected_false=False, evidence_sufficiency_accuracy=None,
        input_tokens=10, output_tokens=5, estimated_cost_usd=0.0001, answer_latency_seconds=0.5,
    )


def test_unresolved_citation_is_counted_never_rendered_as_a_fake_chunk():
    """A claim citing a chunk_id with NO resolved provenance (invalid
    citation) must show up as a COUNT, never as a fabricated
    CitedChunkView with invented fields."""
    retrieved = [_retrieval_result("c1", 1, "x/y.pdf", "some text")]
    claim = ClaimCitation(claim_text="a claim", cited_chunk_ids=["c1", "c_phantom"], cited_chunk_provenance=[_provenance("c1", "x/y.pdf")])
    answer = AnswerResult(
        question_id="Q1", question="q", answer_text="a", evidence_sufficient=True,
        cited_chunks=["c1", "c_phantom"], claim_citations=[claim], retrieved_chunk_ids=["c1"],
        model_identity="m", answer_latency_seconds=0.1,
    )
    qr = QuestionAnswerResult(
        question_id="Q1", question="q", difficulty="direct", answer_rubric="r",
        top_k_results=retrieved, answer=answer, validation=_validation_stub("Q1"),
    )
    view = build_question_view(qr)
    assert len(view.claims) == 1
    assert view.claims[0].unresolved_citation_count == 1
    assert [c.chunk_id for c in view.claims[0].cited_chunks] == ["c1"]


def test_provenance_fields_copied_verbatim_from_answer_result():
    retrieved = [_retrieval_result("c1", 1, "parity/PARITY_001.pdf", "The RTO is 4 hours.")]
    provenance = _provenance("c1", "parity/PARITY_001.pdf")
    claim = ClaimCitation(claim_text="a claim", cited_chunk_ids=["c1"], cited_chunk_provenance=[provenance])
    answer = AnswerResult(
        question_id="Q1", question="q", answer_text="a", evidence_sufficient=True,
        cited_chunks=["c1"], claim_citations=[claim], retrieved_chunk_ids=["c1"],
        model_identity="m", answer_latency_seconds=0.1,
    )
    qr = QuestionAnswerResult(
        question_id="Q1", question="q", difficulty="direct", answer_rubric="r",
        top_k_results=retrieved, answer=answer, validation=_validation_stub("Q1"),
    )
    view = build_question_view(qr)
    chunk_view = view.claims[0].cited_chunks[0]
    assert chunk_view.chunk_id == provenance.chunk_id
    assert chunk_view.fixture == provenance.fixture
    assert chunk_view.doc_id == provenance.doc_id
    assert chunk_view.source_format == provenance.source_format
    assert chunk_view.unit_indices == provenance.unit_indices
    assert chunk_view.source_element_ids == provenance.source_element_ids
    assert chunk_view.heading_source_element_ids == provenance.heading_source_element_ids
    assert chunk_view.annotation_ids == provenance.annotation_ids
    assert chunk_view.source_refs == provenance.source_refs
    assert chunk_view.chunk_text == "The RTO is 4 hours."


def test_every_cited_chunk_view_resolves_to_a_retrieved_chunk():
    retrieved = [_retrieval_result("c1", 1, "x/y.pdf", "text one"), _retrieval_result("c2", 2, "x/y.pdf", "text two")]
    claims = [
        ClaimCitation(claim_text="a", cited_chunk_ids=["c1"], cited_chunk_provenance=[_provenance("c1", "x/y.pdf")]),
        ClaimCitation(claim_text="b", cited_chunk_ids=["c2"], cited_chunk_provenance=[_provenance("c2", "x/y.pdf")]),
    ]
    answer = AnswerResult(
        question_id="Q1", question="q", answer_text="a", evidence_sufficient=True,
        cited_chunks=["c1", "c2"], claim_citations=claims, retrieved_chunk_ids=["c1", "c2"],
        model_identity="m", answer_latency_seconds=0.1,
    )
    qr = QuestionAnswerResult(
        question_id="Q1", question="q", difficulty="direct", answer_rubric="r",
        top_k_results=retrieved, answer=answer, validation=_validation_stub("Q1"),
    )
    view = build_question_view(qr)
    displayed_ids = {c.chunk_id for claim in view.claims for c in claim.cited_chunks}
    assert displayed_ids <= set(view.retrieved_chunk_ids)
    assert displayed_ids == {"c1", "c2"}


def test_cross_document_warning_flags_the_worse_ranked_different_fixture_chunk():
    """Two chunks cited by ONE claim, different fixtures -- the
    better-ranked (rank 1) chunk's fixture is principal; the
    worse-ranked (rank 2) chunk from a DIFFERENT fixture gets the
    warning, its own same-fixture counterpart never does."""
    retrieved = [
        _retrieval_result("c_main", 1, "parity/PARITY_001.pdf", "Payment Settlement RTO is 4 hours."),
        _retrieval_result("c_other", 2, "stress/STRESS_PPTX_001.pptx", "Primary annotation: RTO target 4h"),
    ]
    claim = ClaimCitation(
        claim_text="RTO is 4 hours",
        cited_chunk_ids=["c_main", "c_other"],
        cited_chunk_provenance=[_provenance("c_main", "parity/PARITY_001.pdf"), _provenance("c_other", "stress/STRESS_PPTX_001.pptx")],
    )
    answer = AnswerResult(
        question_id="Q1", question="q", answer_text="a", evidence_sufficient=True,
        cited_chunks=["c_main", "c_other"], claim_citations=[claim], retrieved_chunk_ids=["c_main", "c_other"],
        model_identity="m", answer_latency_seconds=0.1,
    )
    qr = QuestionAnswerResult(
        question_id="Q1", question="q", difficulty="direct", answer_rubric="r",
        top_k_results=retrieved, answer=answer, validation=_validation_stub("Q1"),
    )
    view = build_question_view(qr)
    by_id = {c.chunk_id: c for c in view.claims[0].cited_chunks}
    assert by_id["c_main"].cross_document_warning is False
    assert by_id["c_other"].cross_document_warning is True


def test_no_cross_document_warning_when_every_citation_shares_one_fixture():
    retrieved = [_retrieval_result("c1", 1, "x/y.pdf", "text"), _retrieval_result("c2", 2, "x/y.pdf", "more text")]
    claims = [
        ClaimCitation(claim_text="a", cited_chunk_ids=["c1"], cited_chunk_provenance=[_provenance("c1", "x/y.pdf")]),
        ClaimCitation(claim_text="b", cited_chunk_ids=["c2"], cited_chunk_provenance=[_provenance("c2", "x/y.pdf")]),
    ]
    answer = AnswerResult(
        question_id="Q1", question="q", answer_text="a", evidence_sufficient=True,
        cited_chunks=["c1", "c2"], claim_citations=claims, retrieved_chunk_ids=["c1", "c2"],
        model_identity="m", answer_latency_seconds=0.1,
    )
    qr = QuestionAnswerResult(
        question_id="Q1", question="q", difficulty="direct", answer_rubric="r",
        top_k_results=retrieved, answer=answer, validation=_validation_stub("Q1"),
    )
    view = build_question_view(qr)
    assert all(not c.cross_document_warning for claim in view.claims for c in claim.cited_chunks)


def test_detect_explicit_status_labels_is_literal_substring_only():
    assert detect_explicit_status_labels("Superseded annotation: RTO target 6h (draft, do not use)") == [
        "superseded",
        "draft",
    ]
    assert detect_explicit_status_labels("Primary annotation: RTO target 4h") == []
    assert detect_explicit_status_labels("This control is CURRENT and active.") == ["current"]
    assert detect_explicit_status_labels("Nothing status-related here.") == []


def test_real_committed_q_consolidation_001_exposes_stress_pptx_citation():
    """Against the ACTUAL committed Stage 7A.2/7A.2a answer run: the
    RTO=4h claim's citations include the Payment Settlement narrative
    chunk (principal, rank 1) and the STRESS_PPTX_001 annotation chunk,
    and the STRESS_PPTX_001 one -- and only that one -- must be flagged
    as a cross-document citation."""
    results_path = config.REPORTS_ROOT / "stage7a2_vector_answer_results.json"
    if not results_path.exists():
        import pytest

        pytest.skip("reports/stage7a2_vector_answer_results.json not present in this environment")
    run = AnswerEvaluationRun.model_validate(json.loads(results_path.read_text(encoding="utf-8")))
    qr = next(q for q in run.question_results if q.question_id == "Q_CONSOLIDATION_001")
    view = build_question_view(qr)

    flagged = [c for claim in view.claims for c in claim.cited_chunks if c.cross_document_warning]
    assert len(flagged) == 1
    assert flagged[0].fixture == "stress/STRESS_PPTX_001.pptx"
    assert "4h" in flagged[0].chunk_text or "4 h" in flagged[0].chunk_text.lower()

    not_flagged = [c for claim in view.claims for c in claim.cited_chunks if not c.cross_document_warning]
    assert all(c.fixture == "parity/PARITY_001.pdf" for c in not_flagged)
