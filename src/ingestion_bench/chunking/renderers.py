"""Deterministic text rendering for canonical elements and annotations.

Pure functions only: given the same inputs, always the same string. No
randomness, no wall-clock, no I/O.
"""

from __future__ import annotations

from collections import defaultdict

from ingestion_bench.canonical import (
    CanonicalListItem,
    CanonicalTable,
    DiagramEdgeAnnotation,
    DiagramNodeAnnotation,
    ImageDescriptionAnnotation,
    PictureClassAnnotation,
    SemanticClaimAnnotation,
    UncertaintyAnnotation,
    VisibleTextAnnotation,
    VisualFactAnnotation,
)


def render_list_item(item: CanonicalListItem) -> str:
    """Deterministic textual rendering that preserves indent level: two
    spaces per level, a leading "- " marker, e.g. indent_level=2 ->
    "    - text"."""
    return f"{'  ' * item.indent_level}- {item.text}"


def render_table_text(table: CanonicalTable) -> str:
    """Readable, deterministic, information-preserving table rendering.
    Plain Markdown pipe tables cannot express row/col spans, so header
    status and any span > 1 are noted explicitly per cell rather than
    silently dropped."""
    lines = [f"Table ({table.n_rows}x{table.n_cols}):"]
    cells_by_row: dict[int, list] = defaultdict(list)
    for cell in table.cells:
        cells_by_row[cell.row].append(cell)

    for row_index in sorted(cells_by_row):
        row_cells = sorted(cells_by_row[row_index], key=lambda c: c.col)
        rendered_cells = []
        for cell in row_cells:
            text = f"**{cell.text}**" if cell.is_header else cell.text
            if cell.row_span > 1 or cell.col_span > 1:
                text = f"{text} [rowspan={cell.row_span},colspan={cell.col_span}]"
            rendered_cells.append(text)
        lines.append("| " + " | ".join(rendered_cells) + " |")

    return "\n".join(lines)


def render_visual_fact(annotation: VisualFactAnnotation) -> str:
    if annotation.fact_type == "comparative" and annotation.object is not None:
        return f"Visual fact: {annotation.subject} {annotation.relation} {annotation.object}"
    value_part = f"{annotation.value}{annotation.unit or ''}" if annotation.value is not None else ""
    return f"Visual fact: {annotation.subject} {annotation.relation} {value_part}".rstrip()


def render_diagram_node(annotation: DiagramNodeAnnotation) -> str:
    return f"Diagram node: {annotation.label}"


def render_diagram_edge(annotation: DiagramEdgeAnnotation, label_by_node_id: dict[str, str]) -> str:
    source_label = label_by_node_id.get(annotation.source_node_id, annotation.source_node_id)
    target_label = label_by_node_id.get(annotation.target_node_id, annotation.target_node_id)
    arrow = "->" if annotation.directed else "--"
    return f"Diagram edge: {source_label} {arrow} {target_label}"


def render_model_derived_annotation(annotation, label_by_node_id: dict[str, str]) -> str | None:
    """Dispatch by concrete annotation type. Returns None for annotation
    types that never carry model-derived, human-readable text on their own
    (currently none reach here since callers only pass derivation=
    "model_derived" annotations, but kept defensive)."""
    if isinstance(annotation, VisibleTextAnnotation):
        return f"Visible text (model-derived): {annotation.text}"
    if isinstance(annotation, PictureClassAnnotation):
        return f"Picture class (model-derived): {annotation.picture_class}"
    if isinstance(annotation, VisualFactAnnotation):
        return render_visual_fact(annotation)
    if isinstance(annotation, DiagramNodeAnnotation):
        return render_diagram_node(annotation)
    if isinstance(annotation, DiagramEdgeAnnotation):
        return render_diagram_edge(annotation, label_by_node_id)
    if isinstance(annotation, ImageDescriptionAnnotation):
        return f"Description (model-derived, unverified): {annotation.description}"
    if isinstance(annotation, SemanticClaimAnnotation):
        return f"Claim (model-derived, unverified): {annotation.claim}"
    if isinstance(annotation, UncertaintyAnnotation):
        return f"Uncertainty (model-derived): {annotation.note}"
    return None


def render_extracted_annotation(annotation, label_by_node_id: dict[str, str]) -> str | None:
    """Same dispatch, for derivation="extracted" annotations (e.g. OCR text,
    a non-generative picture classifier, or native-shape diagram structure)."""
    from ingestion_bench.canonical import OcrAnnotation

    if isinstance(annotation, OcrAnnotation):
        return f"OCR: {annotation.text}"
    if isinstance(annotation, PictureClassAnnotation):
        return f"Picture class: {annotation.picture_class}"
    if isinstance(annotation, DiagramNodeAnnotation):
        return render_diagram_node(annotation)
    if isinstance(annotation, DiagramEdgeAnnotation):
        return render_diagram_edge(annotation, label_by_node_id)
    return None
