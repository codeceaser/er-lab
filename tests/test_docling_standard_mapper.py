"""Unit tests for the Docling-to-CanonicalDocument mapper (Stage 5A).

Uses small, real DoclingDocument objects built directly via docling_core's
own builder API (DoclingDocument.add_heading/add_text/add_table/...) --
never the full Docling conversion pipeline, and never a hand-rolled fake
that only loosely resembles a real Docling object. This keeps these tests
fast (no model inference) while still exercising the mapper's real
structural logic against real docling-core types.
"""

from __future__ import annotations

import hashlib
import inspect
import re

import pytest
from docling_core.types.doc import BoundingBox, CoordOrigin, DocItemLabel, DoclingDocument, GroupLabel, Size
from docling_core.types.doc.common.reference import ImageRef, ProvenanceItem
from PIL import Image
from pydantic import ValidationError

from ingestion_bench.adapters.docling_standard.mapper import DocxPageFallback, DoclingToCanonicalMapper

FORBIDDEN_IMPORT_MODULES = ["docling", "docling_core"]


def _prov(page_no=1, l=10.0, t=780.0, r=200.0, b=760.0, charspan=(0, 10)):
    return ProvenanceItem(page_no=page_no, bbox=BoundingBox(l=l, t=t, r=r, b=b, coord_origin=CoordOrigin.BOTTOMLEFT), charspan=charspan)


def _pdf_doc(width: float = 612.0, height: float = 792.0, n_pages: int = 1) -> DoclingDocument:
    doc = DoclingDocument(name="test")
    for page_no in range(1, n_pages + 1):
        doc.add_page(page_no=page_no, size=Size(width=width, height=height))
    return doc


def _mapper(source_format="pdf", doc_id="TEST_001", docx_page_fallback=None) -> DoclingToCanonicalMapper:
    return DoclingToCanonicalMapper(
        doc_id=doc_id, source_format=source_format,
        source_filename=f"{doc_id}.{source_format}", source_relative_path=f"parity/{doc_id}.{source_format}",
        source_sha256="a" * 64, docx_page_fallback=docx_page_fallback,
    )


def _image_saver(store: dict | None = None):
    store = store if store is not None else {}

    def saver(picture_id, pil_image):
        raw = pil_image.tobytes()
        sha = hashlib.sha256(raw).hexdigest()
        ref = f"stage5a/assets/TEST/{picture_id}.png"
        store[picture_id] = (ref, sha, pil_image)
        return ref, sha
    return saver


def _pil_image(size=(4, 3), color=(10, 20, 30)) -> Image.Image:
    return Image.new("RGB", size, color)


# --- units / page_no / coordinate conversion --------------------------------


def test_page_no_converted_to_zero_based_unit_index():
    doc = _pdf_doc(n_pages=2)
    mapper = _mapper()
    assert mapper.build_units(doc)
    assert set(mapper._units.keys()) == {0, 1}
    assert mapper._units[0].unit_index == 0
    assert mapper._units[1].unit_index == 1


def test_bbox_bottomleft_converted_to_top_left_origin():
    doc = _pdf_doc(height=792.0)
    mapper = _mapper()
    mapper.build_units(doc)
    heading = doc.add_heading(text="Title", level=1, prov=_prov(page_no=1, l=10, t=780, r=200, b=760))
    block_id = mapper.map_heading(heading)
    assert block_id is not None
    mapped = mapper.headings[0]
    assert mapped.bbox.coordinate_origin == "top-left"
    # bottom-left t=780 -> top-left y0 = 792-780=12; bottom-left b=760 -> top-left y1 = 792-760=32
    assert mapped.bbox.y0 == pytest.approx(12.0)
    assert mapped.bbox.y1 == pytest.approx(32.0)
    assert mapped.bbox.x0 == 10.0
    assert mapped.bbox.x1 == 200.0
    assert mapped.bbox.y1 >= mapped.bbox.y0  # canonical BoundingBox invariant


# --- headings ----------------------------------------------------------------


def test_heading_mapping_preserves_text_and_level():
    doc = _pdf_doc()
    mapper = _mapper()
    mapper.build_units(doc)
    item = doc.add_heading(text="Recovery Objectives", level=2, prov=_prov())
    mapper.map_heading(item)
    assert len(mapper.headings) == 1
    assert mapper.headings[0].text == "Recovery Objectives"
    assert mapper.headings[0].level == 2


