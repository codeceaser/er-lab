"""Tests for the canonical chunking layer (Stage 4).

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
from ingestion_bench.chunking import CanonicalChunk, ChunkingConfig, canonical_sha256, chunk_document
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
    chunks_a = chunk_document(document, config)
    chunks_b = chunk_document(document, config)

    serialized_a = [c.model_dump_json() for c in chunks_a]
    serialized_b = [c.model_dump_json() for c in chunks_b]
    assert serialized_a == serialized_b


def test_chunk_ids_and_content_hashes_are_deterministic():
    document = _sample_document()
    chunks_a = chunk_document(document)
    chunks_b = chunk_document(document)
    assert [c.chunk_id for c in chunks_a] == [c.chunk_id for c in chunks_b]
    assert [c.content_sha256 for c in chunks_a] == [c.content_sha256 for c in chunks_b]


def test_changing_source_content_changes_content_hash():
    chunks_a = chunk_document(_sample_document("Hello world."))
    chunks_b = chunk_document(_sample_document("Goodbye world."))
    assert chunks_a[0].content_sha256 != chunks_b[0].content_sha256
    assert chunks_a[0].chunk_id != chunks_b[0].chunk_id


def test_unchanged_content_same_doc_id_gives_identical_hash():
    chunks_a = chunk_document(_sample_document("Hello world."))
    chunks_b = chunk_document(_sample_document("Hello world."))
    assert chunks_a[0].content_sha256 == chunks_b[0].content_sha256


# --- 4. changing config changes config hash and chunk boundaries -----------


def test_changing_config_changes_config_hash():
    document = _sample_document()
    default_chunks = chunk_document(document, ChunkingConfig())
    other_chunks = chunk_document(document, ChunkingConfig(max_chars=5000))
    assert default_chunks[0].chunking_config_hash != other_chunks[0].chunking_config_hash


def test_smaller_max_chars_changes_chunk_boundaries():
    document = _doc(
        paragraphs=[
            CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="A" * 100),
            CanonicalParagraph(block_id="p2", unit_index=0, order_index=1, text="B" * 100),
        ],
    )
    packed = chunk_document(document, ChunkingConfig(max_chars=1000))
    assert len(packed) == 1  # both paragraphs fit in one chunk

    split = chunk_document(document, ChunkingConfig(max_chars=150))
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
    chunks = chunk_document(document)
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
    chunks = chunk_document(document)
    assert chunks[0].source_text == "First.\n\nSecond.\n\nThird."


# --- 6. chunks do not cross unit boundaries by default ----------------------


def test_chunks_do_not_cross_unit_boundaries_by_default():
    document = _doc(
        paragraphs=[
            CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="Page zero text."),
            CanonicalParagraph(block_id="p2", unit_index=1, order_index=0, text="Page one text."),
        ],
    )
    chunks = chunk_document(document)
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
    chunks = chunk_document(document, ChunkingConfig(cross_unit_boundaries=True))
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
    chunks = chunk_document(document)
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
    chunks = chunk_document(document)
    text_chunks = [c for c in chunks if c.chunk_type == "text" and c.source_text == "Body."]
    assert len(text_chunks) == 1
    assert text_chunks[0].heading_path == ["H3-sibling-of-h1"]

    # H1/H2's section had no real content before being superseded -> each
    # gets its own heading-only chunk.
    heading_only = {c.source_text for c in chunks if c.source_text in ("H1", "H2")}
    assert heading_only == {"H1", "H2"}


def test_heading_with_no_following_content_gets_standalone_chunk():
    document = _doc(headings=[CanonicalHeading(block_id="h1", unit_index=0, order_index=0, text="Lonely Heading", level=1)])
    chunks = chunk_document(document)
    assert len(chunks) == 1
    assert chunks[0].source_text == "Lonely Heading"
    assert chunks[0].source_element_ids == ["h1"]


def test_heading_with_content_does_not_get_standalone_chunk():
    document = _doc(
        headings=[CanonicalHeading(block_id="h1", unit_index=0, order_index=0, text="Heading", level=1)],
        paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=1, text="Body.")],
    )
    chunks = chunk_document(document)
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
    chunks = chunk_document(document)
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
    chunks = chunk_document(document)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.chunk_type == "table"
    assert chunk.source_element_ids == ["t1"]
    assert "**Header**" in chunk.source_text
    assert "[rowspan=1,colspan=2]" in chunk.source_text or "colspan=2" in chunk.source_text
    assert "| A |" in chunk.source_text
    assert "| B |" in chunk.source_text


def test_table_as_standalone_false_merges_with_surrounding_text():
    table = CanonicalTable(
        table_id="t1", unit_index=0, order_index=1, n_rows=1, n_cols=1,
        cells=[CanonicalTableCell(row=0, col=0, text="Cell")],
    )
    document = _doc(
        paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="Intro.")],
        tables=[table],
    )
    chunks = chunk_document(document, ChunkingConfig(table_as_standalone_chunk=False))
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "mixed"
    assert "Intro." in chunks[0].source_text
    assert "Cell" in chunks[0].source_text


# --- 10/15. pictures combined with captions, never duplicated --------------


def test_picture_combined_with_caption():
    picture = CanonicalPicture(picture_id="pic1", unit_index=0, content_sha256="c" * 64, artifact_ref="parity/pic1.png")
    caption = CanonicalCaption(block_id="cap1", unit_index=0, order_index=0, text="Figure 1: a diagram.", target_picture_id="pic1")
    document = _doc(pictures=[picture], captions=[caption])
    chunks = chunk_document(document)
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "picture"
    assert "Figure 1: a diagram." in chunks[0].source_text
    assert chunks[0].source_element_ids == ["pic1", "cap1"]


def test_caption_not_duplicated_as_standalone_chunk():
    picture = CanonicalPicture(picture_id="pic1", unit_index=0, content_sha256="c" * 64, artifact_ref="parity/pic1.png")
    caption = CanonicalCaption(block_id="cap1", unit_index=0, order_index=0, text="Figure 1.", target_picture_id="pic1")
    paragraph = CanonicalParagraph(block_id="p1", unit_index=0, order_index=1, text="Unrelated paragraph.")
    document = _doc(pictures=[picture], captions=[caption], paragraphs=[paragraph])
    chunks = chunk_document(document)

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
    chunks = chunk_document(document)
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
    chunks_on = chunk_document(document, ChunkingConfig(include_model_derived_annotations=True))
    chunks_off = chunk_document(document, ChunkingConfig(include_model_derived_annotations=False))

    assert "model reading" in chunks_on[0].retrieval_text
    assert "model reading" not in chunks_off[0].retrieval_text
    # model_derived_text itself is still populated regardless -- only
    # retrieval_text (the config-filtered view) is affected.
    assert chunks_off[0].model_derived_text is not None
    assert chunks_off[0].contains_model_derived is True


def test_ocr_annotation_is_source_visible_text_annotation_is_model_derived():
    document = _picture_with_annotations()
    chunk = chunk_document(document)[0]
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
    chunk = chunk_document(document)[0]
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
    chunk_a = chunk_document(document)[0]
    chunk_b = chunk_document(document)[0]

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
    chunk = chunk_document(document)[0]
    assert "Diagram node: Detect" in chunk.source_text
    assert chunk.model_derived_text is None


# --- 16. oversized element splitting ----------------------------------------


def test_split_oversized_text_algorithm_is_documented_and_deterministic():
    text = "First sentence. Second sentence. Third sentence."
    fragments = split_oversized_text(text, max_chars=20)
    assert fragments == split_oversized_text(text, max_chars=20)  # deterministic
    assert "".join(fragments).replace(" ", "") == text.replace(" ", "")  # no content lost
    assert all(len(f) <= 20 or " " not in f for f in fragments)  # never splits mid-word


def test_split_oversized_text_falls_back_to_whitespace_for_long_sentence():
    text = "Word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12."
    fragments = split_oversized_text(text, max_chars=15)
    assert all(len(f) <= 15 for f in fragments)
    assert " ".join(fragments) == text  # no words lost, reassembles exactly


def test_oversized_paragraph_splits_deterministically_and_retains_source_id():
    long_text = "This is a long sentence that will be repeated. " * 10
    document = _doc(paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text=long_text)])
    chunks = chunk_document(document, ChunkingConfig(max_chars=100))
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.source_element_ids == ["p1"]
        assert len(chunk.source_text) <= 100 or " " not in chunk.source_text


def test_oversized_element_policy_keep_oversized_does_not_split():
    long_text = "This is a long sentence that will be repeated. " * 10
    document = _doc(paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text=long_text)])
    chunks = chunk_document(document, ChunkingConfig(max_chars=100, oversized_element_policy="keep_oversized"))
    assert len(chunks) == 1
    assert chunks[0].source_text == long_text


# --- 17. no empty chunks -----------------------------------------------------


def test_no_empty_chunks_emitted():
    document = _doc(
        paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="   ")],
    )
    chunks = chunk_document(document)
    assert chunks == []


def test_no_empty_chunks_across_full_document():
    document = _sample_document()
    chunks = chunk_document(document)
    for chunk in chunks:
        assert chunk.source_text or chunk.model_derived_text


# --- 18. purity: CanonicalDocument unchanged after chunking -----------------


def test_document_unchanged_after_chunking():
    document = _sample_document()
    before = document.model_dump_json()
    chunk_document(document)
    after = document.model_dump_json()
    assert before == after


# --- 19. JSON round-trip -----------------------------------------------------


def test_chunk_json_round_trip():
    document = _sample_document()
    chunks = chunk_document(document)
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
    chunk = chunk_document(document)[0]
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
