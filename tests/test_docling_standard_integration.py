"""Integration tests against the real generated benchmark fixtures
(Stage 5A). These run the actual Docling standard-local pipeline -- no
mocking of Docling itself -- against fixtures/generated/*.{pdf,docx,pptx}.

Deliberately does NOT read reference_manifest.json from the adapter or
mapper (neither ever does) -- expected facts used for assertions here are
hard-coded in this test/evaluation layer only, exactly as chunking rule 12
requires ("The adapter and runner must not read [the manifest] while
creating CanonicalDocument").

Each fixture is converted at most once per test session (module-level
cache) -- conversion cost is real wall-clock time (model inference), and
many assertions target the same fixture's output.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion_bench.adapters.docling_standard import DoclingStandardAdapter
from ingestion_bench.canonical.hashing import stable_canonical_hash
from ingestion_bench.chunking import ChunkingConfig, DocumentRevisionContext, chunk_document, compute_document_revision_id

FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "generated"

_CACHE: dict[str, object] = {}


@pytest.fixture(scope="module")
def adapter(tmp_path_factory) -> DoclingStandardAdapter:
    debug_dir = tmp_path_factory.mktemp("docling_raw")
    assets_dir = tmp_path_factory.mktemp("assets")
    return DoclingStandardAdapter(raw_debug_dir=debug_dir, assets_dir=assets_dir)


def _convert(adapter: DoclingStandardAdapter, relative_path: str):
    if relative_path not in _CACHE:
        _CACHE[relative_path] = adapter.convert(FIXTURES_ROOT / relative_path, source_root=FIXTURES_ROOT)
    return _CACHE[relative_path]


def _chunk(document, doc_id: str):
    revision_context = DocumentRevisionContext(
        logical_document_id=doc_id,
        document_revision_id=compute_document_revision_id(doc_id, document.source_sha256),
        source_document_sha256=document.source_sha256,
    )
    return chunk_document(document, ChunkingConfig(), revision_context=revision_context)


def _all_text(document) -> str:
    return "\n".join([h.text for h in document.headings] + [p.text for p in document.paragraphs] + [li.text for li in document.list_items])


# --- A. parity PDF / DOCX / PPTX ---------------------------------------------


@pytest.mark.parametrize("relative_path", ["parity/PARITY_001.pdf", "parity/PARITY_001.docx", "parity/PARITY_001.pptx"])
def test_parity_conversion_succeeds_and_validates(adapter, relative_path):
    result = _convert(adapter, relative_path)
    assert result.conversion_status in ("success", "partial"), result.errors
    assert result.canonical_document is not None
    assert len(result.canonical_document.units) >= 1


@pytest.mark.parametrize("relative_path", ["parity/PARITY_001.pdf", "parity/PARITY_001.docx", "parity/PARITY_001.pptx"])
def test_parity_core_paragraph_text_and_identifiers_present(adapter, relative_path):
    result = _convert(adapter, relative_path)
    text = _all_text(result.canonical_document)
    for expected in ("APP-224510", "O-31", "C-88", "P-205"):
        assert expected in text, f"{expected!r} missing from {relative_path}"


@pytest.mark.parametrize("relative_path", ["parity/PARITY_001.pdf", "parity/PARITY_001.docx", "parity/PARITY_001.pptx"])
def test_parity_native_table_cells_present(adapter, relative_path):
    result = _convert(adapter, relative_path)
    document = result.canonical_document
    assert len(document.tables) >= 1
    cell_texts = {c.text for t in document.tables for c in t.cells}
    assert "RTO" in cell_texts
    assert "4 hours" in cell_texts


@pytest.mark.parametrize("relative_path", ["parity/PARITY_001.pdf", "parity/PARITY_001.docx", "parity/PARITY_001.pptx"])
def test_parity_at_least_one_picture_retained(adapter, relative_path):
    result = _convert(adapter, relative_path)
    assert len(result.canonical_document.pictures) >= 1
    picture = result.canonical_document.pictures[0]
    assert len(picture.content_sha256) == 64
    assert picture.artifact_ref


def test_parity_pdf_caption_is_linked_to_its_picture(adapter):
    """Caption-to-picture linking is proven to work via Docling's PDF
    layout backend (verified against the real DoclingDocument during
    Stage 5A implementation) -- DOCX/PPTX are NOT asserted here; see
    reports/stage5a_docling_standard_baseline.md for the documented
    per-format limitation (Docling's DOCX/PPTX backends did not populate
    PictureItem.captions for this fixture in docling 2.114.0/
    docling-core 2.87.1)."""
    result = _convert(adapter, "parity/PARITY_001.pdf")
    document = result.canonical_document
    assert len(document.captions) == 1
    assert document.captions[0].target_picture_id == document.pictures[0].picture_id
    assert "Figure 1" in document.captions[0].text


@pytest.mark.parametrize("relative_path", ["parity/PARITY_001.pdf", "parity/PARITY_001.docx", "parity/PARITY_001.pptx"])
def test_parity_canonical_chunks_validate_with_nonempty_retrieval_text(adapter, relative_path):
    result = _convert(adapter, relative_path)
    chunks = _chunk(result.canonical_document, "PARITY_001")
    assert len(chunks) >= 1
    textual_chunks = [c for c in chunks if c.chunk_type in ("text", "mixed")]
    assert textual_chunks
    for chunk in textual_chunks:
        assert chunk.retrieval_text.strip() != ""


# --- B. scanned PDF ------------------------------------------------------------


def test_scanned_pdf_has_no_digital_text_layer_per_existing_fixture_test():
    """Reuses the same content-stream check test_fixture_generation.py
    already established, rather than re-implementing PDF parsing here --
    confirms the premise still holds for the exact file this test
    converts."""
    from test_fixture_generation import _pdf_glyph_operator_count

    path = FIXTURES_ROOT / "stress" / "STRESS_SCANNED_001.pdf"
    assert _pdf_glyph_operator_count(path) == 0


def test_scanned_pdf_docling_ocr_returns_nonempty_source_text(adapter):
    result = _convert(adapter, "stress/STRESS_SCANNED_001.pdf")
    assert result.conversion_status in ("success", "partial"), result.errors
    document = result.canonical_document
    text = _all_text(document)
    assert text.strip() != ""
    assert "P-205" in text or "Recovery" in text


def test_scanned_pdf_produces_no_model_derived_annotation(adapter):
    result = _convert(adapter, "stress/STRESS_SCANNED_001.pdf")
    assert all(a.derivation == "extracted" for a in result.canonical_document.annotations)


# --- C. chart fixture ----------------------------------------------------------


def test_chart_fixture_picture_retained_with_provenance(adapter):
    result = _convert(adapter, "stress/STRESS_CHART_001.pdf")
    document = result.canonical_document
    assert len(document.pictures) >= 1
    picture = document.pictures[0]
    provenance_for_picture = [p for p in document.provenance if p.element_id == picture.picture_id]
    assert provenance_for_picture, "picture must have a ProvenanceEntry"


def test_chart_fixture_never_produces_a_visual_fact_annotation(adapter):
    """Stage 5A must not invent quarterly numeric visual facts -- the only
    annotation type it can ever produce is OcrAnnotation (source-derived
    text actually read off the chart image, if any), never a
    VisualFactAnnotation."""
    result = _convert(adapter, "stress/STRESS_CHART_001.pdf")
    assert all(a.annotation_type == "ocr" for a in result.canonical_document.annotations)


# --- D. stress DOCX --------------------------------------------------------------


def test_stress_docx_nested_headings_retained(adapter):
    result = _convert(adapter, "stress/STRESS_DOCX_001.docx")
    document = result.canonical_document
    heading_texts = {h.text: h.level for h in document.headings}
    assert heading_texts.get("Business Continuity Roles") == 1
    assert heading_texts.get("Primary Responders") == 2
    assert heading_texts.get("On-call Rotation") == 3


def test_stress_docx_list_items_retained_lost_nesting_is_reported(adapter):
    """All 5 list items are retained with correct text -- but as a
    documented Stage 5A baseline finding (not an adapter defect), Docling
    2.114.0's DOCX backend does not preserve this fixture's 3-level nested
    list as parent/child structure: it returns 3 flat, sibling list
    groups sharing one heading parent, with no per-item indent signal. The
    mapper's response (_walk_list_ancestry) is real and structurally
    grounded -- it would correctly compute indent_level > 0 and a
    parent_block_id if Docling's own output for THIS fixture exposed real
    nesting; it does not, so every item here honestly lands at
    indent_level=0 / parent_block_id=None rather than fabricating depth.
    This is exactly the kind of gap Stage 5A exists to surface -- see
    reports/stage5a_docling_standard_baseline.md."""
    result = _convert(adapter, "stress/STRESS_DOCX_001.docx")
    document = result.canonical_document
    list_texts = {li.text for li in document.list_items}
    for expected in ("Resilience Engineering Team", "Incident Commander", "Technical Lead", "Primary (Mon-Wed)", "Secondary (Thu-Fri)"):
        assert expected in list_texts

    assert all(li.indent_level == 0 for li in document.list_items)
    assert all(li.parent_block_id is None for li in document.list_items)
    list_ids = {li.list_id for li in document.list_items}
    assert len(list_ids) == 3, "Docling returned 3 flat sibling list groups for this fixture, not 1"


# --- E. stress PDF (two-column + merged table) ----------------------------------


def test_stress_pdf_two_column_converts_without_adapter_failure(adapter):
    result = _convert(adapter, "stress/STRESS_PDF_001.pdf")
    assert result.conversion_status in ("success", "partial"), result.errors
    text = _all_text(result.canonical_document)
    assert "Column one" in text or "primary recovery timeline" in text
    assert "Column two" in text or "secondary failover timeline" in text


def test_stress_pdf_merged_table_mapped_when_exposed(adapter):
    result = _convert(adapter, "stress/STRESS_PDF_001.pdf")
    document = result.canonical_document
    assert len(document.tables) >= 1
    header_cells = [c for t in document.tables for c in t.cells if c.is_header]
    assert any(c.col_span > 1 for c in header_cells), "expected the merged (col_span=2) header cell to be preserved"


# --- F. stress PPTX --------------------------------------------------------------


def test_stress_pptx_overlapping_textboxes_both_retained_if_exposed(adapter):
    result = _convert(adapter, "stress/STRESS_PPTX_001.pptx")
    text = _all_text(result.canonical_document)
    assert "RTO target 4h" in text
    assert "RTO target 6h" in text or "draft" in text.lower()


def test_stress_pptx_native_diagram_text_retained_no_relationship_invented(adapter):
    result = _convert(adapter, "stress/STRESS_PPTX_002.pptx")
    document = result.canonical_document
    text = _all_text(document)
    for expected in ("Detect", "Contain", "Recover"):
        assert expected in text
    # no semantic diagram edge/node relationship may ever be invented in Stage 5A
    assert document.annotations == [] or all(a.annotation_type == "ocr" for a in document.annotations)


# --- determinism (section 15) ---------------------------------------------------


@pytest.mark.parametrize("relative_path", ["parity/PARITY_001.pdf", "parity/PARITY_001.docx", "parity/PARITY_001.pptx"])
def test_repeated_conversion_is_deterministic(adapter, relative_path):
    source_path = FIXTURES_ROOT / relative_path
    result_a = adapter.convert(source_path, source_root=FIXTURES_ROOT)
    result_b = adapter.convert(source_path, source_root=FIXTURES_ROOT)

    assert result_a.canonical_document.model_dump_json() == result_b.canonical_document.model_dump_json()
    assert stable_canonical_hash(result_a.canonical_document) == stable_canonical_hash(result_b.canonical_document)

    chunks_a = _chunk(result_a.canonical_document, "PARITY_001")
    chunks_b = _chunk(result_b.canonical_document, "PARITY_001")
    assert [c.model_dump_json() for c in chunks_a] == [c.model_dump_json() for c in chunks_b]
    assert [c.chunk_id for c in chunks_a] == [c.chunk_id for c in chunks_b]
    assert [c.content_sha256 for c in chunks_a] == [c.content_sha256 for c in chunks_b]
