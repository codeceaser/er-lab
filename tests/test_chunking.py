"""Tests for the canonical chunking layer (Stage 4 / Stage 4.1 / Stage 4.2).

Uses manually constructed CanonicalDocument objects only -- the Stage 3
source fixtures (DOCX/PDF/PPTX) are deliberately not parsed here; that's a
Stage 5 (adapter) concern.
"""

from __future__ import annotations

import inspect
import json
import re

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
    OcrAnnotation,
    VisibleTextAnnotation,
)
from ingestion_bench.chunking import (
    CanonicalChunk,
    ChunkAssetRef,
    ChunkingConfig,
    ChunkSourceRef,
    DocumentRevisionContext,
    TextFragment,
    canonical_sha256,
    chunk_document,
    compute_document_revision_id,
    text_sha256,
)
from ingestion_bench.chunking.chunker import split_oversized_text

# Checked as actual `import x` / `from x import ...` statements, not bare
# substrings -- this module's own docstrings name "Docling"/"OpenAI" to
# document what it deliberately does NOT depend on, which a naive substring
# ban would itself trip (the same false-positive class fixed in Stage 2 for
# the "uuid4"/"hash()" docstring mentions in hashing.py).
FORBIDDEN_IMPORT_MODULES = [
    "docling", "openai", "requests", "urllib", "http", "httpx", "socket",
    "psycopg", "sqlalchemy", "sentence_transformers", "docx", "pptx",
    "reportlab", "PIL", "fitz", "pypdf",
]


def _unit(index: int = 0, unit_type: str = "page") -> CanonicalUnit:
    return CanonicalUnit(unit_index=index, unit_type=unit_type, width=612, height=792, coordinate_unit="pt", coordinate_origin="top-left")


def _doc(**overrides) -> CanonicalDocument:
    kwargs = dict(
        doc_id="DOC1", source_format="pdf", source_filename="doc1.pdf",
        source_relative_path="parity/doc1.pdf", source_sha256="a" * 64,
        units=[_unit(0), _unit(1)],
    )
    kwargs.update(overrides)
    return CanonicalDocument(**kwargs)


def _bbox(x0: float = 0, y0: float = 0, x1: float = 10, y1: float = 10) -> BoundingBox:
    return BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1, coordinate_unit="pt", coordinate_origin="top-left")


def _revision_context(document: CanonicalDocument | None = None, **overrides) -> DocumentRevisionContext:
    """Test-only helper: builds a valid DocumentRevisionContext, defaulting
    logical_document_id/source_document_sha256 from the given document (or
    from _doc()'s own defaults) so most tests never need to think about
    revision lineage explicitly -- only the tests in the revision-lineage
    section below construct one by hand."""
    logical_document_id = overrides.pop("logical_document_id", document.doc_id if document else "DOC1")
    source_document_sha256 = overrides.pop("source_document_sha256", document.source_sha256 if document else "a" * 64)
    version_label = overrides.pop("version_label", None)
    revision_number = overrides.pop("revision_number", None)
    document_revision_id = compute_document_revision_id(
        logical_document_id=logical_document_id,
        source_document_sha256=source_document_sha256,
        version_label=version_label,
        revision_number=revision_number,
    )
    return DocumentRevisionContext(
        logical_document_id=logical_document_id,
        document_revision_id=document_revision_id,
        source_document_sha256=source_document_sha256,
        version_label=version_label,
        revision_number=revision_number,
    )


def _chunk(
    document: CanonicalDocument,
    config: ChunkingConfig | None = None,
    revision_context: DocumentRevisionContext | None = None,
) -> list[CanonicalChunk]:
    """Test-only wrapper over chunk_document() that supplies a default
    DocumentRevisionContext (derived from the document) when the caller
    doesn't need to exercise revision lineage explicitly."""
    rc = revision_context or _revision_context(document)
    return chunk_document(document, config, revision_context=rc)


# --- 1/2/3. determinism, stable ids/hashes, content-change sensitivity -----


def _sample_document(paragraph_text: str = "Hello world.") -> CanonicalDocument:
    return _doc(
        headings=[CanonicalHeading(block_id="h1", unit_index=0, order_index=0, text="Title", level=1)],
        paragraphs=[
            CanonicalParagraph(block_id="p1", unit_index=0, order_index=1, text=paragraph_text),
            CanonicalParagraph(block_id="p2", unit_index=0, order_index=2, text="Second paragraph."),
        ],
    )


def test_repeated_runs_produce_byte_equivalent_serialized_chunks():
    document = _sample_document()
    config = ChunkingConfig()
    chunks_a = _chunk(document, config)
    chunks_b = _chunk(document, config)

    serialized_a = [c.model_dump_json() for c in chunks_a]
    serialized_b = [c.model_dump_json() for c in chunks_b]
    assert serialized_a == serialized_b


def test_chunk_ids_and_content_hashes_are_deterministic():
    document = _sample_document()
    chunks_a = _chunk(document)
    chunks_b = _chunk(document)
    assert [c.chunk_id for c in chunks_a] == [c.chunk_id for c in chunks_b]
    assert [c.content_sha256 for c in chunks_a] == [c.content_sha256 for c in chunks_b]


def test_changing_source_content_changes_content_hash():
    chunks_a = _chunk(_sample_document("Hello world."))
    chunks_b = _chunk(_sample_document("Goodbye world."))
    assert chunks_a[0].content_sha256 != chunks_b[0].content_sha256
    assert chunks_a[0].chunk_id != chunks_b[0].chunk_id


def test_unchanged_content_same_doc_id_gives_identical_hash():
    chunks_a = _chunk(_sample_document("Hello world."))
    chunks_b = _chunk(_sample_document("Hello world."))
    assert chunks_a[0].content_sha256 == chunks_b[0].content_sha256


# --- 4. changing config changes config hash and chunk boundaries -----------


def test_changing_config_changes_config_hash():
    document = _sample_document()
    default_chunks = _chunk(document, ChunkingConfig())
    other_chunks = _chunk(document, ChunkingConfig(max_chars=5000))
    assert default_chunks[0].chunking_config_hash != other_chunks[0].chunking_config_hash


def test_smaller_max_chars_changes_chunk_boundaries():
    document = _doc(
        paragraphs=[
            CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="A" * 100),
            CanonicalParagraph(block_id="p2", unit_index=0, order_index=1, text="B" * 100),
        ],
    )
    packed = _chunk(document, ChunkingConfig(max_chars=1000))
    assert len(packed) == 1  # both paragraphs fit in one chunk

    split = _chunk(document, ChunkingConfig(max_chars=150))
    assert len(split) == 2  # forced into separate chunks
    assert split[0].chunking_config_hash != packed[0].chunking_config_hash


# --- 5. text chunks preserve paragraph order --------------------------------


def test_text_chunk_preserves_paragraph_order():
    document = _doc(
        paragraphs=[
            CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="First."),
            CanonicalParagraph(block_id="p2", unit_index=0, order_index=1, text="Second."),
            CanonicalParagraph(block_id="p3", unit_index=0, order_index=2, text="Third."),
        ],
    )
    chunks = _chunk(document)
    assert len(chunks) == 1
    assert chunks[0].source_text == "First.\n\nSecond.\n\nThird."
    assert chunks[0].source_element_ids == ["p1", "p2", "p3"]


def test_paragraph_order_independent_of_input_list_order():
    """Ordering comes from (unit_index, order_index, ...), never from the
    order paragraphs happen to appear in the CanonicalDocument's list."""
    document = _doc(
        paragraphs=[
            CanonicalParagraph(block_id="p3", unit_index=0, order_index=2, text="Third."),
            CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="First."),
            CanonicalParagraph(block_id="p2", unit_index=0, order_index=1, text="Second."),
        ],
    )
    chunks = _chunk(document)
    assert chunks[0].source_text == "First.\n\nSecond.\n\nThird."