def test_heading_level_defaults_to_1_when_docling_omits_it():
    doc = _pdf_doc()
    mapper = _mapper()
    mapper.build_units(doc)
    item = doc.add_heading(text="Title", level=1, prov=_prov())
    item.level = None  # simulate Docling not exposing a usable level
    mapper.map_heading(item)
    assert mapper.headings[0].level == 1


# --- paragraphs ----------------------------------------------------------------


def test_paragraph_mapping_preserves_clean_text():
    doc = _pdf_doc()
    mapper = _mapper()
    mapper.build_units(doc)
    item = doc.add_text(label=DocItemLabel.TEXT, text="Application APP-224510 supports the service.", prov=_prov())
    block_id = mapper.map_paragraph(item)
    assert block_id is not None
    assert mapper.paragraphs[0].text == "Application APP-224510 supports the service."
    # no bullet/markdown/OCR-label decoration ever added by the mapper
    assert not mapper.paragraphs[0].text.startswith(("-", "*", "OCR:"))


def test_formula_label_mapped_as_paragraph_with_reduced_fidelity_diagnostic():
    doc = _pdf_doc()
    mapper = _mapper()
    mapper.build_units(doc)
    item = doc.add_text(label=DocItemLabel.FORMULA, text="E = mc^2", prov=_prov())
    mapper.map_paragraph(item, reduced_fidelity=True)
    assert mapper.paragraphs[0].text == "E = mc^2"
    categories = [d.category for d in mapper.diagnostics.diagnostics]
    assert "reduced_fidelity_mapping" in categories


# --- list items ----------------------------------------------------------------


def test_list_item_indentation_and_parent_relationship():
    doc = _pdf_doc()
    mapper = _mapper()
    mapper.build_units(doc)

    outer_group = doc.add_group(label=GroupLabel.LIST, name="list")
    root_item = doc.add_list_item(text="Resilience Engineering Team", prov=_prov(), parent=outer_group)

    inner_group = doc.add_group(label=GroupLabel.LIST, name="list", parent=root_item)
    child_item = doc.add_list_item(text="Incident Commander", prov=_prov(), parent=inner_group)

    block_id_by_self_ref: dict[str, str] = {}
    mapper.map_list_item(root_item, doc, block_id_by_self_ref)
    mapper.map_list_item(child_item, doc, block_id_by_self_ref)

    root_mapped, child_mapped = mapper.list_items
    assert root_mapped.indent_level == 0
    assert root_mapped.parent_block_id is None
    assert child_mapped.indent_level == 1
    assert child_mapped.parent_block_id == root_mapped.block_id
    # genuinely nested items share ONE list_id, derived from the outermost
    # enclosing list group -- they belong to the same overall list
    assert child_mapped.list_id == root_mapped.list_id


def test_list_item_with_no_explicit_group_still_maps_with_sensible_default():
    """docling_core auto-creates an implicit list group for an orphan
    ListItem (a deprecation warning, not an error) -- this proves the
    mapper still produces a valid, indent_level=0 CanonicalListItem in
    that case rather than crashing or fabricating deeper nesting."""
    doc = _pdf_doc()
    mapper = _mapper()
    mapper.build_units(doc)
    item = doc.add_list_item(text="Orphan item", prov=_prov())  # parent defaults to #/body
    mapper.map_list_item(item, doc, {})
    assert mapper.list_items[0].indent_level == 0
    assert mapper.list_items[0].parent_block_id is None


def test_walk_list_ancestry_defaults_indent_zero_with_no_group_ancestor():
    """docling_core's own add_list_item() always auto-wraps an orphan item
    in an implicit list group (a public API guarantee, per its own
    deprecation warning), so a truly group-less ListItem cannot be
    constructed through it. _walk_list_ancestry's own degrade-gracefully
    path is exercised directly instead, against an item whose .parent is
    simply not a group at all."""
    from ingestion_bench.adapters.docling_standard.mapper import _walk_list_ancestry

    doc = _pdf_doc()
    heading = doc.add_heading(text="Some heading", level=1, prov=_prov())
    item = doc.add_text(label=DocItemLabel.TEXT, text="not really a list item, just needs a .parent", prov=_prov(), parent=heading)

    indent_level, list_group_ref, parent_owner_ref = _walk_list_ancestry(item, doc)
    assert indent_level == 0
    assert list_group_ref is None
    assert parent_owner_ref is None


# --- tables ----------------------------------------------------------------


