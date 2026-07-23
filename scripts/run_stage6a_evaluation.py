"""Stage 6A runner: scores Stage 5A DOCLING_STANDARD_LOCAL output
(artifacts/stage5a/) against the frozen fixtures/reference_manifest.json,
and writes the scorecard, aggregate results, miss ledger, per-fixture
evaluation artifacts, and the gold evidence-alignment catalog.

This is the ONLY entrypoint in the repository that reads
reference_manifest.json while evaluating Stage 5A output -- it never
modifies any Stage 5A artifact, the manifest, or any fixture.

Usage (from the repository root, with the venv active, AFTER running
scripts/run_docling_standard.py at least once):
    python scripts/run_stage6a_evaluation.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "fixtures"))

from ingestion_bench.canonical.hashing import compute_manifest_sha256  # noqa: E402
from ingestion_bench.evaluation.aggregation import (  # noqa: E402
    build_evaluation_run,
    build_evidence_alignment_catalog,
    build_miss_ledger,
    render_scorecard_markdown,
)
from ingestion_bench.evaluation.evaluator import evaluate_fixture, load_fixture_artifacts, load_manifest  # noqa: E402

FIXTURES_ROOT = REPO_ROOT / "fixtures"
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "stage5a"
STAGE6A_ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "stage6a"
REPORTS_DIR = REPO_ROOT / "reports"


def main() -> None:
    manifest = load_manifest(FIXTURES_ROOT)
    manifest_sha256 = compute_manifest_sha256(manifest)

    stage5a_results_path = REPORTS_DIR / "stage5a_docling_standard_results.json"
    stage5a_results_bytes = stage5a_results_path.read_bytes()
    stage5a_results_sha256 = hashlib.sha256(stage5a_results_bytes).hexdigest()
    stage5a_results = json.loads(stage5a_results_bytes)
    # Stage 6A.1 item 11: never leave operational.determinism silently
    # null when Stage 5A actually supplied determinism evidence.
    determinism_by_fixture = stage5a_results.get("determinism_results", {})

    loaded_fixtures = load_fixture_artifacts(ARTIFACTS_ROOT, determinism_by_fixture=determinism_by_fixture)
    fixture_results = [evaluate_fixture(loaded, manifest) for loaded in loaded_fixtures]

    run = build_evaluation_run(fixture_results, manifest, manifest_sha256, stage5a_results_sha256)

    (STAGE6A_ARTIFACTS_ROOT / "evaluation").mkdir(parents=True, exist_ok=True)
    for result in run.fixture_results:
        artifact_key = result.fixture.split("/")[-1].rsplit(".", 1)[0] + "_" + result.source_format
        (STAGE6A_ARTIFACTS_ROOT / "evaluation" / f"{artifact_key}_evaluation.json").write_text(
            result.model_dump_json(indent=2), encoding="utf-8"
        )

    evidence_catalog = build_evidence_alignment_catalog(run)
    (STAGE6A_ARTIFACTS_ROOT / "evidence_alignment.json").write_text(
        json.dumps(evidence_catalog, indent=2), encoding="utf-8"
    )

    miss_ledger = build_miss_ledger(run)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "stage6a_docling_miss_ledger.json").write_text(json.dumps(miss_ledger, indent=2), encoding="utf-8")

    # Both reports come from this SAME `run` object -- never two separate
    # evaluation executions (Stage 5A.1/D-039 discipline, reused here).
    (REPORTS_DIR / "stage6a_docling_baseline_results.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")
    (REPORTS_DIR / "stage6a_docling_baseline_scorecard.md").write_text(render_scorecard_markdown(run), encoding="utf-8")

    print(f"Evaluated {len(fixture_results)} fixtures")
    for result in fixture_results:
        scores = {name: (round(m.score, 3) if m.score is not None else None) for name, m in result.metrics.items()}
        print(f"  {result.fixture:35s} misses={len(result.miss_records):3d} evidence={len(result.evidence_alignments):3d}")
    print(f"Total misses: {sum(run.aggregate.miss_count_by_classification.values())}")
    print(f"Miss by classification: {run.aggregate.miss_count_by_classification}")
    print(f"Evidence alignment entries: {run.aggregate.evidence_alignment_count} (by status: {run.aggregate.evidence_alignment_count_by_status})")
    print(f"input_bundle_hash: {run.input_bundle_hash}")
    print(f"evaluation_content_hash: {run.evaluation_content_hash}")
    print(f"run_id: {run.run_id}")
    print(f"Scorecard written to {REPORTS_DIR / 'stage6a_docling_baseline_scorecard.md'}")
    print(f"Results written to {REPORTS_DIR / 'stage6a_docling_baseline_results.json'}")
    print(f"Miss ledger written to {REPORTS_DIR / 'stage6a_docling_miss_ledger.json'}")
    print(f"Evidence alignment catalog written to {STAGE6A_ARTIFACTS_ROOT / 'evidence_alignment.json'}")


if __name__ == "__main__":
    main()
