"""Stage 7A.3: pure, deterministic view-model construction.

Every field on every dataclass below is COPIED verbatim from an
already-computed `QuestionAnswerResult` (Stage 7A.2/7A.2a's own frozen
output) -- this module never accepts, trusts, or renders any
user-supplied chunk id, source reference, or provenance value, and it
never performs retrieval or answer generation itself. A citation is only
ever represented here via `ClaimCitation.cited_chunk_provenance`, which
Stage 7A.2's own answer_generator.py resolves ONLY for chunk_ids that
were actually retrieved (never fabricated) -- so a `CitedChunkView`
constructed by this module always resolves to a real retrieved chunk by
construction, never by a separate check bolted on afterward.
"""

from __future__ import annotations

from dataclasses import dataclass

from ingestion_bench.answer_baseline.evaluation import QuestionAnswerResult
from ingestion_bench.demo.status_labels import detect_explicit_status_labels


@dataclass(frozen=True)
class CitedChunkView:
    chunk_id: str
    fixture: str
    doc_id: str
    source_format: str
    unit_indices: list[int]
    source_element_ids: list[str]
    heading_source_element_ids: list[str]
    annotation_ids: list[str]
    source_refs: list[dict]
    chunk_text: str
    status_labels: list[str]
    # Informational only (item 8): true when this chunk's fixture differs
    # from the question's own PRINCIPAL fixture (the majority fixture
    # among its cited chunks). Evidence is never removed/hidden for this
    # -- only flagged.
    cross_document_warning: bool


@dataclass(frozen=True)
class ClaimView:
    claim_text: str
    cited_chunks: list[CitedChunkView]
    # A citation whose chunk_id has NO resolved provenance (the answer
    # model cited a chunk_id that was never actually retrieved) is
    # counted here, never rendered as a fabricated CitedChunkView -- see
    # module docstring.
    unresolved_citation_count: int = 0


@dataclass(frozen=True)
class QuestionDemoView:
    question_id: str
    question: str
    difficulty: str
    answer_text: str
    evidence_sufficient: bool
    claims: list[ClaimView]
    retrieved_chunk_ids: list[str]
    model_identity: str
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None
    answer_latency_seconds: float
    answer_text_correctness_human_review: str
    citation_support_human_review: str


def _principal_fixture(question_result: QuestionAnswerResult) -> str | None:
    """The fixture of the question's own BEST-RANKED cited chunk (lowest
    `RetrievalResult.rank`, i.e. the chunk Stage 7A.1's frozen retrieval
    itself considered most relevant to the query) -- a purely structural,
    already-computed signal, never an inferred one. Deliberately NOT a
    majority-vote over the deduplicated `cited_chunks` set: that set is
    alphabetically sorted by chunk_id (model.py), so a naive majority/
    tie-break over it can pick an arbitrary fixture when a question cites
    exactly one chunk per fixture (e.g. Q_DIRECT_003, which cites one
    PARITY_001 chunk at rank 3 and one STRESS_PPTX_001 chunk at rank 4 in
    the SAME claim) -- rank breaks that tie correctly and consistently
    with claim-frequency-weighted cases like Q_CONSOLIDATION_001, where
    PARITY_001 is both rank-1 AND cited by 4x as many claims. None when
    nothing was validly cited."""
    chunk_by_id = {r.chunk_id: r for r in question_result.top_k_results}
    cited_chunks = [chunk_by_id[cid] for cid in question_result.answer.cited_chunks if cid in chunk_by_id]
    if not cited_chunks:
        return None
    return min(cited_chunks, key=lambda r: r.rank).fixture


def build_question_view(question_result: QuestionAnswerResult) -> QuestionDemoView:
    chunk_by_id = {r.chunk_id: r for r in question_result.top_k_results}
    principal_fixture = _principal_fixture(question_result)

    claims: list[ClaimView] = []
    for claim in question_result.answer.claim_citations:
        cited_views: list[CitedChunkView] = []
        for provenance in claim.cited_chunk_provenance:
            retrieved = chunk_by_id.get(provenance.chunk_id)
            chunk_text = retrieved.retrieval_text if retrieved is not None else ""
            cited_views.append(
                CitedChunkView(
                    chunk_id=provenance.chunk_id,
                    fixture=provenance.fixture,
                    doc_id=provenance.doc_id,
                    source_format=provenance.source_format,
                    unit_indices=list(provenance.unit_indices),
                    source_element_ids=list(provenance.source_element_ids),
                    heading_source_element_ids=list(provenance.heading_source_element_ids),
                    annotation_ids=list(provenance.annotation_ids),
                    source_refs=list(provenance.source_refs),
                    chunk_text=chunk_text,
                    status_labels=detect_explicit_status_labels(chunk_text),
                    cross_document_warning=(
                        principal_fixture is not None and provenance.fixture != principal_fixture
                    ),
                )
            )
        unresolved = len(claim.cited_chunk_ids) - len(claim.cited_chunk_provenance)
        claims.append(ClaimView(claim_text=claim.claim_text, cited_chunks=cited_views, unresolved_citation_count=unresolved))

    return QuestionDemoView(
        question_id=question_result.question_id,
        question=question_result.question,
        difficulty=question_result.difficulty,
        answer_text=question_result.answer.answer_text,
        evidence_sufficient=question_result.answer.evidence_sufficient,
        claims=claims,
        retrieved_chunk_ids=list(question_result.answer.retrieved_chunk_ids),
        model_identity=question_result.answer.model_identity,
        input_tokens=question_result.answer.input_tokens,
        output_tokens=question_result.answer.output_tokens,
        estimated_cost_usd=question_result.answer.estimated_cost_usd,
        answer_latency_seconds=question_result.answer.answer_latency_seconds,
        answer_text_correctness_human_review=question_result.answer_text_correctness_human_review,
        citation_support_human_review=question_result.citation_support_human_review,
    )


def build_all_question_views(question_results: list[QuestionAnswerResult]) -> list[QuestionDemoView]:
    return [build_question_view(qr) for qr in question_results]
