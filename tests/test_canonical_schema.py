"""Schema validation tests for the canonical document model (Stage 2)."""

import math

import pytest
from pydantic import ValidationError

from ingestion_bench.canonical import (
    BoundingBox,
    CanonicalCaption,
    CanonicalDocument,
    CanonicalHeading,
    CanonicalListItem,
    CanonicalParagraph,
    CanonicalPicture,
    CanonicalTable,
    CanonicalTableCell,
    CanonicalUnit,
    DiagramEdgeAnnotation,
    DiagramNodeAnnotation,
    IdentifierAnnotation,
    ImageDescriptionAnnotation,
    NormalizedBoundingBox,
    OcrAnnotation,
    ProvenanceEntry,
    VisibleTextAnnotation,
    VisualFactAnnotation,
)


def _bbox(**overrides) -> BoundingBox:
    kwargs = dict(x0=0.0, y0=0.0, x1=100.0, y1=20.0, coordinate_unit="pt", coordinate_origin="top-left")
    kwargs.update(overrides)
    return BoundingBox(**kwargs)


def _valid_document(**overrides) -> CanonicalDocument:
    unit0 = CanonicalUnit(unit_index=0, unit_type="page", width=612, height=792, coordinate_unit="pt", coordinate_origin="top-left")
    unit1 = CanonicalUnit(unit_index=1, unit_type="page", width=612, height=792, coordinate_unit="pt", coordinate_origin="top-left")

    heading = CanonicalHeading(block_id="h1", unit_index=0, order_index=0, text="Title", level=1, bbox=_bbox())
    paragraph = CanonicalParagraph(block_id="p1", unit_index=0, order_index=1, text="Application APP-224510 supports the service.")
    table = CanonicalTable(
        table_id="t1", unit_index=0, order_index=2, n_rows=1, n_cols=1,
        cells=[CanonicalTableCell(row=0, col=0, text="x", is_header=True)],
    )
    picture = CanonicalPicture(picture_id="pic1", unit_index=1, content_sha256="c" * 64, artifact_ref="parity/pic1.png")
    caption = CanonicalCaption(block_id="cap1", unit_index=1, order_index=0, text="Figure 1", target_picture_id="pic1")

    node1 = DiagramNodeAnnotation(
        annotation_id="ann_node1", target_ref="pic1", unit_index=1,
        derivation="model_derived", extraction_method="openai_vision_enrichment",
        node_id="node1", label="Detect",
    )
    node2 = DiagramNodeAnnotation(
        annotation_id="ann_node2", target_ref="pic1", unit_index=1,
        derivation="model_derived", extraction_method="openai_vision_enrichment",
        node_id="node2", label="Contain",
    )
    edge = DiagramEdgeAnnotation(
        annotation_id="ann_edge1", target_ref="pic1", unit_index=1,
        derivation="model_derived", extraction_method="openai_vision_enrichment",
        source_node_id="node1", target_node_id="node2",
    )
    identifier = IdentifierAnnotation(
        annotation_id="ann_id1", target_ref="p1", unit_index=0,
        derivation="extracted", extraction_method="text_scan",
        raw_text="APP-224510", normalized_value="APP-224510", start_char=12, end_char=22,
    )

    kwargs = dict(
        doc_id="DOC1", source_format="pdf", source_filename="doc1.pdf",
        source_relative_path="parity/doc1.pdf", source_sha256="a" * 64,
        units=[unit0, unit1],
        headings=[heading], paragraphs=[paragraph], tables=[table],
        pictures=[picture], captions=[caption],
        annotations=[node1, node2, edge, identifier],
    )
    kwargs.update(overrides)
    return CanonicalDocument(**kwargs)


def test_valid_document_constructs():
    doc = _valid_document()
    assert len(doc.annotations) == 4
    assert isinstance(doc.annotations[0], DiagramNodeAnnotation)
    assert isinstance(doc.annotations[3], IdentifierAnnotation)


def test_canonical_document_has_no_manifest_fields():
    """CanonicalDocument says what was extracted; it must never carry
    benchmark/manifest identity -- that belongs on BenchmarkBinding."""
    assert "manifest_version" not in CanonicalDocument.model_fields
    assert "manifest_sha256" not in CanonicalDocument.model_fields


