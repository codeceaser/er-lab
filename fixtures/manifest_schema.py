"""Pydantic schema for reference_manifest.json itself.

Validates the frozen manifest's structure so the fixture generator (and any
future consumer) fails loudly on drift, rather than silently reading a
malformed or unexpectedly-shaped manifest. This schema describes the
manifest's OWN shape -- it has nothing to do with the canonical document
model in src/ingestion_bench/canonical/, which describes extracted content,
not ground truth.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExpectedLocation(StrictModel):
    unit_index: int
    role: str
    precedes: str | None = None
    order_hint: int | None = None
    after_heading: str | None = None


class ManifestUnit(StrictModel):
    unit_index: int
    unit_type: str
    content: str


class Heading(StrictModel):
    fact_id: str
    level: int
    text: str
    expected_location: ExpectedLocation


class Paragraph(StrictModel):
    fact_id: str
    text: str
    expected_location: ExpectedLocation


class IdentifierOccurrence(StrictModel):
    raw_text: str
    source_fact: str
    note: str | None = None


class IdentifierEntry(StrictModel):
    fact_id: str
    normalized_value: str
    is_distractor: bool
    occurrences: list[IdentifierOccurrence]
    false_merge_risk: str | None = None


class OccurrenceTotals(StrictModel):
    target_identifiers_total_occurrences: int
    target_identifiers_unique_count: int
    distractor_identifiers_total_occurrences: int
    distractor_identifiers_unique_count: int


class Identifiers(StrictModel):
    note: str
    target_identifiers: list[IdentifierEntry]
    distractor_identifiers: list[IdentifierEntry]
    occurrence_totals: OccurrenceTotals


class DistractorFact(StrictModel):
    fact_id: str
    text: str
    purpose: str
    expected_location: ExpectedLocation


class TableCell(StrictModel):
    row: int
    col: int
    text: str
    is_header: bool = False
    col_span: int = 1


class ManifestTable(StrictModel):
    fact_id: str
    expected_location: ExpectedLocation | None = None
    n_rows: int
    n_cols: int
    cells: list[TableCell]
    notes: str | None = None


class Caption(StrictModel):
    fact_id: str
    text: str
    target_picture: str
    expected_location: ExpectedLocation


class Picture(StrictModel):
    fact_id: str
    shared_image_ref: str
    expected_location: ExpectedLocation
    description_for_generator: str
    expected_picture_class: str
    expected_picture_class_note: str
    expected_ocr_tokens: list[str]


class DiagramNode(StrictModel):
    fact_id: str
    label: str
    bbox_px: list[int] | None = None


class DiagramEdge(StrictModel):
    fact_id: str
    source: str
    target: str
    directed: bool = True


class VisualDistractorFact(StrictModel):
    fact_id: str
    claim: str
    claim_type: str
    purpose: str


class ParitySuite(StrictModel):
    suite_id: str
    doc_id: str
    description: str
    units: list[ManifestUnit]
    headings: list[Heading]
    paragraphs: list[Paragraph]
    list_items: list[Any]
    identifiers: Identifiers
    distractor_facts: list[DistractorFact]
    tables: list[ManifestTable]
    captions: list[Caption]
    pictures: list[Picture]
    diagram_nodes: list[DiagramNode]
    diagram_edges: list[DiagramEdge]
    diagram_nodes_edges_note: str
    visual_distractor_facts: list[VisualDistractorFact]


class StressHeading(StrictModel):
    fact_id: str
    level: int
    text: str


class StressListItem(StrictModel):
    fact_id: str
    text: str
    indent_level: int
    list_id: str
    parent: str | None = None


class DocxNestedStructure(StrictModel):
    doc_id: str
    format: str
    headings: list[StressHeading]
    list_items: list[StressListItem]
    notes: str


class StressParagraph(StrictModel):
    fact_id: str
    column: int
    text: str


class PdfComplexLayout(StrictModel):
    doc_id: str
    format: str
    layout: str
    paragraphs: list[StressParagraph]
    tables: list[ManifestTable]
    notes: str


class TextBox(StrictModel):
    fact_id: str
    text: str
    z_order: int


class PptxOverlappingTextboxes(StrictModel):
    doc_id: str
    format: str
    text_boxes: list[TextBox]
    table: ManifestTable
    evaluation_expectation: str
    notes: str


class PptxNativeDiagram(StrictModel):
    doc_id: str
    format: str
    description: str
    capability_breakdown: dict[str, str]
    diagram_nodes: list[DiagramNode]
    diagram_edges: list[DiagramEdge]


class VisualFact(StrictModel):
    fact_id: str
    fact_type: str
    subject: str
    relation: str
    object: str | None = None
    value: float | None = None
    unit: str | None = None
    raw_text: str


class UnsupportedClaim(StrictModel):
    fact_id: str
    fact_type: str
    subject: str
    relation: str
    object: str | None = None
    value: float | None = None
    unit: str | None = None
    claim: str
    is_supported: bool
    reason: str


class ChartVisualStress(StrictModel):
    doc_id: str
    format: str
    description: str
    expected_picture_class: str
    visual_facts: list[VisualFact]
    unsupported_claims: list[UnsupportedClaim]


class ScannedPdfOcrStress(StrictModel):
    doc_id: str
    format: str
    description: str
    expected_ocr_text: str


class StressSuite(StrictModel):
    suite_id: str
    description: str
    docx_nested_structure: DocxNestedStructure
    pdf_complex_layout: PdfComplexLayout
    pptx_overlapping_textboxes: PptxOverlappingTextboxes
    pptx_native_diagram: PptxNativeDiagram
    chart_visual_stress: ChartVisualStress
    scanned_pdf_ocr_stress: ScannedPdfOcrStress


class ReferenceManifest(StrictModel):
    manifest_version: str
    status: str
    note: str
    domain: str
    parity_suite: ParitySuite
    stress_suite: StressSuite


def load_manifest_raw(path: Path) -> dict[str, Any]:
    """Load reference_manifest.json as a plain dict, exactly as stored on
    disk -- this, not a pydantic round-trip, is what compute_manifest_sha256
    should hash, so the hash reflects the actual frozen file content."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest(path: Path) -> ReferenceManifest:
    """Load and validate reference_manifest.json against this schema."""
    return ReferenceManifest.model_validate(load_manifest_raw(path))
