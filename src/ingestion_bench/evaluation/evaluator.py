"""Stage 6A deterministic ingestion-fidelity evaluator (hardened by Stage
6A.1 -- see docs/POC_DECISION_LOG.md D-044 onward for the correction
rationale).

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
CanonicalDocument as the scored representation. A raw self_ref proves
TEXT existence only; classification.py::classify_relationship_absence is
the only path that may assign mapper_loss for a missing RELATIONSHIP/
STRUCTURE, and only when the specific raw relation field explicitly
exposes it (Stage 6A.1 item 4).

The gold evidence-alignment catalog this module builds is COMPLETE: one
EvidenceAlignment per expected manifest fact -- matched, partial, missing,
or not_applicable -- never only the matched ones (Stage 6A.1 item 2).
"""

from __future__ import annotations

import hashlib
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
    OCR_PHRASE_MATCH_RULE,
    TEXT_NORMALIZED_CASE_FOLD_RULE,
    find_identifier_occurrences,
    identifier_present,
    normalize_text_for_comparison,
    ocr_phrase_recovered,
)

EVALUATOR_VERSION = "1.2.0"

# --- fixture registry --------------------------------------------------
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


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    canonical_document_file_sha256: str
    canonical_chunks_file_sha256: str | None
    conversion_report_file_sha256: str
    raw_docling_debug_file_sha256: str | None
    artifact_completeness: dict[str, bool]
    determinism: dict[str, Any] | None
    _raw_debug: dict[str, Any] | None = dataclass_field(default=None, repr=False)

    def raw_debug(self) -> dict[str, Any]:
        if self._raw_debug is None:
            self._raw_debug = json.loads(self.raw_debug_path.read_text(encoding="utf-8"))
        return self._raw_debug


def load_fixture_artifacts(
    artifacts_root: Path, *, determinism_by_fixture: dict[str, dict] | None = None,
) -> list[LoadedFixture]:
    """Reads Stage 5A's own output verbatim -- never mutates, never
    re-derives a value Stage 5A already computed. Stage 6A.1 item 11:
    also computes a raw-bytes SHA-256 of every artifact file read and
    records which expected artifacts were actually present."""
    determinism_by_fixture = determinism_by_fixture or {}
    loaded = []
    for fixture, doc_id, artifact_key, source_format, suite_key in FIXTURES:
        fixture_dir = artifacts_root / artifact_key
        document_path = fixture_dir / "canonical_document.json"
        chunks_path = fixture_dir / "canonical_chunks.jsonl"
        conversion_report_path = fixture_dir / "conversion_report.json"
        raw_debug_path = artifacts_root / "docling_raw" / f"{artifact_key}.json"

        document = CanonicalDocument.model_validate(json.loads(document_path.read_text(encoding="utf-8")))
        chunks = []
        if chunks_path.exists():
            for line in chunks_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    chunks.append(CanonicalChunk.model_validate(json.loads(line)))
        conversion_report = json.loads(conversion_report_path.read_text(encoding="utf-8"))

        artifact_completeness = {
            "canonical_document": document_path.exists(),
            "canonical_chunks": chunks_path.exists(),
            "conversion_report": conversion_report_path.exists(),
            "raw_docling_debug": raw_debug_path.exists(),
        }

        loaded.append(
            LoadedFixture(
                fixture=fixture, doc_id=doc_id, artifact_key=artifact_key, source_format=source_format,
                suite_key=suite_key, document=document, chunks=chunks, conversion_report=conversion_report,
                raw_debug_path=raw_debug_path,
                canonical_document_file_sha256=_sha256_file(document_path) or "",
                canonical_chunks_file_sha256=_sha256_file(chunks_path),
                conversion_report_file_sha256=_sha256_file(conversion_report_path) or "",
                raw_docling_debug_file_sha256=_sha256_file(raw_debug_path),
                artifact_completeness=artifact_completeness,
                determinism=determinism_by_fixture.get(fixture),
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


# --- generic scoring bookkeeping ------------------------------------------


def _metric(name: str, rule: str, numerator: int, denominator: int, *, excluded: int = 0,
            matches: list[str] | None = None, misses: list[str] | None = None) -> MetricResult:
    score = None if denominator == 0 else numerator / denominator
    return MetricResult(
        metric_name=name, matching_rule=rule, numerator=numerator, denominator=denominator,
        excluded_not_applicable=excluded, score=score,
        supporting_matches=matches or [], supporting_misses=misses or [],
    )


class _MetricAcc:
    """Stage 6A.1 item 5: a single accumulator that keeps numerator/
    denominator/excluded AND the exact fact_ids behind them in lockstep,
    so `supporting_matches`/`supporting_misses` can never silently drift
    out of sync with the counts (every metric built through this class is
    exhaustively backed by real fact ids, not just numbers)."""

    def __init__(self, name: str, rule: str) -> None:
        self.name = name
        self.rule = rule
        self.numerator = 0
        self.denominator = 0
        self.excluded = 0
        self.matches: list[str] = []
        self.misses: list[str] = []

    def record_match(self, fact_id: str) -> None:
        self.numerator += 1
        self.denominator += 1
        self.matches.append(fact_id)

    def record_partial(self, fact_id: str) -> None:
        self.denominator += 1
        self.misses.append(fact_id)

    def record_miss(self, fact_id: str) -> None:
        self.denominator += 1
        self.misses.append(fact_id)

    def record_excluded(self) -> None:
        self.excluded += 1

    def result(self) -> MetricResult:
        return _metric(self.name, self.rule, self.numerator, self.denominator, excluded=self.excluded,
                        matches=self.matches, misses=self.misses)


def _alignment(
    fact_id: str, fixture: str, fact_type: str, *, expected_value: dict, expected_location: dict | None = None,
    matched_element_ids: list[str] | None = None, matched_annotation_ids: list[str] | None = None,
    matched_chunk_ids: list[str] | None = None, match_status: str, derivation: str,
) -> EvidenceAlignment:
    return EvidenceAlignment(
        fact_id=fact_id, fixture=fixture, fact_type=fact_type, expected_value=expected_value,
        expected_location=expected_location or {}, matched_canonical_element_ids=matched_element_ids or [],
        matched_annotation_ids=matched_annotation_ids or [], matched_chunk_ids=matched_chunk_ids or [],
        match_status=match_status, derivation=derivation, expected_retrieval_difficulty=None,
    )


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
    """Stage 6A.1 item 7: visual_facts and unsupported_claims are kept as
    SEPARATE fact-catalog keys -- never combined into one bucket -- so
    they can be scored with different, correctly-named metrics
    (visual_fact_recall vs. unsupported_visual_claim_absence).

    Stage 6A.2a item 1: the manifest's full structured shape -- fact_type/
    subject/relation/object/value/unit -- is preserved for BOTH
    visual_facts and unsupported_claims, not truncated to fact_id/raw_text
    or fact_id/claim. `_visual_fact_matches_claim` (Stage 6A.2 item 2)
    compares exactly these structured fields; truncating them here would
    silently make every real per-claim structural comparison compare
    against `None` for every field but fact_id, defeating that fix."""
    facts: dict[str, list[dict]] = {"picture": [], "visual_fact": [], "unsupported_claim": []}
    facts["picture"].append({"fact_id": f"{section['doc_id']}_PICTURE", "expected_picture_class": section.get("expected_picture_class")})
    for vf in section.get("visual_facts", []):
        facts["visual_fact"].append({
            "fact_id": vf["fact_id"], "fact_type": vf.get("fact_type"), "subject": vf.get("subject"),
            "relation": vf.get("relation"), "object": vf.get("object"), "value": vf.get("value"),
            "unit": vf.get("unit"), "raw_text": vf.get("raw_text"),
        })
    for uc in section.get("unsupported_claims", []):
        facts["unsupported_claim"].append({
            "fact_id": uc["fact_id"], "fact_type": uc.get("fact_type"), "subject": uc.get("subject"),
            "relation": uc.get("relation"), "object": uc.get("object"), "value": uc.get("value"),
            "unit": uc.get("unit"), "claim": uc.get("claim"), "is_supported": uc.get("is_supported"),
            "reason": uc.get("reason"),
        })
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
) -> tuple[dict[str, MetricResult], list[MissRecord], list[UnexpectedObservation], list[EvidenceAlignment], dict[str, TextElement]]:
    """text_fact_recall, text_fact_location_accuracy, no_unexpected_text_duplication.
    Returns a fact_id -> matched TextElement map too, reused by identifier
    occurrence resolution (Stage 6A.1 item 1)."""
    recall_acc = _MetricAcc("text_fact_recall", TEXT_NORMALIZED_CASE_FOLD_RULE)
    location_acc = _MetricAcc("text_fact_location_accuracy", "unit_index of the matched element == expected_location.unit_index (only facts declaring one)")
    miss_records: list[MissRecord] = []
    alignments: list[EvidenceAlignment] = []
    matched_by_fact_id: dict[str, TextElement] = {}

    for fact in text_facts:
        fact_type = "distractor_paragraph" if fact.get("is_distractor") else "paragraph"
        found = find_exact_text_matches(fact["text"], elements)
        if found:
            best = found[0]
            matched_by_fact_id[fact["fact_id"]] = best
            recall_acc.record_match(fact["fact_id"])
            expected_unit = _location_unit_index(fact.get("expected_location", {}))
            if expected_unit is not None:
                if best.unit_index == expected_unit:
                    location_acc.record_match(fact["fact_id"])
                else:
                    location_acc.record_miss(fact["fact_id"])
                    miss_records.append(MissRecord(
                        fixture=fixture, fact_id=fact["fact_id"], metric="text_fact_location_accuracy",
                        expected_value={"unit_index": expected_unit}, observed_value={"unit_index": best.unit_index}, result="partial",
                        failure_class="parser_structure_loss", confidence="certain",
                        explanation=f"{fact['fact_id']!r} matched text but at unit_index={best.unit_index}, expected {expected_unit}",
                        supporting_canonical_element_ids=[best.element_id],
                    ))
            alignments.append(_alignment(
                fact["fact_id"], fixture, fact_type, expected_value={"text": fact["text"]}, expected_location=fact.get("expected_location", {}),
                matched_element_ids=[e.element_id for e in found], matched_chunk_ids=sorted({cid for e in found for cid in chunk_map.get(e.element_id, [])}),
                match_status="matched", derivation="source_derived",
            ))
        else:
            recall_acc.record_miss(fact["fact_id"])
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
            alignments.append(_alignment(
                fact["fact_id"], fixture, fact_type, expected_value={"text": fact["text"]}, expected_location=fact.get("expected_location", {}),
                match_status="missing", derivation="not_applicable",
            ))

    # Stage 6A.1 item 6: renamed to a higher-is-better metric -- numerator
    # counts elements WITHOUT unexpected duplication.
    expected_norms = {normalize_text_for_comparison(f["text"]) for f in text_facts}
    matched_norms_seen: dict[str, int] = {}
    unexpected: list[UnexpectedObservation] = []
    checked = 0
    duplicated = 0
    for element in elements:
        if element.element_type == "ocr_annotation":
            continue
        checked += 1
        norm = normalize_text_for_comparison(element.text)
        if not norm:
            continue
        if norm in expected_norms:
            matched_norms_seen[norm] = matched_norms_seen.get(norm, 0) + 1
            if matched_norms_seen[norm] > 1:
                duplicated += 1
                unexpected.append(UnexpectedObservation(
                    fixture=fixture, element_id=element.element_id, element_type=element.element_type,
                    text=element.text, reason="duplicate occurrence of an expected fact's exact text beyond the manifest's declared occurrence count",
                ))
    duplication_metric = _metric(
        "no_unexpected_text_duplication",
        "count of canonical text elements whose normalized text does NOT repeat an already-matched expected fact (higher is better)",
        checked - duplicated, checked,
    )
    metrics = {"text_fact_recall": recall_acc.result(), "text_fact_location_accuracy": location_acc.result(), "no_unexpected_text_duplication": duplication_metric}
    return metrics, miss_records, unexpected, alignments, matched_by_fact_id


def _score_headings(
    fixture: str, heading_facts: list[dict], document: CanonicalDocument, elements: list[TextElement],
    chunk_map: dict[str, list[str]], raw_text_blob: list[tuple[str, str]] | None,
) -> tuple[dict[str, MetricResult], list[MissRecord], list[EvidenceAlignment], dict[str, TextElement]]:
    text_acc = _MetricAcc("heading_text_recall", TEXT_NORMALIZED_CASE_FOLD_RULE)
    level_acc = _MetricAcc("heading_level_accuracy", "of headings correctly classified as CanonicalHeading, exact level match")
    classification_acc = _MetricAcc("heading_classification_accuracy", "of headings whose text matched, fraction represented as CanonicalHeading (not degraded to CanonicalParagraph)")
    location_acc = _MetricAcc("heading_unit_location_accuracy", "unit_index of the matched element == expected_location.unit_index")
    miss_records: list[MissRecord] = []
    alignments: list[EvidenceAlignment] = []
    matched_by_fact_id: dict[str, TextElement] = {}
    canonical_headings_by_id = {h.block_id: h for h in document.headings}

    for fact in heading_facts:
        found = find_exact_text_matches(fact["text"], elements)
        if not found:
            text_acc.record_miss(fact["fact_id"])
            if raw_text_blob is not None:
                failure_class, confidence, raw_refs = classification.classify_text_absence(fact["text"], raw_text_blob)
            else:
                failure_class, confidence, raw_refs = classification.unresolved_classification("no raw debug artifact")
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="heading_text_recall",
                expected_value={"text": fact["text"]}, result="miss", failure_class=failure_class, confidence=confidence,
                explanation=f"expected heading text for {fact['fact_id']!r} not found in any canonical text element", raw_docling_references=raw_refs,
            ))
            alignments.append(_alignment(
                fact["fact_id"], fixture, "heading", expected_value={"text": fact["text"], "level": fact["level"]},
                expected_location=fact.get("expected_location", {}), match_status="missing", derivation="not_applicable",
            ))
            continue

        best = found[0]
        matched_by_fact_id[fact["fact_id"]] = best
        text_acc.record_match(fact["fact_id"])
        is_real_heading = best.element_id in canonical_headings_by_id

        expected_unit = _location_unit_index(fact.get("expected_location", {}))
        if expected_unit is not None:
            if best.unit_index == expected_unit:
                location_acc.record_match(fact["fact_id"])
            else:
                location_acc.record_miss(fact["fact_id"])
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=fact["fact_id"], metric="heading_unit_location_accuracy",
                    expected_value={"unit_index": expected_unit}, observed_value={"unit_index": best.unit_index}, result="partial",
                    failure_class="parser_structure_loss", confidence="certain",
                    explanation=f"heading {fact['fact_id']!r} matched text but at the wrong unit_index",
                    supporting_canonical_element_ids=[best.element_id],
                ))

        if is_real_heading:
            classification_acc.record_match(fact["fact_id"])
            actual_level = canonical_headings_by_id[best.element_id].level
            if actual_level == fact["level"]:
                level_acc.record_match(fact["fact_id"])
            else:
                level_acc.record_miss(fact["fact_id"])
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=fact["fact_id"], metric="heading_level_accuracy",
                    expected_value={"level": fact["level"]}, observed_value={"level": actual_level}, result="partial",
                    failure_class="parser_classification_loss", confidence="certain",
                    explanation=f"heading {fact['fact_id']!r} text matched but level {actual_level} != expected {fact['level']}",
                    supporting_canonical_element_ids=[best.element_id],
                ))
        else:
            classification_acc.record_miss(fact["fact_id"])
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="heading_classification_accuracy",
                expected_value={"as": "heading"}, observed_value={"as": best.element_type}, result="partial",
                failure_class="parser_classification_loss", confidence="certain",
                explanation=f"heading text for {fact['fact_id']!r} present but represented as {best.element_type}, not CanonicalHeading -- text present, heading classification missed",
                supporting_canonical_element_ids=[best.element_id],
            ))
        alignments.append(_alignment(
            fact["fact_id"], fixture, "heading", expected_value={"text": fact["text"], "level": fact["level"]},
            expected_location=fact.get("expected_location", {}), matched_element_ids=[best.element_id],
            matched_chunk_ids=sorted(chunk_map.get(best.element_id, [])), match_status="matched" if is_real_heading else "partial",
            derivation="source_derived",
        ))

    metrics = {
        "heading_text_recall": text_acc.result(), "heading_level_accuracy": level_acc.result(),
        "heading_classification_accuracy": classification_acc.result(), "heading_unit_location_accuracy": location_acc.result(),
    }
    return metrics, miss_records, alignments, matched_by_fact_id