def test_annotation_discriminated_union_parses_raw_dicts():
    doc = CanonicalDocument(
        doc_id="DOC2", source_format="pptx", source_filename="d.pptx",
        source_relative_path="stress/d.pptx", source_sha256="a" * 64,
        units=[{"unit_index": 0, "unit_type": "slide", "width": 100, "height": 100, "coordinate_unit": "emu", "coordinate_origin": "top-left"}],
        pictures=[{"picture_id": "pic1", "unit_index": 0, "content_sha256": "c" * 64, "artifact_ref": "stress/pic1.png"}],
        annotations=[
            {
                # OCR is mechanical, character-level text recognition (RapidOCR /
                # Docling's OCR pipeline) -- "extracted", not "model_derived".
                # "model_derived" is reserved for annotations involving real
                # semantic/interpretive judgment (picture_class, visual_fact,
                # image_description, ...), which OCR is not.
                "annotation_id": "ann1", "annotation_type": "ocr", "target_ref": "pic1",
                "unit_index": 0, "derivation": "extracted", "extraction_method": "rapidocr",
                "text": "Incident Detected",
            },
            {
                "annotation_id": "ann2", "annotation_type": "picture_class", "target_ref": "pic1",
                "unit_index": 0, "derivation": "model_derived", "extraction_method": "docling_picture_classifier",
                "picture_class": "diagram",
            },
        ],
    )
    assert type(doc.annotations[0]).__name__ == "OcrAnnotation"
    assert doc.annotations[0].derivation == "extracted"
    assert type(doc.annotations[1]).__name__ == "PictureClassAnnotation"
    assert doc.annotations[0].text == "Incident Detected"


def test_unknown_annotation_type_rejected():
    with pytest.raises(ValidationError):
        CanonicalDocument(
            doc_id="DOC3", source_format="pdf", source_filename="d.pdf",
            source_relative_path="stress/d.pdf", source_sha256="a" * 64,
            units=[{"unit_index": 0, "unit_type": "page", "width": 1, "height": 1, "coordinate_unit": "pt", "coordinate_origin": "top-left"}],
            annotations=[
                {
                    "annotation_id": "ann1", "annotation_type": "bogus_type", "target_ref": "x",
                    "unit_index": 0, "derivation": "extracted", "extraction_method": "x",
                }
            ],
        )


def test_bbox_coordinate_unit_mismatch_rejected():
    with pytest.raises(ValidationError):
        _valid_document(paragraphs=[
            CanonicalParagraph(block_id="p1", unit_index=0, order_index=1, text="x", bbox=_bbox(coordinate_unit="px"))
        ])


def test_bbox_coordinate_origin_mismatch_rejected():
    with pytest.raises(ValidationError):
        _valid_document(paragraphs=[
            CanonicalParagraph(block_id="p1", unit_index=0, order_index=1, text="x", bbox=_bbox(coordinate_origin="bottom-left"))
        ])


def test_bbox_unknown_unit_index_rejected():
    with pytest.raises(ValidationError):
        _valid_document(paragraphs=[
            CanonicalParagraph(block_id="p1", unit_index=99, order_index=1, text="x", bbox=_bbox())
        ])


def test_unit_index_unknown_rejected_even_without_bbox():
    """Regression test for the gap where an element with no bbox skipped
    unit_index validation entirely."""
    with pytest.raises(ValidationError):
        _valid_document(paragraphs=[
            CanonicalParagraph(block_id="p1", unit_index=99, order_index=1, text="no bbox here")
        ])


def test_diagram_node_bbox_coordinate_mismatch_rejected():
    with pytest.raises(ValidationError):
        _valid_document(annotations=[
            DiagramNodeAnnotation(
                annotation_id="ann_node1", target_ref="pic1", unit_index=1,
                derivation="model_derived", extraction_method="openai_vision_enrichment",
                node_id="node1", label="Detect", node_bbox=_bbox(coordinate_unit="px"),
            )
        ])


def test_diagram_edge_unresolved_node_id_rejected():
    with pytest.raises(ValidationError):
        _valid_document(annotations=[
            DiagramNodeAnnotation(
                annotation_id="ann_node1", target_ref="pic1", unit_index=1,
                derivation="model_derived", extraction_method="openai_vision_enrichment",
                node_id="node1", label="Detect",
            ),
            DiagramEdgeAnnotation(
                annotation_id="ann_edge1", target_ref="pic1", unit_index=1,
                derivation="model_derived", extraction_method="openai_vision_enrichment",
                source_node_id="node1", target_node_id="does_not_exist",
            ),
        ])