def test_table_cells_with_row_and_col_spans():
    from docling_core.types.doc import TableCell, TableData

    doc = _pdf_doc()
    mapper = _mapper()
    mapper.build_units(doc)
    data = TableData(num_rows=2, num_cols=2, table_cells=[
        TableCell(text="Header", start_row_offset_idx=0, end_row_offset_idx=1, start_col_offset_idx=0, end_col_offset_idx=2, row_span=1, col_span=2, column_header=True),
        TableCell(text="A", start_row_offset_idx=1, end_row_offset_idx=2, start_col_offset_idx=0, end_col_offset_idx=1, row_span=1, col_span=1),
        TableCell(text="B", start_row_offset_idx=1, end_row_offset_idx=2, start_col_offset_idx=1, end_col_offset_idx=2, row_span=1, col_span=1),
    ])
    item = doc.add_table(data=data, prov=_prov())
    mapper.map_table(item)

    assert len(mapper.tables) == 1
    table = mapper.tables[0]
    assert table.n_rows == 2 and table.n_cols == 2
    header = next(c for c in table.cells if c.text == "Header")
    assert header.is_header is True
    assert header.col_span == 2


def test_sparse_table_cells_not_fabricated():
    from docling_core.types.doc import TableCell, TableData

    doc = _pdf_doc()
    mapper = _mapper()
    mapper.build_units(doc)
    data = TableData(num_rows=2, num_cols=2, table_cells=[
        TableCell(text="TopLeft", start_row_offset_idx=0, end_row_offset_idx=1, start_col_offset_idx=0, end_col_offset_idx=1),
        TableCell(text="BottomRight", start_row_offset_idx=1, end_row_offset_idx=2, start_col_offset_idx=1, end_col_offset_idx=2),
    ])
    item = doc.add_table(data=data, prov=_prov())
    mapper.map_table(item)
    assert len(mapper.tables[0].cells) == 2  # exactly what was declared, nothing invented for the 2 missing cells


def test_malformed_table_cell_out_of_bounds_is_skipped_and_diagnosed():
    from docling_core.types.doc import TableCell, TableData

    doc = _pdf_doc()
    mapper = _mapper()
    mapper.build_units(doc)
    data = TableData(num_rows=1, num_cols=1, table_cells=[
        TableCell(text="Bad", start_row_offset_idx=0, end_row_offset_idx=1, start_col_offset_idx=5, end_col_offset_idx=6),
    ])
    item = doc.add_table(data=data, prov=_prov())
    mapper.map_table(item)
    assert mapper.tables[0].cells == []
    assert any(d.category == "malformed_table_cell" for d in mapper.diagnostics.diagnostics)


# --- pictures / captions / OCR ------------------------------------------------


def test_picture_artifact_hashing_and_content_sha256():
    doc = _pdf_doc()
    mapper = _mapper()
    mapper.build_units(doc)
    pil_image = _pil_image()
    ref = ImageRef.from_pil(pil_image, dpi=72)
    item = doc.add_picture(prov=_prov(), image=ref)
    store: dict = {}
    picture_id = mapper.map_picture(item, doc, _image_saver(store))
    assert picture_id is not None
    picture = mapper.pictures[0]
    expected_sha = hashlib.sha256(pil_image.tobytes()).hexdigest()
    assert picture.content_sha256 == expected_sha
    assert picture.artifact_ref == f"stage5a/assets/TEST/{picture_id}.png"


def test_picture_with_no_image_bytes_is_skipped_not_invented():
    doc = _pdf_doc()
    mapper = _mapper()
    mapper.build_units(doc)
    item = doc.add_picture(prov=_prov())  # no image= supplied -> get_image() returns None
    picture_id = mapper.map_picture(item, doc, _image_saver())
    assert picture_id is None
    assert mapper.pictures == []
    assert any(d.category == "missing_picture_bytes" for d in mapper.diagnostics.diagnostics)


