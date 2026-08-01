"""Stage 7A.2: answer-generator tests (FakeAnswerGenerator only -- no
network, no API key needed). Proves the "no answer claim can introduce a
new source reference" invariant: every CitedChunkProvenance field is
copied verbatim from the retrieval context, and a citation to a chunk
that was never retrieved gets no fabricated provenance at all.
"""

from __future__ import annotations

from ingestion_bench.answer_baseline.answer_generator import FakeAnswerClaim, FakeAnswerGenerator, FakeAnswerResponse
from ingestion_bench.retrieval_baseline.retrieval import RetrievalResult


def _result(chunk_id: str) -> RetrievalResult:
    return RetrievalResult(
        rank=1, score=0.9, chunk_id=chunk_id, content_sha256="a" * 64, retrieval_text="some retrieved text",
        fixture="parity/PARITY_001.pdf", doc_id="PARITY_001", source_format="pdf", unit_indices=[2],
        source_element_ids=["el_1"], heading_source_element_ids=["h_1"], annotation_ids=["ann_1"],
        source_refs=[{"page": 1}], heading_path=["Section 1"],
    )


def test_citing_a_retrieved_chunk_resolves_provenance_copied_verbatim():
    retrieved = [_result("c1")]
    responses = {
        "Q1": FakeAnswerResponse(
            evidence_sufficient=True, answer_text="ans",
            claims=[FakeAnswerClaim(claim_text="claim citing c1", cited_chunk_ids=["c1"])],
        )
    }
    generator = FakeAnswerGenerator(responses)
    result = generator.generate("Q1", "q?", retrieved)

    assert result.cited_chunks == ["c1"]
    provenance = result.claim_citations[0].cited_chunk_provenance[0]
    assert provenance.chunk_id == "c1"
    assert provenance.fixture == "parity/PARITY_001.pdf"
    assert provenance.doc_id == "PARITY_001"
    assert provenance.source_format == "pdf"
    assert provenance.unit_indices == [2]
    assert provenance.source_element_ids == ["el_1"]
    assert provenance.heading_source_element_ids == ["h_1"]
    assert provenance.annotation_ids == ["ann_1"]
    assert provenance.source_refs == [{"page": 1}]


def test_citing_an_unretrieved_chunk_id_produces_no_fabricated_provenance():
    retrieved = [_result("c1")]
    responses = {
        "Q1": FakeAnswerResponse(
            evidence_sufficient=True, answer_text="ans",
            claims=[FakeAnswerClaim(claim_text="claim citing a phantom chunk", cited_chunk_ids=["c_phantom"])],
        )
    }
    generator = FakeAnswerGenerator(responses)
    result = generator.generate("Q1", "q?", retrieved)

    assert result.cited_chunks == ["c_phantom"]
    assert result.claim_citations[0].cited_chunk_provenance == []
    assert "c_phantom" not in result.retrieved_chunk_ids


def test_retrieved_chunk_ids_on_result_matches_supplied_retrieval_context():
    retrieved = [_result("c1"), _result("c2")]
    generator = FakeAnswerGenerator()
    result = generator.generate("Q1", "q?", retrieved)
    assert result.retrieved_chunk_ids == ["c1", "c2"]


def test_default_response_cites_every_retrieved_chunk_once():
    retrieved = [_result("c1"), _result("c2")]
    generator = FakeAnswerGenerator()
    result = generator.generate("Q1", "q?", retrieved)
    assert set(result.cited_chunks) == {"c1", "c2"}
    assert result.model_identity == FakeAnswerGenerator.model_identity


def test_fake_generator_has_no_token_usage_or_cost():
    retrieved = [_result("c1")]
    generator = FakeAnswerGenerator()
    result = generator.generate("Q1", "q?", retrieved)
    assert result.input_tokens is None
    assert result.output_tokens is None
    assert result.estimated_cost_usd is None