def test_diagram_edge_resolved_node_id_accepted():
    doc = _valid_document()
    edge = next(a for a in doc.annotations if type(a).__name__ == "DiagramEdgeAnnotation")
    node_ids = {a.node_id for a in doc.annotations if type(a).__name__ == "DiagramNodeAnnotation"}
    assert edge.source_node_id in node_ids
    assert edge.target_node_id in node_ids


def test_caption_unresolved_target_picture_rejected():
    with pytest.raises(ValidationError):
        _valid_document(captions=[
            CanonicalCaption(block_id="cap1", unit_index=1, order_index=0, text="Figure 1", target_picture_id="does_not_exist")
        ])


def test_list_item_unresolved_parent_rejected():
    with pytest.raises(ValidationError):
        _valid_document(list_items=[
            CanonicalListItem(block_id="li1", unit_index=0, order_index=0, text="child", list_id="l", indent_level=1, parent_block_id="does_not_exist")
        ])


def test_list_item_resolved_parent_accepted():
    doc = _valid_document(list_items=[
        CanonicalListItem(block_id="li_parent", unit_index=0, order_index=0, text="parent", list_id="l", indent_level=0),
        CanonicalListItem(block_id="li_child", unit_index=0, order_index=1, text="child", list_id="l", indent_level=1, parent_block_id="li_parent"),
    ])
    assert len(doc.list_items) == 2


def test_annotation_target_ref_unresolved_rejected():
    with pytest.raises(ValidationError):
        _valid_document(annotations=[
            IdentifierAnnotation(
                annotation_id="ann_id1", target_ref="does_not_exist", unit_index=0,
                derivation="extracted", extraction_method="text_scan",
                raw_text="APP-224510", normalized_value="APP-224510",
            )
        ])


def test_table_cell_row_out_of_bounds_rejected():
    with pytest.raises(ValidationError):
        _valid_document(tables=[
            CanonicalTable(table_id="t1", unit_index=0, order_index=2, n_rows=1, n_cols=1,
                            cells=[CanonicalTableCell(row=5, col=0, text="x")])
        ])


def test_table_cell_col_out_of_bounds_rejected():
    with pytest.raises(ValidationError):
        _valid_document(tables=[
            CanonicalTable(table_id="t1", unit_index=0, order_index=2, n_rows=1, n_cols=1,
                            cells=[CanonicalTableCell(row=0, col=5, text="x")])
        ])


def test_table_cell_span_exceeds_bounds_rejected():
    with pytest.raises(ValidationError):
        _valid_document(tables=[
            CanonicalTable(table_id="t1", unit_index=0, order_index=2, n_rows=1, n_cols=2,
                            cells=[CanonicalTableCell(row=0, col=1, col_span=2, text="x")])
        ])


def test_duplicate_block_id_rejected():
    with pytest.raises(ValidationError):
        _valid_document(paragraphs=[
            CanonicalParagraph(block_id="h1", unit_index=0, order_index=1, text="duplicate of the heading's block_id")
        ])


def test_duplicate_picture_id_rejected():
    with pytest.raises(ValidationError):
        _valid_document(pictures=[
            CanonicalPicture(picture_id="pic1", unit_index=1, content_sha256="c" * 64, artifact_ref="parity/a.png"),
            CanonicalPicture(picture_id="pic1", unit_index=1, content_sha256="d" * 64, artifact_ref="parity/b.png"),
        ], captions=[])


def test_duplicate_annotation_id_rejected():
    with pytest.raises(ValidationError):
        _valid_document(annotations=[
            IdentifierAnnotation(
                annotation_id="dup", target_ref="p1", unit_index=0,
                derivation="extracted", extraction_method="text_scan",
                raw_text="APP-224510", normalized_value="APP-224510",
            ),
            IdentifierAnnotation(
                annotation_id="dup", target_ref="p1", unit_index=0,
                derivation="extracted", extraction_method="text_scan",
                raw_text="O-31", normalized_value="O-31",
            ),
        ])