def _select_best_table(expected_cells: dict[tuple[int, int], dict], document: CanonicalDocument):
    """Stage 6A.1 item 10: selects the table with MAXIMUM cell-text
    overlap across ALL candidate tables, never the first one exceeding a
    threshold -- deterministic tie-break by document order (table_id
    sorted, since tables are already emitted in reading order)."""
    expected_texts_norm = {normalize_text_for_comparison(c["text"]) for c in expected_cells.values()}
    best_table = None
    best_overlap = -1
    for table in document.tables:
        observed_texts_norm = {normalize_text_for_comparison(c.text) for c in table.cells}
        overlap = len(expected_texts_norm & observed_texts_norm)
        if overlap > best_overlap:
            best_overlap = overlap
            best_table = table
    if best_table is None or best_overlap <= 0:
        return None
    return best_table


def _score_tables(
    fixture: str, table_facts: list[dict], document: CanonicalDocument, chunk_map: dict[str, list[str]],
) -> tuple[dict[str, MetricResult], list[MissRecord], list[EvidenceAlignment]]:
    presence_acc = _MetricAcc("table_presence", "best deterministic cell-text-overlap table identification (max overlap across all candidates)")
    structure_acc = _MetricAcc("table_structure_accuracy", "exact n_rows/n_cols match, of tables identified")
    cell_text_acc = _MetricAcc("table_cell_text_recall", TEXT_NORMALIZED_CASE_FOLD_RULE)
    coord_acc = _MetricAcc("table_cell_coordinate_accuracy", "exact (row, col) match, of cells whose text was found")
    header_acc = _MetricAcc("table_header_status_accuracy", "is_header match, of cells whose text was found")
    span_acc = _MetricAcc("table_span_accuracy", "row_span/col_span exact match, of cells whose text was found")
    miss_records: list[MissRecord] = []
    alignments: list[EvidenceAlignment] = []

    for fact in table_facts:
        expected_cells = {(c["row"], c["col"]): c for c in fact["cells"]}
        candidate_table = _select_best_table(expected_cells, document)

        if candidate_table is None:
            presence_acc.record_miss(fact["fact_id"])
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="table_presence",
                expected_value={"n_rows": fact["n_rows"], "n_cols": fact["n_cols"]}, result="miss",
                failure_class="parser_structure_loss", confidence="supported",
                explanation=f"no CanonicalTable in this document has meaningful cell-text overlap with expected table {fact['fact_id']!r}",
            ))
            for (row, col), expected_cell in expected_cells.items():
                cell_fact_id = f"{fact['fact_id']}_r{row}c{col}"
                cell_text_acc.record_miss(cell_fact_id)
                # Stage 6A.2 item 3: every supporting_misses entry must
                # resolve to a real MissRecord with the SAME metric name
                # and fact_id -- a per-cell MissRecord is required here
                # too, not just the one table-level "table_presence" entry.
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=cell_fact_id, metric="table_cell_text_recall",
                    expected_value={"row": row, "col": col, "text": expected_cell["text"]}, result="miss",
                    failure_class="parser_structure_loss", confidence="supported",
                    explanation=f"no candidate table identified for {fact['fact_id']!r} -- cell (row={row}, col={col}) could not be scored",
                ))
                alignments.append(_alignment(
                    cell_fact_id, fixture, "table_cell", expected_value={"row": row, "col": col, "text": expected_cell["text"]},
                    match_status="missing", derivation="not_applicable",
                ))
            alignments.append(_alignment(
                fact["fact_id"], fixture, "table", expected_value={"n_rows": fact["n_rows"], "n_cols": fact["n_cols"]},
                expected_location=fact.get("expected_location", {}), match_status="missing", derivation="not_applicable",
            ))
            continue

        presence_acc.record_match(fact["fact_id"])
        if candidate_table.n_rows == fact["n_rows"] and candidate_table.n_cols == fact["n_cols"]:
            structure_acc.record_match(fact["fact_id"])
        else:
            structure_acc.record_miss(fact["fact_id"])
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="table_structure_accuracy",
                expected_value={"n_rows": fact["n_rows"], "n_cols": fact["n_cols"]},
                observed_value={"n_rows": candidate_table.n_rows, "n_cols": candidate_table.n_cols}, result="partial",
                failure_class="parser_structure_loss", confidence="certain",
                explanation=f"table {fact['fact_id']!r} dimension mismatch",
                supporting_canonical_element_ids=[candidate_table.table_id],
            ))

        # Stage 6A.1 item 10: one-to-one cell matching -- a consumed
        # observed cell (by identity) can never satisfy a second expected
        # cell, even if two expected cells share the same text value.
        consumed_cell_ids: set[int] = set()
        observed_by_text: dict[str, list] = {}
        for cell in candidate_table.cells:
            observed_by_text.setdefault(normalize_text_for_comparison(cell.text), []).append(cell)

        for (row, col), expected_cell in sorted(expected_cells.items()):
            cell_fact_id = f"{fact['fact_id']}_r{row}c{col}"
            norm = normalize_text_for_comparison(expected_cell["text"])
            candidates = [c for c in observed_by_text.get(norm, []) if id(c) not in consumed_cell_ids]
            if not candidates:
                cell_text_acc.record_miss(cell_fact_id)
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=cell_fact_id, metric="table_cell_text_recall",
                    expected_value={"row": row, "col": col, "text": expected_cell["text"]}, result="miss",
                    failure_class="parser_content_loss", confidence="supported",
                    explanation=f"table {fact['fact_id']!r} cell (row={row}, col={col}) text {expected_cell['text']!r} not found among unconsumed extracted cells",
                    supporting_canonical_element_ids=[candidate_table.table_id],
                ))
                alignments.append(_alignment(
                    cell_fact_id, fixture, "table_cell", expected_value={"row": row, "col": col, "text": expected_cell["text"]},
                    match_status="missing", derivation="not_applicable",
                ))
                continue

            exact = next((c for c in candidates if c.row == row and c.col == col), None)
            observed_cell = exact if exact is not None else candidates[0]
            consumed_cell_ids.add(id(observed_cell))
            cell_text_acc.record_match(cell_fact_id)

            coordinate_ok = observed_cell.row == row and observed_cell.col == col
            if coordinate_ok:
                coord_acc.record_match(cell_fact_id)
            else:
                coord_acc.record_miss(cell_fact_id)
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=cell_fact_id, metric="table_cell_coordinate_accuracy",
                    expected_value={"row": row, "col": col}, observed_value={"row": observed_cell.row, "col": observed_cell.col},
                    result="partial", failure_class="parser_structure_loss", confidence="certain",
                    explanation=f"table {fact['fact_id']!r}: cell text {expected_cell['text']!r} present but at the wrong row/col -- content match, coordinate miss",
                    supporting_canonical_element_ids=[candidate_table.table_id],
                ))

            expected_header = bool(expected_cell.get("is_header", False))
            if bool(observed_cell.is_header) == expected_header:
                header_acc.record_match(cell_fact_id)
            else:
                header_acc.record_miss(cell_fact_id)
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=cell_fact_id, metric="table_header_status_accuracy",
                    expected_value={"is_header": expected_header}, observed_value={"is_header": observed_cell.is_header},
                    result="partial", failure_class="parser_classification_loss", confidence="certain",
                    explanation=f"table {fact['fact_id']!r} cell (row={row}, col={col}) header-status mismatch",
                ))

            expected_row_span = int(expected_cell.get("row_span", 1))
            expected_col_span = int(expected_cell.get("col_span", 1))
            if observed_cell.row_span == expected_row_span and observed_cell.col_span == expected_col_span:
                span_acc.record_match(cell_fact_id)
            else:
                span_acc.record_miss(cell_fact_id)
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=cell_fact_id, metric="table_span_accuracy",
                    expected_value={"row_span": expected_row_span, "col_span": expected_col_span},
                    observed_value={"row_span": observed_cell.row_span, "col_span": observed_cell.col_span},
                    result="partial", failure_class="parser_structure_loss", confidence="certain",
                    explanation=f"table {fact['fact_id']!r} cell (row={row}, col={col}) span mismatch",
                ))

            # Stage 6A.1 item 10: one EvidenceAlignment PER expected cell.
            alignments.append(_alignment(
                cell_fact_id, fixture, "table_cell", expected_value={"row": row, "col": col, "text": expected_cell["text"]},
                matched_element_ids=[candidate_table.table_id], matched_chunk_ids=sorted(chunk_map.get(candidate_table.table_id, [])),
                match_status="matched" if coordinate_ok else "partial", derivation="source_derived",
            ))

        alignments.append(_alignment(
            fact["fact_id"], fixture, "table", expected_value={"n_rows": fact["n_rows"], "n_cols": fact["n_cols"]},
            expected_location=fact.get("expected_location", {}), matched_element_ids=[candidate_table.table_id],
            matched_chunk_ids=sorted(chunk_map.get(candidate_table.table_id, [])), match_status="matched", derivation="source_derived",
        ))

    metrics = {
        "table_presence": presence_acc.result(), "table_structure_accuracy": structure_acc.result(),
        "table_cell_text_recall": cell_text_acc.result(), "table_cell_coordinate_accuracy": coord_acc.result(),
        "table_header_status_accuracy": header_acc.result(), "table_span_accuracy": span_acc.result(),
    }
    return metrics, miss_records, alignments