# --- 6. chunks do not cross unit boundaries by default ----------------------


def test_chunks_do_not_cross_unit_boundaries_by_default():
    document = _doc(
        paragraphs=[
            CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="Page zero text."),
            CanonicalParagraph(block_id="p2", unit_index=1, order_index=0, text="Page one text."),
        ],
    )
    chunks = _chunk(document)
    assert len(chunks) == 2
    assert chunks[0].unit_indices == [0]
    assert chunks[1].unit_indices == [1]


def test_cross_unit_boundaries_true_merges_when_enabled():
    document = _doc(
        paragraphs=[
            CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="Page zero text."),
            CanonicalParagraph(block_id="p2", unit_index=1, order_index=0, text="Page one text."),
        ],
    )
    chunks = _chunk(document, ChunkingConfig(cross_unit_boundaries=True))
    assert len(chunks) == 1
    assert chunks[0].unit_indices == [0, 1]


# --- 7. heading hierarchy ----------------------------------------------------


def test_heading_hierarchy_included_correctly():
    document = _doc(
        headings=[
            CanonicalHeading(block_id="h1", unit_index=0, order_index=0, text="H1", level=1),
            CanonicalHeading(block_id="h2", unit_index=0, order_index=1, text="H2", level=2),
        ],
        paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=2, text="Body.")],
    )
    chunks = _chunk(document)
    assert len(chunks) == 1
    assert chunks[0].heading_path == ["H1", "H2"]
    assert chunks[0].retrieval_text.startswith("H1 > H2\n\n")


def test_sibling_heading_replaces_deeper_heading_in_path():
    document = _doc(
        headings=[
            CanonicalHeading(block_id="h1", unit_index=0, order_index=0, text="H1", level=1),
            CanonicalHeading(block_id="h2", unit_index=0, order_index=1, text="H2", level=2),
            CanonicalHeading(block_id="h3", unit_index=0, order_index=2, text="H3-sibling-of-h1", level=1),
        ],
        paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=3, text="Body.")],
    )
    chunks = _chunk(document)
    text_chunks = [c for c in chunks if c.chunk_type == "text" and c.source_text == "Body."]
    assert len(text_chunks) == 1
    assert text_chunks[0].heading_path == ["H3-sibling-of-h1"]

    # H1/H2's section had no real content before being superseded -> each
    # gets its own heading-only chunk.
    heading_only = {c.source_text for c in chunks if c.source_text in ("H1", "H2")}
    assert heading_only == {"H1", "H2"}


def test_heading_with_no_following_content_gets_standalone_chunk():
    document = _doc(headings=[CanonicalHeading(block_id="h1", unit_index=0, order_index=0, text="Lonely Heading", level=1)])
    chunks = _chunk(document)
    assert len(chunks) == 1
    assert chunks[0].source_text == "Lonely Heading"
    assert chunks[0].source_element_ids == ["h1"]


def test_heading_with_content_does_not_get_standalone_chunk():
    document = _doc(
        headings=[CanonicalHeading(block_id="h1", unit_index=0, order_index=0, text="Heading", level=1)],
        paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=1, text="Body.")],
    )
    chunks = _chunk(document)
    assert len(chunks) == 1
    assert chunks[0].source_text == "Body."
    assert chunks[0].heading_path == ["Heading"]


# --- 8. nested list order/indentation ---------------------------------------


def test_nested_list_order_and_indentation_preserved():
    document = _doc(
        list_items=[
            CanonicalListItem(block_id="l1", unit_index=0, order_index=0, text="Parent", list_id="l", indent_level=0),
            CanonicalListItem(block_id="l2", unit_index=0, order_index=1, text="Child A", list_id="l", indent_level=1, parent_block_id="l1"),
            CanonicalListItem(block_id="l3", unit_index=0, order_index=2, text="Child B", list_id="l", indent_level=1, parent_block_id="l1"),
            CanonicalListItem(block_id="l4", unit_index=0, order_index=3, text="Grandchild", list_id="l", indent_level=2, parent_block_id="l3"),
        ],
    )
    chunks = _chunk(document)
    assert len(chunks) == 1
    assert chunks[0].source_text == (
        "- Parent\n\n"
        "  - Child A\n\n"
        "  - Child B\n\n"
        "    - Grandchild"
    )
    assert chunks[0].source_element_ids == ["l1", "l2", "l3", "l4"]


# --- 9. tables -----------------------------------------------------------


def test_table_becomes_standalone_chunk_with_all_cells_and_spans():
    table = CanonicalTable(
        table_id="t1", unit_index=0, order_index=0, n_rows=2, n_cols=2,
        cells=[
            CanonicalTableCell(row=0, col=0, text="Header", is_header=True, col_span=2),
            CanonicalTableCell(row=1, col=0, text="A", row_span=1),
            CanonicalTableCell(row=1, col=1, text="B"),
        ],
    )
    document = _doc(tables=[table])
    chunks = _chunk(document)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.chunk_type == "table"
    assert chunk.source_element_ids == ["t1"]
    assert "**Header**" in chunk.source_text
    assert "row=0,col=0,header=true,rowspan=1,colspan=2" in chunk.source_text
    assert "row=1,col=0,header=false,rowspan=1,colspan=1" in chunk.source_text
    assert "row=1,col=1,header=false,rowspan=1,colspan=1" in chunk.source_text


def test_table_as_standalone_false_merges_with_surrounding_text():
    table = CanonicalTable(
        table_id="t1", unit_index=0, order_index=1, n_rows=1, n_cols=1,
        cells=[CanonicalTableCell(row=0, col=0, text="Cell")],
    )
    document = _doc(
        paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="Intro.")],
        tables=[table],
    )
    chunks = _chunk(document, ChunkingConfig(table_as_standalone_chunk=False))
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "mixed"
    assert "Intro." in chunks[0].source_text
    assert "Cell" in chunks[0].source_text


# --- 10/15. pictures combined with captions, never duplicated --------------


def test_picture_combined_with_caption():
    picture = CanonicalPicture(picture_id="pic1", unit_index=0, content_sha256="c" * 64, artifact_ref="parity/pic1.png")
    caption = CanonicalCaption(block_id="cap1", unit_index=0, order_index=0, text="Figure 1: a diagram.", target_picture_id="pic1")
    document = _doc(pictures=[picture], captions=[caption])
    chunks = _chunk(document)
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "picture"
    assert "Figure 1: a diagram." in chunks[0].source_text
    assert chunks[0].source_element_ids == ["pic1", "cap1"]


def test_caption_not_duplicated_as_standalone_chunk():
    picture = CanonicalPicture(picture_id="pic1", unit_index=0, content_sha256="c" * 64, artifact_ref="parity/pic1.png")
    caption = CanonicalCaption(block_id="cap1", unit_index=0, order_index=0, text="Figure 1.", target_picture_id="pic1")
    paragraph = CanonicalParagraph(block_id="p1", unit_index=0, order_index=1, text="Unrelated paragraph.")
    document = _doc(pictures=[picture], captions=[caption], paragraphs=[paragraph])
    chunks = _chunk(document)

    picture_chunks = [c for c in chunks if c.chunk_type == "picture"]
    text_chunks = [c for c in chunks if c.chunk_type == "text"]
    assert len(picture_chunks) == 1
    assert "Figure 1." in picture_chunks[0].source_text
    # the caption text must not ALSO appear in any text chunk
    assert not any("Figure 1." in c.source_text for c in text_chunks)


# --- 11/12/13. source vs. model-derived separation --------------------------