def test_duplicate_diagram_node_id_rejected():
    with pytest.raises(ValidationError):
        _valid_document(annotations=[
            DiagramNodeAnnotation(
                annotation_id="ann_node1", target_ref="pic1", unit_index=1,
                derivation="model_derived", extraction_method="openai_vision_enrichment",
                node_id="dup_node", label="Detect",
            ),
            DiagramNodeAnnotation(
                annotation_id="ann_node2", target_ref="pic1", unit_index=1,
                derivation="model_derived", extraction_method="openai_vision_enrichment",
                node_id="dup_node", label="Contain",
            ),
        ])


def test_absolute_source_relative_path_rejected():
    with pytest.raises(ValidationError):
        _valid_document(source_relative_path="/abs/parity/doc1.pdf")


def test_windows_absolute_source_relative_path_rejected():
    with pytest.raises(ValidationError):
        _valid_document(source_relative_path=r"C:\Users\Admin\doc1.pdf")


def test_backslash_source_relative_path_rejected():
    with pytest.raises(ValidationError):
        _valid_document(source_relative_path=r"parity\doc1.pdf")


def test_absolute_artifact_ref_rejected():
    with pytest.raises(ValidationError):
        _valid_document(pictures=[
            CanonicalPicture(picture_id="pic1", unit_index=1, content_sha256="c" * 64, artifact_ref="/abs/pic1.png")
        ])


def test_windows_absolute_artifact_ref_rejected():
    with pytest.raises(ValidationError):
        _valid_document(pictures=[
            CanonicalPicture(picture_id="pic1", unit_index=1, content_sha256="c" * 64, artifact_ref=r"C:\pics\pic1.png")
        ])


def test_empty_artifact_ref_rejected():
    with pytest.raises(ValidationError):
        _valid_document(pictures=[
            CanonicalPicture(picture_id="pic1", unit_index=1, content_sha256="c" * 64, artifact_ref="")
        ])


def test_empty_source_relative_path_rejected():
    with pytest.raises(ValidationError):
        _valid_document(source_relative_path="")


def test_traversal_source_relative_path_rejected():
    with pytest.raises(ValidationError):
        _valid_document(source_relative_path="parity/../../etc/passwd")


def test_traversal_artifact_ref_rejected():
    with pytest.raises(ValidationError):
        _valid_document(pictures=[
            CanonicalPicture(picture_id="pic1", unit_index=1, content_sha256="c" * 64, artifact_ref="parity/../secret.png")
        ])


def test_source_filename_with_slash_rejected():
    with pytest.raises(ValidationError):
        _valid_document(source_filename="parity/doc1.pdf")


def test_source_filename_with_backslash_rejected():
    with pytest.raises(ValidationError):
        _valid_document(source_filename=r"parity\doc1.pdf")


def test_source_filename_empty_rejected():
    with pytest.raises(ValidationError):
        _valid_document(source_filename="")


# --- SHA-256 field validation --------------------------------------------


def test_source_sha256_rejects_non_hex():
    with pytest.raises(ValidationError):
        _valid_document(source_sha256="z" * 64)


def test_source_sha256_rejects_wrong_length():
    with pytest.raises(ValidationError):
        _valid_document(source_sha256="a" * 63)


def test_source_sha256_rejects_uppercase():
    with pytest.raises(ValidationError):
        _valid_document(source_sha256="A" * 64)


def test_content_sha256_rejects_non_hex():
    with pytest.raises(ValidationError):
        _valid_document(pictures=[
            CanonicalPicture(picture_id="pic1", unit_index=1, content_sha256="z" * 64, artifact_ref="parity/pic1.png")
        ])


# --- Geometry validation (BoundingBox / NormalizedBoundingBox) ----------


def test_bbox_x1_less_than_x0_rejected():
    with pytest.raises(ValidationError):
        _bbox(x0=100.0, x1=0.0)


def test_bbox_y1_less_than_y0_rejected():
    with pytest.raises(ValidationError):
        _bbox(y0=100.0, y1=0.0)


def test_bbox_equal_x0_x1_accepted():
    # x1 >= x0 permits a zero-width box (e.g. a degenerate/point annotation).
    box = _bbox(x0=10.0, x1=10.0)
    assert box.x1 == box.x0


