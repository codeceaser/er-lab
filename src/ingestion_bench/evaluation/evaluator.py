"""Stage 6A deterministic ingestion-fidelity evaluator.

Compares reference_manifest.json (frozen ground truth) against Stage 5A
DOCLING_STANDARD_LOCAL output (CanonicalDocument/CanonicalChunk/
conversion_report.json) fixture by fixture. This is the ONLY package in
the repository that reads reference_manifest.json -- adapters/,
canonical/, and chunking/ must and do remain manifest-independent (see
tests/test_stage6a_integration.py).

Scores primarily against CanonicalDocument. Uses CanonicalChunk only to
establish downstream evidence availability and fact-to-chunk alignment.
Uses raw Docling debug JSON only to classify the ORIGIN of an already-
established miss (classification.py) -- raw Docling output never replaces
CanonicalDocument as the scored representation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any

from ingestion_bench.canonical import CanonicalDocument
from ingestion_bench.canonical.hashing import stable_canonical_hash
from ingestion_bench.chunking.model import CanonicalChunk

from . import classification
from .matcher import TextElement, find_exact_text_matches, find_identifier_matches
from .model import (
    EvidenceAlignment,
    FixtureEvaluationResult,
    MetricResult,
    MissRecord,
    OperationalEvidence,
    UnexpectedObservation,
)
from .normalization import (
    IDENTIFIER_MATCH_RULE,
    TEXT_NORMALIZED_CASE_FOLD_RULE,
    find_identifier_occurrences,
    identifier_present,
    normalize_text_for_comparison,
)

EVALUATOR_VERSION = "1.0.0"

# --- fixture registry --------------------------------------------------
# (fixture_relative_path, doc_id, artifact_key, source_format, suite_key)
# artifact_key matches adapter.py/run_docling_standard.py's own
# f"{doc_id}_{source_format}" convention -- never re-derived differently
# here, so a Stage 5A artifact-path change would surface as a loud
# FileNotFoundError, not a silent mismatch.
FIXTURES: list[tuple[str, str, str, str, str]] = [
    ("parity/PARITY_001.pdf", "PARITY_001", "PARITY_001_pdf", "pdf", "parity"),
    ("parity/PARITY_001.docx", "PARITY_001", "PARITY_001_docx", "docx", "parity"),
    ("parity/PARITY_001.pptx", "PARITY_001", "PARITY_001_pptx", "pptx", "parity"),
    ("stress/STRESS_DOCX_001.docx", "STRESS_DOCX_001", "STRESS_DOCX_001_docx", "docx", "stress_docx"),
    ("stress/STRESS_PDF_001.pdf", "STRESS_PDF_001", "STRESS_PDF_001_pdf", "pdf", "stress_pdf"),
    ("stress/STRESS_PPTX_001.pptx", "STRESS_PPTX_001", "STRESS_PPTX_001_pptx", "pptx", "stress_pptx_overlap"),
    ("stress/STRESS_PPTX_002.pptx", "STRESS_PPTX_002", "STRESS_PPTX_002_pptx", "pptx", "stress_pptx_diagram"),
    ("stress/STRESS_CHART_001.pdf", "STRESS_CHART_001", "STRESS_CHART_001_pdf", "pdf", "stress_chart"),
    ("stress/STRESS_SCANNED_001.pdf", "STRESS_SCANNED_001", "STRESS_SCANNED_001_pdf", "pdf", "stress_scanned"),
]


def load_manifest(fixtures_root: Path) -> dict[str, Any]:
    return json.loads((fixtures_root / "reference_manifest.json").read_text(encoding="utf-8"))


@dataclass
class LoadedFixture:
    fixture: str
    doc_id: str
    artifact_key: str
    source_format: str
    suite_key: str
    document: CanonicalDocument
    chunks: list[CanonicalChunk]
    conversion_report: dict[str, Any]
    raw_debug_path: Path
    _raw_debug: dict[str, Any] | None = dataclass_field(default=None, repr=False)

    def raw_debug(self) -> dict[str, Any]:
        if self._raw_debug is None:
            self._raw_debug = json.loads(self.raw_debug_path.read_text(encoding="utf-8"))
        return self._raw_debug


def load_fixture_artifacts(artifacts_root: Path) -> list[LoadedFixture]:
    """Reads Stage 5A's own output verbatim -- never mutates, never
    re-derives a value Stage 5A already computed."""
    loaded = []
    for fixture, doc_id, artifact_key, source_format, suite_key in FIXTURES:
        fixture_dir = artifacts_root / artifact_key
        document = CanonicalDocument.model_validate(
            json.loads((fixture_dir / "canonical_document.json").read_text(encoding="utf-8"))
        )
        chunks = []
        chunks_path = fixture_dir / "canonical_chunks.jsonl"
        if chunks_path.exists():
            for line in chunks_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    chunks.append(CanonicalChunk.model_validate(json.loads(line)))
        conversion_report = json.loads((fixture_dir / "conversion_report.json").read_text(encoding="utf-8"))
        raw_debug_path = artifacts_root / "docling_raw" / f"{artifact_key}.json"
        loaded.append(
            LoadedFixture(
                fixture=fixture, doc_id=doc_id, artifact_key=artifact_key, source_format=source_format,
                suite_key=suite_key, document=document, chunks=chunks, conversion_report=conversion_report,
                raw_debug_path=raw_debug_path,
            )
        )
    return loaded


# --- flattening CanonicalDocument into uniform TextElements -------------


def flatten_text_elements(document: CanonicalDocument) -> list[TextElement]:
    """Every text-bearing canonical element -- headings, paragraphs, list
    items, captions, and OCR-annotation text -- flattened for uniform
    exact-text matching. Table cell text is handled separately (table
    metrics need row/col/span, not just text)."""
    elements: list[TextElement] = []
    for heading in document.headings:
        elements.append(TextElement(heading.block_id, heading.text, "heading", heading.unit_index))
    for paragraph in document.paragraphs:
        elements.append(TextElement(paragraph.block_id, paragraph.text, "paragraph", paragraph.unit_index))
    for list_item in document.list_items:
        elements.append(TextElement(list_item.block_id, list_item.text, "list_item", list_item.unit_index))
    for caption in document.captions:
        elements.append(TextElement(caption.block_id, caption.text, "caption", caption.unit_index))
    for annotation in document.annotations:
        if annotation.annotation_type == "ocr":
            elements.append(TextElement(annotation.annotation_id, annotation.text, "ocr_annotation", annotation.unit_index))
    return elements


def element_to_chunk_ids(chunks: list[CanonicalChunk]) -> dict[str, list[str]]:
    """Maps every core-element id, annotation id, and picture id to the
    chunk id(s) that carry it -- established via CanonicalChunk fields
    only, never guessed."""
    mapping: dict[str, list[str]] = {}
    for chunk in chunks:
        ids = list(chunk.source_element_ids) + list(chunk.heading_source_element_ids) + list(chunk.annotation_ids)
        ids += [asset.picture_id for asset in chunk.asset_refs]
        for element_id in ids:
            mapping.setdefault(element_id, []).append(chunk.chunk_id)
    return mapping


# --- generic metric-building helpers ------------------------------------


def _metric(name: str, rule: str, numerator: int, denominator: int, *, excluded: int = 0,
            matches: list[str] | None = None, misses: list[str] | None = None) -> MetricResult:
    score = None if denominator == 0 else numerator / denominator
    return MetricResult(
        metric_name=name, matching_rule=rule, numerator=numerator, denominator=denominator,
        excluded_not_applicable=excluded, score=score,
        supporting_matches=matches or [], supporting_misses=misses or [],
    )


def _difficulty_for(fact_type: str, *, is_distractor: bool, occurrence_count: int = 1) -> str:
    """Coarse, deterministic retrieval-difficulty heuristic (Stage 6A
    section 16) -- NOT a retrieval question, just a reusable difficulty
    tag for the gold evidence-alignment catalog. Documented here, not
    invented per-fact: distractor facts are distractor_sensitive by
    construction; multi-occurrence identifiers require connecting more
    than one mention (multi_hop); structured table content requires
    assembling a record (consolidation); a caption's meaning depends on
    its linked picture (relational); everything else is a single direct
    lookup."""
    if is_distractor:
        return "distractor_sensitive"
    if fact_type in ("table", "table_cell"):
        return "consolidation"
    if fact_type == "identifier_target" and occurrence_count > 1:
        return "multi_hop"
    if fact_type == "caption":
        return "relational"
    return "direct"


# --- manifest fact extraction, per suite ---------------------------------


def _location_unit_index(expected_location: dict) -> int | None:
    return expected_location.get("unit_index") if isinstance(expected_location, dict) else None


def _parity_facts(parity: dict) -> dict[str, list[dict]]:
    facts: dict[str, list[dict]] = {
        "heading": [], "paragraph": [], "identifier_target": [], "identifier_distractor": [],
        "table": [], "caption": [], "picture": [], "ocr_token": [],
    }
    for h in parity["headings"]:
        facts["heading"].append({"fact_id": h["fact_id"], "text": h["text"], "level": h["level"], "expected_location": h["expected_location"]})
    for p in parity["paragraphs"]:
        facts["paragraph"].append({"fact_id": p["fact_id"], "text": p["text"], "expected_location": p["expected_location"], "is_distractor": False})
    for d in parity["distractor_facts"]:
        facts["paragraph"].append({"fact_id": d["fact_id"], "text": d["text"], "expected_location": d["expected_location"], "is_distractor": True, "purpose": d["purpose"]})
    for ident in parity["identifiers"]["target_identifiers"]:
        facts["identifier_target"].append({"fact_id": ident["fact_id"], "normalized_value": ident["normalized_value"], "occurrences": ident["occurrences"]})
    for ident in parity["identifiers"]["distractor_identifiers"]:
        facts["identifier_distractor"].append({"fact_id": ident["fact_id"], "normalized_value": ident["normalized_value"], "occurrences": ident["occurrences"], "false_merge_risk": ident.get("false_merge_risk")})
    for t in parity["tables"]:
        facts["table"].append({"fact_id": t["fact_id"], "n_rows": t["n_rows"], "n_cols": t["n_cols"], "cells": t["cells"], "expected_location": t["expected_location"]})
    for c in parity["captions"]:
        facts["caption"].append({"fact_id": c["fact_id"], "text": c["text"], "target_picture": c["target_picture"], "expected_location": c["expected_location"]})
    for pic in parity["pictures"]:
        facts["picture"].append({"fact_id": pic["fact_id"], "expected_location": pic["expected_location"], "expected_picture_class": pic.get("expected_picture_class")})
        for i, token in enumerate(pic.get("expected_ocr_tokens", [])):
            facts["ocr_token"].append({"fact_id": f"{pic['fact_id']}_ocr_{i}", "text": token, "picture_fact_id": pic["fact_id"]})
    return facts


def _stress_docx_facts(section: dict) -> dict[str, list[dict]]:
    facts: dict[str, list[dict]] = {"heading": [], "list_item": []}
    for h in section["headings"]:
        facts["heading"].append({"fact_id": h["fact_id"], "text": h["text"], "level": h["level"], "expected_location": {}})
    for li in section["list_items"]:
        facts["list_item"].append({
            "fact_id": li["fact_id"], "text": li["text"], "indent_level": li["indent_level"],
            "list_id": li["list_id"], "parent": li.get("parent"),
        })
    return facts


def _stress_pdf_facts(section: dict) -> dict[str, list[dict]]:
    facts: dict[str, list[dict]] = {"paragraph": [], "table": []}
    for p in section["paragraphs"]:
        facts["paragraph"].append({"fact_id": p["fact_id"], "text": p["text"], "expected_location": {}, "column": p["column"], "is_distractor": False})
    for t in section["tables"]:
        facts["table"].append({"fact_id": t["fact_id"], "n_rows": t["n_rows"], "n_cols": t["n_cols"], "cells": t["cells"], "expected_location": {}})
    return facts


def _stress_pptx_overlap_facts(section: dict) -> dict[str, list[dict]]:
    facts: dict[str, list[dict]] = {"text_box": [], "table": []}
    for tb in section["text_boxes"]:
        facts["text_box"].append({"fact_id": tb["fact_id"], "text": tb["text"], "z_order": tb["z_order"]})
    t = section["table"]
    facts["table"].append({"fact_id": t["fact_id"], "n_rows": t["n_rows"], "n_cols": t["n_cols"], "cells": t["cells"], "expected_location": {}})
    return facts


def _stress_pptx_diagram_facts(section: dict) -> dict[str, list[dict]]:
    facts: dict[str, list[dict]] = {"diagram_node": [], "diagram_edge": []}
    for n in section["diagram_nodes"]:
        facts["diagram_node"].append({"fact_id": n["fact_id"], "label": n["label"]})
    for e in section["diagram_edges"]:
        facts["diagram_edge"].append({"fact_id": e["fact_id"], "source": e["source"], "target": e["target"], "directed": e["directed"]})
    return facts


def _stress_chart_facts(section: dict) -> dict[str, list[dict]]:
    facts: dict[str, list[dict]] = {"picture": [], "visual_fact": []}
    facts["picture"].append({"fact_id": f"{section['doc_id']}_PICTURE", "expected_picture_class": section.get("expected_picture_class")})
    for vf in section.get("visual_facts", []):
        facts["visual_fact"].append({"fact_id": vf["fact_id"]})
    for vf in section.get("unsupported_claims", []):
        facts["visual_fact"].append({"fact_id": vf["fact_id"]})
    return facts


def _stress_scanned_facts(section: dict) -> dict[str, list[dict]]:
    return {"whole_page_ocr_text": [{"fact_id": f"{section['doc_id']}_OCR_TEXT", "text": section["expected_ocr_text"]}]}


def build_fact_catalog(manifest: dict[str, Any], suite_key: str, doc_id: str) -> dict[str, list[dict]]:
    if suite_key == "parity":
        return _parity_facts(manifest["parity_suite"])
    stress = manifest["stress_suite"]
    if suite_key == "stress_docx":
        return _stress_docx_facts(stress["docx_nested_structure"])
    if suite_key == "stress_pdf":
        return _stress_pdf_facts(stress["pdf_complex_layout"])
    if suite_key == "stress_pptx_overlap":
        return _stress_pptx_overlap_facts(stress["pptx_overlapping_textboxes"])
    if suite_key == "stress_pptx_diagram":
        return _stress_pptx_diagram_facts(stress["pptx_native_diagram"])
    if suite_key == "stress_chart":
        section = dict(stress["chart_visual_stress"])
        section["doc_id"] = doc_id
        return _stress_chart_facts(section)
    if suite_key == "stress_scanned":
        section = dict(stress["scanned_pdf_ocr_stress"])
        section["doc_id"] = doc_id
        return _stress_scanned_facts(section)
    raise ValueError(f"unknown suite_key: {suite_key!r}")


# --- per-category metric scoring ------------------------------------------


def _score_text_facts(
    fixture: str, text_facts: list[dict], elements: list[TextElement], chunk_map: dict[str, list[str]],
    raw_text_blob: list[tuple[str, str]] | None,
) -> tuple[MetricResult, MetricResult, MetricResult, list[MissRecord], list[UnexpectedObservation], list[EvidenceAlignment]]:
    """text_fact_recall, text_fact_location_accuracy, unexpected_text_duplication."""
    matches: list[str] = []
    misses: list[str] = []
    location_num = 0
    location_den = 0
    miss_records: list[MissRecord] = []
    alignments: list[EvidenceAlignment] = []
    matched_element_ids: set[str] = set()

    for fact in text_facts:
        found = find_exact_text_matches(fact["text"], elements)
        if found:
            matches.append(fact["fact_id"])
            best = found[0]
            matched_element_ids.add(best.element_id)
            expected_unit = _location_unit_index(fact.get("expected_location", {}))
            if expected_unit is not None:
                location_den += 1
                if best.unit_index == expected_unit:
                    location_num += 1
            alignments.append(EvidenceAlignment(
                fact_id=fact["fact_id"], fixture=fixture, fact_type="distractor_paragraph" if fact.get("is_distractor") else "paragraph",
                expected_value={"text": fact["text"]}, expected_location=fact.get("expected_location", {}),
                matched_canonical_element_ids=[e.element_id for e in found],
                matched_chunk_ids=sorted({cid for e in found for cid in chunk_map.get(e.element_id, [])}),
                match_status="matched", derivation="source_derived",
                expected_retrieval_difficulty=_difficulty_for("paragraph", is_distractor=fact.get("is_distractor", False)),
            ))
        else:
            misses.append(fact["fact_id"])
            if raw_text_blob is not None:
                failure_class, confidence, raw_refs = classification.classify_text_absence(fact["text"], raw_text_blob)
            else:
                failure_class, confidence, raw_refs = classification.unresolved_classification("no raw debug artifact available")
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="text_fact_recall",
                expected_value={"text": fact["text"]}, observed_value=None, result="miss",
                failure_class=failure_class, confidence=confidence,
                explanation=f"expected text for {fact['fact_id']!r} not found as any canonical text element (heading/paragraph/list_item/caption)",
                raw_docling_references=raw_refs,
            ))

    recall = _metric("text_fact_recall", TEXT_NORMALIZED_CASE_FOLD_RULE, len(matches), len(text_facts), matches=matches, misses=misses)
    location = _metric("text_fact_location_accuracy", "unit_index of the matched element == expected_location.unit_index (only facts declaring one)", location_num, location_den)

    # unexpected_text_duplication: canonical paragraph/heading/list_item/caption
    # elements whose normalized text does not match ANY expected fact text --
    # a duplicate is flagged when this text ALSO exactly equals another
    # matched element's text (i.e. it's a real repeat of expected content,
    # not merely unrelated furniture).
    expected_norms = {normalize_text_for_comparison(f["text"]) for f in text_facts}
    matched_norms_seen: dict[str, int] = {}
    unexpected: list[UnexpectedObservation] = []
    for element in elements:
        if element.element_type == "ocr_annotation":
            continue
        norm = normalize_text_for_comparison(element.text)
        if not norm:
            continue
        if norm in expected_norms:
            matched_norms_seen[norm] = matched_norms_seen.get(norm, 0) + 1
            if matched_norms_seen[norm] > 1:
                unexpected.append(UnexpectedObservation(
                    fixture=fixture, element_id=element.element_id, element_type=element.element_type,
                    text=element.text, reason="duplicate occurrence of an expected fact's exact text beyond the manifest's declared occurrence count",
                ))
    duplication = _metric(
        "unexpected_text_duplication", "count of canonical text elements whose normalized text exactly repeats an already-matched expected fact",
        len(unexpected), len(elements),
    )
    return recall, location, duplication, miss_records, unexpected, alignments


def _score_identifiers(
    fixture: str, target_facts: list[dict], distractor_facts: list[dict], elements: list[TextElement],
    chunk_map: dict[str, list[str]], occurrence_totals: dict | None, raw_text_blob: list[tuple[str, str]] | None,
) -> tuple[MetricResult, MetricResult, MetricResult, list[MissRecord], list[EvidenceAlignment]]:
    unique_matches: list[str] = []
    unique_misses: list[str] = []
    occ_num = 0
    occ_den = 0
    miss_records: list[MissRecord] = []
    alignments: list[EvidenceAlignment] = []

    for fact in target_facts:
        identifier = fact["normalized_value"]
        found = find_identifier_matches(identifier, elements)
        occurrence_count = sum(count for _, count in found)
        expected_occurrences = len(fact["occurrences"])
        occ_den += expected_occurrences
        occ_num += min(occurrence_count, expected_occurrences)
        if found:
            unique_matches.append(fact["fact_id"])
            alignments.append(EvidenceAlignment(
                fact_id=fact["fact_id"], fixture=fixture, fact_type="identifier_target",
                expected_value={"normalized_value": identifier, "expected_occurrences": expected_occurrences},
                matched_canonical_element_ids=[e.element_id for e, _ in found],
                matched_chunk_ids=sorted({cid for e, _ in found for cid in chunk_map.get(e.element_id, [])}),
                match_status="matched" if occurrence_count >= expected_occurrences else "partial",
                derivation="source_derived",
                expected_retrieval_difficulty=_difficulty_for("identifier_target", is_distractor=False, occurrence_count=expected_occurrences),
            ))
            if occurrence_count < expected_occurrences:
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=fact["fact_id"], metric="identifier_occurrence_recall",
                    expected_value={"expected_occurrences": expected_occurrences}, observed_value={"observed_occurrences": occurrence_count},
                    result="partial", failure_class="parser_content_loss", confidence="certain",
                    explanation=f"identifier {identifier!r} found in only {occurrence_count} of {expected_occurrences} expected occurrences",
                    supporting_canonical_element_ids=[e.element_id for e, _ in found],
                ))
        else:
            unique_misses.append(fact["fact_id"])
            if raw_text_blob is not None:
                failure_class, confidence, raw_refs = classification.classify_identifier_absence(identifier, raw_text_blob)
            else:
                failure_class, confidence, raw_refs = classification.unresolved_classification("no raw debug artifact available")
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="identifier_unique_recall",
                expected_value={"normalized_value": identifier}, result="miss",
                failure_class=failure_class, confidence=confidence,
                explanation=f"identifier {identifier!r} not found (boundary-safe) in any canonical text element",
                raw_docling_references=raw_refs,
            ))

    unique_metric = _metric("identifier_unique_recall", IDENTIFIER_MATCH_RULE, len(unique_matches), len(target_facts), matches=unique_matches, misses=unique_misses)
    occurrence_metric = _metric("identifier_occurrence_recall", IDENTIFIER_MATCH_RULE, occ_num, occ_den)

    # Distractor identifiers: must remain recognizable as themselves
    # (boundary-safe) and must never inflate a target identifier's
    # occurrence count -- since our own target search is already
    # boundary-safe by construction, this metric is a real regression
    # guard on that property using real extracted data, not a synthetic
    # unit test.
    no_false_merge_num = 0
    no_false_merge_den = 0
    for fact in distractor_facts:
        distractor_value = fact["normalized_value"]
        for occurrence in fact["occurrences"]:
            no_false_merge_den += 1
            found_as_distractor = any(identifier_present(e.text, distractor_value) for e in elements)
            # Does ANY element matching the distractor ALSO register a
            # boundary-safe hit for a *shorter* identifier value that is a
            # literal substring of this distractor (the real stress case:
            # "C-88a" containing "C-88")? If our matcher is correct, no.
            false_merge_detected = False
            for target in target_facts:
                target_value = target["normalized_value"]
                if target_value == distractor_value or target_value not in distractor_value:
                    continue
                for e in elements:
                    distractor_spans = find_identifier_occurrences(e.text, distractor_value)
                    target_spans = find_identifier_occurrences(e.text, target_value)
                    for d_start, d_end in distractor_spans:
                        for t_start, t_end in target_spans:
                            if t_start >= d_start and t_end <= d_end:
                                false_merge_detected = True
            if found_as_distractor and not false_merge_detected:
                no_false_merge_num += 1
            elif not found_as_distractor:
                # Distractor simply absent -- not a false-merge issue but
                # still worth recording as a miss on this metric's own terms.
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=fact["fact_id"], metric="identifier_distractor_no_false_merge",
                    expected_value={"normalized_value": distractor_value}, result="miss",
                    failure_class="parser_content_loss", confidence="certain",
                    explanation=f"distractor identifier {distractor_value!r} not found at all -- cannot verify it was not falsely merged",
                ))
            elif false_merge_detected:
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=fact["fact_id"], metric="identifier_distractor_no_false_merge",
                    expected_value={"normalized_value": distractor_value}, result="unexpected",
                    failure_class="distractor_false_positive", confidence="certain",
                    explanation=f"distractor identifier {distractor_value!r} appears to have been falsely merged with a target identifier",
                ))

    no_false_merge_metric = _metric(
        "identifier_distractor_no_false_merge",
        IDENTIFIER_MATCH_RULE + " -- verifies a distractor identifier's occurrences are never counted toward a target identifier's occurrence tally",
        no_false_merge_num, no_false_merge_den,
    )
    return unique_metric, occurrence_metric, no_false_merge_metric, miss_records, alignments


def _score_headings(
    fixture: str, heading_facts: list[dict], document: CanonicalDocument, elements: list[TextElement],
    chunk_map: dict[str, list[str]], raw_text_blob: list[tuple[str, str]] | None,
) -> tuple[MetricResult, MetricResult, MetricResult, list[MissRecord], list[EvidenceAlignment]]:
    text_matches: list[str] = []
    text_misses: list[str] = []
    level_num = 0
    level_den = 0
    classification_num = 0
    classification_den = 0
    miss_records: list[MissRecord] = []
    alignments: list[EvidenceAlignment] = []
    canonical_headings_by_id = {h.block_id: h for h in document.headings}

    for fact in heading_facts:
        found = find_exact_text_matches(fact["text"], elements)
        if not found:
            text_misses.append(fact["fact_id"])
            if raw_text_blob is not None:
                failure_class, confidence, raw_refs = classification.classify_text_absence(fact["text"], raw_text_blob)
            else:
                failure_class, confidence, raw_refs = classification.unresolved_classification("no raw debug artifact")
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="heading_text_recall",
                expected_value={"text": fact["text"]}, result="miss", failure_class=failure_class, confidence=confidence,
                explanation=f"expected heading text for {fact['fact_id']!r} not found in any canonical text element", raw_docling_references=raw_refs,
            ))
            continue

        text_matches.append(fact["fact_id"])
        best = found[0]
        is_real_heading = best.element_id in canonical_headings_by_id
        classification_den += 1
        if is_real_heading:
            classification_num += 1
            level_den += 1
            actual_level = canonical_headings_by_id[best.element_id].level
            if actual_level == fact["level"]:
                level_num += 1
            else:
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=fact["fact_id"], metric="heading_level_accuracy",
                    expected_value={"level": fact["level"]}, observed_value={"level": actual_level}, result="partial",
                    failure_class="parser_classification_loss", confidence="certain",
                    explanation=f"heading {fact['fact_id']!r} text matched but level {actual_level} != expected {fact['level']}",
                    supporting_canonical_element_ids=[best.element_id],
                ))
        else:
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="heading_classification_accuracy",
                expected_value={"as": "heading"}, observed_value={"as": best.element_type}, result="partial",
                failure_class="parser_classification_loss", confidence="certain",
                explanation=f"heading text for {fact['fact_id']!r} present but represented as {best.element_type}, not CanonicalHeading -- text present, heading classification missed",
                supporting_canonical_element_ids=[best.element_id],
            ))
        alignments.append(EvidenceAlignment(
            fact_id=fact["fact_id"], fixture=fixture, fact_type="heading", expected_value={"text": fact["text"], "level": fact["level"]},
            expected_location=fact.get("expected_location", {}), matched_canonical_element_ids=[best.element_id],
            matched_chunk_ids=sorted(chunk_map.get(best.element_id, [])), match_status="matched" if is_real_heading else "partial",
            derivation="source_derived", expected_retrieval_difficulty=_difficulty_for("heading", is_distractor=False),
        ))

    text_recall = _metric("heading_text_recall", TEXT_NORMALIZED_CASE_FOLD_RULE, len(text_matches), len(heading_facts), matches=text_matches, misses=text_misses)
    level_accuracy = _metric("heading_level_accuracy", "of headings correctly classified as CanonicalHeading, exact level match", level_num, level_den)
    classification_accuracy = _metric("heading_classification_accuracy", "of headings whose text matched, fraction represented as CanonicalHeading (not degraded to CanonicalParagraph)", classification_num, classification_den)
    return text_recall, level_accuracy, classification_accuracy, miss_records, alignments


def _cells_key(cells: list[dict]) -> dict[tuple[int, int], dict]:
    return {(c["row"], c["col"]): c for c in cells}


def _score_tables(
    fixture: str, table_facts: list[dict], document: CanonicalDocument, chunk_map: dict[str, list[str]],
) -> tuple[dict[str, MetricResult], list[MissRecord], list[EvidenceAlignment]]:
    presence_num = presence_den = 0
    structure_num = structure_den = 0
    cell_text_num = cell_text_den = 0
    coord_num = coord_den = 0
    header_num = header_den = 0
    span_num = span_den = 0
    miss_records: list[MissRecord] = []
    alignments: list[EvidenceAlignment] = []

    for fact in table_facts:
        presence_den += 1
        expected_cells = _cells_key(fact["cells"])
        expected_texts_norm = {normalize_text_for_comparison(c["text"]): key for key, c in expected_cells.items()}

        candidate_table = None
        for table in document.tables:
            observed_texts_norm = {normalize_text_for_comparison(c.text) for c in table.cells}
            overlap = len(expected_texts_norm.keys() & observed_texts_norm)
            if overlap >= max(1, len(expected_texts_norm) // 2):
                candidate_table = table
                break

        if candidate_table is None:
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="table_presence",
                expected_value={"n_rows": fact["n_rows"], "n_cols": fact["n_cols"]}, result="miss",
                failure_class="parser_structure_loss", confidence="supported",
                explanation=f"no CanonicalTable in this document has meaningful cell-text overlap with expected table {fact['fact_id']!r}",
            ))
            cell_text_den += len(fact["cells"])
            continue

        presence_num += 1
        structure_den += 1
        if candidate_table.n_rows == fact["n_rows"] and candidate_table.n_cols == fact["n_cols"]:
            structure_num += 1
        else:
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="table_structure_accuracy",
                expected_value={"n_rows": fact["n_rows"], "n_cols": fact["n_cols"]},
                observed_value={"n_rows": candidate_table.n_rows, "n_cols": candidate_table.n_cols}, result="partial",
                failure_class="parser_structure_loss", confidence="certain",
                explanation=f"table {fact['fact_id']!r} dimension mismatch",
                supporting_canonical_element_ids=[candidate_table.table_id],
            ))

        observed_by_text: dict[str, list] = {}
        for cell in candidate_table.cells:
            observed_by_text.setdefault(normalize_text_for_comparison(cell.text), []).append(cell)

        matched_cell_ids: list[str] = []
        for (row, col), expected_cell in expected_cells.items():
            cell_text_den += 1
            norm = normalize_text_for_comparison(expected_cell["text"])
            candidates = observed_by_text.get(norm, [])
            if not candidates:
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=f"{fact['fact_id']}_r{row}c{col}", metric="table_cell_text_recall",
                    expected_value={"row": row, "col": col, "text": expected_cell["text"]}, result="miss",
                    failure_class="parser_content_loss", confidence="supported",
                    explanation=f"table {fact['fact_id']!r} cell (row={row}, col={col}) text {expected_cell['text']!r} not found among extracted cells",
                    supporting_canonical_element_ids=[candidate_table.table_id],
                ))
                continue
            cell_text_num += 1
            matched_cell_ids.append(candidate_table.table_id)

            coord_den += 1
            exact = next((c for c in candidates if c.row == row and c.col == col), None)
            if exact is not None:
                coord_num += 1
                observed_cell = exact
            else:
                observed_cell = candidates[0]
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=f"{fact['fact_id']}_r{row}c{col}", metric="table_cell_coordinate_accuracy",
                    expected_value={"row": row, "col": col}, observed_value={"row": observed_cell.row, "col": observed_cell.col},
                    result="partial", failure_class="parser_structure_loss", confidence="certain",
                    explanation=f"table {fact['fact_id']!r}: cell text {expected_cell['text']!r} present but at the wrong row/col -- content match, coordinate miss",
                    supporting_canonical_element_ids=[candidate_table.table_id],
                ))

            header_den += 1
            expected_header = bool(expected_cell.get("is_header", False))
            if bool(observed_cell.is_header) == expected_header:
                header_num += 1
            else:
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=f"{fact['fact_id']}_r{row}c{col}", metric="table_header_status_accuracy",
                    expected_value={"is_header": expected_header}, observed_value={"is_header": observed_cell.is_header},
                    result="partial", failure_class="parser_classification_loss", confidence="certain",
                    explanation=f"table {fact['fact_id']!r} cell (row={row}, col={col}) header-status mismatch",
                ))

            expected_row_span = int(expected_cell.get("row_span", 1))
            expected_col_span = int(expected_cell.get("col_span", 1))
            span_den += 1
            if observed_cell.row_span == expected_row_span and observed_cell.col_span == expected_col_span:
                span_num += 1
            else:
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=f"{fact['fact_id']}_r{row}c{col}", metric="table_span_accuracy",
                    expected_value={"row_span": expected_row_span, "col_span": expected_col_span},
                    observed_value={"row_span": observed_cell.row_span, "col_span": observed_cell.col_span},
                    result="partial", failure_class="parser_structure_loss", confidence="certain",
                    explanation=f"table {fact['fact_id']!r} cell (row={row}, col={col}) span mismatch",
                ))

        alignments.append(EvidenceAlignment(
            fact_id=fact["fact_id"], fixture=fixture, fact_type="table",
            expected_value={"n_rows": fact["n_rows"], "n_cols": fact["n_cols"]}, expected_location=fact.get("expected_location", {}),
            matched_canonical_element_ids=[candidate_table.table_id], matched_chunk_ids=sorted(chunk_map.get(candidate_table.table_id, [])),
            match_status="matched", derivation="source_derived", expected_retrieval_difficulty=_difficulty_for("table", is_distractor=False),
        ))

    metrics = {
        "table_presence": _metric("table_presence", "cell-text-overlap table identification (>= half of expected cell texts present)", presence_num, presence_den),
        "table_structure_accuracy": _metric("table_structure_accuracy", "exact n_rows/n_cols match, of tables identified", structure_num, structure_den),
        "table_cell_text_recall": _metric("table_cell_text_recall", TEXT_NORMALIZED_CASE_FOLD_RULE, cell_text_num, cell_text_den),
        "table_cell_coordinate_accuracy": _metric("table_cell_coordinate_accuracy", "exact (row, col) match, of cells whose text was found", coord_num, coord_den),
        "table_header_status_accuracy": _metric("table_header_status_accuracy", "is_header match, of cells whose text was found", header_num, header_den),
        "table_span_accuracy": _metric("table_span_accuracy", "row_span/col_span exact match, of cells whose text was found", span_num, span_den),
    }
    return metrics, miss_records, alignments


def _score_pictures_captions(
    fixture: str, picture_facts: list[dict], caption_facts: list[dict], document: CanonicalDocument, chunk_map: dict[str, list[str]],
) -> tuple[dict[str, MetricResult], list[MissRecord], list[EvidenceAlignment]]:
    presence_num = presence_den = 0
    provenance_num = provenance_den = 0
    caption_text_num = caption_text_den = 0
    caption_link_num = caption_link_den = 0
    miss_records: list[MissRecord] = []
    alignments: list[EvidenceAlignment] = []
    provenance_element_ids = {p.element_id for p in document.provenance}

    matched_picture_ids: list[str] = []
    for index, fact in enumerate(picture_facts):
        presence_den += 1
        if index < len(document.pictures):
            presence_num += 1
            picture = document.pictures[index]
            matched_picture_ids.append(picture.picture_id)
            provenance_den += 1
            has_provenance = picture.picture_id in provenance_element_ids
            has_bbox = picture.bbox is not None
            if has_provenance:
                provenance_num += 1
            else:
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=fact["fact_id"], metric="picture_provenance_completeness",
                    expected_value={"has_provenance": True}, observed_value={"has_provenance": False, "has_bbox": has_bbox}, result="partial",
                    failure_class="parser_provenance_loss", confidence="certain",
                    explanation=f"picture {fact['fact_id']!r} extracted but has no ProvenanceEntry",
                ))
            alignments.append(EvidenceAlignment(
                fact_id=fact["fact_id"], fixture=fixture, fact_type="picture", expected_value={k: v for k, v in fact.items() if k != "fact_id"},
                expected_location=fact.get("expected_location", {}), matched_canonical_element_ids=[picture.picture_id],
                matched_chunk_ids=sorted(chunk_map.get(picture.picture_id, [])), match_status="matched", derivation="source_derived",
                expected_retrieval_difficulty=_difficulty_for("picture", is_distractor=False),
            ))
        else:
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="picture_presence",
                expected_value={"expected": True}, result="miss", failure_class="parser_content_loss", confidence="certain",
                explanation=f"expected picture {fact['fact_id']!r} not present in CanonicalDocument.pictures",
            ))

    provenance_ref_by_element_id = {p.element_id: p.source_element_ref for p in document.provenance if p.source_element_ref}
    for fact in caption_facts:
        caption_text_den += 1
        target_text = normalize_text_for_comparison(fact["text"])
        caption_matches = [c for c in document.captions if normalize_text_for_comparison(c.text) == target_text]
        paragraph_matches = [] if caption_matches else [p for p in document.paragraphs if normalize_text_for_comparison(p.text) == target_text]

        if not caption_matches and not paragraph_matches:
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="caption_text_recall",
                expected_value={"text": fact["text"]}, result="miss", failure_class="parser_content_loss", confidence="supported",
                explanation=f"caption text for {fact['fact_id']!r} not found as any CanonicalCaption or CanonicalParagraph",
            ))
            continue

        caption_text_num += 1
        caption_link_den += 1
        if caption_matches:
            caption = caption_matches[0]
            if caption.target_picture_id in matched_picture_ids:
                caption_link_num += 1
            else:
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=fact["fact_id"], metric="caption_linkage_accuracy",
                    expected_value={"target_picture": fact.get("target_picture")}, observed_value={"target_picture_id": caption.target_picture_id}, result="partial",
                    failure_class="parser_relationship_loss", confidence="certain",
                    explanation=f"caption {fact['fact_id']!r} is a real CanonicalCaption but target_picture_id does not resolve to the expected picture",
                    supporting_canonical_element_ids=[caption.block_id],
                ))
            alignments.append(EvidenceAlignment(
                fact_id=fact["fact_id"], fixture=fixture, fact_type="caption", expected_value={"text": fact["text"]},
                expected_location=fact.get("expected_location", {}), matched_canonical_element_ids=[caption.block_id],
                matched_chunk_ids=sorted(chunk_map.get(caption.block_id, [])), match_status="matched", derivation="source_derived",
                expected_retrieval_difficulty=_difficulty_for("caption", is_distractor=False),
            ))
        else:
            # Caption text present as a plain paragraph, not linked to its
            # picture (Stage 5A's known DOCX/PPTX limitation) -- text
            # present, relationship missed, never total content loss.
            paragraph = paragraph_matches[0]
            raw_ref = provenance_ref_by_element_id.get(paragraph.block_id)
            # mapper_loss is only assignable with real raw-Docling evidence
            # (MissRecord's own invariant) -- this element was successfully
            # mapped into CanonicalDocument, so it always has a
            # ProvenanceEntry.source_element_ref in practice; fall back to
            # "unresolved" rather than assert mapper_loss without it.
            failure_class = "mapper_loss" if raw_ref else "unresolved"
            confidence = "supported" if raw_ref else "unresolved"
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="caption_linkage_accuracy",
                expected_value={"text": fact["text"], "target_picture": fact.get("target_picture")}, observed_value={"as": "paragraph"}, result="partial",
                failure_class=failure_class, confidence=confidence,
                explanation=f"caption text for {fact['fact_id']!r} present as a plain CanonicalParagraph, not linked to its picture -- caption text present, caption relationship missed",
                supporting_canonical_element_ids=[paragraph.block_id],
                raw_docling_references=[raw_ref] if raw_ref else [],
            ))
            alignments.append(EvidenceAlignment(
                fact_id=fact["fact_id"], fixture=fixture, fact_type="caption", expected_value={"text": fact["text"]},
                expected_location=fact.get("expected_location", {}), matched_canonical_element_ids=[paragraph.block_id],
                matched_chunk_ids=sorted(chunk_map.get(paragraph.block_id, [])), match_status="partial", derivation="source_derived",
                expected_retrieval_difficulty=_difficulty_for("caption", is_distractor=False),
            ))

    metrics = {
        "picture_presence": _metric("picture_presence", "at least one CanonicalPicture present per expected picture fact", presence_num, presence_den),
        "picture_provenance_completeness": _metric("picture_provenance_completeness", "matched picture has a ProvenanceEntry", provenance_num, provenance_den),
        "caption_text_recall": _metric("caption_text_recall", TEXT_NORMALIZED_CASE_FOLD_RULE + " -- matched against CanonicalCaption OR CanonicalParagraph text (text recovery is scored independently of caption-picture linkage)", caption_text_num, caption_text_den),
        "caption_linkage_accuracy": _metric("caption_linkage_accuracy", "of captions whose text was found (as caption or paragraph), represented as a real CanonicalCaption with target_picture_id resolving to the expected picture", caption_link_num, caption_link_den),
    }
    return metrics, miss_records, alignments


def _score_ocr_tokens(
    fixture: str, ocr_token_facts: list[dict], document: CanonicalDocument, chunk_map: dict[str, list[str]],
) -> tuple[MetricResult, MetricResult, list[MissRecord], list[EvidenceAlignment]]:
    ocr_annotations = [a for a in document.annotations if a.annotation_type == "ocr"]
    provenance_element_ids = {p.element_id for p in document.provenance}
    token_num = 0
    miss_records: list[MissRecord] = []
    alignments: list[EvidenceAlignment] = []
    for fact in ocr_token_facts:
        norm_target = normalize_text_for_comparison(fact["text"])
        found = [a for a in ocr_annotations if norm_target in normalize_text_for_comparison(a.text) or normalize_text_for_comparison(a.text) in norm_target]
        if found:
            token_num += 1
            annotation = found[0]
            alignments.append(EvidenceAlignment(
                fact_id=fact["fact_id"], fixture=fixture, fact_type="ocr_token", expected_value={"text": fact["text"]},
                matched_annotation_ids=[annotation.annotation_id], matched_chunk_ids=sorted(chunk_map.get(annotation.annotation_id, [])),
                match_status="matched", derivation="source_derived", expected_retrieval_difficulty="direct",
            ))
        else:
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="ocr_token_recall",
                expected_value={"text": fact["text"]}, result="miss", failure_class="parser_content_loss", confidence="supported",
                explanation=f"expected OCR token {fact['text']!r} not found (as substring, either direction) among extracted OcrAnnotation text",
            ))
    token_metric = _metric("ocr_token_recall", "case-folded substring match (either direction) against OcrAnnotation.text -- OCR engines may merge/split tokens", token_num, len(ocr_token_facts))

    prov_den = len(ocr_annotations)
    prov_num = sum(1 for a in ocr_annotations if a.annotation_id in provenance_element_ids)
    provenance_metric = _metric("ocr_provenance_completeness", "OcrAnnotation.annotation_id resolves to a ProvenanceEntry.element_id", prov_num, prov_den)
    return token_metric, provenance_metric, miss_records, alignments


def _score_whole_page_ocr(
    fixture: str, facts: list[dict], document: CanonicalDocument, chunk_map: dict[str, list[str]],
) -> tuple[MetricResult, list[MissRecord], list[EvidenceAlignment]]:
    elements = flatten_text_elements(document)
    miss_records: list[MissRecord] = []
    alignments: list[EvidenceAlignment] = []
    num = 0
    for fact in facts:
        found = find_exact_text_matches(fact["text"], elements)
        if found:
            num += 1
            alignments.append(EvidenceAlignment(
                fact_id=fact["fact_id"], fixture=fixture, fact_type="whole_page_ocr_text", expected_value={"text": fact["text"]},
                matched_canonical_element_ids=[found[0].element_id], matched_chunk_ids=sorted(chunk_map.get(found[0].element_id, [])),
                match_status="matched", derivation="source_derived", expected_retrieval_difficulty="direct",
            ))
        else:
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="ocr_whole_page_text_recall",
                expected_value={"text": fact["text"]}, result="miss", failure_class="parser_content_loss", confidence="supported",
                explanation="expected whole-page OCR text not found as any canonical text element",
            ))
    metric = _metric("ocr_whole_page_text_recall", TEXT_NORMALIZED_CASE_FOLD_RULE + " -- scored as text recovery, independent of OCR-origin classification (Stage 5A maps whole-page OCR as a plain paragraph, per D-035)", num, len(facts))
    return metric, miss_records, alignments


def _score_list_items(
    fixture: str, facts: list[dict], document: CanonicalDocument, chunk_map: dict[str, list[str]],
) -> tuple[dict[str, MetricResult], list[MissRecord], list[EvidenceAlignment]]:
    elements = [TextElement(li.block_id, li.text, "list_item", li.unit_index) for li in document.list_items]
    by_text = {normalize_text_for_comparison(li.text): li for li in document.list_items}
    recall_num = 0
    indent_num = indent_den = 0
    parent_num = parent_den = 0
    miss_records: list[MissRecord] = []
    alignments: list[EvidenceAlignment] = []
    matched_block_id_by_fact_id: dict[str, str] = {}

    for fact in facts:
        norm = normalize_text_for_comparison(fact["text"])
        item = by_text.get(norm)
        if item is None:
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="list_item_recall",
                expected_value={"text": fact["text"]}, result="miss", failure_class="parser_content_loss", confidence="supported",
                explanation=f"expected list item text for {fact['fact_id']!r} not found among CanonicalListItem",
            ))
            continue
        recall_num += 1
        matched_block_id_by_fact_id[fact["fact_id"]] = item.block_id
        indent_den += 1
        if item.indent_level == fact["indent_level"]:
            indent_num += 1
        else:
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="list_indentation_accuracy",
                expected_value={"indent_level": fact["indent_level"]}, observed_value={"indent_level": item.indent_level}, result="partial",
                failure_class="parser_structure_loss", confidence="certain",
                explanation=f"list item {fact['fact_id']!r} text matched but indent_level {item.indent_level} != expected {fact['indent_level']}",
                supporting_canonical_element_ids=[item.block_id],
            ))
        alignments.append(EvidenceAlignment(
            fact_id=fact["fact_id"], fixture=fixture, fact_type="list_item", expected_value={"text": fact["text"], "indent_level": fact["indent_level"]},
            matched_canonical_element_ids=[item.block_id], matched_chunk_ids=sorted(chunk_map.get(item.block_id, [])),
            match_status="matched", derivation="source_derived", expected_retrieval_difficulty=_difficulty_for("list_item", is_distractor=False),
        ))

    for fact in facts:
        expected_parent_fact_id = fact.get("parent")
        if expected_parent_fact_id is None:
            continue
        parent_den += 1
        item_block_id = matched_block_id_by_fact_id.get(fact["fact_id"])
        expected_parent_block_id = matched_block_id_by_fact_id.get(expected_parent_fact_id)
        item = next((li for li in document.list_items if li.block_id == item_block_id), None)
        if item is not None and expected_parent_block_id is not None and item.parent_block_id == expected_parent_block_id:
            parent_num += 1
        else:
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="list_parent_link_accuracy",
                expected_value={"parent": expected_parent_fact_id}, observed_value={"parent_block_id": item.parent_block_id if item else None}, result="partial",
                failure_class="parser_relationship_loss", confidence="certain",
                explanation=f"list item {fact['fact_id']!r} does not carry the expected parent_block_id linkage to {expected_parent_fact_id!r}",
            ))

    metrics = {
        "list_item_recall": _metric("list_item_recall", TEXT_NORMALIZED_CASE_FOLD_RULE, recall_num, len(facts)),
        "list_indentation_accuracy": _metric("list_indentation_accuracy", "exact indent_level match, of list items whose text matched", indent_num, indent_den),
        "list_parent_link_accuracy": _metric("list_parent_link_accuracy", "parent_block_id resolves to the expected parent list item, of items declaring a parent", parent_num, parent_den),
    }
    return metrics, miss_records, alignments


def _score_provenance(fixture: str, document: CanonicalDocument) -> dict[str, MetricResult]:
    provenance_by_id = {p.element_id: p for p in document.provenance}
    categories: dict[str, list[tuple[str, bool]]] = {
        "heading": [(h.block_id, h.bbox is not None) for h in document.headings],
        "paragraph": [(p.block_id, p.bbox is not None) for p in document.paragraphs],
        "list_item": [(li.block_id, li.bbox is not None) for li in document.list_items],
        "table": [(t.table_id, t.bbox is not None) for t in document.tables],
        "picture": [(p.picture_id, p.bbox is not None) for p in document.pictures],
        "caption": [(c.block_id, c.bbox is not None) for c in document.captions],
        "annotation": [(a.annotation_id, a.bbox is not None) for a in document.annotations],
    }
    metrics: dict[str, MetricResult] = {}
    total_num = total_den = 0
    for category, items in categories.items():
        num = sum(1 for element_id, _ in items if element_id in provenance_by_id)
        bbox_num = sum(1 for element_id, has_bbox in items if element_id in provenance_by_id and provenance_by_id[element_id].bbox is not None)
        den = len(items)
        metrics[f"provenance_coverage_{category}"] = _metric(f"provenance_coverage_{category}", "element_id present as a ProvenanceEntry.element_id", num, den)
        metrics[f"provenance_bbox_coverage_{category}"] = _metric(f"provenance_bbox_coverage_{category}", "has a ProvenanceEntry AND that entry's bbox is not None (bbox absence is not treated as total provenance absence)", bbox_num, den)
        total_num += num
        total_den += den
    metrics["provenance_coverage_overall"] = _metric("provenance_coverage_overall", "element_id present as a ProvenanceEntry.element_id, across every element category", total_num, total_den)
    return metrics


def _score_structural_stress(
    fixture: str, suite_key: str, facts: dict[str, list[dict]], document: CanonicalDocument, chunk_map: dict[str, list[str]],
) -> tuple[dict[str, MetricResult], list[MissRecord], list[EvidenceAlignment]]:
    metrics: dict[str, MetricResult] = {}
    miss_records: list[MissRecord] = []
    alignments: list[EvidenceAlignment] = []
    elements = flatten_text_elements(document)

    if suite_key == "stress_pdf" and facts.get("paragraph"):
        by_fact = {}
        for fact in facts["paragraph"]:
            found = find_exact_text_matches(fact["text"], elements)
            if found:
                by_fact[fact["fact_id"]] = found[0]
        retained_num = len(by_fact)
        metrics["column_text_retention"] = _metric("column_text_retention", TEXT_NORMALIZED_CASE_FOLD_RULE, retained_num, len(facts["paragraph"]))
        ordered_ids = sorted(facts["paragraph"], key=lambda f: f["column"])
        if len(ordered_ids) == 2 and all(f["fact_id"] in by_fact for f in ordered_ids):
            first, second = ordered_ids
            # Reading order within one unit isn't captured on TextElement
            # (order_index lives on the canonical model, not the flattened
            # dataclass) -- read it back from the document's own paragraphs.
            para_order = {p.block_id: p.order_index for p in document.paragraphs}
            first_order = para_order.get(by_fact[first["fact_id"]].element_id)
            second_order = para_order.get(by_fact[second["fact_id"]].element_id)
            correct = first_order is not None and second_order is not None and first_order < second_order
            metrics["column_reading_order_correct"] = _metric("column_reading_order_correct", "column-1 paragraph's order_index < column-2 paragraph's order_index", 1 if correct else 0, 1)
            if not correct:
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id="STRESS_PDF_001_reading_order", metric="column_reading_order_correct",
                    expected_value={"column_1_before_column_2": True}, result="miss", failure_class="parser_structure_loss", confidence="certain",
                    explanation="column-1 text does not precede column-2 text in reading order",
                ))

    if suite_key == "stress_pptx_overlap" and facts.get("text_box"):
        by_fact = {}
        for fact in facts["text_box"]:
            found = find_exact_text_matches(fact["text"], elements)
            if found:
                by_fact[fact["fact_id"]] = found[0]
        metrics["overlap_both_retained"] = _metric("overlap_both_retained", TEXT_NORMALIZED_CASE_FOLD_RULE, len(by_fact), len(facts["text_box"]))
        provenance_by_id = {p.element_id: p for p in document.provenance}
        z_order_den = len(by_fact)
        z_order_num = sum(1 for e in by_fact.values() if provenance_by_id.get(e.element_id) is not None and provenance_by_id[e.element_id].z_order is not None)
        metrics["overlap_z_order_recorded"] = _metric("overlap_z_order_recorded", "matched text box has a non-None ProvenanceEntry.z_order (Stage 5A/Docling does not currently expose PPTX shape z-order)", z_order_num, z_order_den)
        for fact in facts["text_box"]:
            if fact["fact_id"] not in by_fact:
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=fact["fact_id"], metric="overlap_both_retained",
                    expected_value={"text": fact["text"]}, result="miss", failure_class="parser_content_loss", confidence="supported",
                    explanation="expected overlapping text box not retained",
                ))

    if suite_key == "stress_pptx_diagram":
        node_facts = facts.get("diagram_node", [])
        by_fact = {}
        for fact in node_facts:
            found = find_exact_text_matches(fact["label"], elements)
            if found:
                by_fact[fact["fact_id"]] = found[0]
                alignments.append(EvidenceAlignment(
                    fact_id=fact["fact_id"], fixture=fixture, fact_type="diagram_node_label", expected_value={"label": fact["label"]},
                    matched_canonical_element_ids=[found[0].element_id], matched_chunk_ids=sorted(chunk_map.get(found[0].element_id, [])),
                    match_status="matched", derivation="source_derived", expected_retrieval_difficulty="direct",
                ))
            else:
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=fact["fact_id"], metric="diagram_label_recall",
                    expected_value={"label": fact["label"]}, result="miss", failure_class="parser_content_loss", confidence="supported",
                    explanation="expected native-diagram node label not found as any canonical text element",
                ))
        metrics["diagram_label_recall"] = _metric("diagram_label_recall", TEXT_NORMALIZED_CASE_FOLD_RULE, len(by_fact), len(node_facts))
        no_diagram_annotation = not any(a.annotation_type in ("diagram_node", "diagram_edge") for a in document.annotations)
        metrics["no_invented_diagram_relationships"] = _metric(
            "no_invented_diagram_relationships", "Stage 5A must never produce DiagramNode/EdgeAnnotation (no VisionEnricher exists) -- verifies zero such annotations exist",
            1 if no_diagram_annotation else 0, 1,
        )
        edge_facts = facts.get("diagram_edge", [])
        metrics["diagram_edge_recovery"] = _metric(
            "diagram_edge_recovery", "DiagramEdgeAnnotation recovery -- structurally not_applicable to path A (no VisionEnricher; Docling's native PPTX backend does not expose connector source/target linkage to this mapper)",
            0, 0, excluded=len(edge_facts),
        )

    return metrics, miss_records, alignments


# --- top-level per-fixture orchestration ------------------------------------


def evaluate_fixture(loaded: LoadedFixture, manifest: dict[str, Any]) -> FixtureEvaluationResult:
    document = loaded.document
    chunks = loaded.chunks
    chunk_map = element_to_chunk_ids(chunks)
    elements = flatten_text_elements(document)
    facts = build_fact_catalog(manifest, loaded.suite_key, loaded.doc_id)

    raw_text_blob: list[tuple[str, str]] | None = None
    if loaded.raw_debug_path.exists():
        raw_text_blob = classification.extract_raw_text_blob(loaded.raw_debug())

    metrics: dict[str, MetricResult] = {}
    miss_records: list[MissRecord] = []
    unexpected_observations: list[UnexpectedObservation] = []
    evidence_alignments: list[EvidenceAlignment] = []

    text_facts = facts.get("paragraph", [])
    if text_facts:
        recall, location, duplication, misses, unexpected, alignments = _score_text_facts(
            loaded.fixture, text_facts, elements, chunk_map, raw_text_blob
        )
        metrics.update({"text_fact_recall": recall, "text_fact_location_accuracy": location, "unexpected_text_duplication": duplication})
        miss_records += misses
        unexpected_observations += unexpected
        evidence_alignments += alignments

    if facts.get("identifier_target") or facts.get("identifier_distractor"):
        unique_m, occ_m, no_merge_m, misses, alignments = _score_identifiers(
            loaded.fixture, facts.get("identifier_target", []), facts.get("identifier_distractor", []),
            elements, chunk_map, None, raw_text_blob,
        )
        metrics.update({
            "identifier_unique_recall": unique_m, "identifier_occurrence_recall": occ_m,
            "identifier_distractor_no_false_merge": no_merge_m,
        })
        miss_records += misses
        evidence_alignments += alignments
        for fact in facts.get("identifier_distractor", []):
            evidence_alignments.append(EvidenceAlignment(
                fact_id=fact["fact_id"], fixture=loaded.fixture, fact_type="identifier_distractor",
                expected_value={"normalized_value": fact["normalized_value"]},
                matched_canonical_element_ids=[e.element_id for e, _ in find_identifier_matches(fact["normalized_value"], elements)],
                matched_chunk_ids=sorted({cid for e, _ in find_identifier_matches(fact["normalized_value"], elements) for cid in chunk_map.get(e.element_id, [])}),
                match_status="matched" if find_identifier_matches(fact["normalized_value"], elements) else "missing",
                derivation="source_derived", expected_retrieval_difficulty="distractor_sensitive",
            ))

    if facts.get("heading"):
        text_m, level_m, class_m, misses, alignments = _score_headings(loaded.fixture, facts["heading"], document, elements, chunk_map, raw_text_blob)
        metrics.update({"heading_text_recall": text_m, "heading_level_accuracy": level_m, "heading_classification_accuracy": class_m})
        miss_records += misses
        evidence_alignments += alignments

    if facts.get("table"):
        table_metrics, misses, alignments = _score_tables(loaded.fixture, facts["table"], document, chunk_map)
        metrics.update(table_metrics)
        miss_records += misses
        evidence_alignments += alignments

    if facts.get("picture") or facts.get("caption"):
        pc_metrics, misses, alignments = _score_pictures_captions(loaded.fixture, facts.get("picture", []), facts.get("caption", []), document, chunk_map)
        metrics.update(pc_metrics)
        miss_records += misses
        evidence_alignments += alignments

    if facts.get("ocr_token"):
        token_m, prov_m, misses, alignments = _score_ocr_tokens(loaded.fixture, facts["ocr_token"], document, chunk_map)
        metrics.update({"ocr_token_recall": token_m, "ocr_provenance_completeness": prov_m})
        miss_records += misses
        evidence_alignments += alignments

    if facts.get("whole_page_ocr_text"):
        m, misses, alignments = _score_whole_page_ocr(loaded.fixture, facts["whole_page_ocr_text"], document, chunk_map)
        metrics["ocr_whole_page_text_recall"] = m
        miss_records += misses
        evidence_alignments += alignments

    if facts.get("list_item"):
        li_metrics, misses, alignments = _score_list_items(loaded.fixture, facts["list_item"], document, chunk_map)
        metrics.update(li_metrics)
        miss_records += misses
        evidence_alignments += alignments

    if facts.get("visual_fact"):
        metrics["visual_fact_accuracy"] = _metric(
            "visual_fact_accuracy", "VisualFactAnnotation recovery -- structurally not_applicable to path A (no VisionEnricher, Stage 5A never produces VisualFactAnnotation)",
            0, 0, excluded=len(facts["visual_fact"]),
        )

    structural_metrics, structural_misses, structural_alignments = _score_structural_stress(loaded.fixture, loaded.suite_key, facts, document, chunk_map)
    metrics.update(structural_metrics)
    miss_records += structural_misses
    evidence_alignments += structural_alignments

    # Stage 6A section 1: evaluation-contract limitation, recorded rather
    # than invented -- the chart fixture declares visual_facts (numeric
    # values, requiring a VisionEnricher path A doesn't have) but no
    # expected_ocr_tokens/expected_ocr_text field the way the parity
    # picture and scanned-PDF fixtures do, so OCR-token recall cannot be
    # scored for this fixture from the frozen manifest alone.
    if loaded.suite_key == "stress_chart":
        miss_records.append(MissRecord(
            fixture=loaded.fixture, fact_id=f"{loaded.doc_id}_ocr_tokens_undeclared", metric="ocr_token_recall",
            expected_value=None, observed_value=None, result="miss", failure_class="evaluation_contract_insufficient",
            confidence="certain",
            explanation=(
                "chart_visual_stress declares visual_facts (CF_*/CC_*/CU_*, numeric-value facts requiring a "
                "VisionEnricher path A does not have) but no expected_ocr_tokens/expected_ocr_text field -- unlike "
                "the parity picture and scanned-PDF fixtures, this manifest section provides no frozen ground truth "
                "an evaluator could score raw chart-label OCR recall against without inventing expected values. "
                "Proposed fix: a separate, versioned evaluation-profile addendum (never a frozen-manifest edit) "
                "adding an explicit expected_ocr_tokens list for chart_visual_stress."
            ),
        ))

    metrics.update(_score_provenance(loaded.fixture, document))

    # Backfill EvidenceAlignment.unit_indexes (Stage 6A section 16) from
    # every matched canonical element/annotation's own unit_index, rather
    # than threading it through all dozen construction call sites above --
    # a single, exhaustive lookup here is less error-prone than repeating
    # the same lookup logic at every call site.
    unit_index_by_id: dict[str, int] = {}
    for h in document.headings:
        unit_index_by_id[h.block_id] = h.unit_index
    for p in document.paragraphs:
        unit_index_by_id[p.block_id] = p.unit_index
    for li in document.list_items:
        unit_index_by_id[li.block_id] = li.unit_index
    for cap in document.captions:
        unit_index_by_id[cap.block_id] = cap.unit_index
    for t in document.tables:
        unit_index_by_id[t.table_id] = t.unit_index
    for pic in document.pictures:
        unit_index_by_id[pic.picture_id] = pic.unit_index
    for ann in document.annotations:
        unit_index_by_id[ann.annotation_id] = ann.unit_index
    source_ref_by_id = {p.element_id: p.source_element_ref for p in document.provenance if p.source_element_ref}
    evidence_alignments = [
        alignment.model_copy(update={
            "unit_indexes": sorted({
                unit_index_by_id[eid]
                for eid in (*alignment.matched_canonical_element_ids, *alignment.matched_annotation_ids)
                if eid in unit_index_by_id
            }),
            "source_references": sorted({
                source_ref_by_id[eid]
                for eid in (*alignment.matched_canonical_element_ids, *alignment.matched_annotation_ids)
                if eid in source_ref_by_id
            }),
        })
        for alignment in evidence_alignments
    ]

    operational = OperationalEvidence(
        conversion_status=loaded.conversion_report["conversion_status"],
        elapsed_ms=loaded.conversion_report["elapsed_ms"],
        diagnostics_by_category=loaded.conversion_report.get("diagnostics_by_category", {}),
        diagnostics_by_severity=loaded.conversion_report.get("diagnostics_by_severity", {}),
        diagnostics_by_affects_fidelity=loaded.conversion_report.get("diagnostics_by_affects_fidelity", {}),
        unit_count=loaded.conversion_report["unit_count"],
        heading_count=loaded.conversion_report["heading_count"],
        paragraph_count=loaded.conversion_report["paragraph_count"],
        list_item_count=loaded.conversion_report["list_item_count"],
        table_count=loaded.conversion_report["table_count"],
        table_cell_count=loaded.conversion_report["table_cell_count"],
        picture_count=loaded.conversion_report["picture_count"],
        caption_count=loaded.conversion_report["caption_count"],
        annotation_counts=loaded.conversion_report.get("annotation_counts", {}),
        provenance_count=loaded.conversion_report["provenance_count"],
        canonical_chunk_count=loaded.conversion_report["canonical_chunk_count"],
        textual_chunk_count=loaded.conversion_report["textual_chunk_count"],
        asset_only_chunk_count=loaded.conversion_report["asset_only_chunk_count"],
        canonical_document_hash=stable_canonical_hash(document),
    )

    return FixtureEvaluationResult(
        fixture=loaded.fixture, doc_id=loaded.doc_id, source_format=loaded.source_format,
        operational=operational, metrics=metrics, miss_records=miss_records,
        unexpected_observations=unexpected_observations, evidence_alignments=evidence_alignments,
    )
