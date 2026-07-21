"""Deterministic, parser-agnostic chunking: CanonicalDocument -> CanonicalChunk[].

Depends only on ingestion_bench.canonical (CanonicalDocument, its structural
element types, the Annotation union, and stable_element_id/BoundingBox) --
never on Docling, OpenAI, or any DOCX/PDF/PPTX library, and never on
reference_manifest.json or any other benchmark ground truth. This module's
only job is faithful, deterministic segmentation of what a CanonicalDocument
already says was extracted -- it does not interpret or judge truth.

chunk_document() is pure: it never mutates the input CanonicalDocument,
performs no filesystem/network/database I/O, and is fully deterministic --
same document + same config always produces byte-identical serialized
output (see stable ID / content-hash design below).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from ingestion_bench.canonical import CanonicalDocument, DiagramNodeAnnotation, IdentifierAnnotation
from ingestion_bench.canonical.hashing import stable_element_id

from .model import CanonicalChunk, ChunkingConfig, ChunkSourceRef, canonical_sha256, compute_chunking_config_hash
from .renderers import render_extracted_annotation, render_list_item, render_model_derived_annotation, render_table_text

# Bumped whenever the CHUNKING ALGORITHM changes (ordering, packing, or
# rendering rules) -- not when ChunkingConfig's *values* change, which is
# what chunking_config_hash is for.
CHUNKER_VERSION = "1.0.0"

_TYPE_RANK = {"heading": 0, "paragraph": 1, "list_item": 2, "table": 3, "picture": 4}

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def split_oversized_text(text: str, max_chars: int) -> list[str]:
    """Deterministic fallback split for a single source element whose own
    text exceeds max_chars (chunking rule 4). Always the same algorithm, no
    randomness:

      1. Split on sentence boundaries (after '.', '!', or '?' followed by
         whitespace).
      2. Greedily pack consecutive sentences into fragments, each up to
         max_chars.
      3. If a single sentence is itself still longer than max_chars, split
         IT on whitespace (word) boundaries and greedily pack words into
         sub-fragments up to max_chars.
      4. If a single word is still longer than max_chars (pathological),
         it becomes its own oversized fragment rather than being cut
         mid-word -- word integrity is never broken.
    """
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s]
    fragments: list[str] = []
    current = ""

    def flush_current() -> None:
        nonlocal current
        if current:
            fragments.append(current)
            current = ""

    for sentence in sentences:
        if len(sentence) > max_chars:
            flush_current()
            word_current = ""
            for word in sentence.split(" "):
                candidate = f"{word_current} {word}".strip() if word_current else word
                if word_current and len(candidate) > max_chars:
                    fragments.append(word_current)
                    word_current = word
                else:
                    word_current = candidate
            if word_current:
                fragments.append(word_current)
            continue

        candidate = f"{current} {sentence}".strip() if current else sentence
        if current and len(candidate) > max_chars:
            flush_current()
            current = sentence
        else:
            current = candidate

    flush_current()
    return fragments if fragments else [text]


def _join_source_texts(parts: list[str]) -> str:
    return "\n\n".join(p for p in parts if p)


@dataclass
class _RenderedElement:
    kind: str  # "heading" | "paragraph" | "list_item" | "table" | "picture"
    unit_index: int
    order_index: int | None
    element_ids: list[str]
    annotation_ids: list[str]
    source_refs: list[ChunkSourceRef]
    source_text: str
    model_derived_text: str | None
    heading_level: int | None = None


@dataclass
class _HeadingFrame:
    level: int
    text: str
    element_id: str
    unit_index: int
    source_ref: ChunkSourceRef
    has_content: bool = False


def _annotations_by_target(document: CanonicalDocument) -> dict[str, list]:
    grouped: dict[str, list] = defaultdict(list)
    for annotation in document.annotations:
        grouped[annotation.target_ref].append(annotation)
    return grouped


def _render_annotations_for_element(
    annotations_by_target: dict[str, list], element_id: str
) -> tuple[str, str | None, list[str]]:
    """Splits an element's annotations into (extra_source_text,
    model_derived_text_or_None, annotation_ids_in_order), routing each
    annotation by its OWN derivation field -- "extracted" always renders
    into the source-derived text, "model_derived" always renders into the
    model-derived text, regardless of concrete annotation type. This is a
    deliberate generalization of chunking rule 6's per-type list: every
    concrete annotation type in this codebase has either a fixed derivation
    (OcrAnnotation is always "extracted"; VisibleTextAnnotation/
    ImageDescriptionAnnotation/VisualFactAnnotation are always
    "model_derived") or a genuinely either-way derivation
    (DiagramNodeAnnotation/DiagramEdgeAnnotation/PictureClassAnnotation), so
    routing purely by derivation reproduces rule 6's table exactly while
    also generalizing correctly to annotations on non-picture elements.

    IdentifierAnnotation is deliberately never rendered into either text
    section (rule 6: identifiers remain metadata/source references, not
    duplicated text) -- but its id is still included in annotation_ids for
    auditability.

    Annotations are processed in annotation_id order (never raw list/dict
    insertion order) for determinism.
    """
    annotations = sorted(annotations_by_target.get(element_id, []), key=lambda a: a.annotation_id)
    if not annotations:
        return "", None, []

    label_by_node_id = {a.node_id: a.label for a in annotations if isinstance(a, DiagramNodeAnnotation)}

    source_lines: list[str] = []
    model_derived_lines: list[str] = []
    annotation_ids: list[str] = []

    for annotation in annotations:
        annotation_ids.append(annotation.annotation_id)
        if isinstance(annotation, IdentifierAnnotation):
            continue
        if annotation.derivation == "extracted":
            rendered = render_extracted_annotation(annotation, label_by_node_id)
            if rendered:
                source_lines.append(rendered)
        else:
            rendered = render_model_derived_annotation(annotation, label_by_node_id)
            if rendered:
                model_derived_lines.append(rendered)

    extra_source_text = "\n".join(source_lines)
    model_derived_text = "\n".join(model_derived_lines) if model_derived_lines else None
    return extra_source_text, model_derived_text, annotation_ids


def _build_ordered_elements(document: CanonicalDocument) -> list[_RenderedElement]:
    """Gathers headings/paragraphs/list_items/tables/pictures (never
    captions -- those are only ever pulled in via their target picture, per
    chunking rule 7) into a single reading-order sequence, sorted by
    (unit_index, order_index, deterministic element-type tie-breaker,
    stable element id) -- chunking rule 1. Never depends on dict insertion
    order or randomness: the sort key is fully explicit and every tie-break
    falls through to a stable, content-derived id."""
    annotations_by_target = _annotations_by_target(document)

    provenance_order_index: dict[str, int] = {}
    for entry in document.provenance:
        if entry.order_index is not None:
            provenance_order_index.setdefault(entry.element_id, entry.order_index)

    captions_by_picture: dict[str, list] = defaultdict(list)
    for caption in document.captions:
        captions_by_picture[caption.target_picture_id].append(caption)

    keyed: list[tuple[tuple, _RenderedElement]] = []

    for heading in document.headings:
        extra_src, model_text, annotation_ids = _render_annotations_for_element(annotations_by_target, heading.block_id)
        source_text = heading.text + (f"\n{extra_src}" if extra_src else "")
        element = _RenderedElement(
            kind="heading",
            unit_index=heading.unit_index,
            order_index=heading.order_index,
            element_ids=[heading.block_id],
            annotation_ids=annotation_ids,
            source_refs=[ChunkSourceRef(
                element_id=heading.block_id, unit_index=heading.unit_index,
                order_index=heading.order_index, bbox=heading.bbox, element_type="heading",
            )],
            source_text=source_text, model_derived_text=model_text, heading_level=heading.level,
        )
        keyed.append(((heading.unit_index, heading.order_index, _TYPE_RANK["heading"], heading.block_id), element))

    for paragraph in document.paragraphs:
        extra_src, model_text, annotation_ids = _render_annotations_for_element(annotations_by_target, paragraph.block_id)
        source_text = paragraph.text + (f"\n{extra_src}" if extra_src else "")
        element = _RenderedElement(
            kind="paragraph",
            unit_index=paragraph.unit_index,
            order_index=paragraph.order_index,
            element_ids=[paragraph.block_id],
            annotation_ids=annotation_ids,
            source_refs=[ChunkSourceRef(
                element_id=paragraph.block_id, unit_index=paragraph.unit_index,
                order_index=paragraph.order_index, bbox=paragraph.bbox, element_type="paragraph",
            )],
            source_text=source_text, model_derived_text=model_text,
        )
        keyed.append(((paragraph.unit_index, paragraph.order_index, _TYPE_RANK["paragraph"], paragraph.block_id), element))

    for item in document.list_items:
        extra_src, model_text, annotation_ids = _render_annotations_for_element(annotations_by_target, item.block_id)
        rendered = render_list_item(item)
        source_text = rendered + (f"\n{extra_src}" if extra_src else "")
        element = _RenderedElement(
            kind="list_item",
            unit_index=item.unit_index,
            order_index=item.order_index,
            element_ids=[item.block_id],
            annotation_ids=annotation_ids,
            source_refs=[ChunkSourceRef(
                element_id=item.block_id, unit_index=item.unit_index,
                order_index=item.order_index, bbox=item.bbox, element_type="list_item",
            )],
            source_text=source_text, model_derived_text=model_text,
        )
        keyed.append(((item.unit_index, item.order_index, _TYPE_RANK["list_item"], item.block_id), element))

    for table in document.tables:
        extra_src, model_text, annotation_ids = _render_annotations_for_element(annotations_by_target, table.table_id)
        rendered = render_table_text(table)
        source_text = rendered + (f"\n{extra_src}" if extra_src else "")
        element = _RenderedElement(
            kind="table",
            unit_index=table.unit_index,
            order_index=table.order_index,
            element_ids=[table.table_id],
            annotation_ids=annotation_ids,
            source_refs=[ChunkSourceRef(
                element_id=table.table_id, unit_index=table.unit_index,
                order_index=table.order_index, bbox=table.bbox, element_type="table",
            )],
            source_text=source_text, model_derived_text=model_text,
        )
        keyed.append(((table.unit_index, table.order_index, _TYPE_RANK["table"], table.table_id), element))

    for picture in document.pictures:
        extra_src, model_text, annotation_ids = _render_annotations_for_element(annotations_by_target, picture.picture_id)
        captions = sorted(captions_by_picture.get(picture.picture_id, []), key=lambda c: c.block_id)

        element_ids = [picture.picture_id] + [c.block_id for c in captions]
        source_refs = [ChunkSourceRef(
            element_id=picture.picture_id, unit_index=picture.unit_index,
            order_index=None, bbox=picture.bbox, element_type="picture",
        )]
        source_refs += [
            ChunkSourceRef(
                element_id=c.block_id, unit_index=c.unit_index,
                order_index=c.order_index, bbox=c.bbox, element_type="caption",
            )
            for c in captions
        ]

        source_parts = [c.text for c in captions]
        if extra_src:
            source_parts.append(extra_src)
        source_text = "\n".join(source_parts)

        # CanonicalPicture has no order_index of its own (Stage 2 contract);
        # fall back to a ProvenanceEntry's order_index when the adapter
        # supplied one, else sort after all positioned elements in its unit.
        order_index = provenance_order_index.get(picture.picture_id)
        sort_order_index = order_index if order_index is not None else float("inf")

        element = _RenderedElement(
            kind="picture",
            unit_index=picture.unit_index,
            order_index=order_index,
            element_ids=element_ids,
            annotation_ids=annotation_ids,
            source_refs=source_refs,
            source_text=source_text, model_derived_text=model_text,
        )
        keyed.append(((picture.unit_index, sort_order_index, _TYPE_RANK["picture"], picture.picture_id), element))

    keyed.sort(key=lambda pair: pair[0])
    return [element for _, element in keyed]


def chunk_document(document: CanonicalDocument, config: ChunkingConfig | None = None) -> list[CanonicalChunk]:
    config = config or ChunkingConfig()
    config_hash = compute_chunking_config_hash(config)
    elements = _build_ordered_elements(document)

    chunks: list[CanonicalChunk] = []
    chunk_index = 0

    heading_stack: list[_HeadingFrame] = []
    buffer: list[_RenderedElement] = []
    buffer_unit_indices: set[int] = set()

    def current_heading_path() -> list[str]:
        return [frame.text for frame in heading_stack]

    def mark_headings_have_content() -> None:
        for frame in heading_stack:
            frame.has_content = True

    def emit_chunk(
        chunk_type: str,
        unit_indices: list[int],
        heading_path: list[str],
        source_element_ids: list[str],
        annotation_ids: list[str],
        source_refs: list[ChunkSourceRef],
        source_text: str,
        model_derived_text: str | None,
    ) -> None:
        nonlocal chunk_index
        if not source_text and not model_derived_text:
            return  # never emit a genuinely empty chunk

        content_payload = {
            "chunk_type": chunk_type,
            "unit_indices": unit_indices,
            "heading_path": heading_path,
            "source_element_ids": source_element_ids,
            "annotation_ids": annotation_ids,
            "source_text": source_text,
            "model_derived_text": model_derived_text,
        }
        content_sha256 = canonical_sha256(content_payload)

        retrieval_parts: list[str] = []
        if config.include_heading_context and heading_path:
            retrieval_parts.append(" > ".join(heading_path))
        if source_text:
            retrieval_parts.append(source_text)
        if config.include_model_derived_annotations and model_derived_text:
            retrieval_parts.append(f"Model-derived (unverified):\n{model_derived_text}")
        retrieval_text = "\n\n".join(retrieval_parts)

        chunk_id = stable_element_id(
            document.doc_id,
            "chunk",
            unit_indices[0],
            order_index=chunk_index,
            discriminator=f"{CHUNKER_VERSION}:{config_hash}",
            extra={
                "source_element_ids": source_element_ids,
                "annotation_ids": annotation_ids,
                "content_sha256": content_sha256,
            },
        )

        chunks.append(CanonicalChunk(
            chunk_id=chunk_id,
            doc_id=document.doc_id,
            chunk_index=chunk_index,
            chunk_type=chunk_type,
            unit_indices=unit_indices,
            heading_path=heading_path,
            source_element_ids=source_element_ids,
            annotation_ids=annotation_ids,
            source_refs=source_refs,
            source_text=source_text,
            model_derived_text=model_derived_text,
            retrieval_text=retrieval_text,
            contains_model_derived=model_derived_text is not None,
            content_sha256=content_sha256,
            chunker_version=CHUNKER_VERSION,
            chunking_config_hash=config_hash,
        ))
        chunk_index += 1

    def buffer_chunk_type() -> str:
        kinds = {element.kind for element in buffer}
        if kinds <= {"heading", "paragraph", "list_item"}:
            return "text"
        if kinds == {"table"}:
            return "table"
        if kinds == {"picture"}:
            return "picture"
        return "mixed"

    def flush_buffer() -> None:
        if not buffer:
            return
        chunk_type = buffer_chunk_type()
        source_text = _join_source_texts([element.source_text for element in buffer])
        model_derived_parts = [element.model_derived_text for element in buffer if element.model_derived_text]
        model_derived_text = "\n".join(model_derived_parts) if model_derived_parts else None
        source_element_ids = [eid for element in buffer for eid in element.element_ids]
        annotation_ids = [aid for element in buffer for aid in element.annotation_ids]
        source_refs = [ref for element in buffer for ref in element.source_refs]
        unit_indices = sorted(buffer_unit_indices)

        emit_chunk(
            chunk_type, unit_indices, current_heading_path(),
            source_element_ids, annotation_ids, source_refs, source_text, model_derived_text,
        )
        buffer.clear()
        buffer_unit_indices.clear()

    def pop_headings_to_level(min_level_inclusive: int) -> None:
        while heading_stack and heading_stack[-1].level >= min_level_inclusive:
            frame = heading_stack.pop()
            if not frame.has_content:
                emit_chunk(
                    "text", [frame.unit_index], [f.text for f in heading_stack],
                    [frame.element_id], [], [frame.source_ref], frame.text, None,
                )

    for element in elements:
        if element.kind == "heading":
            flush_buffer()
            pop_headings_to_level(element.heading_level)
            heading_stack.append(_HeadingFrame(
                level=element.heading_level, text=element.source_text,
                element_id=element.element_ids[0], unit_index=element.unit_index,
                source_ref=element.source_refs[0],
            ))
            continue

        mark_headings_have_content()

        if element.kind in ("paragraph", "list_item"):
            if not element.source_text.strip():
                continue  # defensively never buffer a genuinely empty element

            if buffer and not config.cross_unit_boundaries and element.unit_index not in buffer_unit_indices:
                flush_buffer()

            if len(element.source_text) > config.max_chars:
                flush_buffer()
                if config.oversized_element_policy == "split":
                    fragments = split_oversized_text(element.source_text, config.max_chars)
                else:
                    fragments = [element.source_text]
                for fragment_index, fragment in enumerate(fragments):
                    emit_chunk(
                        "text", [element.unit_index], current_heading_path(),
                        list(element.element_ids),
                        list(element.annotation_ids) if fragment_index == 0 else [],
                        list(element.source_refs), fragment,
                        element.model_derived_text if fragment_index == 0 else None,
                    )
                continue

            projected = _join_source_texts([e.source_text for e in buffer] + [element.source_text])
            if buffer and len(projected) > config.max_chars:
                flush_buffer()

            buffer.append(element)
            buffer_unit_indices.add(element.unit_index)
            continue

        # table or picture
        standalone = (
            config.table_as_standalone_chunk if element.kind == "table"
            else config.picture_as_standalone_chunk
        )
        if standalone:
            # Standalone tables/pictures never merge with surrounding text,
            # in either direction -- flush whatever text preceded it first.
            flush_buffer()
            emit_chunk(
                element.kind, [element.unit_index], current_heading_path(),
                list(element.element_ids), list(element.annotation_ids),
                list(element.source_refs), element.source_text, element.model_derived_text,
            )
        else:
            # Not standalone: merge into the current buffer like a packable
            # element (still atomic -- never split -- but subject to the
            # same unit-boundary and max_chars packing rules).
            if buffer and not config.cross_unit_boundaries and element.unit_index not in buffer_unit_indices:
                flush_buffer()
            projected = _join_source_texts([e.source_text for e in buffer] + [element.source_text])
            if buffer and len(projected) > config.max_chars:
                flush_buffer()
            buffer.append(element)
            buffer_unit_indices.add(element.unit_index)

    flush_buffer()
    pop_headings_to_level(0)

    return chunks
