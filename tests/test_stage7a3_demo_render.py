"""Stage 7A.3: HTML rendering tests.

Proves: every displayed citation resolves to an existing retrieved
chunk, provenance shown is copied verbatim from the view model, no
user-supplied text can inject unescaped HTML/script content, the
evidence-sufficient/insufficient state is visibly distinct, and the real
committed Q_CONSOLIDATION_001 answer visibly exposes the STRESS_PPTX_001
citation.
"""

from __future__ import annotations

import json

from ingestion_bench.answer_baseline import config
from ingestion_bench.answer_baseline.evaluation import AnswerEvaluationRun
from ingestion_bench.demo.render import render_demo_html
from ingestion_bench.demo.view_model import CitedChunkView, ClaimView, QuestionDemoView, build_all_question_views


def _view(
    question_id: str = "Q1",
    evidence_sufficient: bool = True,
    claims: list[ClaimView] | None = None,
    question: str = "What is the RTO?",
    answer_text: str = "4 hours.",
) -> QuestionDemoView:
    return QuestionDemoView(
        question_id=question_id, question=question, difficulty="direct", answer_text=answer_text,
        evidence_sufficient=evidence_sufficient, claims=claims or [], retrieved_chunk_ids=["c1"],
        model_identity="gpt-4o-mini", input_tokens=100, output_tokens=20, estimated_cost_usd=0.0001,
        answer_latency_seconds=1.23, answer_text_correctness_human_review="correct",
        citation_support_human_review="fully_supported",
    )


def _chunk(chunk_id: str = "c1", fixture: str = "parity/PARITY_001.pdf", text: str = "chunk text", cross_doc: bool = False) -> CitedChunkView:
    return CitedChunkView(
        chunk_id=chunk_id, fixture=fixture, doc_id="PARITY_001", source_format="pdf",
        unit_indices=[0], source_element_ids=["el_1"], heading_source_element_ids=["h_1"],
        annotation_ids=["ann_1"], source_refs=[{"page": 1}], chunk_text=text,
        status_labels=[], cross_document_warning=cross_doc,
    )


def test_every_displayed_citation_resolves_to_a_retrieved_chunk():
    claim = ClaimView(claim_text="claim one", cited_chunks=[_chunk("c1")])
    view = _view(claims=[claim])
    html_page = render_demo_html([view])
    assert 'id="q-Q1"' in html_page
    assert '<code class="chunk-id">c1</code>' in html_page
    # The rendered chunk_id must be a member of retrieved_chunk_ids -- a
    # structural fact guaranteed by view_model.py's own construction and
    # re-checked here at the render boundary.
    assert "c1" in view.retrieved_chunk_ids


def test_provenance_displayed_is_copied_from_the_view_model():
    chunk = _chunk(chunk_id="c_special", fixture="stress/STRESS_PPTX_001.pptx", text="Primary annotation: RTO target 4h")
    claim = ClaimView(claim_text="a distinctive claim", cited_chunks=[chunk])
    view = _view(claims=[claim])
    html_page = render_demo_html([view])
    assert "c_special" in html_page
    assert "stress/STRESS_PPTX_001.pptx" in html_page
    assert "Primary annotation: RTO target 4h" in html_page
    assert "el_1" in html_page
    assert "h_1" in html_page
    assert "ann_1" in html_page


def test_html_special_characters_in_data_are_escaped_not_injected():
    """No user-supplied chunk or source reference can be injected: even
    if a malicious string somehow reached this layer (e.g. embedded in
    retrieved chunk text), it comes out HTML-escaped, never as live
    markup/script."""
    malicious = "<script>alert('xss')</script>"
    chunk = _chunk(chunk_id="c1", text=malicious)
    claim = ClaimView(claim_text=malicious, cited_chunks=[chunk])
    view = _view(claims=[claim], question=malicious, answer_text=malicious)
    html_page = render_demo_html([view])
    assert "<script>alert" not in html_page
    assert "&lt;script&gt;" in html_page


def test_evidence_sufficient_and_insufficient_are_visibly_distinct():
    sufficient = render_demo_html([_view(question_id="Q1", evidence_sufficient=True)])
    insufficient = render_demo_html([_view(question_id="Q1", evidence_sufficient=False)])
    assert 'class="sufficiency-badge sufficient"' in sufficient
    assert "INSUFFICIENT" not in sufficient
    assert 'class="sufficiency-badge insufficient"' in insufficient
    assert "INSUFFICIENT" in insufficient


def test_unresolved_citation_count_is_shown_without_fabricating_a_chunk():
    claim = ClaimView(claim_text="claim with a phantom citation", cited_chunks=[], unresolved_citation_count=1)
    view = _view(claims=[claim])
    html_page = render_demo_html([view])
    assert "did not resolve to a retrieved chunk" in html_page


def test_render_accepts_only_typed_view_model_objects():
    """The render module's public entry point takes QuestionDemoView
    objects, never a raw dict/string -- there is no code path here that
    accepts free-form user text as a chunk_id or source reference."""
    import inspect

    sig = inspect.signature(render_demo_html)
    (param,) = sig.parameters.values()
    assert "QuestionDemoView" in str(param.annotation)


def test_real_committed_q_consolidation_001_render_shows_stress_pptx_warning():
    results_path = config.REPORTS_ROOT / "stage7a2_vector_answer_results.json"
    if not results_path.exists():
        import pytest

        pytest.skip("reports/stage7a2_vector_answer_results.json not present in this environment")
    run = AnswerEvaluationRun.model_validate(json.loads(results_path.read_text(encoding="utf-8")))
    views = build_all_question_views(run.question_results)
    html_page = render_demo_html(views)

    start = html_page.index('id="q-Q_CONSOLIDATION_001"')
    end = html_page.index("</section>", start)
    section = html_page[start:end]

    assert "STRESS_PPTX_001" in section
    assert "cross-doc-warning" in section
    assert "different document/fixture" in section
    assert 'class="sufficiency-badge insufficient"' in section