def _score_pictures_captions(
    fixture: str, picture_facts: list[dict], caption_facts: list[dict], document: CanonicalDocument,
    chunk_map: dict[str, list[str]], raw_debug: dict[str, Any] | None,
) -> tuple[dict[str, MetricResult], list[MissRecord], list[EvidenceAlignment], dict[str, TextElement], list[str]]:
    presence_acc = _MetricAcc("picture_presence", "at least one CanonicalPicture present per expected picture fact")
    provenance_acc = _MetricAcc("picture_provenance_completeness", "matched picture has a ProvenanceEntry")
    location_acc = _MetricAcc("picture_unit_location_accuracy", "unit_index of the matched picture == expected_location.unit_index")
    artifact_acc = _MetricAcc("picture_artifact_completeness", "matched picture has a non-empty artifact_ref and a valid content_sha256")
    caption_text_acc = _MetricAcc("caption_text_recall", TEXT_NORMALIZED_CASE_FOLD_RULE + " -- matched against CanonicalCaption OR CanonicalParagraph text (text recovery is scored independently of caption-picture linkage)")
    caption_link_acc = _MetricAcc("caption_linkage_accuracy", "of captions whose text was found (as caption or paragraph), represented as a real CanonicalCaption with target_picture_id resolving to the expected picture")
    caption_location_acc = _MetricAcc("caption_unit_location_accuracy", "unit_index of the matched caption element == expected_location.unit_index")
    miss_records: list[MissRecord] = []
    alignments: list[EvidenceAlignment] = []
    matched_by_fact_id: dict[str, TextElement] = {}
    provenance_element_ids = {p.element_id for p in document.provenance}
    provenance_ref_by_element_id = {p.element_id: p.source_element_ref for p in document.provenance if p.source_element_ref}

    matched_picture_ids: list[str] = []
    for index, fact in enumerate(picture_facts):
        expected_unit = _location_unit_index(fact.get("expected_location", {}))
        if index < len(document.pictures):
            picture = document.pictures[index]
            matched_picture_ids.append(picture.picture_id)
            presence_acc.record_match(fact["fact_id"])

            has_provenance = picture.picture_id in provenance_element_ids
            if has_provenance:
                provenance_acc.record_match(fact["fact_id"])
            else:
                provenance_acc.record_miss(fact["fact_id"])
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=fact["fact_id"], metric="picture_provenance_completeness",
                    expected_value={"has_provenance": True}, observed_value={"has_provenance": False}, result="partial",
                    failure_class="parser_provenance_loss", confidence="certain",
                    explanation=f"picture {fact['fact_id']!r} extracted but has no ProvenanceEntry",
                ))

            if expected_unit is not None:
                if picture.unit_index == expected_unit:
                    location_acc.record_match(fact["fact_id"])
                else:
                    location_acc.record_miss(fact["fact_id"])
                    miss_records.append(MissRecord(
                        fixture=fixture, fact_id=fact["fact_id"], metric="picture_unit_location_accuracy",
                        expected_value={"unit_index": expected_unit}, observed_value={"unit_index": picture.unit_index}, result="partial",
                        failure_class="parser_structure_loss", confidence="certain",
                        explanation=f"picture {fact['fact_id']!r} at wrong unit_index",
                        supporting_canonical_element_ids=[picture.picture_id],
                    ))

            artifact_ok = bool(picture.artifact_ref) and bool(picture.content_sha256)
            if artifact_ok:
                artifact_acc.record_match(fact["fact_id"])
            else:
                artifact_acc.record_miss(fact["fact_id"])
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=fact["fact_id"], metric="picture_artifact_completeness",
                    expected_value={"artifact_ref_and_content_sha256": True}, observed_value={"artifact_ref": picture.artifact_ref, "content_sha256": picture.content_sha256},
                    result="partial", failure_class="parser_provenance_loss", confidence="certain",
                    explanation=f"picture {fact['fact_id']!r} missing artifact_ref or content_sha256",
                    supporting_canonical_element_ids=[picture.picture_id],
                ))

            alignments.append(_alignment(
                fact["fact_id"], fixture, "picture", expected_value={k: v for k, v in fact.items() if k != "fact_id"},
                expected_location=fact.get("expected_location", {}), matched_element_ids=[picture.picture_id],
                matched_chunk_ids=sorted(chunk_map.get(picture.picture_id, [])), match_status="matched", derivation="source_derived",
            ))
        else:
            presence_acc.record_miss(fact["fact_id"])
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="picture_presence",
                expected_value={"expected": True}, result="miss", failure_class="parser_content_loss", confidence="certain",
                explanation=f"expected picture {fact['fact_id']!r} not present in CanonicalDocument.pictures",
            ))
            alignments.append(_alignment(
                fact["fact_id"], fixture, "picture", expected_value={k: v for k, v in fact.items() if k != "fact_id"},
                expected_location=fact.get("expected_location", {}), match_status="missing", derivation="not_applicable",
            ))

    for fact in caption_facts:
        target_text = normalize_text_for_comparison(fact["text"])
        caption_matches = [c for c in document.captions if normalize_text_for_comparison(c.text) == target_text]
        paragraph_matches = [] if caption_matches else [p for p in document.paragraphs if normalize_text_for_comparison(p.text) == target_text]
        expected_unit = _location_unit_index(fact.get("expected_location", {}))

        if not caption_matches and not paragraph_matches:
            caption_text_acc.record_miss(fact["fact_id"])
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="caption_text_recall",
                expected_value={"text": fact["text"]}, result="miss", failure_class="parser_content_loss", confidence="supported",
                explanation=f"caption text for {fact['fact_id']!r} not found as any CanonicalCaption or CanonicalParagraph",
            ))
            alignments.append(_alignment(
                fact["fact_id"], fixture, "caption", expected_value={"text": fact["text"]},
                expected_location=fact.get("expected_location", {}), match_status="missing", derivation="not_applicable",
            ))
            continue

        caption_text_acc.record_match(fact["fact_id"])

        if caption_matches:
            caption = caption_matches[0]
            matched_by_fact_id[fact["fact_id"]] = TextElement(caption.block_id, caption.text, "caption", caption.unit_index)
            if expected_unit is not None:
                if caption.unit_index == expected_unit:
                    caption_location_acc.record_match(fact["fact_id"])
                else:
                    caption_location_acc.record_miss(fact["fact_id"])
                    miss_records.append(MissRecord(
                        fixture=fixture, fact_id=fact["fact_id"], metric="caption_unit_location_accuracy",
                        expected_value={"unit_index": expected_unit}, observed_value={"unit_index": caption.unit_index}, result="partial",
                        failure_class="parser_structure_loss", confidence="certain",
                        explanation=f"caption {fact['fact_id']!r} at wrong unit_index", supporting_canonical_element_ids=[caption.block_id],
                    ))
            if caption.target_picture_id in matched_picture_ids:
                caption_link_acc.record_match(fact["fact_id"])
                match_status = "matched"
            else:
                caption_link_acc.record_miss(fact["fact_id"])
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=fact["fact_id"], metric="caption_linkage_accuracy",
                    expected_value={"target_picture": fact.get("target_picture")}, observed_value={"target_picture_id": caption.target_picture_id}, result="partial",
                    failure_class="parser_relationship_loss", confidence="certain",
                    explanation=f"caption {fact['fact_id']!r} is a real CanonicalCaption but target_picture_id does not resolve to the expected picture",
                    supporting_canonical_element_ids=[caption.block_id],
                ))
                match_status = "partial"
            alignments.append(_alignment(
                fact["fact_id"], fixture, "caption", expected_value={"text": fact["text"]}, expected_location=fact.get("expected_location", {}),
                matched_element_ids=[caption.block_id], matched_chunk_ids=sorted(chunk_map.get(caption.block_id, [])),
                match_status=match_status, derivation="source_derived",
            ))
        else:
            # Stage 6A.1 item 4: caption text present as a plain paragraph
            # -- attribute the missing RELATIONSHIP by inspecting raw
            # Docling's own picture.captions list directly, never by mere
            # text self_ref presence.
            paragraph = paragraph_matches[0]
            matched_by_fact_id[fact["fact_id"]] = TextElement(paragraph.block_id, paragraph.text, "paragraph", paragraph.unit_index)
            caption_link_acc.record_miss(fact["fact_id"])
            failure_class, confidence, raw_refs = "parser_relationship_loss", "unresolved", []
            picture_self_ref = None
            paragraph_self_ref = provenance_ref_by_element_id.get(paragraph.block_id)
            if matched_picture_ids:
                picture_self_ref = provenance_ref_by_element_id.get(matched_picture_ids[0])
            if raw_debug is not None and picture_self_ref is not None:
                failure_class, confidence, raw_refs = classification.classify_relationship_absence(
                    raw_debug, parent_collection="pictures", parent_self_ref=picture_self_ref,
                    relation_field="captions", child_self_ref=paragraph_self_ref,
                )
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="caption_linkage_accuracy",
                expected_value={"text": fact["text"], "target_picture": fact.get("target_picture")}, observed_value={"as": "paragraph"}, result="partial",
                failure_class=failure_class, confidence=confidence,
                explanation=f"caption text for {fact['fact_id']!r} present as a plain CanonicalParagraph, not linked to its picture -- caption text present, caption relationship missed",
                supporting_canonical_element_ids=[paragraph.block_id], raw_docling_references=raw_refs,
            ))
            if expected_unit is not None:
                if paragraph.unit_index == expected_unit:
                    caption_location_acc.record_match(fact["fact_id"])
                else:
                    caption_location_acc.record_miss(fact["fact_id"])
                    miss_records.append(MissRecord(
                        fixture=fixture, fact_id=fact["fact_id"], metric="caption_unit_location_accuracy",
                        expected_value={"unit_index": expected_unit}, observed_value={"unit_index": paragraph.unit_index}, result="partial",
                        failure_class="parser_structure_loss", confidence="certain",
                        explanation=f"caption {fact['fact_id']!r} (present as paragraph) at wrong unit_index",
                        supporting_canonical_element_ids=[paragraph.block_id],
                    ))
            alignments.append(_alignment(
                fact["fact_id"], fixture, "caption", expected_value={"text": fact["text"]}, expected_location=fact.get("expected_location", {}),
                matched_element_ids=[paragraph.block_id], matched_chunk_ids=sorted(chunk_map.get(paragraph.block_id, [])),
                match_status="partial", derivation="source_derived",
            ))

    metrics = {
        "picture_presence": presence_acc.result(), "picture_provenance_completeness": provenance_acc.result(),
        "picture_unit_location_accuracy": location_acc.result(), "picture_artifact_completeness": artifact_acc.result(),
        "caption_text_recall": caption_text_acc.result(), "caption_linkage_accuracy": caption_link_acc.result(),
        "caption_unit_location_accuracy": caption_location_acc.result(),
    }
    return metrics, miss_records, alignments, matched_by_fact_id, matched_picture_ids