def _picture_with_annotations(include_ocr=True, include_visible_text=True) -> CanonicalDocument:
    picture = CanonicalPicture(picture_id="pic1", unit_index=0, content_sha256="c" * 64, artifact_ref="parity/pic1.png")
    annotations = []
    if include_ocr:
        annotations.append(OcrAnnotation(
            annotation_id="a1", target_ref="pic1", unit_index=0,
            extraction_method="rapidocr", text="Incident Detected",
        ))
    if include_visible_text:
        annotations.append(VisibleTextAnnotation(
            annotation_id="a2", target_ref="pic1", unit_index=0,
            extraction_method="openai_vision_enrichment", text="Incident Detected (model reading)",
        ))
    annotations.append(ImageDescriptionAnnotation(
        annotation_id="a3", target_ref="pic1", unit_index=0,
        extraction_method="openai_vision_enrichment", description="A flow diagram showing escalation.",
    ))
    return _doc(pictures=[picture], annotations=annotations)


def test_source_text_and_model_derived_text_remain_separate():
    document = _picture_with_annotations()
    chunks = _chunk(document)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert "Incident Detected" in chunk.source_text
    assert "model reading" not in chunk.source_text
    assert "flow diagram" not in chunk.source_text
    assert chunk.model_derived_text is not None
    assert "model reading" in chunk.model_derived_text
    assert "flow diagram" in chunk.model_derived_text
    assert chunk.contains_model_derived is True


def test_model_derived_annotations_excluded_from_retrieval_text_when_configured_off():
    document = _picture_with_annotations()
    chunks_on = _chunk(document, ChunkingConfig(include_model_derived_annotations=True))
    chunks_off = _chunk(document, ChunkingConfig(include_model_derived_annotations=False))

    assert "model reading" in chunks_on[0].retrieval_text
    assert "model reading" not in chunks_off[0].retrieval_text
    # model_derived_text itself is still populated regardless -- only
    # retrieval_text (the config-filtered view) is affected.
    assert chunks_off[0].model_derived_text is not None
    assert chunks_off[0].contains_model_derived is True


def test_ocr_annotation_is_source_visible_text_annotation_is_model_derived():
    document = _picture_with_annotations()
    chunk = _chunk(document)[0]
    assert "Incident Detected" in chunk.source_text  # from OcrAnnotation
    assert "Incident Detected (model reading)" in chunk.model_derived_text  # from VisibleTextAnnotation


def test_identifier_annotation_not_duplicated_into_text():
    paragraph = CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="Application APP-224510 supports the service.")
    identifier = IdentifierAnnotation(
        annotation_id="a1", target_ref="p1", unit_index=0,
        derivation="extracted", extraction_method="text_scan",
        raw_text="APP-224510", normalized_value="APP-224510", start_char=12, end_char=22,
    )
    document = _doc(paragraphs=[paragraph], annotations=[identifier])
    chunk = _chunk(document)[0]
    assert chunk.source_text.count("APP-224510") == 1  # from the paragraph text itself, not duplicated
    assert chunk.annotation_ids == ["a1"]  # still tracked as metadata


# --- 14. diagram nodes/edges render deterministically -----------------------


def test_diagram_nodes_and_edges_render_deterministically():
    picture = CanonicalPicture(picture_id="pic1", unit_index=0, content_sha256="c" * 64, artifact_ref="parity/pic1.png")
    node1 = DiagramNodeAnnotation(
        annotation_id="a1", target_ref="pic1", unit_index=0,
        derivation="model_derived", extraction_method="openai_vision_enrichment",
        node_id="n1", label="Detect",
    )
    node2 = DiagramNodeAnnotation(
        annotation_id="a2", target_ref="pic1", unit_index=0,
        derivation="model_derived", extraction_method="openai_vision_enrichment",
        node_id="n2", label="Contain",
    )
    edge = DiagramEdgeAnnotation(
        annotation_id="a3", target_ref="pic1", unit_index=0,
        derivation="model_derived", extraction_method="openai_vision_enrichment",
        source_node_id="n1", target_node_id="n2",
    )
    document = _doc(pictures=[picture], annotations=[node1, node2, edge])
    chunk_a = _chunk(document)[0]
    chunk_b = _chunk(document)[0]

    assert "Diagram node: Detect" in chunk_a.model_derived_text
    assert "Diagram node: Contain" in chunk_a.model_derived_text
    assert "Diagram edge: Detect -> Contain" in chunk_a.model_derived_text
    assert chunk_a.model_derived_text == chunk_b.model_derived_text


def test_extracted_diagram_nodes_render_as_source_text():
    """DiagramNodeAnnotation/DiagramEdgeAnnotation with derivation="extracted"
    (e.g. native PPTX shapes) belong in source_text, not model_derived_text."""
    table = CanonicalTable(table_id="t1", unit_index=0, order_index=0, n_rows=1, n_cols=1, cells=[CanonicalTableCell(row=0, col=0, text="x")])
    node = DiagramNodeAnnotation(
        annotation_id="a1", target_ref="t1", unit_index=0,
        derivation="extracted", extraction_method="pptx_native_shapes",
        node_id="n1", label="Detect",
    )
    document = _doc(tables=[table], annotations=[node])
    chunk = _chunk(document)[0]
    assert "Diagram node: Detect" in chunk.source_text
    assert chunk.model_derived_text is None


# --- 16. oversized element splitting ----------------------------------------


def test_split_oversized_text_algorithm_is_documented_and_deterministic():
    text = "First sentence. Second sentence. Third sentence."
    fragments = split_oversized_text(text, max_chars=20)
    assert fragments == split_oversized_text(text, max_chars=20)  # deterministic
    assert "".join(f.text for f in fragments) == text  # exact, lossless reconstruction (no whitespace normalization)
    assert all(len(f.text) <= 20 or " " not in f.text for f in fragments)  # never splits mid-word
    assert [f.fragment_index for f in fragments] == list(range(len(fragments)))
    for f in fragments:
        assert text[f.start_char:f.end_char] == f.text  # span is a verbatim slice of the source text


def test_split_oversized_text_falls_back_to_whitespace_for_long_sentence():
    text = "Word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12."
    fragments = split_oversized_text(text, max_chars=15)
    assert all(len(f.text) <= 15 for f in fragments)
    assert "".join(f.text for f in fragments) == text  # no words lost, reassembles exactly


def test_split_oversized_text_fragments_are_ordered_and_nonoverlapping():
    text = "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu."
    fragments = split_oversized_text(text, max_chars=20)
    assert len(fragments) > 1
    assert fragments[0].start_char == 0
    assert fragments[-1].end_char == len(text)
    for prev, nxt in zip(fragments, fragments[1:]):
        assert prev.end_char == nxt.start_char  # contiguous, non-overlapping


def test_split_oversized_text_empty_text_returns_single_zero_length_fragment():
    fragments = split_oversized_text("", max_chars=20)
    assert len(fragments) == 1
    assert fragments[0] == TextFragment(text="", fragment_index=0, start_char=0, end_char=0)


def test_oversized_paragraph_splits_deterministically_and_retains_source_id():
    long_text = " ".join(f"This is sentence number {i} in a long paragraph." for i in range(15))
    document = _doc(paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text=long_text)])
    chunks = _chunk(document, ChunkingConfig(max_chars=100))
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.source_element_ids == ["p1"]
        assert len(chunk.source_text) <= 100 or " " not in chunk.source_text


def test_oversized_element_policy_keep_oversized_does_not_split():
    long_text = "This is a long sentence that will be repeated. " * 10
    document = _doc(paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text=long_text)])
    chunks = _chunk(document, ChunkingConfig(max_chars=100, oversized_element_policy="keep_oversized"))
    assert len(chunks) == 1
    assert chunks[0].source_text == long_text


# --- 17. no empty chunks -----------------------------------------------------


def test_no_empty_chunks_emitted():
    document = _doc(
        paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="   ")],
    )
    chunks = _chunk(document)
    assert chunks == []


def test_no_empty_chunks_across_full_document():
    document = _sample_document()
    chunks = _chunk(document)
    for chunk in chunks:
        assert chunk.source_text or chunk.model_derived_text


