"""Combines per-fixture FixtureEvaluationResults into an EvaluationRun,
and renders the Stage 6A Markdown scorecard, JSON results, and miss
ledger from that ONE in-memory result -- the Markdown and JSON aggregate
reports must never come from two separate evaluation executions (same
discipline as Stage 5A.1 item 7 / D-039's component-level-reporting
principle).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .evaluator import EVALUATOR_VERSION, FIXTURES
from .model import AggregateEvaluationResult, EvaluationRun, FixtureEvaluationResult, MetricResult


def _canonical_json_bytes(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _compute_input_bundle_hash(
    fixture_results: list[FixtureEvaluationResult], manifest_sha256: str, stage5a_results_sha256: str,
) -> str:
    """Stage 6A.1 item 11: a deterministic SHA-256 over every input this
    run actually read -- the manifest, the Stage 5A aggregate results
    file, and every fixture's own four raw-artifact-bytes hashes. Two
    evaluation runs over byte-identical inputs always produce the same
    input_bundle_hash; any single-byte drift in any input file changes
    it."""
    fixtures = sorted(
        (
            {
                "fixture": r.fixture,
                "canonical_document_file_sha256": r.operational.canonical_document_file_sha256,
                "canonical_chunks_file_sha256": r.operational.canonical_chunks_file_sha256,
                "conversion_report_file_sha256": r.operational.conversion_report_file_sha256,
                "raw_docling_debug_file_sha256": r.operational.raw_docling_debug_file_sha256,
            }
            for r in fixture_results
        ),
        key=lambda d: d["fixture"],
    )
    payload = {"manifest_sha256": manifest_sha256, "stage5a_results_sha256": stage5a_results_sha256, "fixtures": fixtures}
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _compute_run_id(input_bundle_hash: str) -> str:
    """Deterministic, never uuid4() -- a pure function of input_bundle_hash
    (which is itself a pure function of every input file's bytes) and the
    evaluator version, consistent with this project's established
    identity discipline (D-010). run_id is derived FROM input_bundle_hash,
    not computed independently of it (Stage 6A.1 item 11)."""
    payload = {"input_bundle_hash": input_bundle_hash, "evaluator_version": EVALUATOR_VERSION}
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _compute_evaluation_content_hash(
    input_bundle_hash: str, evaluator_version: str, manifest_version: str, manifest_sha256: str,
    stage5a_results_sha256: str, fixture_results: list[FixtureEvaluationResult], aggregate: AggregateEvaluationResult,
) -> str:
    """Stage 6A.2 item 4: a deterministic SHA-256 over every STABLE piece
    of EvaluationRun content -- explicitly excluding `generated_at`
    (mutable runtime/report metadata) and `evaluation_content_hash` itself
    (this function's own output is never fed back into its own input).
    Two runs over byte-identical inputs that produce byte-identical
    results always share this hash, independent of wall-clock time; any
    change to a metric, evidence alignment, miss record, input artifact
    hash, or evaluator_version changes it."""
    payload = {
        "input_bundle_hash": input_bundle_hash,
        "evaluator_version": evaluator_version,
        "manifest_version": manifest_version,
        "manifest_sha256": manifest_sha256,
        "stage5a_results_sha256": stage5a_results_sha256,
        "fixture_results": [r.model_dump(mode="json") for r in fixture_results],
        "aggregate": aggregate.model_dump(mode="json"),
    }
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _merge_metric(a: MetricResult, b: MetricResult) -> MetricResult:
    numerator = a.numerator + b.numerator
    denominator = a.denominator + b.denominator
    excluded = a.excluded_not_applicable + b.excluded_not_applicable
    score = None if denominator == 0 else numerator / denominator
    return MetricResult(
        metric_name=a.metric_name, matching_rule=a.matching_rule, numerator=numerator, denominator=denominator,
        excluded_not_applicable=excluded, score=score,
        supporting_matches=sorted(set(a.supporting_matches) | set(b.supporting_matches)),
        supporting_misses=sorted(set(a.supporting_misses) | set(b.supporting_misses)),
    )


def aggregate_metrics_by_format(fixture_results: list[FixtureEvaluationResult]) -> dict[str, dict[str, MetricResult]]:
    by_format: dict[str, dict[str, MetricResult]] = {"pdf": {}, "docx": {}, "pptx": {}, "overall": {}}
    for result in fixture_results:
        for bucket in (result.source_format, "overall"):
            target = by_format[bucket]
            for metric_name, metric in result.metrics.items():
                target[metric_name] = _merge_metric(target[metric_name], metric) if metric_name in target else metric
    return by_format


def build_aggregate(fixture_results: list[FixtureEvaluationResult]) -> AggregateEvaluationResult:
    miss_by_class: dict[str, int] = {}
    for result in fixture_results:
        for miss in result.miss_records:
            miss_by_class[miss.failure_class] = miss_by_class.get(miss.failure_class, 0) + 1
    evidence_count = sum(len(r.evidence_alignments) for r in fixture_results)
    evidence_by_status: dict[str, int] = {}
    for result in fixture_results:
        for alignment in result.evidence_alignments:
            evidence_by_status[alignment.match_status] = evidence_by_status.get(alignment.match_status, 0) + 1
    return AggregateEvaluationResult(
        metrics_by_format=aggregate_metrics_by_format(fixture_results),
        miss_count_by_classification=miss_by_class,
        evidence_alignment_count=evidence_count,
        evidence_alignment_count_by_status=evidence_by_status,
        total_fixtures=len(fixture_results),
    )


def build_evaluation_run(
    fixture_results: list[FixtureEvaluationResult], manifest: dict[str, Any], manifest_sha256: str, stage5a_results_sha256: str,
) -> EvaluationRun:
    aggregate = build_aggregate(fixture_results)
    input_bundle_hash = _compute_input_bundle_hash(fixture_results, manifest_sha256, stage5a_results_sha256)
    evaluation_content_hash = _compute_evaluation_content_hash(
        input_bundle_hash, EVALUATOR_VERSION, manifest["manifest_version"], manifest_sha256, stage5a_results_sha256,
        fixture_results, aggregate,
    )
    return EvaluationRun(
        run_id=_compute_run_id(input_bundle_hash),
        input_bundle_hash=input_bundle_hash,
        evaluation_content_hash=evaluation_content_hash,
        generated_at=datetime.now(timezone.utc).isoformat(),
        manifest_version=manifest["manifest_version"],
        manifest_sha256=manifest_sha256,
        stage5a_results_sha256=stage5a_results_sha256,
        evaluator_version=EVALUATOR_VERSION,
        fixture_results=fixture_results,
        aggregate=aggregate,
    )


def build_miss_ledger(run: EvaluationRun) -> dict[str, Any]:
    entries = []
    for result in run.fixture_results:
        for miss in result.miss_records:
            entries.append(miss.model_dump(mode="json"))
    return {
        "run_id": run.run_id,
        "generated_at": run.generated_at,
        "total_misses": len(entries),
        "miss_count_by_classification": run.aggregate.miss_count_by_classification,
        "entries": entries,
    }


def build_evidence_alignment_catalog(run: EvaluationRun) -> list[dict[str, Any]]:
    entries = []
    for result in run.fixture_results:
        for alignment in result.evidence_alignments:
            entries.append(alignment.model_dump(mode="json"))
    return entries


# Stage 6A.1 item 12: labels corrected -- picture OCR is never labeled
# generically as "OCR text recall" (whole-page OCR gets its own row), and
# new rows added for heading classification, provenance-entry/bbox
# coverage, and unsupported-visual-claim absence.
_SCORECARD_METRIC_COLUMNS: list[tuple[str, str]] = [
    ("text_fact_recall", "Text fact recall"),
    ("identifier_unique_recall", "Unique identifier recall"),
    ("identifier_occurrence_recall", "Occurrence identifier recall"),
    ("heading_text_recall", "Heading text recall"),
    ("heading_level_accuracy", "Heading level accuracy"),
    ("heading_classification_accuracy", "Heading classification accuracy"),
    ("table_cell_text_recall", "Table cell-text accuracy"),
    ("table_cell_coordinate_accuracy", "Table coordinate accuracy"),
    ("picture_presence", "Picture detection"),
    ("caption_linkage_accuracy", "Caption linking"),
    ("picture_ocr_token_recall", "Picture OCR token recall"),
    ("whole_page_ocr_text_recall", "Whole-page OCR recall"),
    ("unsupported_visual_claim_absence", "Unsupported-visual-claim absence"),
    ("provenance_coverage_overall", "Provenance-entry coverage"),
    ("provenance_bbox_coverage_overall", "Bbox-provenance coverage"),
    ("chunk_availability", "Chunk availability"),
]


def _fmt_score(metric: MetricResult | None) -> str:
    if metric is None:
        return "n/a"
    if metric.score is None:
        excluded_note = f", {metric.excluded_not_applicable} excluded" if metric.excluded_not_applicable else ""
        return f"n/a (0/0{excluded_note})"
    return f"{metric.score * 100:.1f}% ({metric.numerator}/{metric.denominator})"


def render_scorecard_markdown(run: EvaluationRun) -> str:
    by_format = run.aggregate.metrics_by_format
    header = "| Metric | PDF | DOCX | PPTX | Overall |\n|---|---:|---:|---:|---:|"
    rows = []
    for metric_key, label in _SCORECARD_METRIC_COLUMNS:
        rows.append(
            f"| {label} | {_fmt_score(by_format['pdf'].get(metric_key))} | {_fmt_score(by_format['docx'].get(metric_key))} | "
            f"{_fmt_score(by_format['pptx'].get(metric_key))} | {_fmt_score(by_format['overall'].get(metric_key))} |"
        )
    scorecard_table = header + "\n" + "\n".join(rows)

    fixture_lines = []
    for result in run.fixture_results:
        top_metrics = ", ".join(
            f"{name}={_fmt_score(metric)}" for name, metric in sorted(result.metrics.items())
            if name in {k for k, _ in _SCORECARD_METRIC_COLUMNS}
        )
        determinism_note = ""
        if result.operational.determinism is not None:
            all_equal = result.operational.determinism.get("all_equal")
            determinism_note = f", determinism.all_equal={all_equal}"
        fixture_lines.append(
            f"- **{result.fixture}** ({result.operational.conversion_status}, "
            f"{len(result.miss_records)} misses, {len(result.evidence_alignments)} evidence alignments{determinism_note}): "
            f"{top_metrics or '(no applicable expectations for the headline metrics)'}"
        )

    miss_class_lines = "\n".join(
        f"| `{cls}` | {count} |" for cls, count in sorted(run.aggregate.miss_count_by_classification.items())
    ) or "| (none) | 0 |"

    evidence_status_lines = "\n".join(
        f"| `{status}` | {count} |" for status, count in sorted(run.aggregate.evidence_alignment_count_by_status.items())
    ) or "| (none) | 0 |"

    limitation_entries = [
        m for r in run.fixture_results for m in r.miss_records if m.failure_class == "evaluation_contract_insufficient"
    ]
    limitation_lines = "\n".join(f"- **{m.fixture}** / `{m.fact_id}`: {m.explanation}" for m in limitation_entries) or "None recorded."

    input_bundle_lines = "\n".join(
        f"| {r.fixture} | `{r.operational.canonical_document_file_sha256[:16]}...` | "
        f"`{(r.operational.canonical_chunks_file_sha256 or 'MISSING')[:16]}...` | "
        f"`{r.operational.conversion_report_file_sha256[:16]}...` | "
        f"`{(r.operational.raw_docling_debug_file_sha256 or 'MISSING')[:16]}...` | "
        f"{r.operational.determinism.get('all_equal') if r.operational.determinism else 'n/a'} |"
        for r in run.fixture_results
    )

    return f"""# Stage 6A — Deterministic Ingestion-Fidelity Evaluator: Docling Standard Local Baseline

Generated by `scripts/run_stage6a_evaluation.py` from a single execution
-- this Markdown and `reports/stage6a_docling_baseline_results.json` come
from the same in-memory `EvaluationRun`, never two separate runs (same
discipline as Stage 5A.1/D-039).

`run_id`: `{run.run_id}`
`input_bundle_hash` (every input file this run actually read, hashed together -- Stage 6A.1 item 11): `{run.input_bundle_hash}`
`evaluation_content_hash` (every STABLE result this run produced, hashed together, excluding `generated_at` -- Stage 6A.2 item 4): `{run.evaluation_content_hash}`
`manifest_version`: `{run.manifest_version}` (`manifest_sha256`: `{run.manifest_sha256}`)
`stage5a_results_sha256` (the exact `reports/stage5a_docling_standard_results.json` bytes this run scored): `{run.stage5a_results_sha256}`
`evaluator_version`: `{run.evaluator_version}`
Fixtures scored: {run.aggregate.total_fixtures} / {len(FIXTURES)}

This report compares the frozen `fixtures/reference_manifest.json` against
Stage 5A `DOCLING_STANDARD_LOCAL` output only (path A). It never invents
an expected value not present in the manifest, never claims retrieval or
answer-quality was measured, and scores primarily against
`CanonicalDocument` (`CanonicalChunk` establishes downstream evidence
availability; raw Docling debug JSON is consulted only to attribute an
already-established miss between the parser and the Stage 5A mapper --
see `src/ingestion_bench/evaluation/classification.py`). Every
`EvidenceAlignment.expected_retrieval_difficulty` is `null`/unclassified
in Stage 6A -- Stage 6B assigns real difficulty to concrete benchmark
questions, never inferred here from ingestion-side signals alone.

## Aggregate scorecard

{scorecard_table}

Cells read `score% (numerator/denominator)`; `n/a` means the metric had
zero applicable expectations for that format (never silently reported as
0%) -- see the full per-metric breakdown in
`reports/stage6a_docling_baseline_results.json` for every metric beyond
this headline table (table span/header accuracy, list-item indentation/
parent-link accuracy, per-category provenance coverage, occurrence-level
identifier location accuracy, structural stress metrics, and more).

## Fixture-by-fixture summary

{chr(10).join(fixture_lines)}

## Miss count by classification

| Classification | Count |
|---|---:|
{miss_class_lines}

Total misses: {sum(run.aggregate.miss_count_by_classification.values())}. Full detail: `reports/stage6a_docling_miss_ledger.json`.

## Gold evidence-alignment catalog

{run.aggregate.evidence_alignment_count} entries written to
`artifacts/stage6a/evidence_alignment.json` -- ONE ENTRY PER EXPECTED
MANIFEST FACT, not only matched ones (Stage 6A.1 item 2): every heading,
paragraph/distractor, identifier occurrence, table cell, caption, picture,
OCR expectation, diagram node/edge, visual fact, and unsupported claim has
a record, with `match_status` distinguishing matched/partial/missing/
not_applicable so a future retrieval evaluation can tell ingestion loss
apart from retrieval loss. Status breakdown:

| Status | Count |
|---|---:|
{evidence_status_lines}

This catalog is the gold evidence set later reused, unmodified, to
evaluate vector RAG, Graph RAG, and wiki retrieval against the SAME
expected facts and supporting chunks (D-040) -- no retrieval questions or
difficulty labels are invented here (Stage 6B).

## Input-bundle traceability (Stage 6A.1 item 11)

| Fixture | canonical_document SHA-256 | canonical_chunks SHA-256 | conversion_report SHA-256 | raw_docling_debug SHA-256 | determinism.all_equal |
|---|---|---|---|---|---|
{input_bundle_lines}

## Manifest fields insufficient for scoring (recorded, not invented)

{limitation_lines}

## What this report does NOT establish

- Retrieval relevance or answer quality of any kind -- no retrieval layer
  exists (Stages 6B/7A/7B/7C, not started).
- Vision-enrichment accuracy (picture classification, diagram node/edge
  recovery, visual-fact accuracy) -- Stage 5A path A produces none of this
  content by design; every such expectation is recorded as
  not_applicable/excluded, never scored as a failure.
- ROI, cost, or latency comparison across ingestion approaches (Stage 9).
- OpenAI-based ingestion (paths B/C) quality -- not implemented.
"""