def _score_ocr_tokens(
    fixture: str, ocr_token_facts: list[dict], document: CanonicalDocument, chunk_map: dict[str, list[str]],
) -> tuple[dict[str, MetricResult], list[MissRecord], list[EvidenceAlignment]]:
    ocr_annotations = [a for a in document.annotations if a.annotation_type == "ocr"]
    provenance_by_id = {p.element_id: p for p in document.provenance}
    token_acc = _MetricAcc("picture_ocr_token_recall", OCR_PHRASE_MATCH_RULE)
    provenance_acc = _MetricAcc("ocr_provenance_completeness", "OcrAnnotation.annotation_id resolves to a ProvenanceEntry.element_id")
    miss_records: list[MissRecord] = []
    alignments: list[EvidenceAlignment] = []

    ordered_lines: list[tuple[str, int | None]] = []
    for a in ocr_annotations:
        prov = provenance_by_id.get(a.annotation_id)
        seq = (prov.source_locator or {}).get("ocr_sequence") if prov and prov.source_locator else None
        ordered_lines.append((a.text, seq))

    for fact in ocr_token_facts:
        if ocr_phrase_recovered(fact["text"], ordered_lines):
            token_acc.record_match(fact["fact_id"])
            matches_annotations = [a for a in ocr_annotations if normalize_text_for_comparison(fact["text"]) in normalize_text_for_comparison(a.text)]
            annotation_ids = [a.annotation_id for a in matches_annotations] or [a.annotation_id for a in ocr_annotations]
            alignments.append(_alignment(
                fact["fact_id"], fixture, "ocr_token", expected_value={"text": fact["text"]},
                matched_annotation_ids=annotation_ids, matched_chunk_ids=sorted({cid for aid in annotation_ids for cid in chunk_map.get(aid, [])}),
                match_status="matched", derivation="source_derived",
            ))
        else:
            token_acc.record_miss(fact["fact_id"])
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="picture_ocr_token_recall",
                expected_value={"text": fact["text"]}, result="miss", failure_class="parser_content_loss", confidence="supported",
                explanation=f"expected OCR phrase {fact['text']!r} not recovered (single-line or adjacent-fragment containment) among extracted OcrAnnotation text",
            ))
            alignments.append(_alignment(
                fact["fact_id"], fixture, "ocr_token", expected_value={"text": fact["text"]}, match_status="missing", derivation="not_applicable",
            ))

    for a in ocr_annotations:
        if a.annotation_id in provenance_by_id:
            provenance_acc.record_match(a.annotation_id)
        else:
            provenance_acc.record_miss(a.annotation_id)
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=a.annotation_id, metric="ocr_provenance_completeness",
                expected_value={"has_provenance": True}, observed_value={"has_provenance": False}, result="partial",
                failure_class="parser_provenance_loss", confidence="certain",
                explanation=f"OcrAnnotation {a.annotation_id!r} has no matching ProvenanceEntry",
            ))

    metrics = {"picture_ocr_token_recall": token_acc.result(), "ocr_provenance_completeness": provenance_acc.result()}
    return metrics, miss_records, alignments


def _score_whole_page_ocr(
    fixture: str, facts: list[dict], document: CanonicalDocument, chunk_map: dict[str, list[str]],
) -> tuple[MetricResult, list[MissRecord], list[EvidenceAlignment]]:
    elements = flatten_text_elements(document)
    acc = _MetricAcc("whole_page_ocr_text_recall", TEXT_NORMALIZED_CASE_FOLD_RULE + " -- scored as text recovery, independent of OCR-origin classification (Stage 5A maps whole-page OCR as a plain paragraph, per D-035)")
    miss_records: list[MissRecord] = []
    alignments: list[EvidenceAlignment] = []
    for fact in facts:
        found = find_exact_text_matches(fact["text"], elements)
        if found:
            acc.record_match(fact["fact_id"])
            alignments.append(_alignment(
                fact["fact_id"], fixture, "whole_page_ocr_text", expected_value={"text": fact["text"]},
                matched_element_ids=[found[0].element_id], matched_chunk_ids=sorted(chunk_map.get(found[0].element_id, [])),
                match_status="matched", derivation="source_derived",
            ))
        else:
            acc.record_miss(fact["fact_id"])
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="whole_page_ocr_text_recall",
                expected_value={"text": fact["text"]}, result="miss", failure_class="parser_content_loss", confidence="supported",
                explanation="expected whole-page OCR text not found as any canonical text element",
            ))
            alignments.append(_alignment(
                fact["fact_id"], fixture, "whole_page_ocr_text", expected_value={"text": fact["text"]}, match_status="missing", derivation="not_applicable",
            ))
    return acc.result(), miss_records, alignments


def _score_list_items(
    fixture: str, facts: list[dict], document: CanonicalDocument, chunk_map: dict[str, list[str]],
) -> tuple[dict[str, MetricResult], list[MissRecord], list[EvidenceAlignment]]:
    by_text = {normalize_text_for_comparison(li.text): li for li in document.list_items}
    recall_acc = _MetricAcc("list_item_recall", TEXT_NORMALIZED_CASE_FOLD_RULE)
    indent_acc = _MetricAcc("list_indentation_accuracy", "exact indent_level match, of list items whose text matched")
    parent_acc = _MetricAcc("list_parent_link_accuracy", "parent_block_id resolves to the expected parent list item, of items declaring a parent")
    miss_records: list[MissRecord] = []
    alignments: list[EvidenceAlignment] = []
    matched_block_id_by_fact_id: dict[str, str] = {}

    for fact in facts:
        norm = normalize_text_for_comparison(fact["text"])
        item = by_text.get(norm)
        if item is None:
            recall_acc.record_miss(fact["fact_id"])
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="list_item_recall",
                expected_value={"text": fact["text"]}, result="miss", failure_class="parser_content_loss", confidence="supported",
                explanation=f"expected list item text for {fact['fact_id']!r} not found among CanonicalListItem",
            ))
            alignments.append(_alignment(fact["fact_id"], fixture, "list_item", expected_value={"text": fact["text"]}, match_status="missing", derivation="not_applicable"))
            continue

        recall_acc.record_match(fact["fact_id"])
        matched_block_id_by_fact_id[fact["fact_id"]] = item.block_id
        indent_ok = item.indent_level == fact["indent_level"]
        if indent_ok:
            indent_acc.record_match(fact["fact_id"])
        else:
            indent_acc.record_miss(fact["fact_id"])
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="list_indentation_accuracy",
                expected_value={"indent_level": fact["indent_level"]}, observed_value={"indent_level": item.indent_level}, result="partial",
                failure_class="parser_structure_loss", confidence="certain",
                explanation=f"list item {fact['fact_id']!r} text matched but indent_level {item.indent_level} != expected {fact['indent_level']}",
                supporting_canonical_element_ids=[item.block_id],
            ))
        alignments.append(_alignment(
            fact["fact_id"], fixture, "list_item", expected_value={"text": fact["text"], "indent_level": fact["indent_level"]},
            matched_element_ids=[item.block_id], matched_chunk_ids=sorted(chunk_map.get(item.block_id, [])),
            match_status="matched" if indent_ok else "partial", derivation="source_derived",
        ))

    for fact in facts:
        expected_parent_fact_id = fact.get("parent")
        if expected_parent_fact_id is None:
            continue
        item_block_id = matched_block_id_by_fact_id.get(fact["fact_id"])
        expected_parent_block_id = matched_block_id_by_fact_id.get(expected_parent_fact_id)
        item = next((li for li in document.list_items if li.block_id == item_block_id), None)
        if item is not None and expected_parent_block_id is not None and item.parent_block_id == expected_parent_block_id:
            parent_acc.record_match(fact["fact_id"])
        else:
            parent_acc.record_miss(fact["fact_id"])
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="list_parent_link_accuracy",
                expected_value={"parent": expected_parent_fact_id}, observed_value={"parent_block_id": item.parent_block_id if item else None}, result="partial",
                failure_class="parser_relationship_loss", confidence="certain",
                explanation=f"list item {fact['fact_id']!r} does not carry the expected parent_block_id linkage to {expected_parent_fact_id!r}",
            ))

    metrics = {"list_item_recall": recall_acc.result(), "list_indentation_accuracy": indent_acc.result(), "list_parent_link_accuracy": parent_acc.result()}
    return metrics, miss_records, alignments