# --- 18. purity: CanonicalDocument unchanged after chunking -----------------


def test_document_unchanged_after_chunking():
    document = _sample_document()
    before = document.model_dump_json()
    _chunk(document)
    after = document.model_dump_json()
    assert before == after


# --- 19. JSON round-trip -----------------------------------------------------


def test_chunk_json_round_trip():
    document = _sample_document()
    chunks = _chunk(document)
    for chunk in chunks:
        serialized = chunk.model_dump_json()
        restored = CanonicalChunk.model_validate_json(serialized)
        assert restored == chunk


def test_chunking_config_json_round_trip():
    config = ChunkingConfig(max_chars=500, cross_unit_boundaries=True)
    restored = ChunkingConfig.model_validate_json(config.model_dump_json())
    assert restored == config


# --- 20. no forbidden dependencies ------------------------------------------


def test_chunking_source_has_no_forbidden_import_statements():
    """Checks for actual `import x` / `from x import ...` statements, module
    by module -- not bare substrings, since these modules' own docstrings
    legitimately name Docling/OpenAI to document what they don't depend on."""
    import ingestion_bench.chunking.chunker as chunker_module
    import ingestion_bench.chunking.model as model_module
    import ingestion_bench.chunking.renderers as renderers_module

    import_re = re.compile(r"^\s*(import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.MULTILINE)

    for module in (chunker_module, model_module, renderers_module):
        source = inspect.getsource(module)
        imported_top_level_modules = {m.group(2) for m in import_re.finditer(source)}
        forbidden_hits = imported_top_level_modules & set(FORBIDDEN_IMPORT_MODULES)
        assert not forbidden_hits, f"{module.__name__} imports forbidden module(s): {forbidden_hits}"


# --- extra: strict schema validation (extra="forbid") -----------------------


def test_canonical_chunk_rejects_unexpected_field():
    document = _sample_document()
    chunk = _chunk(document)[0]
    data = json.loads(chunk.model_dump_json())
    data["unexpected_field"] = "nope"
    with pytest.raises(ValidationError):
        CanonicalChunk.model_validate(data)


def test_chunking_config_rejects_unexpected_field():
    with pytest.raises(ValidationError):
        ChunkingConfig(max_chars=100, bogus_field=True)


def test_chunking_config_defaults_match_spec():
    config = ChunkingConfig()
    assert config.cross_unit_boundaries is False
    assert config.table_as_standalone_chunk is True
    assert config.picture_as_standalone_chunk is True


def test_canonical_sha256_is_deterministic_and_key_order_independent():
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})
    assert canonical_sha256({"a": 1}) != canonical_sha256({"a": 2})


# =====================================================================
# Stage 4.1 hardening
# =====================================================================

# --- 21. heading context is auditable ---------------------------------------


def test_content_chunk_traces_heading_context_to_both_canonical_elements():
    document = _doc(
        headings=[
            CanonicalHeading(block_id="h1", unit_index=0, order_index=0, text="H1", level=1),
            CanonicalHeading(block_id="h2", unit_index=0, order_index=1, text="H2", level=2),
        ],
        paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=2, text="Body.")],
    )
    chunk = _chunk(document)[0]
    assert chunk.heading_path == ["H1", "H2"]
    assert chunk.heading_source_element_ids == ["h1", "h2"]  # outermost to innermost
    assert [ref.element_id for ref in chunk.heading_source_refs] == ["h1", "h2"]
    assert all(ref.element_type == "heading" for ref in chunk.heading_source_refs)


def test_heading_own_annotations_are_not_silently_lost_when_popped_without_content():
    """A heading with no following content becomes its own standalone
    chunk (existing Stage 4 behavior) -- its own annotation_ids and
    model-derived rendering must survive onto that chunk, not be dropped."""
    heading = CanonicalHeading(block_id="h1", unit_index=0, order_index=0, text="Lonely Heading", level=1)
    annotation = ImageDescriptionAnnotation(
        annotation_id="a1", target_ref="h1", unit_index=0,
        extraction_method="openai_vision_enrichment", description="A heading-level note.",
    )
    document = _doc(headings=[heading], annotations=[annotation])
    chunk = _chunk(document)[0]
    assert chunk.source_text == "Lonely Heading"
    assert chunk.annotation_ids == ["a1"]
    assert chunk.model_derived_text is not None
    assert "heading-level note" in chunk.model_derived_text
    assert chunk.contains_model_derived is True


def test_active_heading_annotation_ids_propagate_into_content_chunks():
    heading = CanonicalHeading(block_id="h1", unit_index=0, order_index=0, text="H1", level=1)
    heading_annotation = ImageDescriptionAnnotation(
        annotation_id="a_head", target_ref="h1", unit_index=0,
        extraction_method="openai_vision_enrichment", description="Heading note.",
    )
    paragraph = CanonicalParagraph(block_id="p1", unit_index=0, order_index=1, text="Body.")
    document = _doc(headings=[heading], paragraphs=[paragraph], annotations=[heading_annotation])
    chunk = _chunk(document)[0]
    assert chunk.source_text == "Body."
    assert "a_head" in chunk.annotation_ids  # heading's own annotation is still tracked for audit
    assert chunk.heading_source_element_ids == ["h1"]


def test_heading_source_refs_empty_when_no_active_heading():
    document = _doc(paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="No heading.")])
    chunk = _chunk(document)[0]
    assert chunk.heading_source_element_ids == []
    assert chunk.heading_source_refs == []


# --- 22. structural table rendering -----------------------------------------


def test_sparse_table_renders_explicit_row_col_for_missing_cells():
    table = CanonicalTable(
        table_id="t1", unit_index=0, order_index=0, n_rows=2, n_cols=2,
        cells=[
            CanonicalTableCell(row=0, col=0, text="TopLeft"),
            CanonicalTableCell(row=1, col=1, text="BottomRight"),
        ],
    )
    document = _doc(tables=[table])
    chunk = _chunk(document)[0]
    assert "TopLeft [row=0,col=0,header=false,rowspan=1,colspan=1]" in chunk.source_text
    assert "BottomRight [row=1,col=1,header=false,rowspan=1,colspan=1]" in chunk.source_text


def test_table_cell_starting_at_nonzero_column_preserves_column_index():
    table = CanonicalTable(
        table_id="t1", unit_index=0, order_index=0, n_rows=2, n_cols=3,
        cells=[
            CanonicalTableCell(row=0, col=0, text="Spans", col_span=3, is_header=True),
            CanonicalTableCell(row=1, col=2, text="OnlyCell"),
        ],
    )
    document = _doc(tables=[table])
    chunk = _chunk(document)[0]
    assert "OnlyCell [row=1,col=2,header=false,rowspan=1,colspan=1]" in chunk.source_text
    assert "col=0" not in chunk.source_text.split("OnlyCell")[1]  # not misattributed to col 0


def test_table_rendering_independent_of_cell_input_order():
    cells_in_order = [
        CanonicalTableCell(row=0, col=0, text="A"),
        CanonicalTableCell(row=0, col=1, text="B"),
        CanonicalTableCell(row=1, col=0, text="C"),
        CanonicalTableCell(row=1, col=1, text="D"),
    ]
    cells_scrambled = [cells_in_order[3], cells_in_order[1], cells_in_order[2], cells_in_order[0]]

    document_a = _doc(tables=[CanonicalTable(table_id="t1", unit_index=0, order_index=0, n_rows=2, n_cols=2, cells=cells_in_order)])
    document_b = _doc(tables=[CanonicalTable(table_id="t1", unit_index=0, order_index=0, n_rows=2, n_cols=2, cells=cells_scrambled)])

    chunk_a = _chunk(document_a)[0]
    chunk_b = _chunk(document_b)[0]
    assert chunk_a.source_text == chunk_b.source_text


# --- 23. provenance included in content hashing -----------------------------