def test_bbox_rejects_non_finite_values():
    with pytest.raises(ValidationError):
        _bbox(x1=math.inf)
    with pytest.raises(ValidationError):
        _bbox(y0=math.nan)


def test_normalized_bbox_valid_range_accepted():
    box = NormalizedBoundingBox(nx0=0.1, ny0=0.1, nx1=0.9, ny1=0.9)
    assert box.nx1 >= box.nx0


def test_normalized_bbox_out_of_range_rejected():
    with pytest.raises(ValidationError):
        NormalizedBoundingBox(nx0=0.1, ny0=0.1, nx1=1.5, ny1=0.9)


def test_normalized_bbox_x_ordering_rejected():
    with pytest.raises(ValidationError):
        NormalizedBoundingBox(nx0=0.9, ny0=0.1, nx1=0.1, ny1=0.9)


def test_normalized_bbox_y_ordering_rejected():
    with pytest.raises(ValidationError):
        NormalizedBoundingBox(nx0=0.1, ny0=0.9, nx1=0.9, ny1=0.1)


# --- Unit and index validation -------------------------------------------


def test_negative_unit_index_rejected():
    with pytest.raises(ValidationError):
        CanonicalUnit(unit_index=-1, unit_type="page", width=1, height=1, coordinate_unit="pt", coordinate_origin="top-left")


def test_zero_width_unit_rejected():
    with pytest.raises(ValidationError):
        CanonicalUnit(unit_index=0, unit_type="page", width=0, height=1, coordinate_unit="pt", coordinate_origin="top-left")


def test_zero_height_unit_rejected():
    with pytest.raises(ValidationError):
        CanonicalUnit(unit_index=0, unit_type="page", width=1, height=0, coordinate_unit="pt", coordinate_origin="top-left")


def test_duplicate_unit_index_rejected():
    unit0a = CanonicalUnit(unit_index=0, unit_type="page", width=1, height=1, coordinate_unit="pt", coordinate_origin="top-left")
    unit0b = CanonicalUnit(unit_index=0, unit_type="page", width=2, height=2, coordinate_unit="pt", coordinate_origin="top-left")
    with pytest.raises(ValidationError):
        _valid_document(units=[unit0a, unit0b])


def test_negative_order_index_rejected():
    with pytest.raises(ValidationError):
        _valid_document(paragraphs=[
            CanonicalParagraph(block_id="p1", unit_index=0, order_index=-1, text="x")
        ])


def test_heading_level_zero_rejected():
    with pytest.raises(ValidationError):
        CanonicalHeading(block_id="h1", unit_index=0, order_index=0, text="x", level=0)


def test_list_item_negative_indent_level_rejected():
    with pytest.raises(ValidationError):
        CanonicalListItem(block_id="li1", unit_index=0, order_index=0, text="x", list_id="l", indent_level=-1)


# --- Table primitive validation -------------------------------------------


def test_table_zero_rows_rejected():
    with pytest.raises(ValidationError):
        CanonicalTable(table_id="t1", unit_index=0, order_index=0, n_rows=0, n_cols=1, cells=[])


def test_table_zero_cols_rejected():
    with pytest.raises(ValidationError):
        CanonicalTable(table_id="t1", unit_index=0, order_index=0, n_rows=1, n_cols=0, cells=[])


def test_table_cell_negative_row_rejected():
    with pytest.raises(ValidationError):
        CanonicalTableCell(row=-1, col=0, text="x")


def test_table_cell_negative_col_rejected():
    with pytest.raises(ValidationError):
        CanonicalTableCell(row=0, col=-1, text="x")


def test_table_cell_zero_row_span_rejected():
    with pytest.raises(ValidationError):
        CanonicalTableCell(row=0, col=0, row_span=0, text="x")


def test_table_cell_zero_col_span_rejected():
    with pytest.raises(ValidationError):
        CanonicalTableCell(row=0, col=0, col_span=0, text="x")


# --- Provenance integrity --------------------------------------------------


def test_provenance_unresolved_element_id_rejected():
    with pytest.raises(ValidationError):
        _valid_document(provenance=[
            ProvenanceEntry(element_id="does_not_exist", unit_index=0)
        ])


def test_provenance_resolves_to_core_element():
    doc = _valid_document(provenance=[
        ProvenanceEntry(element_id="p1", unit_index=0, z_order=1)
    ])
    assert doc.provenance[0].element_id == "p1"