def _visual_fact_matches_claim(annotation: Any, claim: dict) -> bool:
    """Stage 6A.2 item 2: structured equality between ONE manifest claim
    (an unsupported_claim or a visual_fact entry -- both share the same
    fact_type/subject/relation/object/value/unit shape) and ONE actual
    VisualFactAnnotation. Never a blanket 'any VisualFactAnnotation
    exists' check -- a correct visual fact asserting a DIFFERENT claim
    must never match here."""
    if annotation.fact_type != claim.get("fact_type"):
        return False
    if normalize_text_for_comparison(annotation.subject) != normalize_text_for_comparison(str(claim.get("subject", ""))):
        return False
    if normalize_text_for_comparison(annotation.relation) != normalize_text_for_comparison(str(claim.get("relation", ""))):
        return False

    expected_object = claim.get("object")
    if (annotation.object is None) != (expected_object is None):
        return False
    if annotation.object is not None and expected_object is not None:
        if normalize_text_for_comparison(annotation.object) != normalize_text_for_comparison(str(expected_object)):
            return False

    expected_value = claim.get("value")
    if (annotation.value is None) != (expected_value is None):
        return False
    if annotation.value is not None and expected_value is not None:
        try:
            if float(annotation.value) != float(expected_value):
                return False
        except (TypeError, ValueError):
            if normalize_text_for_comparison(str(annotation.value)) != normalize_text_for_comparison(str(expected_value)):
                return False

    expected_unit = claim.get("unit")
    if (annotation.unit is None) != (expected_unit is None):
        return False
    if annotation.unit is not None and expected_unit is not None:
        if normalize_text_for_comparison(annotation.unit) != normalize_text_for_comparison(str(expected_unit)):
            return False
    return True


def _score_visual_facts_and_unsupported_claims(
    fixture: str, visual_facts: list[dict], unsupported_claims: list[dict], document: CanonicalDocument,
) -> tuple[dict[str, MetricResult], list[MissRecord], list[EvidenceAlignment]]:
    """Stage 6A.1 item 7: scored, and catalogued, SEPARATELY. Path A never
    produces VisualFactAnnotation -- visual_fact_recall is structurally
    not_applicable (excluded, never scored as 0%).

    Stage 6A.2 item 2: unsupported_visual_claim_absence is scored PER
    CLAIM -- each unsupported claim's own structured content
    (fact_type/subject/relation/object/value/unit) is matched against
    actual VisualFactAnnotation output via `_visual_fact_matches_claim`.
    A correct, DIFFERENT visual fact being present must never trigger
    failure for an unrelated unsupported claim -- only a structural match
    of THAT claim's own content counts as a failure."""
    alignments: list[EvidenceAlignment] = []
    miss_records: list[MissRecord] = []
    visual_fact_metric = _metric(
        "visual_fact_recall", "VisualFactAnnotation recovery -- structurally not_applicable to path A (no VisionEnricher, Stage 5A never produces VisualFactAnnotation)",
        0, 0, excluded=len(visual_facts),
    )
    for vf in visual_facts:
        # Stage 6A.2a item 2: the full structured fact (fact_type/subject/
        # relation/object/value/unit/raw_text), not only raw_text -- this
        # catalog is the future source for expected-visual-fact/forbidden-
        # answer-claim definitions in retrieval/answer evaluation.
        alignments.append(_alignment(vf["fact_id"], fixture, "visual_fact", expected_value={k: v for k, v in vf.items() if k != "fact_id"}, match_status="not_applicable", derivation="not_applicable"))

    visual_fact_annotations = [a for a in document.annotations if a.annotation_type == "visual_fact"]
    unsupported_acc = _MetricAcc(
        "unsupported_visual_claim_absence",
        "per-claim structural match (fact_type/subject/relation/object/value/unit) of each manifest unsupported_claim "
        "against actual VisualFactAnnotation output -- never inferred from the mere presence of any OTHER visual fact "
        "(Stage 6A.2 item 2)",
    )
    for uc in unsupported_claims:
        asserted = [a for a in visual_fact_annotations if _visual_fact_matches_claim(a, uc)]
        # An "unsupported claim" fact is an ABSENCE check, not a presence
        # check -- when Stage 5A correctly never asserts THIS SPECIFIC
        # claim, there is no canonical element to point evidence at
        # (nothing was extracted, by design), so match_status=
        # "not_applicable" (never "matched", which would wrongly imply
        # real supporting evidence exists and would trip the chunk-
        # availability sweep, item 9, into demanding a chunk for a fact
        # that was never meant to be ingested). "missing" is reserved for
        # the genuine failure case: Stage 5A DID structurally assert this
        # exact claim (the EvidenceAlignment validator forbids evidence
        # ids on a "missing" entry, so the asserting annotation id is
        # recorded on the MissRecord instead).
        # Stage 6A.2a item 2: the full structured claim (fact_type/subject/
        # relation/object/value/unit/claim/is_supported/reason), not only
        # the prose `claim` string -- this catalog is the future source
        # for forbidden-answer-claim definitions in retrieval/answer
        # evaluation.
        structured_expected_value = {k: v for k, v in uc.items() if k != "fact_id"}
        if asserted:
            unsupported_acc.record_miss(uc["fact_id"])
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=uc["fact_id"], metric="unsupported_visual_claim_absence",
                expected_value={**structured_expected_value, "should_be_asserted": False},
                observed_value={"asserted": True}, result="unexpected",
                failure_class="unexpected_content", confidence="certain",
                explanation=f"unsupported claim {uc['fact_id']!r} ({uc.get('claim')!r}) was structurally asserted by a "
                            f"VisualFactAnnotation matching its own subject/relation/object/value/unit",
                supporting_canonical_element_ids=[a.annotation_id for a in asserted],
            ))
            alignments.append(_alignment(uc["fact_id"], fixture, "unsupported_claim", expected_value=structured_expected_value, match_status="missing", derivation="model_derived"))
        else:
            unsupported_acc.record_match(uc["fact_id"])
            alignments.append(_alignment(uc["fact_id"], fixture, "unsupported_claim", expected_value=structured_expected_value, match_status="not_applicable", derivation="not_applicable"))

    metrics = {}
    if visual_facts:
        metrics["visual_fact_recall"] = visual_fact_metric
    if unsupported_claims:
        metrics["unsupported_visual_claim_absence"] = unsupported_acc.result()
    return metrics, miss_records, alignments


def _score_provenance(fixture: str, document: CanonicalDocument) -> tuple[dict[str, MetricResult], list[MissRecord]]:
    provenance_by_id = {p.element_id: p for p in document.provenance}
    categories: dict[str, list[str]] = {
        "heading": [h.block_id for h in document.headings],
        "paragraph": [p.block_id for p in document.paragraphs],
        "list_item": [li.block_id for li in document.list_items],
        "table": [t.table_id for t in document.tables],
        "picture": [p.picture_id for p in document.pictures],
        "caption": [c.block_id for c in document.captions],
        "annotation": [a.annotation_id for a in document.annotations],
    }
    metrics: dict[str, MetricResult] = {}
    miss_records: list[MissRecord] = []
    total_num = total_den = 0
    bbox_total_num = bbox_total_den = 0
    all_cov_matches: list[str] = []
    all_bbox_matches: list[str] = []
    for category, element_ids in categories.items():
        cov_acc = _MetricAcc(f"provenance_coverage_{category}", "element_id present as a ProvenanceEntry.element_id")
        bbox_acc = _MetricAcc(f"provenance_bbox_coverage_{category}", "has a ProvenanceEntry AND that entry's bbox is not None (bbox absence is not treated as total provenance absence)")
        for element_id in element_ids:
            entry = provenance_by_id.get(element_id)
            if entry is not None:
                cov_acc.record_match(element_id)
            else:
                cov_acc.record_miss(element_id)
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=element_id, metric=f"provenance_coverage_{category}",
                    expected_value={"has_provenance": True}, observed_value={"has_provenance": False}, result="partial",
                    failure_class="parser_provenance_loss", confidence="certain",
                    explanation=f"{category} {element_id!r} has no ProvenanceEntry at all",
                ))
            if entry is not None and entry.bbox is not None:
                bbox_acc.record_match(element_id)
            else:
                bbox_acc.record_miss(element_id)
                if entry is not None:
                    miss_records.append(MissRecord(
                        fixture=fixture, fact_id=element_id, metric=f"provenance_bbox_coverage_{category}",
                        expected_value={"has_bbox": True}, observed_value={"has_bbox": False}, result="partial",
                        failure_class="parser_provenance_loss", confidence="certain",
                        explanation=f"{category} {element_id!r} has a ProvenanceEntry but no bbox",
                    ))
        metrics[f"provenance_coverage_{category}"] = cov_acc.result()
        metrics[f"provenance_bbox_coverage_{category}"] = bbox_acc.result()
        total_num += cov_acc.numerator
        total_den += cov_acc.denominator
        bbox_total_num += bbox_acc.numerator
        bbox_total_den += bbox_acc.denominator
        all_cov_matches += cov_acc.matches
        all_bbox_matches += bbox_acc.matches
    # Stage 6A.2 item 3: supporting_misses on the OVERALL rollup metrics
    # must resolve to a real MissRecord with the SAME metric name -- the
    # per-category MissRecords above carry metric=f"provenance_coverage_
    # {category}", never "provenance_coverage_overall", so they can never
    # legitimately appear in this metric's own supporting_misses. The
    # overall metric instead references only its own single summary
    # MissRecord (created below), by that record's own fact_id.
    metrics["provenance_coverage_overall"] = _metric(
        "provenance_coverage_overall", "element_id present as a ProvenanceEntry.element_id, across every element category",
        total_num, total_den, matches=all_cov_matches,
        misses=["provenance_coverage_overall"] if total_num < total_den else [],
    )
    metrics["provenance_bbox_coverage_overall"] = _metric(
        "provenance_bbox_coverage_overall", "has a ProvenanceEntry with a non-None bbox, across every element category",
        bbox_total_num, bbox_total_den, matches=all_bbox_matches,
        misses=["provenance_bbox_coverage_overall"] if bbox_total_num < bbox_total_den else [],
    )
    # Stage 6A.1 item 5: the "overall" rollups are sums of the per-category
    # accumulators above (which already have their own per-element
    # MissRecords) -- but the exhaustiveness contract is per METRIC NAME,
    # so a deficit in the overall metric also gets its own single summary
    # MissRecord, distinct from (and referencing) the constituent
    # per-category ones, rather than requiring a reader to infer it.
    if total_num < total_den:
        miss_records.append(MissRecord(
            fixture=fixture, fact_id="provenance_coverage_overall", metric="provenance_coverage_overall",
            expected_value={"covered": total_den}, observed_value={"covered": total_num}, result="partial",
            failure_class="parser_provenance_loss", confidence="certain",
            explanation=f"{total_den - total_num} of {total_den} canonical elements have no ProvenanceEntry at all, across every category",
        ))
    if bbox_total_num < bbox_total_den:
        miss_records.append(MissRecord(
            fixture=fixture, fact_id="provenance_bbox_coverage_overall", metric="provenance_bbox_coverage_overall",
            expected_value={"covered": bbox_total_den}, observed_value={"covered": bbox_total_num}, result="partial",
            failure_class="parser_provenance_loss", confidence="certain",
            explanation=f"{bbox_total_den - bbox_total_num} of {bbox_total_den} canonical elements have no bbox-carrying ProvenanceEntry, across every category",
        ))
    return metrics, miss_records