def test_changing_bbox_changes_content_hash_and_chunk_id_when_text_unchanged():
    doc_a = _doc(paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="Same text.", bbox=_bbox(0, 0, 10, 10))])
    doc_b = _doc(paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="Same text.", bbox=_bbox(5, 5, 15, 15))])
    chunk_a = _chunk(doc_a)[0]
    chunk_b = _chunk(doc_b)[0]
    assert chunk_a.source_text == chunk_b.source_text
    assert chunk_a.content_sha256 != chunk_b.content_sha256
    assert chunk_a.chunk_id != chunk_b.chunk_id


def test_changing_heading_bbox_changes_content_hash_via_heading_source_refs():
    doc_a = _doc(
        headings=[CanonicalHeading(block_id="h1", unit_index=0, order_index=0, text="H1", level=1, bbox=_bbox(0, 0, 10, 10))],
        paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=1, text="Body.")],
    )
    doc_b = _doc(
        headings=[CanonicalHeading(block_id="h1", unit_index=0, order_index=0, text="H1", level=1, bbox=_bbox(1, 1, 11, 11))],
        paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=1, text="Body.")],
    )
    chunk_a = [c for c in _chunk(doc_a) if c.source_text == "Body."][0]
    chunk_b = [c for c in _chunk(doc_b) if c.source_text == "Body."][0]
    assert chunk_a.content_sha256 != chunk_b.content_sha256


# --- 24. asset-only pictures --------------------------------------------------


def test_picture_with_caption_retains_asset_ref():
    picture = CanonicalPicture(picture_id="pic1", unit_index=0, content_sha256="c" * 64, artifact_ref="parity/pic1.png")
    caption = CanonicalCaption(block_id="cap1", unit_index=0, order_index=0, text="Figure 1.", target_picture_id="pic1")
    document = _doc(pictures=[picture], captions=[caption])
    chunk = _chunk(document)[0]
    assert len(chunk.asset_refs) == 1
    assert chunk.asset_refs[0].picture_id == "pic1"
    assert chunk.asset_refs[0].artifact_ref == "parity/pic1.png"
    assert chunk.asset_refs[0].content_sha256 == "c" * 64


def test_picture_with_ocr_retains_asset_ref():
    picture = CanonicalPicture(picture_id="pic1", unit_index=0, content_sha256="c" * 64, artifact_ref="parity/pic1.png")
    ocr = OcrAnnotation(annotation_id="a1", target_ref="pic1", unit_index=0, extraction_method="rapidocr", text="Detected text")
    document = _doc(pictures=[picture], annotations=[ocr])
    chunk = _chunk(document)[0]
    assert len(chunk.asset_refs) == 1
    assert "Detected text" in chunk.source_text


def test_picture_with_model_derived_annotations_retains_asset_ref():
    picture = CanonicalPicture(picture_id="pic1", unit_index=0, content_sha256="c" * 64, artifact_ref="parity/pic1.png")
    description = ImageDescriptionAnnotation(
        annotation_id="a1", target_ref="pic1", unit_index=0,
        extraction_method="openai_vision_enrichment", description="A chart.",
    )
    document = _doc(pictures=[picture], annotations=[description])
    chunk = _chunk(document)[0]
    assert len(chunk.asset_refs) == 1
    assert chunk.source_text == ""
    assert chunk.model_derived_text is not None


def test_picture_with_no_textual_annotations_still_emits_asset_only_chunk():
    picture = CanonicalPicture(picture_id="pic1", unit_index=0, content_sha256="c" * 64, artifact_ref="parity/pic1.png")
    document = _doc(pictures=[picture])
    chunks = _chunk(document)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.chunk_type == "picture"
    assert chunk.source_text == ""
    assert chunk.model_derived_text is None
    assert len(chunk.asset_refs) == 1
    assert chunk.asset_refs[0].picture_id == "pic1"
    # no artificial artifact-path prose was injected into retrieval_text
    assert "parity/pic1.png" not in chunk.retrieval_text
    assert chunk.retrieval_text == ""


# --- 25. chunk schema hardening ----------------------------------------------


def test_chunk_source_ref_rejects_negative_unit_index():
    with pytest.raises(ValidationError):
        ChunkSourceRef(element_id="x", unit_index=-1, element_type="paragraph")


def test_chunk_source_ref_rejects_negative_order_index():
    with pytest.raises(ValidationError):
        ChunkSourceRef(element_id="x", unit_index=0, order_index=-1, element_type="paragraph")


def test_chunk_source_ref_rejects_non_literal_element_type():
    with pytest.raises(ValidationError):
        ChunkSourceRef(element_id="x", unit_index=0, element_type="not_a_real_type")


def test_chunk_asset_ref_rejects_malformed_sha256():
    with pytest.raises(ValidationError):
        ChunkAssetRef(picture_id="pic1", artifact_ref="parity/pic1.png", content_sha256="not-hex", unit_index=0)


def test_canonical_chunk_rejects_uppercase_content_sha256():
    document = _sample_document()
    chunk = _chunk(document)[0]
    data = json.loads(chunk.model_dump_json())
    data["content_sha256"] = data["content_sha256"].upper()
    with pytest.raises(ValidationError):
        CanonicalChunk.model_validate(data)


def test_canonical_chunk_rejects_empty_unit_indices():
    document = _sample_document()
    chunk = _chunk(document)[0]
    data = json.loads(chunk.model_dump_json())
    data["unit_indices"] = []
    with pytest.raises(ValidationError):
        CanonicalChunk.model_validate(data)


def test_canonical_chunk_rejects_unsorted_unit_indices():
    document = _doc(paragraphs=[
        CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="A."),
        CanonicalParagraph(block_id="p2", unit_index=1, order_index=0, text="B."),
    ])
    chunk = _chunk(document, ChunkingConfig(cross_unit_boundaries=True))[0]
    data = json.loads(chunk.model_dump_json())
    data["unit_indices"] = list(reversed(data["unit_indices"]))
    with pytest.raises(ValidationError):
        CanonicalChunk.model_validate(data)


def test_canonical_chunk_rejects_duplicate_unit_indices():
    document = _sample_document()
    chunk = _chunk(document)[0]
    data = json.loads(chunk.model_dump_json())
    data["unit_indices"] = [0, 0]
    with pytest.raises(ValidationError):
        CanonicalChunk.model_validate(data)


def test_canonical_chunk_rejects_duplicate_source_element_ids():
    document = _sample_document()
    chunk = _chunk(document)[0]
    data = json.loads(chunk.model_dump_json())
    data["source_element_ids"] = [data["source_element_ids"][0], data["source_element_ids"][0]]
    with pytest.raises(ValidationError):
        CanonicalChunk.model_validate(data)


def test_canonical_chunk_rejects_duplicate_annotation_ids():
    document = _picture_with_annotations()
    chunk = _chunk(document)[0]
    data = json.loads(chunk.model_dump_json())
    assert data["annotation_ids"]  # sanity: this fixture actually has annotations
    data["annotation_ids"] = [data["annotation_ids"][0], data["annotation_ids"][0]]
    with pytest.raises(ValidationError):
        CanonicalChunk.model_validate(data)


def test_canonical_chunk_rejects_contains_model_derived_inconsistency():
    document = _sample_document()
    chunk = _chunk(document)[0]
    data = json.loads(chunk.model_dump_json())
    assert data["model_derived_text"] is None
    data["contains_model_derived"] = True  # inconsistent: no model_derived_text
    with pytest.raises(ValidationError):
        CanonicalChunk.model_validate(data)


# --- 26. max_chars semantics are documented ----------------------------------