def test_provenance_resolves_to_annotation_id():
    doc = _valid_document(provenance=[
        ProvenanceEntry(element_id="ann_id1", unit_index=0)
    ])
    assert doc.provenance[0].element_id == "ann_id1"


# --- Global core-element identity namespace --------------------------------


def test_block_id_colliding_with_picture_id_rejected():
    """block_id/table_id/picture_id share ONE namespace, since
    Annotation.target_ref can reference any of them."""
    with pytest.raises(ValidationError):
        _valid_document(paragraphs=[
            CanonicalParagraph(block_id="pic1", unit_index=0, order_index=1, text="colliding with the picture's id")
        ])


def test_table_id_colliding_with_block_id_rejected():
    with pytest.raises(ValidationError):
        _valid_document(tables=[
            CanonicalTable(table_id="h1", unit_index=0, order_index=2, n_rows=1, n_cols=1,
                            cells=[CanonicalTableCell(row=0, col=0, text="x")])
        ])


# --- Annotation-model hardening --------------------------------------------


def test_annotation_negative_unit_index_rejected():
    with pytest.raises(ValidationError):
        IdentifierAnnotation(
            annotation_id="ann1", target_ref="p1", unit_index=-1,
            derivation="extracted", extraction_method="text_scan",
            raw_text="x", normalized_value="x",
        )


def test_annotation_confidence_out_of_range_rejected():
    with pytest.raises(ValidationError):
        IdentifierAnnotation(
            annotation_id="ann1", target_ref="p1", unit_index=0,
            derivation="extracted", extraction_method="text_scan",
            raw_text="x", normalized_value="x", confidence=1.5,
        )


def test_annotation_confidence_none_accepted():
    ann = IdentifierAnnotation(
        annotation_id="ann1", target_ref="p1", unit_index=0,
        derivation="extracted", extraction_method="text_scan",
        raw_text="x", normalized_value="x", confidence=None,
    )
    assert ann.confidence is None


def test_annotation_confidence_in_range_accepted():
    ann = IdentifierAnnotation(
        annotation_id="ann1", target_ref="p1", unit_index=0,
        derivation="extracted", extraction_method="text_scan",
        raw_text="x", normalized_value="x", confidence=0.75,
    )
    assert ann.confidence == 0.75


def test_annotation_rejects_unexpected_extra_field():
    with pytest.raises(ValidationError):
        IdentifierAnnotation(
            annotation_id="ann1", target_ref="p1", unit_index=0,
            derivation="extracted", extraction_method="text_scan",
            raw_text="x", normalized_value="x",
            unexpected_field="should be rejected",
        )


def test_identifier_char_offsets_both_none_accepted():
    ann = IdentifierAnnotation(
        annotation_id="ann1", target_ref="p1", unit_index=0,
        derivation="extracted", extraction_method="text_scan",
        raw_text="x", normalized_value="x",
    )
    assert ann.start_char is None and ann.end_char is None


def test_identifier_char_offsets_both_populated_accepted():
    ann = IdentifierAnnotation(
        annotation_id="ann1", target_ref="p1", unit_index=0,
        derivation="extracted", extraction_method="text_scan",
        raw_text="x", normalized_value="x", start_char=5, end_char=10,
    )
    assert ann.start_char == 5 and ann.end_char == 10


def test_identifier_char_offsets_only_start_rejected():
    with pytest.raises(ValidationError):
        IdentifierAnnotation(
            annotation_id="ann1", target_ref="p1", unit_index=0,
            derivation="extracted", extraction_method="text_scan",
            raw_text="x", normalized_value="x", start_char=5, end_char=None,
        )


def test_identifier_char_offsets_only_end_rejected():
    with pytest.raises(ValidationError):
        IdentifierAnnotation(
            annotation_id="ann1", target_ref="p1", unit_index=0,
            derivation="extracted", extraction_method="text_scan",
            raw_text="x", normalized_value="x", start_char=None, end_char=10,
        )


def test_identifier_char_offsets_start_after_end_rejected():
    with pytest.raises(ValidationError):
        IdentifierAnnotation(
            annotation_id="ann1", target_ref="p1", unit_index=0,
            derivation="extracted", extraction_method="text_scan",
            raw_text="x", normalized_value="x", start_char=10, end_char=5,
        )