def _score_structural_stress(
    fixture: str, suite_key: str, facts: dict[str, list[dict]], document: CanonicalDocument, chunk_map: dict[str, list[str]],
) -> tuple[dict[str, MetricResult], list[MissRecord], list[EvidenceAlignment]]:
    metrics: dict[str, MetricResult] = {}
    miss_records: list[MissRecord] = []
    alignments: list[EvidenceAlignment] = []
    elements = flatten_text_elements(document)

    if suite_key == "stress_pdf" and facts.get("paragraph"):
        # NOTE: stress_pdf's "paragraph" facts (SP_001/SP_002) are already
        # scored -- and already get an EvidenceAlignment each -- via the
        # generic _score_text_facts pass (evaluate_fixture calls it
        # whenever facts.get("paragraph") is truthy, which it is here).
        # column_text_retention is a distinct, additionally-useful metric
        # NAME over the same underlying matches, but must never emit a
        # second EvidenceAlignment for the same fact_id (would violate the
        # per-fixture fact_id uniqueness invariant).
        retention_acc = _MetricAcc("column_text_retention", TEXT_NORMALIZED_CASE_FOLD_RULE)
        by_fact: dict[str, TextElement] = {}
        for fact in facts["paragraph"]:
            found = find_exact_text_matches(fact["text"], elements)
            if found:
                by_fact[fact["fact_id"]] = found[0]
                retention_acc.record_match(fact["fact_id"])
            else:
                retention_acc.record_miss(fact["fact_id"])
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=fact["fact_id"], metric="column_text_retention",
                    expected_value={"text": fact["text"]}, result="miss", failure_class="parser_content_loss", confidence="supported",
                    explanation="expected column text not retained",
                ))
        metrics["column_text_retention"] = retention_acc.result()

        ordered_ids = sorted(facts["paragraph"], key=lambda f: f["column"])
        if len(ordered_ids) == 2 and all(f["fact_id"] in by_fact for f in ordered_ids):
            first, second = ordered_ids
            para_order = {p.block_id: p.order_index for p in document.paragraphs}
            first_order = para_order.get(by_fact[first["fact_id"]].element_id)
            second_order = para_order.get(by_fact[second["fact_id"]].element_id)
            correct = first_order is not None and second_order is not None and first_order < second_order
            metrics["column_reading_order_correct"] = _metric(
                "column_reading_order_correct", "column-1 paragraph's order_index < column-2 paragraph's order_index",
                1 if correct else 0, 1, misses=[] if correct else ["STRESS_PDF_001_reading_order"],
            )
            if not correct:
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id="STRESS_PDF_001_reading_order", metric="column_reading_order_correct",
                    expected_value={"column_1_before_column_2": True}, result="miss", failure_class="parser_structure_loss", confidence="certain",
                    explanation="column-1 text does not precede column-2 text in reading order",
                ))

    if suite_key == "stress_pptx_overlap" and facts.get("text_box"):
        retention_acc = _MetricAcc("overlap_both_retained", TEXT_NORMALIZED_CASE_FOLD_RULE)
        by_fact: dict[str, TextElement] = {}
        for fact in facts["text_box"]:
            found = find_exact_text_matches(fact["text"], elements)
            if found:
                by_fact[fact["fact_id"]] = found[0]
                retention_acc.record_match(fact["fact_id"])
                alignments.append(_alignment(
                    fact["fact_id"], fixture, "text_box", expected_value={"text": fact["text"], "z_order": fact["z_order"]},
                    matched_element_ids=[found[0].element_id], matched_chunk_ids=sorted(chunk_map.get(found[0].element_id, [])),
                    match_status="matched", derivation="source_derived",
                ))
            else:
                retention_acc.record_miss(fact["fact_id"])
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=fact["fact_id"], metric="overlap_both_retained",
                    expected_value={"text": fact["text"]}, result="miss", failure_class="parser_content_loss", confidence="supported",
                    explanation="expected overlapping text box not retained",
                ))
                alignments.append(_alignment(
                    fact["fact_id"], fixture, "text_box", expected_value={"text": fact["text"], "z_order": fact["z_order"]},
                    match_status="missing", derivation="not_applicable",
                ))
        metrics["overlap_both_retained"] = retention_acc.result()

        provenance_by_id = {p.element_id: p for p in document.provenance}
        z_order_acc = _MetricAcc("overlap_z_order_recorded", "matched text box has a non-None ProvenanceEntry.z_order (Stage 5A/Docling does not currently expose PPTX shape z-order)")
        for fact_id, element in by_fact.items():
            entry = provenance_by_id.get(element.element_id)
            if entry is not None and entry.z_order is not None:
                z_order_acc.record_match(fact_id)
            else:
                z_order_acc.record_miss(fact_id)
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=fact_id, metric="overlap_z_order_recorded",
                    expected_value={"has_z_order": True}, observed_value={"has_z_order": False}, result="partial",
                    failure_class="parser_provenance_loss", confidence="certain",
                    explanation=f"text box {fact_id!r} matched but its ProvenanceEntry carries no z_order",
                    supporting_canonical_element_ids=[element.element_id],
                ))
        metrics["overlap_z_order_recorded"] = z_order_acc.result()

    if suite_key == "stress_pptx_diagram":
        node_facts = facts.get("diagram_node", [])
        label_acc = _MetricAcc("diagram_label_recall", TEXT_NORMALIZED_CASE_FOLD_RULE)
        for fact in node_facts:
            found = find_exact_text_matches(fact["label"], elements)
            if found:
                label_acc.record_match(fact["fact_id"])
                alignments.append(_alignment(
                    fact["fact_id"], fixture, "diagram_node_label", expected_value={"label": fact["label"]},
                    matched_element_ids=[found[0].element_id], matched_chunk_ids=sorted(chunk_map.get(found[0].element_id, [])),
                    match_status="matched", derivation="source_derived",
                ))
            else:
                label_acc.record_miss(fact["fact_id"])
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=fact["fact_id"], metric="diagram_label_recall",
                    expected_value={"label": fact["label"]}, result="miss", failure_class="parser_content_loss", confidence="supported",
                    explanation="expected native-diagram node label not found as any canonical text element",
                ))
                alignments.append(_alignment(fact["fact_id"], fixture, "diagram_node_label", expected_value={"label": fact["label"]}, match_status="missing", derivation="not_applicable"))
        metrics["diagram_label_recall"] = label_acc.result()

        no_diagram_annotation = not any(a.annotation_type in ("diagram_node", "diagram_edge") for a in document.annotations)
        metrics["no_invented_diagram_relationships"] = _metric(
            "no_invented_diagram_relationships", "Stage 5A must never produce DiagramNode/EdgeAnnotation (no VisionEnricher exists) -- verifies zero such annotations exist",
            1 if no_diagram_annotation else 0, 1,
            misses=[] if no_diagram_annotation else [f"{suite_key}_invented_diagram_annotation"],
        )
        if not no_diagram_annotation:
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=f"{suite_key}_invented_diagram_annotation", metric="no_invented_diagram_relationships",
                expected_value={"diagram_node_or_edge_annotation_count": 0}, result="unexpected",
                failure_class="unexpected_content", confidence="certain",
                explanation="Stage 5A path A produced a DiagramNode/EdgeAnnotation despite having no VisionEnricher -- an invented relationship never derivable from raw Docling structure alone",
            ))
        edge_facts = facts.get("diagram_edge", [])
        metrics["diagram_edge_recovery"] = _metric(
            "diagram_edge_recovery", "DiagramEdgeAnnotation recovery -- structurally not_applicable to path A (no VisionEnricher; Docling's native PPTX backend does not expose connector source/target linkage to this mapper)",
            0, 0, excluded=len(edge_facts),
        )
        for fact in edge_facts:
            alignments.append(_alignment(fact["fact_id"], fixture, "diagram_edge", expected_value={"source": fact["source"], "target": fact["target"]}, match_status="not_applicable", derivation="not_applicable"))

    return metrics, miss_records, alignments


# --- identifier occurrence-aware scoring (Stage 6A.1 item 1) ---------------


def _resolve_source_fact_element(
    source_fact_id: str | None, matched_element_by_fact_id: dict[str, TextElement],
) -> TextElement | None:
    if source_fact_id is None:
        return None
    return matched_element_by_fact_id.get(source_fact_id)


def _scoped_raw_items_for_occurrence(
    source_fact_id: str | None, *, matched_element_by_fact_id: dict[str, TextElement],
    source_ref_by_id: dict[str, str], fact_text_by_id: dict[str, str],
    raw_text_blob: list[tuple[str, str]] | None, raw_debug: dict[str, Any] | None,
    matched_picture_ids: list[str],
) -> list[tuple[str, str]] | None:
    """Stage 6A.2 item 1: resolves the raw Docling item(s) relevant to ONE
    identifier occurrence's OWN expected context only -- never the whole-
    document raw text blob (a raw occurrence elsewhere in the document
    must never prove mapper_loss for a different missing occurrence).

    - paragraph/heading/caption source_fact whose element WAS matched in
      CanonicalDocument: the single raw item at that element's own
      source_element_ref.
    - paragraph/heading/caption source_fact whose element was NOT matched
      at all: raw items whose text equals that source fact's own expected
      text (content-identified, since there is no canonical self_ref to
      resolve from).
    - visual node / OCR source_fact (`VF_NODE_*`/`DN_*`): raw items that
      are children of the matched picture(s) (raw `texts[].parent.$ref`
      pointing at the picture's own self_ref) -- Docling's own picture-
      child OCR text, never any other text in the document.

    Returns None when the context itself could not be resolved in raw
    Docling at all (unresolved); an empty list means the context WAS
    resolved but no raw item exists there (parser_content_loss, once
    searched by the caller)."""
    if source_fact_id is None or raw_debug is None:
        return None

    if source_fact_id.startswith("VF_NODE") or source_fact_id.startswith("DN_"):
        picture_self_refs = {source_ref_by_id[pid] for pid in matched_picture_ids if pid in source_ref_by_id}
        if not picture_self_refs:
            return None
        return [
            (item.get("self_ref", "#/texts/?"), item.get("text", ""))
            for item in raw_debug.get("texts", []) or []
            if (item.get("parent") or {}).get("$ref") in picture_self_refs and item.get("text")
        ]

    resolved = matched_element_by_fact_id.get(source_fact_id)
    if resolved is not None:
        self_ref = source_ref_by_id.get(resolved.element_id)
        if self_ref is None:
            return None
        for item in raw_debug.get("texts", []) or []:
            if item.get("self_ref") == self_ref:
                return [(self_ref, item.get("text", ""))] if item.get("text") else []
        return None

    expected_text = fact_text_by_id.get(source_fact_id)
    if expected_text is None or raw_text_blob is None:
        return None
    target = normalize_text_for_comparison(expected_text)
    return [(ref, text) for ref, text in raw_text_blob if normalize_text_for_comparison(text) == target]