def test_max_chars_limits_source_text_packing_not_retrieval_text():
    """max_chars governs how much SOURCE TEXT is packed into a buffer --
    the final retrieval_text may exceed it once heading context and/or a
    model-derived section are layered on top, per ChunkingConfig's
    documented contract."""
    heading = CanonicalHeading(block_id="h1", unit_index=0, order_index=0, text="A Very Long Heading Used As Context " * 3, level=1)
    paragraph = CanonicalParagraph(block_id="p1", unit_index=0, order_index=1, text="X" * 90)
    document = _doc(headings=[heading], paragraphs=[paragraph])
    chunk = _chunk(document, ChunkingConfig(max_chars=100))[0]
    assert len(chunk.source_text) <= 100
    assert len(chunk.retrieval_text) > 100  # heading-path prefix pushes it over max_chars


# --- 27. document-revision lineage and deduplication identities -------------


def test_two_revisions_of_one_logical_document_share_logical_id_differ_in_revision_id():
    rc_a = _revision_context(logical_document_id="LOGICAL1", source_document_sha256="a" * 64)
    rc_b = _revision_context(logical_document_id="LOGICAL1", source_document_sha256="b" * 64)
    assert rc_a.logical_document_id == rc_b.logical_document_id == "LOGICAL1"
    assert rc_a.document_revision_id != rc_b.document_revision_id


def test_identical_chunk_text_across_revisions_differs_in_chunk_id_shares_embedding_hash():
    doc_a = _doc(source_sha256="a" * 64, paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="Same text.")])
    doc_b = _doc(source_sha256="b" * 64, paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="Same text.")])
    rc_a = _revision_context(logical_document_id="LOGICAL1", source_document_sha256="a" * 64)
    rc_b = _revision_context(logical_document_id="LOGICAL1", source_document_sha256="b" * 64)

    chunk_a = _chunk(doc_a, revision_context=rc_a)[0]
    chunk_b = _chunk(doc_b, revision_context=rc_b)[0]

    assert chunk_a.retrieval_text == chunk_b.retrieval_text
    assert chunk_a.chunk_id != chunk_b.chunk_id
    assert chunk_a.document_revision_id != chunk_b.document_revision_id
    assert chunk_a.embedding_input_sha256 == chunk_b.embedding_input_sha256


def test_changing_only_provenance_changes_content_hash_but_not_embedding_hash():
    doc_a = _doc(paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="Same text.", bbox=_bbox(0, 0, 10, 10))])
    doc_b = _doc(paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="Same text.", bbox=_bbox(5, 5, 15, 15))])
    chunk_a = _chunk(doc_a)[0]
    chunk_b = _chunk(doc_b)[0]
    assert chunk_a.content_sha256 != chunk_b.content_sha256
    assert chunk_a.embedding_input_sha256 == chunk_b.embedding_input_sha256


def test_identical_identity_components_give_same_document_revision_id():
    id_a = compute_document_revision_id("LOGICAL1", "a" * 64, version_label="Draft", revision_number=1)
    id_b = compute_document_revision_id("LOGICAL1", "a" * 64, version_label="draft", revision_number=1)
    assert id_a == id_b  # version_label normalized (stripped/lower-cased)


def test_different_source_sha256_gives_different_document_revision_id():
    id_a = compute_document_revision_id("LOGICAL1", "a" * 64)
    id_b = compute_document_revision_id("LOGICAL1", "b" * 64)
    assert id_a != id_b


def test_document_revision_context_rejects_non_deterministic_id():
    with pytest.raises(ValidationError):
        DocumentRevisionContext(
            logical_document_id="LOGICAL1",
            document_revision_id="0" * 64,  # not compute_document_revision_id(...)'s actual output
            source_document_sha256="a" * 64,
        )


def test_chunk_document_rejects_source_sha256_mismatch():
    document = _doc(source_sha256="a" * 64)
    mismatched_context = _revision_context(logical_document_id="LOGICAL1", source_document_sha256="b" * 64)
    with pytest.raises(ValueError):
        chunk_document(document, revision_context=mismatched_context)


def test_no_mutable_revision_state_fields_on_canonical_chunk():
    forbidden_fields = {
        "is_latest", "is_current", "publication_status",
        "superseded_by_revision_id", "ingestion_timestamp", "ingested_at",
    }
    assert forbidden_fields & set(CanonicalChunk.model_fields) == set()


def test_canonical_chunk_carries_revision_lineage_fields():
    rc = _revision_context(
        logical_document_id="LOGICAL1", source_document_sha256="a" * 64,
        version_label="v2", revision_number=2,
    )
    document = _doc(source_sha256="a" * 64, paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="Body.")])
    chunk = _chunk(document, revision_context=rc)[0]
    assert chunk.logical_document_id == "LOGICAL1"
    assert chunk.document_revision_id == rc.document_revision_id
    assert chunk.source_document_sha256 == "a" * 64
    assert chunk.version_label == "v2"
    assert chunk.revision_number == 2


def test_text_sha256_is_deterministic_and_content_sensitive():
    assert text_sha256("hello") == text_sha256("hello")
    assert text_sha256("hello") != text_sha256("goodbye")


# =====================================================================
# Stage 4.2 correctness patch
# =====================================================================

# --- 28. fragment-level provenance for oversized-element splitting ----------


def test_repeated_sentence_paragraph_splits_without_duplicate_occurrence_error():
    """The exact scenario that used to trip the Stage 4.1
    duplicate-occurrence guard: a paragraph that repeats the same sentence
    verbatim. Fragment-level (start_char, end_char) provenance means the
    guard now sees each fragment as distinct even when its rendered text
    is identical to another fragment's."""
    sentence = "This exact sentence repeats. "
    long_text = sentence * 10
    document = _doc(paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text=long_text)])
    chunks = _chunk(document, ChunkingConfig(max_chars=60))  # must not raise

    assert len(chunks) > 1
    assert len(set(c.chunk_id for c in chunks)) == len(chunks)  # unique chunk ids

    spans = [(chunk.source_refs[0].start_char, chunk.source_refs[0].end_char) for chunk in chunks]
    assert spans == sorted(spans)  # ordered
    assert spans[0][0] == 0
    assert spans[-1][1] == len(long_text)
    for (_, prev_end), (next_start, _) in zip(spans, spans[1:]):
        assert prev_end == next_start  # contiguous, non-overlapping

    reconstructed = "".join(chunk.source_text for chunk in chunks)
    assert reconstructed == long_text  # lossless


def test_identifier_annotation_routed_to_later_fragment_by_offset():
    prefix = "Intro sentence one. Intro sentence two. Intro sentence three. "
    identifier_text = "APP-998877"
    long_text = (
        prefix * 3
        + f"Application {identifier_text} is referenced here. "
        + "Trailing filler sentence. " * 3
    )
    start_char = long_text.index(identifier_text)
    end_char = start_char + len(identifier_text)

    identifier = IdentifierAnnotation(
        annotation_id="a1", target_ref="p1", unit_index=0,
        derivation="extracted", extraction_method="text_scan",
        raw_text=identifier_text, normalized_value=identifier_text,
        start_char=start_char, end_char=end_char,
    )
    document = _doc(
        paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text=long_text)],
        annotations=[identifier],
    )
    chunks = _chunk(document, ChunkingConfig(max_chars=80))
    assert len(chunks) > 1

    fragment0_chunk = next(c for c in chunks if c.source_refs[0].fragment_index == 0)
    assert "a1" not in fragment0_chunk.annotation_ids  # identifier is well past fragment 0

    matching = [c for c in chunks if "a1" in c.annotation_ids]
    assert matching  # routed to at least one later fragment
    for c in matching:
        ref = c.source_refs[0]
        assert ref.fragment_index > 0
        assert ref.start_char < end_char and ref.end_char > start_char  # overlaps the identifier's span


def test_chunk_source_ref_fragment_fields_default_to_none_when_not_split():
    document = _doc(paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="Short.")])
    chunk = _chunk(document)[0]
    ref = chunk.source_refs[0]
    assert ref.fragment_index is None
    assert ref.start_char is None
    assert ref.end_char is None


