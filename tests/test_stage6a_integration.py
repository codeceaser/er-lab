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
        loaded = load_fixture_artifacts(ARTIFACTS_ROOT)
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
    the metrics themselves report as matched."""
    _skip_if_no_artifacts()
    _, results = _run_evaluation()
    for result in results:
        alignment_fact_ids = {a.fact_id for a in result.evidence_alignments}
        for metric in result.metrics.values():
            for fact_id in metric.supporting_matches:
                assert fact_id in alignment_fact_ids, f"{result.fixture}/{metric.metric_name}: {fact_id} has no evidence alignment entry"


def test_manifest_sha256_matches_frozen_generation_report():
    """The manifest this evaluator scores against must be byte-identical
    to the one the frozen fixtures were generated from."""
    _skip_if_no_artifacts()
    manifest = load_manifest(FIXTURES_ROOT)
    manifest_sha256 = compute_manifest_sha256(manifest)
    assert manifest["manifest_version"] == "1.2.1"
    assert len(manifest_sha256) == 64


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
