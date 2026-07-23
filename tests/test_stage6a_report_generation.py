"""Tests that scripts/run_stage6a_evaluation.py's report-generation
functions produce the exact required outputs (Stage 6A section 17):
Markdown and JSON from one execution, every scored miss in the miss
ledger, every matched fact in the evidence-alignment catalog."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "fixtures"))

import pytest  # noqa: E402

from ingestion_bench.evaluation.aggregation import (  # noqa: E402
    build_evaluation_run,
    build_evidence_alignment_catalog,
    build_miss_ledger,
    render_scorecard_markdown,
)
from ingestion_bench.evaluation.evaluator import evaluate_fixture, load_fixture_artifacts, load_manifest  # noqa: E402

FIXTURES_ROOT = REPO_ROOT / "fixtures"
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "stage5a"

_CACHE: dict[str, object] = {}


def _run():
    if "run" not in _CACHE:
        if not (ARTIFACTS_ROOT / "PARITY_001_pdf" / "canonical_document.json").exists():
            pytest.skip("artifacts/stage5a/ not present -- run scripts/run_docling_standard.py first")
        manifest = load_manifest(FIXTURES_ROOT)
        loaded = load_fixture_artifacts(ARTIFACTS_ROOT)
        results = [evaluate_fixture(f, manifest) for f in loaded]
        _CACHE["run"] = build_evaluation_run(results, manifest, "m" * 64, "s" * 64)
    return _CACHE["run"]


def test_scorecard_and_results_are_traceable_to_one_run_object():
    run = _run()
    markdown = render_scorecard_markdown(run)
    assert run.run_id in markdown
    assert run.manifest_sha256 in markdown
    results_json = run.model_dump_json()
    assert f'"run_id":"{run.run_id}"' in results_json or run.run_id in results_json


def test_every_scored_miss_appears_in_the_miss_ledger():
    run = _run()
    ledger = build_miss_ledger(run)
    expected_total = sum(len(r.miss_records) for r in run.fixture_results)
    assert ledger["total_misses"] == expected_total
    ledger_fact_ids = {(e["fixture"], e["fact_id"], e["metric"]) for e in ledger["entries"]}
    for result in run.fixture_results:
        for miss in result.miss_records:
            assert (miss.fixture, miss.fact_id, miss.metric) in ledger_fact_ids


def test_every_matched_expected_fact_has_an_evidence_alignment_entry_in_the_catalog():
    run = _run()
    catalog = build_evidence_alignment_catalog(run)
    catalog_keys = {(e["fixture"], e["fact_id"]) for e in catalog}
    for result in run.fixture_results:
        for alignment in result.evidence_alignments:
            assert (alignment.fixture, alignment.fact_id) in catalog_keys


def test_miss_ledger_classification_counts_match_aggregate():
    run = _run()
    ledger = build_miss_ledger(run)
    assert ledger["miss_count_by_classification"] == run.aggregate.miss_count_by_classification


def test_scorecard_markdown_contains_the_required_table_columns():
    run = _run()
    markdown = render_scorecard_markdown(run)
    for column in (
        "Text fact recall", "Unique identifier recall", "Occurrence identifier recall",
        "Heading text recall", "Heading level accuracy", "Table cell-text accuracy",
        "Table coordinate accuracy", "Picture detection", "Caption linking", "OCR text recall",
        "Provenance coverage",
    ):
        assert column in markdown, column


def test_scorecard_never_claims_retrieval_or_answer_quality_was_measured():
    run = _run()
    markdown = render_scorecard_markdown(run)
    assert "does NOT establish" in markdown or "does not establish" in markdown.lower()
    assert "no retrieval layer" in markdown.lower()


def test_run_output_never_contains_an_absolute_windows_path():
    run = _run()
    markdown = render_scorecard_markdown(run)
    assert "C:\\" not in markdown
    results_json = run.model_dump_json()
    assert "C:\\\\" not in results_json


def test_evaluator_never_produces_a_model_derived_annotation_backed_alignment():
    """Stage 5A produces no model-derived annotations (path A only) --
    the evidence catalog must never claim derivation="model_derived"."""
    run = _run()
    catalog = build_evidence_alignment_catalog(run)
    assert all(e["derivation"] != "model_derived" for e in catalog)