def _score_identifiers(
    fixture: str, target_facts: list[dict], distractor_facts: list[dict], elements: list[TextElement],
    chunk_map: dict[str, list[str]], matched_element_by_fact_id: dict[str, TextElement],
    picture_ocr_annotations: list, raw_text_blob: list[tuple[str, str]] | None,
    fact_expected_location_by_id: dict[str, dict] | None = None, *,
    raw_debug: dict[str, Any] | None = None, source_ref_by_id: dict[str, str] | None = None,
    fact_text_by_id: dict[str, str] | None = None, matched_picture_ids: list[str] | None = None,
) -> tuple[dict[str, MetricResult], list[MissRecord], list[UnexpectedObservation], list[EvidenceAlignment]]:
    """Stage 6A.1 item 1: every manifest occurrence is its own expectation
    (`<identifier_fact_id>_occ_<index>`), matched ONE-TO-ONE against the
    specific canonical element its `source_fact` resolves to -- never a
    globally-counted-then-capped total. One observed occurrence can never
    satisfy two expected occurrences (spans are consumed once).

    Stage 6A.2 item 1: miss ATTRIBUTION for a missing occurrence is also
    scoped to that occurrence's own expected context (via
    `_scoped_raw_items_for_occurrence`) -- never a whole-document raw-text
    search, so an identifier appearing elsewhere in the document can never
    manufacture a false mapper_loss for this occurrence."""
    source_ref_by_id = source_ref_by_id or {}
    fact_text_by_id = fact_text_by_id or {}
    matched_picture_ids = matched_picture_ids or []
    unique_acc = _MetricAcc("identifier_unique_recall", IDENTIFIER_MATCH_RULE)
    occurrence_acc = _MetricAcc("identifier_occurrence_recall", IDENTIFIER_MATCH_RULE + " -- occurrence-level, one-to-one against the occurrence's own source_fact location, never globally counted-and-capped (Stage 6A.1 item 1)")
    occ_location_acc = _MetricAcc("identifier_occurrence_location_accuracy", "the resolved source_fact element's unit_index matches that source fact's own expected_location.unit_index (only occurrences whose source resolves and declares a location)")
    no_false_merge_acc = _MetricAcc("identifier_distractor_no_false_merge", IDENTIFIER_MATCH_RULE + " -- verifies a distractor identifier's occurrences are never counted toward a target identifier's occurrence tally")

    miss_records: list[MissRecord] = []
    alignments: list[EvidenceAlignment] = []
    unexpected: list[UnexpectedObservation] = []
    fact_expected_location_by_id = fact_expected_location_by_id or {}
    # (element_id or "ocr:<annotation_id>") -> set of consumed span starts
    consumed_spans: dict[str, set[int]] = {}

    def _try_consume(identifier: str, element_id: str, text: str) -> tuple[bool, int | None]:
        spans = find_identifier_occurrences(text, identifier)
        consumed = consumed_spans.setdefault(element_id, set())
        for start, _end in spans:
            if start not in consumed:
                consumed.add(start)
                return True, start
        return False, None

    def _resolve_and_consume(identifier: str, source_fact_id: str | None) -> tuple[bool, str | None, list[str], int | None]:
        resolved = _resolve_source_fact_element(source_fact_id, matched_element_by_fact_id)
        if resolved is not None:
            ok, _start = _try_consume(identifier, resolved.element_id, resolved.text)
            if ok:
                return True, resolved.element_id, chunk_map.get(resolved.element_id, []), resolved.unit_index
            return False, None, [], None
        if source_fact_id and (source_fact_id.startswith("VF_NODE") or source_fact_id.startswith("DN_")):
            for ann in picture_ocr_annotations:
                key = f"ocr:{ann.annotation_id}"
                ok, _start = _try_consume(identifier, key, ann.text)
                if ok:
                    return True, ann.annotation_id, chunk_map.get(ann.annotation_id, []), None
            return False, None, [], None
        return False, None, [], None

    for fact in target_facts:
        identifier = fact["normalized_value"]
        any_matched = False
        for occ_index, occurrence in enumerate(fact["occurrences"]):
            occ_fact_id = f"{fact['fact_id']}_occ_{occ_index}"
            source_fact_id = occurrence.get("source_fact")
            matched, element_id, occ_chunk_ids, resolved_unit = _resolve_and_consume(identifier, source_fact_id)

            if matched:
                occurrence_acc.record_match(occ_fact_id)
                any_matched = True
                is_ocr_match = element_id in {a.annotation_id for a in picture_ocr_annotations}
                alignments.append(_alignment(
                    occ_fact_id, fixture, "identifier_occurrence",
                    expected_value={"normalized_value": identifier, "source_fact": source_fact_id, "raw_text": occurrence.get("raw_text")},
                    matched_element_ids=[] if is_ocr_match else [element_id],
                    matched_annotation_ids=[element_id] if is_ocr_match else [],
                    matched_chunk_ids=sorted(occ_chunk_ids), match_status="matched", derivation="source_derived",
                ))

                # Stage 6A.1 item 9: occurrence location/context accuracy --
                # reuses whatever expected_location the resolving
                # source_fact itself declares (identifiers have no
                # expected_location of their own in the manifest); OCR-
                # resolved occurrences (source_fact is a diagram-node
                # reference, never declares a location) are correctly
                # excluded rather than compared against nothing.
                expected_unit = _location_unit_index(fact_expected_location_by_id.get(source_fact_id, {}))
                if expected_unit is not None and resolved_unit is not None:
                    if resolved_unit == expected_unit:
                        occ_location_acc.record_match(occ_fact_id)
                    else:
                        occ_location_acc.record_miss(occ_fact_id)
                        miss_records.append(MissRecord(
                            fixture=fixture, fact_id=occ_fact_id, metric="identifier_occurrence_location_accuracy",
                            expected_value={"unit_index": expected_unit}, observed_value={"unit_index": resolved_unit}, result="partial",
                            failure_class="parser_structure_loss", confidence="certain",
                            explanation=f"identifier occurrence {occ_fact_id!r} matched but at unit_index={resolved_unit}, expected {expected_unit} (via source_fact {source_fact_id!r})",
                            supporting_canonical_element_ids=[element_id] if not is_ocr_match else [],
                        ))

                if not occ_chunk_ids:
                    miss_records.append(MissRecord(
                        fixture=fixture, fact_id=occ_fact_id, metric="chunk_availability",
                        expected_value={"has_chunk": True}, observed_value={"has_chunk": False}, result="partial",
                        failure_class="chunk_projection_loss", confidence="certain",
                        explanation=f"identifier occurrence {occ_fact_id!r} matched in CanonicalDocument but is not referenced by any CanonicalChunk",
                        supporting_canonical_element_ids=[element_id],
                    ))
            else:
                occurrence_acc.record_miss(occ_fact_id)
                scoped_raw_items = _scoped_raw_items_for_occurrence(
                    source_fact_id, matched_element_by_fact_id=matched_element_by_fact_id,
                    source_ref_by_id=source_ref_by_id, fact_text_by_id=fact_text_by_id,
                    raw_text_blob=raw_text_blob, raw_debug=raw_debug, matched_picture_ids=matched_picture_ids,
                )
                failure_class, confidence, raw_refs = classification.classify_identifier_occurrence_absence(identifier, scoped_raw_items)
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=occ_fact_id, metric="identifier_occurrence_recall",
                    expected_value={"normalized_value": identifier, "source_fact": source_fact_id}, result="miss",
                    failure_class=failure_class, confidence=confidence,
                    explanation=f"expected occurrence of {identifier!r} tied to source_fact={source_fact_id!r} not found at that resolved location "
                                f"(attribution scoped to that occurrence's own expected context only, Stage 6A.2 item 1)",
                    raw_docling_references=raw_refs,
                ))
                alignments.append(_alignment(
                    occ_fact_id, fixture, "identifier_occurrence",
                    expected_value={"normalized_value": identifier, "source_fact": source_fact_id, "raw_text": occurrence.get("raw_text")},
                    match_status="missing", derivation="not_applicable",
                ))

        if any_matched:
            unique_acc.record_match(fact["fact_id"])
        else:
            unique_acc.record_miss(fact["fact_id"])
            miss_records.append(MissRecord(
                fixture=fixture, fact_id=fact["fact_id"], metric="identifier_unique_recall",
                expected_value={"normalized_value": identifier}, result="miss", failure_class="parser_content_loss", confidence="supported",
                explanation=f"identifier {identifier!r} matched zero of its expected occurrences",
            ))

    # Distractor identifiers -- occurrence-level too, one alignment per
    # occurrence, plus the false-merge regression check.
    for fact in distractor_facts:
        distractor_value = fact["normalized_value"]
        for occ_index, occurrence in enumerate(fact["occurrences"]):
            occ_fact_id = f"{fact['fact_id']}_occ_{occ_index}"
            source_fact_id = occurrence.get("source_fact")
            matched, element_id, occ_chunk_ids, _unit = _resolve_and_consume(distractor_value, source_fact_id)

            is_ocr_match = bool(element_id) and element_id in {a.annotation_id for a in picture_ocr_annotations}
            false_merge_detected = False
            if matched and element_id and not is_ocr_match:
                resolved = matched_element_by_fact_id.get(source_fact_id)
                if resolved is not None:
                    for target in target_facts:
                        target_value = target["normalized_value"]
                        if target_value == distractor_value or target_value not in distractor_value:
                            continue
                        distractor_spans = find_identifier_occurrences(resolved.text, distractor_value)
                        target_spans = find_identifier_occurrences(resolved.text, target_value)
                        for d_start, d_end in distractor_spans:
                            for t_start, t_end in target_spans:
                                if t_start >= d_start and t_end <= d_end:
                                    false_merge_detected = True

            if matched and not false_merge_detected:
                no_false_merge_acc.record_match(occ_fact_id)
                alignments.append(_alignment(
                    occ_fact_id, fixture, "identifier_distractor_occurrence", expected_value={"normalized_value": distractor_value, "source_fact": source_fact_id},
                    matched_element_ids=[] if is_ocr_match else ([element_id] if element_id else []),
                    matched_annotation_ids=[element_id] if is_ocr_match else [],
                    matched_chunk_ids=sorted(occ_chunk_ids), match_status="matched", derivation="source_derived",
                ))
            elif false_merge_detected:
                no_false_merge_acc.record_miss(occ_fact_id)
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=occ_fact_id, metric="identifier_distractor_no_false_merge",
                    expected_value={"normalized_value": distractor_value}, result="unexpected",
                    failure_class="distractor_false_positive", confidence="certain",
                    explanation=f"distractor identifier {distractor_value!r} appears to have been falsely merged with a target identifier",
                ))
                alignments.append(_alignment(
                    occ_fact_id, fixture, "identifier_distractor_occurrence", expected_value={"normalized_value": distractor_value, "source_fact": source_fact_id},
                    match_status="missing", derivation="not_applicable",
                ))
            else:
                no_false_merge_acc.record_miss(occ_fact_id)
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=occ_fact_id, metric="identifier_distractor_no_false_merge",
                    expected_value={"normalized_value": distractor_value}, result="miss",
                    failure_class="parser_content_loss", confidence="certain",
                    explanation=f"distractor identifier {distractor_value!r} not found at its resolved source_fact location -- cannot verify it was not falsely merged",
                ))
                alignments.append(_alignment(
                    occ_fact_id, fixture, "identifier_distractor_occurrence", expected_value={"normalized_value": distractor_value, "source_fact": source_fact_id},
                    match_status="missing", derivation="not_applicable",
                ))

    # Stage 6A.1 item 1: extra observed occurrences beyond every expected
    # occurrence's one-to-one consumption, recorded separately -- never
    # used to silently satisfy a different missing expectation.
    all_identifiers = {f["normalized_value"] for f in target_facts} | {f["normalized_value"] for f in distractor_facts}
    for identifier in all_identifiers:
        for element in elements:
            consumed = consumed_spans.get(element.element_id, set())
            for start, end in find_identifier_occurrences(element.text, identifier):
                if start not in consumed:
                    unexpected.append(UnexpectedObservation(
                        fixture=fixture, element_id=element.element_id, element_type=element.element_type,
                        text=element.text[max(0, start - 20):end + 20], reason=f"extra occurrence of {identifier!r} beyond every manifest-declared occurrence's one-to-one resolution",
                    ))
        for ann in picture_ocr_annotations:
            key = f"ocr:{ann.annotation_id}"
            consumed = consumed_spans.get(key, set())
            for start, end in find_identifier_occurrences(ann.text, identifier):
                if start not in consumed:
                    unexpected.append(UnexpectedObservation(
                        fixture=fixture, element_id=ann.annotation_id, element_type="ocr_annotation",
                        text=ann.text, reason=f"extra occurrence of {identifier!r} beyond every manifest-declared occurrence's one-to-one resolution",
                    ))

    metrics = {
        "identifier_unique_recall": unique_acc.result(), "identifier_occurrence_recall": occurrence_acc.result(),
        "identifier_occurrence_location_accuracy": occ_location_acc.result(),
        "identifier_distractor_no_false_merge": no_false_merge_acc.result(),
    }
    return metrics, miss_records, unexpected, alignments