def test_chunk_source_ref_rejects_unpaired_char_span():
    with pytest.raises(ValidationError):
        ChunkSourceRef(element_id="x", unit_index=0, element_type="paragraph", start_char=5, end_char=None)


def test_chunk_source_ref_rejects_start_greater_than_end():
    with pytest.raises(ValidationError):
        ChunkSourceRef(element_id="x", unit_index=0, element_type="paragraph", start_char=10, end_char=5)


def test_chunk_source_ref_rejects_negative_fragment_index():
    with pytest.raises(ValidationError):
        ChunkSourceRef(element_id="x", unit_index=0, element_type="paragraph", fragment_index=-1)


def test_text_fragment_rejects_start_greater_than_end():
    with pytest.raises(ValidationError):
        TextFragment(text="x", fragment_index=0, start_char=10, end_char=5)


# --- 29. active heading annotation rendering is preserved --------------------


def test_heading_extracted_annotation_content_appears_in_body_chunk_source_text():
    heading = CanonicalHeading(block_id="h1", unit_index=0, order_index=0, text="H1", level=1)
    extracted = OcrAnnotation(
        annotation_id="a1", target_ref="h1", unit_index=0,
        extraction_method="rapidocr", text="Heading OCR text",
    )
    paragraph = CanonicalParagraph(block_id="p1", unit_index=0, order_index=1, text="Body.")
    document = _doc(headings=[heading], paragraphs=[paragraph], annotations=[extracted])
    chunk = _chunk(document)[0]
    assert chunk.source_text == "Body.\n\n[Heading: H1] OCR: Heading OCR text"
    assert "a1" in chunk.annotation_ids  # traceable by annotation_id
    assert chunk.model_derived_text is None


def test_heading_model_derived_annotation_content_appears_in_model_derived_text_and_respects_config():
    heading = CanonicalHeading(block_id="h1", unit_index=0, order_index=0, text="H1", level=1)
    model_derived = ImageDescriptionAnnotation(
        annotation_id="a1", target_ref="h1", unit_index=0,
        extraction_method="openai_vision_enrichment", description="Heading-level insight.",
    )
    paragraph = CanonicalParagraph(block_id="p1", unit_index=0, order_index=1, text="Body.")
    document = _doc(headings=[heading], paragraphs=[paragraph], annotations=[model_derived])

    chunk_on = _chunk(document, ChunkingConfig(include_model_derived_annotations=True))[0]
    chunk_off = _chunk(document, ChunkingConfig(include_model_derived_annotations=False))[0]

    expected_model_derived = "[Heading: H1] Description (model-derived, unverified): Heading-level insight."
    assert chunk_on.model_derived_text == expected_model_derived  # present in the appropriate field
    # model_derived_text itself is always populated, regardless of config --
    # only retrieval_text is config-filtered.
    assert chunk_off.model_derived_text == expected_model_derived
    assert "a1" in chunk_on.annotation_ids  # traceable by annotation_id

    assert "Heading-level insight" in chunk_on.retrieval_text
    assert "Heading-level insight" not in chunk_off.retrieval_text


def test_heading_annotation_content_reaches_standalone_lonely_heading_ancestor_chunk():
    """An ancestor heading's own rendered annotation content must also
    reach a DESCENDANT heading's standalone (no-content) chunk, not just
    ids -- the same rule as for ordinary body content."""
    parent = CanonicalHeading(block_id="h1", unit_index=0, order_index=0, text="Parent", level=1)
    parent_annotation = OcrAnnotation(
        annotation_id="a1", target_ref="h1", unit_index=0,
        extraction_method="rapidocr", text="Parent OCR",
    )
    child = CanonicalHeading(block_id="h2", unit_index=0, order_index=1, text="Child", level=2)
    document = _doc(headings=[parent, child], annotations=[parent_annotation])
    chunks = _chunk(document)
    child_chunk = next(c for c in chunks if c.source_element_ids == ["h2"])
    assert child_chunk.source_text == "Child\n\n[Heading: Parent] OCR: Parent OCR"
    assert "a1" in child_chunk.annotation_ids


# --- 30. revision version-label canonicalization -----------------------------


def test_version_label_is_normalized_on_storage():
    rc = _revision_context(logical_document_id="LOGICAL1", source_document_sha256="a" * 64, version_label="  Draft  ")
    assert rc.version_label == "draft"


def test_version_label_rejects_empty_after_strip():
    with pytest.raises(ValidationError):
        DocumentRevisionContext(
            logical_document_id="LOGICAL1",
            document_revision_id="0" * 64,
            source_document_sha256="a" * 64,
            version_label="   ",
        )


def test_logical_document_id_rejects_empty_after_strip():
    with pytest.raises(ValidationError):
        DocumentRevisionContext(
            logical_document_id="   ",
            document_revision_id="0" * 64,
            source_document_sha256="a" * 64,
        )


def test_equal_normalized_version_label_gives_identical_stored_lineage_and_chunk_metadata():
    rc_a = _revision_context(logical_document_id="LOGICAL1", source_document_sha256="a" * 64, version_label="Draft")
    rc_b = _revision_context(logical_document_id="LOGICAL1", source_document_sha256="a" * 64, version_label="draft")
    assert rc_a.version_label == rc_b.version_label == "draft"
    assert rc_a.document_revision_id == rc_b.document_revision_id

    document = _doc(source_sha256="a" * 64, paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="Body.")])
    chunk_a = _chunk(document, revision_context=rc_a)[0]
    chunk_b = _chunk(document, revision_context=rc_b)[0]
    assert chunk_a.model_dump_json() == chunk_b.model_dump_json()  # fully identical serialized lineage + content


# --- 31. embedding_input_sha256 is optional for non-textual chunks ----------


def test_asset_only_picture_chunk_has_no_embedding_input_hash():
    picture = CanonicalPicture(picture_id="pic1", unit_index=0, content_sha256="c" * 64, artifact_ref="parity/pic1.png")
    document = _doc(pictures=[picture])
    chunk = _chunk(document)[0]
    assert chunk.retrieval_text == ""
    assert chunk.embedding_input_sha256 is None


def test_nontextual_picture_chunks_do_not_share_embedding_hash_of_empty_string():
    picture_a = CanonicalPicture(picture_id="pic1", unit_index=0, content_sha256="c" * 64, artifact_ref="parity/pic1.png")
    picture_b = CanonicalPicture(picture_id="pic2", unit_index=1, content_sha256="d" * 64, artifact_ref="parity/pic2.png")
    document = _doc(pictures=[picture_a, picture_b])
    chunks = _chunk(document)
    assert len(chunks) == 2
    assert all(c.embedding_input_sha256 is None for c in chunks)


def test_nonempty_retrieval_text_chunk_has_embedding_input_hash():
    document = _sample_document()
    chunk = _chunk(document)[0]
    assert chunk.retrieval_text
    assert chunk.embedding_input_sha256 == text_sha256(chunk.retrieval_text)


def test_canonical_chunk_allows_none_embedding_input_sha256_round_trip():
    picture = CanonicalPicture(picture_id="pic1", unit_index=0, content_sha256="c" * 64, artifact_ref="parity/pic1.png")
    document = _doc(pictures=[picture])
    chunk = _chunk(document)[0]
    data = json.loads(chunk.model_dump_json())
    assert data["embedding_input_sha256"] is None
    restored = CanonicalChunk.model_validate(data)
    assert restored.embedding_input_sha256 is None


def test_canonical_chunk_rejects_malformed_embedding_input_sha256_when_present():
    document = _sample_document()
    chunk = _chunk(document)[0]
    data = json.loads(chunk.model_dump_json())
    assert data["embedding_input_sha256"] is not None
    data["embedding_input_sha256"] = "not-a-sha256"
    with pytest.raises(ValidationError):
        CanonicalChunk.model_validate(data)


# --- 32. all stable hash identities are validated ----------------------------


