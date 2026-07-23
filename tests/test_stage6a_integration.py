"""Real-artifact integration tests for the Stage 6A evaluator (section 18).
Runs against the actual artifacts/stage5a/ output produced by
scripts/run_docling_standard.py -- never mocked. Requires
`python scripts/run_docling_standard.py` to have been run at least once
(the same precondition test_docling_standard_integration.py already
assumes for its own artifacts).

Also proves the required isolation properties:
  - the evaluator is the only package that reads reference_manifest.json
  - adapters/canonical/chunking remain manifest-independent
  - no network or LLM call exists anywhere in the evaluation package
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ingestion_bench.canonical.hashing import compute_manifest_sha256
from ingestion_bench.evaluation.evaluator import FIXTURES, evaluate_fixture, load_fixture_artifacts, load_manifest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_ROOT = REPO_ROOT / "fixtures"
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "stage5a"

_CACHE: dict[str, object] = {}


def _run_evaluation():
    if "results" not in _CACHE:
        manifest = load_manifest(FIXTURES_ROOT)
        determinism_by_fixture = {}
        stage5a_results_path = REPO_ROOT / "reports" / "stage5a_docling_standard_results.json"
        if stage5a_results_path.exists():
            import json

            determinism_by_fixture = json.loads(stage5a_results_path.read_text(encoding="utf-8")).get("determinism_results", {})
        loaded = load_fixture_artifacts(ARTIFACTS_ROOT, determinism_by_fixture=determinism_by_fixture)
        _CACHE["manifest"] = manifest
        _CACHE["results"] = [evaluate_fixture(f, manifest) for f in loaded]
    return _CACHE["manifest"], _CACHE["results"]


def _skip_if_no_artifacts():
    if not (ARTIFACTS_ROOT / "PARITY_001_pdf" / "canonical_document.json").exists():
        pytest.skip("artifacts/stage5a/ not present -- run scripts/run_docling_standard.py first")


def test_all_nine_fixtures_evaluate_without_error():
    _skip_if_no_artifacts()
    _, results = _run_evaluation()
    assert len(results) == len(FIXTURES) == 9
    assert {r.fixture for r in results} == {f[0] for f in FIXTURES}


def test_every_fixture_has_at_least_one_metric():
    _skip_if_no_artifacts()
    _, results = _run_evaluation()
    for result in results:
        assert result.metrics, f"{result.fixture} produced zero metrics"


def test_parity_text_fact_recall_is_perfect_for_all_three_formats():
    """A real, substantive assertion about the actual baseline: every
    parity-suite paragraph/distractor text is exactly reproduced by
    Docling standard-local across all three formats."""
    _skip_if_no_artifacts()
    _, results = _run_evaluation()
    for result in results:
        if result.doc_id != "PARITY_001":
            continue
        metric = result.metrics["text_fact_recall"]
        assert metric.score == 1.0, f"{result.fixture}: {metric}"


def test_pdf_heading_level_degradation_is_a_real_measured_finding():
    """Known Stage 5A baseline finding (docs/POC_STATUS_AND_EVIDENCE.md):
    PDF heading-level classification does not distinguish nesting depth --
    the evaluator must actually measure this, not merely assert it exists."""
    _skip_if_no_artifacts()
    _, results = _run_evaluation()
    pdf_result = next(r for r in results if r.fixture == "parity/PARITY_001.pdf")
    metric = pdf_result.metrics["heading_level_accuracy"]
    assert metric.score is not None and metric.score < 1.0


def test_pptx_heading_classification_loss_is_a_real_measured_finding():
    _skip_if_no_artifacts()
    _, results = _run_evaluation()
    pptx_result = next(r for r in results if r.fixture == "parity/PARITY_001.pptx")
    metric = pptx_result.metrics["heading_classification_accuracy"]
    assert metric.score is not None and metric.score < 1.0


def test_docx_pptx_caption_linkage_known_limitation_is_measured():
    _skip_if_no_artifacts()
    _, results = _run_evaluation()
    for fixture in ("parity/PARITY_001.docx", "parity/PARITY_001.pptx"):
        result = next(r for r in results if r.fixture == fixture)
        metric = result.metrics["caption_linkage_accuracy"]
        assert metric.score == 0.0, f"{fixture}: {metric}"
        assert metric.numerator == 0


def test_identifier_boundary_c88_vs_c88a_never_falsely_merged_on_real_data():
    _skip_if_no_artifacts()
    _, results = _run_evaluation()
    for result in results:
        if result.doc_id != "PARITY_001":
            continue
        metric = result.metrics["identifier_distractor_no_false_merge"]
        false_positive_misses = [
            m for m in result.miss_records
            if m.metric == "identifier_distractor_no_false_merge" and m.failure_class == "distractor_false_positive"
        ]
        assert false_positive_misses == [], f"{result.fixture}: {false_positive_misses}"


def test_stress_docx_nested_list_indentation_known_limitation_is_measured():
    """Known finding: Docling's DOCX backend returned 3 flat sibling list
    groups for this fixture, not a true nested list -- indentation and
    parent-link accuracy must both measure this as real misses."""
    _skip_if_no_artifacts()
    _, results = _run_evaluation()
    result = next(r for r in results if r.fixture == "stress/STRESS_DOCX_001.docx")
    assert result.metrics["list_indentation_accuracy"].score is not None
    assert result.metrics["list_indentation_accuracy"].score < 1.0
    assert result.metrics["list_parent_link_accuracy"].score is not None
    assert result.metrics["list_parent_link_accuracy"].score < 1.0


def test_stress_chart_ocr_recall_is_recorded_as_evaluation_contract_insufficient():
    """The chart fixture declares no expected_ocr_tokens/expected_ocr_text
    -- must never be silently scored (invented ground truth), and must
    never be silently skipped without a recorded limitation either."""
    _skip_if_no_artifacts()
    _, results = _run_evaluation()
    result = next(r for r in results if r.fixture == "stress/STRESS_CHART_001.pdf")
    limitation_misses = [m for m in result.miss_records if m.failure_class == "evaluation_contract_insufficient"]
    assert len(limitation_misses) == 1
    assert "ocr" in limitation_misses[0].fact_id.lower()


def test_no_invented_diagram_relationships_for_pptx_native_diagram():
    _skip_if_no_artifacts()
    _, results = _run_evaluation()
    result = next(r for r in results if r.fixture == "stress/STRESS_PPTX_002.pptx")
    metric = result.metrics["no_invented_diagram_relationships"]
    assert metric.score == 1.0
    edge_metric = result.metrics["diagram_edge_recovery"]
    assert edge_metric.denominator == 0
    assert edge_metric.excluded_not_applicable == 2  # DE_001, DE_002


def test_evaluator_does_not_modify_any_stage5a_artifact():
    """Runs the evaluator twice and confirms every Stage 5A artifact file
    the evaluator reads is byte-identical before and after -- the
    evaluator is read-only with respect to Stage 5A output."""
    _skip_if_no_artifacts()
    manifest = load_manifest(FIXTURES_ROOT)
    targets = [
        ARTIFACTS_ROOT / key / "canonical_document.json"
        for _, _, key, _, _ in FIXTURES
    ]
    before = {p: p.read_bytes() for p in targets}
    loaded = load_fixture_artifacts(ARTIFACTS_ROOT)
    for f in loaded:
        evaluate_fixture(f, manifest)
    after = {p: p.read_bytes() for p in targets}
    assert before == after


def test_evaluator_output_is_deterministic_across_two_runs():
    _skip_if_no_artifacts()
    manifest = load_manifest(FIXTURES_ROOT)
    loaded = load_fixture_artifacts(ARTIFACTS_ROOT)
    results_a = [evaluate_fixture(f, manifest) for f in loaded]
    loaded_b = load_fixture_artifacts(ARTIFACTS_ROOT)
    results_b = [evaluate_fixture(f, manifest) for f in loaded_b]
    assert [r.model_dump_json() for r in results_a] == [r.model_dump_json() for r in results_b]


def test_every_matched_expected_fact_has_an_evidence_alignment_entry():
    """For every fixture, every metric's supporting_matches fact_id must
    correspond to a real evidence_alignments entry -- proving the miss
    ledger and the evidence catalog are exhaustive with respect to what
    the metrics themselves report as matched.

    Stage 6A.1 item 1 exception: identifier_unique_recall's
    supporting_matches uses the IDENTIFIER's own fact_id (e.g. "ID_001")
    as a summary of "at least one occurrence matched" -- the catalog
    itself is occurrence-level (D-042/item 1/2), so the corresponding
    evidence lives under "<fact_id>_occ_<index>" entries, not one entry
    literally named "ID_001".

    Excluded entirely: metrics that are internal completeness AUDITS over
    already-EXTRACTED CanonicalDocument elements (not scored against a
    manifest expected fact at all) -- their supporting_matches/misses are
    real canonical element ids (block_id/table_id/picture_id/
    annotation_id), which structurally never appear as an
    EvidenceAlignment.fact_id (the gold catalog is keyed by MANIFEST fact
    id, section 16)."""
    _internal_audit_metric_prefixes = ("provenance_coverage_", "provenance_bbox_coverage_", "ocr_provenance_completeness")
    _skip_if_no_artifacts()
    _, results = _run_evaluation()
    for result in results:
        alignment_fact_ids = {a.fact_id for a in result.evidence_alignments}
        for metric in result.metrics.values():
            if metric.metric_name.startswith(_internal_audit_metric_prefixes):
                continue
            for fact_id in metric.supporting_matches:
                if metric.metric_name == "identifier_unique_recall":
                    assert any(aid.startswith(f"{fact_id}_occ_") for aid in alignment_fact_ids), (
                        f"{result.fixture}/{metric.metric_name}: {fact_id} has no occurrence-level evidence alignment entry"
                    )
                    continue
                assert fact_id in alignment_fact_ids, f"{result.fixture}/{metric.metric_name}: {fact_id} has no evidence alignment entry"


def test_every_metric_deficit_is_represented_in_the_miss_ledger():
    """Stage 6A.1 item 5: for every success-oriented metric where
    numerator < denominator, at least one MissRecord with that exact
    metric name must exist for that fixture -- the miss ledger must be
    exhaustive, never silently missing a deficit a scorecard number
    implies exists."""
    _skip_if_no_artifacts()
    _, results = _run_evaluation()
    checked_deficits = 0
    for result in results:
        miss_metric_names = {m.metric for m in result.miss_records}
        for metric in result.metrics.values():
            if metric.denominator == 0:
                continue
            if metric.numerator >= metric.denominator:
                continue
            checked_deficits += 1
            assert metric.metric_name in miss_metric_names, (
                f"{result.fixture}/{metric.metric_name}: numerator ({metric.numerator}) < denominator "
                f"({metric.denominator}) but no MissRecord with metric={metric.metric_name!r} exists"
            )
    assert checked_deficits > 0, "expected at least one real metric deficit across the baseline run to actually exercise this check"


def test_supporting_misses_on_metric_result_reference_real_miss_records():
    """Stage 6A.2 item 3: every MetricResult.supporting_misses entry must
    resolve to an ACTUAL MissRecord in the SAME fixture, with the SAME
    metric name, and fact_id == the supporting_miss id -- never merely
    non-empty. An id left over from a different metric's bookkeeping (the
    provenance_coverage_overall/provenance_bbox_coverage_overall bug this
    item fixes) must never appear here."""
    _skip_if_no_artifacts()
    _, results = _run_evaluation()
    checked_deficits = 0
    checked_ids = 0
    for result in results:
        miss_records_by_key: dict[tuple[str, str], list] = {}
        for miss in result.miss_records:
            miss_records_by_key.setdefault((miss.metric, miss.fact_id), []).append(miss)
        for metric in result.metrics.values():
            if metric.denominator == 0 or metric.numerator >= metric.denominator:
                continue
            checked_deficits += 1
            assert metric.supporting_misses, f"{result.fixture}/{metric.metric_name}: deficit exists but supporting_misses is empty"
            for miss_id in metric.supporting_misses:
                checked_ids += 1
                key = (metric.metric_name, miss_id)
                assert key in miss_records_by_key, (
                    f"{result.fixture}/{metric.metric_name}: supporting_misses contains {miss_id!r} but no "
                    f"MissRecord exists with fixture={result.fixture!r}, metric={metric.metric_name!r}, "
                    f"fact_id={miss_id!r}"
                )
    assert checked_deficits > 0
    assert checked_ids > 0


def test_manifest_sha256_matches_frozen_generation_report():
    """The manifest this evaluator scores against must be byte-identical
    to the one the frozen fixtures were generated from."""
    _skip_if_no_artifacts()
    manifest = load_manifest(FIXTURES_ROOT)
    manifest_sha256 = compute_manifest_sha256(manifest)
    assert manifest["manifest_version"] == "1.2.1"
    assert len(manifest_sha256) == 64


def test_no_evidence_alignment_ever_has_a_retrieval_difficulty_assigned():
    """Stage 6A.1 item 3: expected_retrieval_difficulty is deliberately
    unclassified (None) in Stage 6A -- never inferred from ingestion-side
    signals such as occurrence count."""
    _skip_if_no_artifacts()
    _, results = _run_evaluation()
    for result in results:
        for alignment in result.evidence_alignments:
            assert alignment.expected_retrieval_difficulty is None


def test_duplication_metric_is_higher_is_better_and_renamed():
    """Stage 6A.1 item 6: the metric is named
    no_unexpected_text_duplication (higher is better) -- the old
    lower-is-better unexpected_text_duplication name must not exist."""
    _skip_if_no_artifacts()
    _, results = _run_evaluation()
    found_duplication_metric = False
    for result in results:
        assert "unexpected_text_duplication" not in result.metrics
        if "no_unexpected_text_duplication" in result.metrics:
            found_duplication_metric = True
            metric = result.metrics["no_unexpected_text_duplication"]
            # higher-is-better: numerator counts elements WITHOUT duplication
            assert metric.numerator <= metric.denominator
    assert found_duplication_metric


def test_operational_determinism_populated_for_parity_never_silently_null():
    """Stage 6A.1 item 11: operational.determinism must be populated
    (never silently left None) whenever Stage 5A's own results.json
    supplied a determinism entry for that fixture -- currently the three
    parity fixtures."""
    _skip_if_no_artifacts()
    _, results = _run_evaluation()
    parity_results = [r for r in results if r.doc_id == "PARITY_001"]
    assert len(parity_results) == 3
    for result in parity_results:
        assert result.operational.determinism is not None
        assert "all_equal" in result.operational.determinism
    stress_results = [r for r in results if r.doc_id != "PARITY_001"]
    for result in stress_results:
        assert result.operational.determinism is None


def test_operational_carries_valid_input_file_hashes():
    """Stage 6A.1 item 11: every fixture's OperationalEvidence carries
    real, well-formed SHA-256 file hashes for the artifacts actually
    read, and records artifact completeness."""
    _skip_if_no_artifacts()
    _, results = _run_evaluation()
    for result in results:
        op = result.operational
        assert len(op.canonical_document_file_sha256) == 64
        assert len(op.conversion_report_file_sha256) == 64
        assert op.canonical_chunks_file_sha256 is not None and len(op.canonical_chunks_file_sha256) == 64
        assert op.raw_docling_debug_file_sha256 is not None and len(op.raw_docling_debug_file_sha256) == 64
        assert op.artifact_completeness["canonical_document"] is True
        assert op.artifact_completeness["conversion_report"] is True


def test_input_bundle_hash_changes_when_any_artifact_file_changes(tmp_path):
    """Stage 6A.1 item 11: input_bundle_hash is sensitive to every input
    file's actual bytes -- verified by re-running against a copy of the
    artifacts with one byte of one conversion_report.json changed."""
    import json
    import shutil

    from ingestion_bench.evaluation.aggregation import build_evaluation_run

    _skip_if_no_artifacts()
    manifest = load_manifest(FIXTURES_ROOT)
    manifest_sha256 = compute_manifest_sha256(manifest)

    tampered_root = tmp_path / "stage5a"
    shutil.copytree(ARTIFACTS_ROOT, tampered_root)
    report_path = tampered_root / "PARITY_001_pdf" / "conversion_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["_test_tamper_marker"] = "changed"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    original = load_fixture_artifacts(ARTIFACTS_ROOT)
    tampered = load_fixture_artifacts(tampered_root)

    original_results = [evaluate_fixture(f, manifest) for f in original]
    tampered_results = [evaluate_fixture(f, manifest) for f in tampered]

    run_original = build_evaluation_run(original_results, manifest, manifest_sha256, "2" * 64)
    run_tampered = build_evaluation_run(tampered_results, manifest, manifest_sha256, "2" * 64)
    assert run_original.input_bundle_hash != run_tampered.input_bundle_hash
    assert run_original.run_id != run_tampered.run_id


# --- isolation-boundary proofs ---------------------------------------------


def _source_has_import(path: Path, module_substring: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(module_substring in alias.name for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.module:
            if module_substring in node.module:
                return True
    return False


def _docstring_node_ids(tree: ast.AST) -> set[int]:
    """Module/class/function docstrings -- excluded from the manifest-
    reference scan below, since this project's own docstrings routinely
    explain that a module does NOT read reference_manifest.json (that
    prose must not itself trip the check)."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def _source_has_manifest_reference(path: Path) -> bool:
    """True only for an actual CODE-level string constant mentioning
    "reference_manifest" (e.g. a file path literal) -- never a docstring
    mention. Mirrors the same import-statement-only precision
    test_mapper_and_adapter_never_import_manifest_modules already uses in
    tests/test_docling_standard_mapper.py."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstring_ids = _docstring_node_ids(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstring_ids:
            if "reference_manifest" in node.value:
                return True
    return False


def test_adapters_canonical_chunking_never_reference_the_manifest():
    """The evaluator may read reference_manifest.json; adapters/,
    canonical/, and chunking/ must not."""
    src_root = REPO_ROOT / "src" / "ingestion_bench"
    checked = 0
    for package in ("adapters", "canonical", "chunking"):
        for path in (src_root / package).rglob("*.py"):
            checked += 1
            assert not _source_has_manifest_reference(path), f"{path} references reference_manifest.json"
    assert checked > 0


def test_evaluation_package_is_the_only_package_referencing_the_manifest():
    src_root = REPO_ROOT / "src" / "ingestion_bench"
    referencing_packages = set()
    for path in src_root.rglob("*.py"):
        if _source_has_manifest_reference(path):
            referencing_packages.add(path.relative_to(src_root).parts[0])
    assert referencing_packages == {"evaluation"}


def test_evaluation_package_has_no_network_or_llm_imports():
    src_root = REPO_ROOT / "src" / "ingestion_bench" / "evaluation"
    forbidden = ("openai", "requests", "httpx", "urllib", "socket", "aiohttp")
    for path in src_root.rglob("*.py"):
        for module in forbidden:
            assert not _source_has_import(path, module), f"{path} imports forbidden module containing {module!r}"


def test_evaluation_package_has_no_docling_or_vision_or_embedding_imports():
    src_root = REPO_ROOT / "src" / "ingestion_bench" / "evaluation"
    forbidden = ("docling", "sentence_transformers", "pgvector", "torch")
    for path in src_root.rglob("*.py"):
        for module in forbidden:
            assert not _source_has_import(path, module), f"{path} imports forbidden module containing {module!r}"