# --- global chunk-availability sweep (Stage 6A.1 item 9) --------------------


def _sweep_chunk_availability(fixture: str, alignments: list[EvidenceAlignment]) -> tuple[MetricResult, list[MissRecord]]:
    """A matched (or partial) canonical fact with no supporting chunk must
    create a chunk_projection_loss MissRecord -- applied uniformly across
    every fact type via one pass over the already-built alignment list,
    rather than duplicated per category. Facts already flagged during
    identifier scoring are not double-counted."""
    acc = _MetricAcc("chunk_availability", "every matched/partial EvidenceAlignment must carry at least one matched_chunk_ids entry")
    miss_records: list[MissRecord] = []
    already_flagged = set()
    for alignment in alignments:
        if alignment.match_status not in ("matched", "partial"):
            continue
        if alignment.fact_type == "identifier_occurrence":
            # already swept during _score_identifiers to avoid duplicate records
            if alignment.matched_chunk_ids:
                acc.record_match(alignment.fact_id)
            else:
                acc.record_miss(alignment.fact_id)
            continue
        if alignment.matched_chunk_ids:
            acc.record_match(alignment.fact_id)
        else:
            acc.record_miss(alignment.fact_id)
            if alignment.fact_id not in already_flagged:
                already_flagged.add(alignment.fact_id)
                miss_records.append(MissRecord(
                    fixture=fixture, fact_id=alignment.fact_id, metric="chunk_availability",
                    expected_value={"has_chunk": True}, observed_value={"has_chunk": False}, result="partial",
                    failure_class="chunk_projection_loss", confidence="certain",
                    explanation=f"{alignment.fact_type} {alignment.fact_id!r} matched in CanonicalDocument but is not referenced by any CanonicalChunk",
                    supporting_canonical_element_ids=list(alignment.matched_canonical_element_ids),
                ))
    return acc.result(), miss_records


# --- top-level per-fixture orchestration ------------------------------------


def evaluate_fixture(loaded: LoadedFixture, manifest: dict[str, Any]) -> FixtureEvaluationResult:
    document = loaded.document
    chunks = loaded.chunks
    chunk_map = element_to_chunk_ids(chunks)
    elements = flatten_text_elements(document)
    facts = build_fact_catalog(manifest, loaded.suite_key, loaded.doc_id)

    raw_debug: dict[str, Any] | None = None
    raw_text_blob: list[tuple[str, str]] | None = None
    if loaded.raw_debug_path.exists():
        raw_debug = loaded.raw_debug()
        raw_text_blob = classification.extract_raw_text_blob(raw_debug)

    metrics: dict[str, MetricResult] = {}
    miss_records: list[MissRecord] = []
    unexpected_observations: list[UnexpectedObservation] = []
    evidence_alignments: list[EvidenceAlignment] = []
    matched_element_by_fact_id: dict[str, TextElement] = {}

    text_facts = facts.get("paragraph", [])
    if text_facts:
        text_metrics, misses, unexpected, alignments, matched_map = _score_text_facts(loaded.fixture, text_facts, elements, chunk_map, raw_text_blob)
        metrics.update(text_metrics)
        miss_records += misses
        unexpected_observations += unexpected
        evidence_alignments += alignments
        matched_element_by_fact_id.update(matched_map)

    if facts.get("heading"):
        heading_metrics, misses, alignments, matched_map = _score_headings(loaded.fixture, facts["heading"], document, elements, chunk_map, raw_text_blob)
        metrics.update(heading_metrics)
        miss_records += misses
        evidence_alignments += alignments
        matched_element_by_fact_id.update(matched_map)

    if facts.get("table"):
        table_metrics, misses, alignments = _score_tables(loaded.fixture, facts["table"], document, chunk_map)
        metrics.update(table_metrics)
        miss_records += misses
        evidence_alignments += alignments

    picture_ocr_annotations: list = []
    matched_picture_ids: list[str] = []
    if facts.get("picture") or facts.get("caption"):
        pc_metrics, misses, alignments, matched_map, matched_picture_ids = _score_pictures_captions(loaded.fixture, facts.get("picture", []), facts.get("caption", []), document, chunk_map, raw_debug)
        metrics.update(pc_metrics)
        miss_records += misses
        evidence_alignments += alignments
        matched_element_by_fact_id.update(matched_map)
        picture_ids = {p.picture_id for p in document.pictures}
        picture_ocr_annotations = [a for a in document.annotations if a.annotation_type == "ocr" and a.target_ref in picture_ids]

    # Stage 6A.2 item 1: element_id -> raw self_ref, needed by identifier
    # occurrence miss attribution BEFORE it runs (moved up from what was
    # previously a post-hoc EvidenceAlignment backfill-only computation --
    # that backfill pass, further below, now reuses this same mapping).
    source_ref_by_id: dict[str, str] = {p.element_id: p.source_element_ref for p in document.provenance if p.source_element_ref}

    if facts.get("identifier_target") or facts.get("identifier_distractor"):
        fact_expected_location_by_id: dict[str, dict] = {}
        fact_text_by_id: dict[str, str] = {}
        for category in ("paragraph", "heading", "caption"):
            for f in facts.get(category, []):
                loc = f.get("expected_location")
                if loc:
                    fact_expected_location_by_id[f["fact_id"]] = loc
                text = f.get("text")
                if text is not None:
                    fact_text_by_id[f["fact_id"]] = text
        id_metrics, misses, unexpected, alignments = _score_identifiers(
            loaded.fixture, facts.get("identifier_target", []), facts.get("identifier_distractor", []),
            elements, chunk_map, matched_element_by_fact_id, picture_ocr_annotations, raw_text_blob,
            fact_expected_location_by_id,
            raw_debug=raw_debug, source_ref_by_id=source_ref_by_id, fact_text_by_id=fact_text_by_id,
            matched_picture_ids=matched_picture_ids,
        )
        metrics.update(id_metrics)
        miss_records += misses
        unexpected_observations += unexpected
        evidence_alignments += alignments

    if facts.get("ocr_token"):
        ocr_metrics, misses, alignments = _score_ocr_tokens(loaded.fixture, facts["ocr_token"], document, chunk_map)
        metrics.update(ocr_metrics)
        miss_records += misses
        evidence_alignments += alignments

    if facts.get("whole_page_ocr_text"):
        m, misses, alignments = _score_whole_page_ocr(loaded.fixture, facts["whole_page_ocr_text"], document, chunk_map)
        metrics["whole_page_ocr_text_recall"] = m
        miss_records += misses
        evidence_alignments += alignments

    if facts.get("list_item"):
        li_metrics, misses, alignments = _score_list_items(loaded.fixture, facts["list_item"], document, chunk_map)
        metrics.update(li_metrics)
        miss_records += misses
        evidence_alignments += alignments

    if facts.get("visual_fact") or facts.get("unsupported_claim"):
        vf_metrics, vf_misses, alignments = _score_visual_facts_and_unsupported_claims(loaded.fixture, facts.get("visual_fact", []), facts.get("unsupported_claim", []), document)
        metrics.update(vf_metrics)
        miss_records += vf_misses
        evidence_alignments += alignments

    structural_metrics, structural_misses, structural_alignments = _score_structural_stress(loaded.fixture, loaded.suite_key, facts, document, chunk_map)
    metrics.update(structural_metrics)
    miss_records += structural_misses
    evidence_alignments += structural_alignments

    # Stage 6A section 1 / item 7: evaluation-contract limitation, recorded
    # rather than invented -- the chart fixture declares visual_facts
    # (requiring a VisionEnricher path A doesn't have) but no
    # expected_ocr_tokens/expected_ocr_text field.
    if loaded.suite_key == "stress_chart":
        miss_records.append(MissRecord(
            fixture=loaded.fixture, fact_id=f"{loaded.doc_id}_ocr_tokens_undeclared", metric="picture_ocr_token_recall",
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

    provenance_metrics, provenance_misses = _score_provenance(loaded.fixture, document)
    metrics.update(provenance_metrics)
    miss_records += provenance_misses

    # Stage 6A.1 item 9: unit_indexes/source_references backfill, plus the
    # global chunk-availability sweep (item 9's "chunk_projection_loss"
    # requirement applied uniformly across every fact type).
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
    # source_ref_by_id computed earlier (before identifier scoring, Stage
    # 6A.2 item 1) -- reused here unchanged for the alignment backfill.

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

    chunk_availability_metric, chunk_availability_misses = _sweep_chunk_availability(loaded.fixture, evidence_alignments)
    metrics["chunk_availability"] = chunk_availability_metric
    miss_records += chunk_availability_misses

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
        determinism=loaded.determinism,
        canonical_document_file_sha256=loaded.canonical_document_file_sha256,
        canonical_chunks_file_sha256=loaded.canonical_chunks_file_sha256,
        conversion_report_file_sha256=loaded.conversion_report_file_sha256,
        raw_docling_debug_file_sha256=loaded.raw_docling_debug_file_sha256,
        artifact_completeness=loaded.artifact_completeness,
    )

    return FixtureEvaluationResult(
        fixture=loaded.fixture, doc_id=loaded.doc_id, source_format=loaded.source_format,
        operational=operational, metrics=metrics, miss_records=miss_records,
        unexpected_observations=unexpected_observations, evidence_alignments=evidence_alignments,
    )