def test_canonical_chunk_rejects_malformed_chunk_id():
    document = _sample_document()
    chunk = _chunk(document)[0]
    data = json.loads(chunk.model_dump_json())
    data["chunk_id"] = "not-a-sha256"
    with pytest.raises(ValidationError):
        CanonicalChunk.model_validate(data)


def test_canonical_chunk_rejects_malformed_document_revision_id():
    document = _sample_document()
    chunk = _chunk(document)[0]
    data = json.loads(chunk.model_dump_json())
    data["document_revision_id"] = "not-a-sha256"
    with pytest.raises(ValidationError):
        CanonicalChunk.model_validate(data)


# --- 33. table metadata always includes every field explicitly --------------


def test_table_rendering_always_includes_header_and_span_defaults():
    table = CanonicalTable(
        table_id="t1", unit_index=0, order_index=0, n_rows=1, n_cols=1,
        cells=[CanonicalTableCell(row=0, col=0, text="Plain")],
    )
    document = _doc(tables=[table])
    chunk = _chunk(document)[0]
    # a plain, non-header, non-spanning cell still states header=false and
    # rowspan=1/colspan=1 explicitly -- never omitted as an implied default.
    assert "Plain [row=0,col=0,header=false,rowspan=1,colspan=1]" in chunk.source_text


# =====================================================================
# Stage 4.2a fragment-provenance correction
# =====================================================================

# --- 34. splitting operates on canonical element text, not rendered text ----


def _long_sentences(n: int, label: str = "Sentence number") -> str:
    return " ".join(f"{label} {i} in a long passage." for i in range(n))


def test_oversized_paragraph_with_extracted_annotation_splits_correctly():
    paragraph_text = _long_sentences(15)
    ocr = OcrAnnotation(annotation_id="a1", target_ref="p1", unit_index=0, extraction_method="rapidocr", text="Extracted note")
    document = _doc(
        paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text=paragraph_text)],
        annotations=[ocr],
    )
    chunks = _chunk(document, ChunkingConfig(max_chars=100))
    assert len(chunks) > 1
    # the extracted annotation's rendered content appears exactly once,
    # attached to fragment 0 only (existing fragment-0-default convention)
    matches = [c for c in chunks if "Extracted note" in c.source_text]
    assert len(matches) == 1
    assert matches[0].source_refs[0].fragment_index == 0
    assert "a1" in matches[0].annotation_ids


def test_annotation_rendering_does_not_affect_fragment_spans():
    paragraph_text = _long_sentences(15)
    doc_without = _doc(paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text=paragraph_text)])
    ocr = OcrAnnotation(annotation_id="a1", target_ref="p1", unit_index=0, extraction_method="rapidocr", text="Extracted note")
    doc_with = _doc(
        paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text=paragraph_text)],
        annotations=[ocr],
    )

    chunks_without = _chunk(doc_without, ChunkingConfig(max_chars=100))
    chunks_with = _chunk(doc_with, ChunkingConfig(max_chars=100))

    spans_without = [(c.source_refs[0].start_char, c.source_refs[0].end_char) for c in chunks_without]
    spans_with = [(c.source_refs[0].start_char, c.source_refs[0].end_char) for c in chunks_with]
    assert spans_without == spans_with  # identical split points regardless of the annotation


def test_fragment_spans_reconstruct_original_paragraph_text_exactly():
    paragraph_text = _long_sentences(15)
    document = _doc(paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text=paragraph_text)])
    chunks = _chunk(document, ChunkingConfig(max_chars=100))
    assert len(chunks) > 1
    reconstructed = "".join(paragraph_text[c.source_refs[0].start_char:c.source_refs[0].end_char] for c in chunks)
    assert reconstructed == paragraph_text


def test_fragment_spans_reconstruct_original_list_item_text_exactly():
    item_text = _long_sentences(15, label="Item sentence number")
    item = CanonicalListItem(block_id="l1", unit_index=0, order_index=0, text=item_text, list_id="l", indent_level=1)
    document = _doc(list_items=[item])
    chunks = _chunk(document, ChunkingConfig(max_chars=100))
    assert len(chunks) > 1
    reconstructed = "".join(item_text[c.source_refs[0].start_char:c.source_refs[0].end_char] for c in chunks)
    assert reconstructed == item_text  # spans are against item.text, never the "  - "-prefixed rendering
    # the display prefix appears on every fragment's rendered source_text,
    # even though it is never part of the canonical span above
    assert all(c.source_text.startswith("  - ") for c in chunks)


def test_oversized_list_item_identifier_routed_to_later_fragment_despite_prefix():
    identifier_text = "APP-334455"
    item_text = (
        _long_sentences(6, label="Filler sentence")
        + f" A reference to {identifier_text} is noted here. "
        + _long_sentences(4, label="Trailing sentence")
    )
    start_char = item_text.index(identifier_text)
    end_char = start_char + len(identifier_text)

    item = CanonicalListItem(block_id="l1", unit_index=0, order_index=0, text=item_text, list_id="l", indent_level=2)
    identifier = IdentifierAnnotation(
        annotation_id="a1", target_ref="l1", unit_index=0,
        derivation="extracted", extraction_method="text_scan",
        raw_text=identifier_text, normalized_value=identifier_text,
        start_char=start_char, end_char=end_char,
    )
    document = _doc(list_items=[item], annotations=[identifier])
    chunks = _chunk(document, ChunkingConfig(max_chars=80))
    assert len(chunks) > 1

    fragment0_chunk = next(c for c in chunks if c.source_refs[0].fragment_index == 0)
    assert "a1" not in fragment0_chunk.annotation_ids  # identifier is well past fragment 0

    matching = [c for c in chunks if "a1" in c.annotation_ids]
    assert matching  # routed to at least one later fragment
    for c in matching:
        ref = c.source_refs[0]
        assert ref.fragment_index > 0
        # overlap test in item.text's own coordinate space -- unaffected
        # by the "    - " display prefix rendered onto c.source_text
        assert ref.start_char < end_char and ref.end_char > start_char
        assert c.source_text.startswith("    - ")  # indent_level=2 -> 4 spaces + "- "


# --- 35. strengthened ChunkSourceRef / TextFragment validation --------------


def test_chunk_source_ref_rejects_fragment_index_without_char_span():
    with pytest.raises(ValidationError):
        ChunkSourceRef(element_id="x", unit_index=0, element_type="paragraph", fragment_index=0)


def test_chunk_source_ref_rejects_char_span_without_fragment_index():
    with pytest.raises(ValidationError):
        ChunkSourceRef(element_id="x", unit_index=0, element_type="paragraph", start_char=0, end_char=5)


def test_chunk_source_ref_rejects_start_char_without_end_char_or_fragment_index():
    with pytest.raises(ValidationError):
        ChunkSourceRef(element_id="x", unit_index=0, element_type="paragraph", start_char=0)


def test_chunk_source_ref_accepts_all_three_fragment_fields_together():
    ref = ChunkSourceRef(element_id="x", unit_index=0, element_type="paragraph", fragment_index=0, start_char=0, end_char=5)
    assert ref.fragment_index == 0
    assert ref.start_char == 0
    assert ref.end_char == 5


def test_chunk_source_ref_accepts_all_three_fragment_fields_absent():
    ref = ChunkSourceRef(element_id="x", unit_index=0, element_type="paragraph")
    assert ref.fragment_index is None
    assert ref.start_char is None
    assert ref.end_char is None


def test_text_fragment_rejects_text_length_span_mismatch():
    with pytest.raises(ValidationError):
        TextFragment(text="hello", fragment_index=0, start_char=0, end_char=10)


def test_text_fragment_accepts_matching_text_length_and_span():
    fragment = TextFragment(text="hello", fragment_index=0, start_char=3, end_char=8)
    assert len(fragment.text) == fragment.end_char - fragment.start_char