def test_caption_linked_to_picture_via_map_document_not_duplicated_as_paragraph():
    doc = _pdf_doc()
    mapper = _mapper()
    mapper.build_units(doc)
    pil_image = _pil_image()
    ref = ImageRef.from_pil(pil_image, dpi=72)
    picture_item = doc.add_picture(prov=_prov(page_no=1, l=10, t=700, r=200, b=650))
    caption_item = doc.add_text(label=DocItemLabel.CAPTION, text="Figure 1: a diagram.", prov=_prov(page_no=1, l=10, t=640, r=200, b=620), parent=picture_item)
    picture_item.image = ref
    picture_item.captions = [caption_item.get_ref()]

    mapper.map_document(doc, _image_saver())
    assert len(mapper.pictures) == 1
    assert len(mapper.captions) == 1
    assert mapper.captions[0].text == "Figure 1: a diagram."
    assert mapper.captions[0].target_picture_id == mapper.pictures[0].picture_id
    assert not any("Figure 1" in p.text for p in mapper.paragraphs)  # never duplicated as a body paragraph


def test_ocr_annotation_only_for_picture_nested_text_not_body_text():
    doc = _pdf_doc()
    mapper = _mapper()
    mapper.build_units(doc)
    pil_image = _pil_image()
    picture_item = doc.add_picture(prov=_prov(), image=ImageRef.from_pil(pil_image, dpi=72))
    ocr_child = doc.add_text(label=DocItemLabel.TEXT, text="Incident Detected", prov=_prov(), parent=picture_item)
    body_text = doc.add_text(label=DocItemLabel.TEXT, text="Ordinary body text.", prov=_prov())

    mapper.map_document(doc, _image_saver())

    assert len(mapper.annotations) == 1
    assert mapper.annotations[0].annotation_type == "ocr"
    assert mapper.annotations[0].text == "Incident Detected"
    assert mapper.annotations[0].derivation == "extracted"
    assert any(p.text == "Ordinary body text." for p in mapper.paragraphs)
    assert not any(p.text == "Incident Detected" for p in mapper.paragraphs)  # never duplicated as a paragraph too


def test_no_model_derived_annotations_are_ever_produced():
    """Stage 5A scope gate: the only annotation type this mapper can ever
    produce is OcrAnnotation, always derivation="extracted"."""
    doc = _pdf_doc()
    mapper = _mapper()
    mapper.build_units(doc)
    pil_image = _pil_image()
    picture_item = doc.add_picture(prov=_prov(), image=ImageRef.from_pil(pil_image, dpi=72))
    doc.add_text(label=DocItemLabel.TEXT, text="Some visible text", prov=_prov(), parent=picture_item)
    mapper.map_document(doc, _image_saver())
    assert all(a.annotation_type == "ocr" for a in mapper.annotations)
    assert all(a.derivation == "extracted" for a in mapper.annotations)


# --- diagnostics: unsupported / missing provenance ----------------------------


def test_unsupported_label_produces_diagnostic_and_is_skipped():
    doc = _pdf_doc()
    mapper = _mapper()
    mapper.build_units(doc)
    item = doc.add_text(label=DocItemLabel.REFERENCE, text="[1] Some reference", prov=_prov())
    mapper.map_document(doc, _image_saver())
    assert mapper.paragraphs == []
    assert any(d.category == "unsupported_label" for d in mapper.diagnostics.diagnostics)
    assert mapper.skipped_counts.get("unsupported_label") == 1


def test_furniture_label_skipped_with_info_diagnostic():
    doc = _pdf_doc()
    mapper = _mapper()
    mapper.build_units(doc)
    doc.add_text(label=DocItemLabel.PAGE_FOOTER, text="Page 1 of 2", prov=_prov())
    mapper.map_document(doc, _image_saver())
    assert mapper.paragraphs == []
    assert any(d.category == "skipped_furniture" for d in mapper.diagnostics.diagnostics)


def test_missing_provenance_produces_diagnostic_and_is_skipped():
    doc = _pdf_doc()
    mapper = _mapper()
    mapper.build_units(doc)
    item = doc.add_text(label=DocItemLabel.TEXT, text="No provenance")  # prov=None
    result = mapper.map_paragraph(item)
    assert result is None
    assert mapper.paragraphs == []
    assert any(d.category == "missing_provenance" for d in mapper.diagnostics.diagnostics)


# --- failure behaviour --------------------------------------------------------


def test_docx_missing_page_geometry_without_fallback_fails_cleanly():
    doc = DoclingDocument(name="test")  # no add_page() calls -- simulates real DOCX behavior
    mapper = _mapper(source_format="docx", docx_page_fallback=None)
    ok = mapper.build_units(doc)
    assert ok is False
    assert any(d.severity == "error" for d in mapper.diagnostics.diagnostics)