def test_identifier_char_offsets_negative_start_rejected():
    with pytest.raises(ValidationError):
        IdentifierAnnotation(
            annotation_id="ann1", target_ref="p1", unit_index=0,
            derivation="extracted", extraction_method="text_scan",
            raw_text="x", normalized_value="x", start_char=-1, end_char=5,
        )


def test_identifier_char_offsets_equal_start_end_accepted():
    # Half-open semantics: start_char == end_char is a valid (empty) span.
    ann = IdentifierAnnotation(
        annotation_id="ann1", target_ref="p1", unit_index=0,
        derivation="extracted", extraction_method="text_scan",
        raw_text="x", normalized_value="x", start_char=5, end_char=5,
    )
    assert ann.start_char == ann.end_char == 5


# --- Derivation invariants per annotation type -----------------------------


def test_ocr_annotation_defaults_to_extracted():
    ann = OcrAnnotation(annotation_id="a1", target_ref="pic1", unit_index=0, extraction_method="rapidocr", text="x")
    assert ann.derivation == "extracted"


def test_ocr_annotation_rejects_model_derived():
    with pytest.raises(ValidationError):
        OcrAnnotation(
            annotation_id="a1", target_ref="pic1", unit_index=0,
            derivation="model_derived", extraction_method="rapidocr", text="x",
        )


def test_visible_text_annotation_defaults_to_model_derived():
    ann = VisibleTextAnnotation(annotation_id="a1", target_ref="pic1", unit_index=0, extraction_method="openai_vision_enrichment", text="x")
    assert ann.derivation == "model_derived"


def test_visible_text_annotation_rejects_extracted():
    with pytest.raises(ValidationError):
        VisibleTextAnnotation(
            annotation_id="a1", target_ref="pic1", unit_index=0,
            derivation="extracted", extraction_method="openai_vision_enrichment", text="x",
        )


def test_image_description_annotation_rejects_extracted():
    with pytest.raises(ValidationError):
        ImageDescriptionAnnotation(
            annotation_id="a1", target_ref="pic1", unit_index=0,
            derivation="extracted", extraction_method="openai_vision_enrichment", description="x",
        )


def test_image_description_annotation_defaults_to_model_derived():
    ann = ImageDescriptionAnnotation(annotation_id="a1", target_ref="pic1", unit_index=0, extraction_method="openai_vision_enrichment", description="x")
    assert ann.derivation == "model_derived"


def test_visual_fact_annotation_rejects_extracted():
    with pytest.raises(ValidationError):
        VisualFactAnnotation(
            annotation_id="a1", target_ref="pic1", unit_index=0,
            derivation="extracted", extraction_method="openai_vision_enrichment",
            fact_type="numeric", subject="Q1", relation="equals", value=82, unit="%", raw_text="Q1: 82%",
        )


def test_visual_fact_annotation_defaults_to_model_derived():
    ann = VisualFactAnnotation(
        annotation_id="a1", target_ref="pic1", unit_index=0, extraction_method="openai_vision_enrichment",
        fact_type="numeric", subject="Q1", relation="equals", value=82, unit="%", raw_text="Q1: 82%",
    )
    assert ann.derivation == "model_derived"


def test_diagram_node_annotation_accepts_extracted():
    ann = DiagramNodeAnnotation(
        annotation_id="a1", target_ref="pic1", unit_index=0,
        derivation="extracted", extraction_method="pptx_native_shapes",
        node_id="n1", label="Detect",
    )
    assert ann.derivation == "extracted"


def test_diagram_node_annotation_accepts_model_derived():
    ann = DiagramNodeAnnotation(
        annotation_id="a1", target_ref="pic1", unit_index=0,
        derivation="model_derived", extraction_method="openai_vision_enrichment",
        node_id="n1", label="Detect",
    )
    assert ann.derivation == "model_derived"


def test_diagram_edge_annotation_accepts_extracted():
    ann = DiagramEdgeAnnotation(
        annotation_id="a1", target_ref="pic1", unit_index=0,
        derivation="extracted", extraction_method="pptx_native_shapes",
        source_node_id="n1", target_node_id="n2",
    )
    assert ann.derivation == "extracted"