def test_docx_page_fallback_produces_valid_unit_with_diagnostic():
    doc = DoclingDocument(name="test")
    mapper = _mapper(source_format="docx", docx_page_fallback=DocxPageFallback(width_pt=612.0, height_pt=792.0))
    ok = mapper.build_units(doc)
    assert ok is True
    assert mapper._units[0].width == 612.0
    fallback_diagnostics = [d for d in mapper.diagnostics.diagnostics if d.category == "docx_pagination_unavailable"]
    assert len(fallback_diagnostics) == 1
    assert fallback_diagnostics[0].affects_fidelity is True
    assert mapper.diagnostics.has_fidelity_impact() is True


def test_no_usable_geometry_at_all_fails_without_fabricating_a_unit():
    doc = _pdf_doc(width=0.0, height=0.0)  # degenerate page size
    mapper = _mapper()
    ok = mapper.build_units(doc)
    assert ok is False
    assert mapper._units == {}


def test_canonical_document_construction_failure_is_reported_not_raised():
    """If, despite best-effort mapping, the assembled document would
    violate a frozen canonical invariant, build() must report a
    diagnostic and return None -- never raise past the mapper boundary,
    never emit a fake/empty CanonicalDocument."""
    doc = _pdf_doc()
    mapper = _mapper()
    mapper.build_units(doc)
    # inject an invalid caption referencing a picture that was never mapped
    from ingestion_bench.canonical import CanonicalCaption
    mapper.captions.append(CanonicalCaption(block_id="bad", unit_index=0, order_index=0, text="orphan caption", target_picture_id="does-not-exist"))
    result = mapper.build()
    assert result is None
    assert any(d.category == "canonical_document_construction_failed" for d in mapper.diagnostics.diagnostics)


# --- determinism / identity ---------------------------------------------------


def test_deterministic_ids_across_two_mapper_runs():
    def run_once():
        doc = _pdf_doc()
        mapper = _mapper()
        mapper.build_units(doc)
        item = doc.add_heading(text="Recovery Objectives", level=2, prov=_prov())
        mapper.map_heading(item)
        return mapper.headings[0].block_id

    assert run_once() == run_once()


def test_source_sha256_and_relative_path_carried_through_unchanged():
    doc = _pdf_doc()
    mapper = DoclingToCanonicalMapper(
        doc_id="DOC1", source_format="pdf", source_filename="DOC1.pdf",
        source_relative_path="parity/DOC1.pdf", source_sha256="b" * 64,
    )
    mapper.build_units(doc)
    canonical = mapper.build()
    assert canonical.source_sha256 == "b" * 64
    assert canonical.source_relative_path == "parity/DOC1.pdf"
    assert "\\" not in canonical.source_relative_path


# --- dependency isolation ------------------------------------------------------


def test_canonical_and_chunking_packages_have_no_docling_imports():
    """The frozen canonical/chunking contracts must remain completely
    independent of Docling -- only ingestion_bench.adapters may import it."""
    import ingestion_bench.canonical.annotations as canonical_annotations
    import ingestion_bench.canonical.extraction_run as canonical_extraction_run
    import ingestion_bench.canonical.hashing as canonical_hashing
    import ingestion_bench.canonical.model as canonical_model
    import ingestion_bench.chunking.chunker as chunker_module
    import ingestion_bench.chunking.model as chunking_model
    import ingestion_bench.chunking.renderers as renderers_module

    import_re = re.compile(r"^\s*(import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.MULTILINE)
    for module in (canonical_annotations, canonical_extraction_run, canonical_hashing, canonical_model, chunker_module, chunking_model, renderers_module):
        source = inspect.getsource(module)
        imported = {m.group(2) for m in import_re.finditer(source)}
        forbidden = imported & set(FORBIDDEN_IMPORT_MODULES)
        assert not forbidden, f"{module.__name__} imports forbidden module(s): {forbidden}"


def test_mapper_and_adapter_never_import_manifest_modules():
    import ingestion_bench.adapters.docling_standard.adapter as adapter_module
    import ingestion_bench.adapters.docling_standard.mapper as mapper_module

    import_re = re.compile(r"^\s*(import|from)\s+([a-zA-Z_][a-zA-Z0-9_.]*)", re.MULTILINE)
    for module in (adapter_module, mapper_module):
        source = inspect.getsource(module)
        imported = {m.group(2) for m in import_re.finditer(source)}
        assert not any("manifest_schema" in name or "reference_manifest" in name for name in imported), module.__name__
