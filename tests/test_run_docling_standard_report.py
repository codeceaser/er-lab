"""Stage 5A.1 item 7: reports/stage5a_docling_standard_results.json and
reports/stage5a_docling_standard_baseline.md must come from ONE in-memory
results object, never two separate executions. Tested here as a pure
function of render_baseline_markdown(results) against a synthetic results
dict -- no real Docling conversion needed to prove report consistency.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from run_docling_standard import render_baseline_markdown  # noqa: E402


def _synthetic_results() -> dict:
    fixture_a = {
        "fixture": "parity/PARITY_001.pdf", "conversion_status": "success", "elapsed_ms": 1234.5,
        "unit_count": 2, "heading_count": 3, "paragraph_count": 7, "list_item_count": 0,
        "table_count": 1, "table_cell_count": 8, "picture_count": 1, "caption_count": 1,
        "annotation_counts": {"ocr": {"extracted": 3}}, "provenance_count": 13,
        "canonical_chunk_count": 3, "textual_chunk_count": 1, "asset_only_chunk_count": 0,
        "diagnostics": [],
    }
    fixture_b = {
        "fixture": "parity/PARITY_001.docx", "conversion_status": "partial", "elapsed_ms": 295.2,
        "unit_count": 1, "heading_count": 3, "paragraph_count": 11, "list_item_count": 0,
        "table_count": 1, "table_cell_count": 8, "picture_count": 1, "caption_count": 0,
        "annotation_counts": {}, "provenance_count": 16,
        "canonical_chunk_count": 5, "textual_chunk_count": 3, "asset_only_chunk_count": 1,
        "diagnostics": [
            {"category": "docx_pagination_unavailable", "severity": "info", "message": "m", "docling_self_ref": None, "unit_index": 0, "affects_fidelity": True},
        ],
    }
    determinism_all_equal = {
        "canonical_json_equal": True, "canonical_hash_equal": True,
        "chunk_json_equal": True, "chunk_ids_equal": True,
        "chunk_content_hashes_equal": True, "all_equal": True,
    }
    determinism_partial_mismatch = {
        "canonical_json_equal": False, "canonical_hash_equal": True,
        "chunk_json_equal": True, "chunk_ids_equal": True,
        "chunk_content_hashes_equal": True, "all_equal": False,
    }

    return {
        "docling_version": "2.114.0",
        "docling_core_version": "2.87.1",
        "effective_configuration": {"accelerator_device": "cpu", "enable_remote_services": False},
        "environment_evidence": {
            "python_version": "3.13.9",
            "os_platform": "Windows-11",
            "docling_version": "2.114.0",
            "docling_core_version": "2.87.1",
            "torch_version": "2.13.0",
            "torchvision_version": "0.28.0",
            "onnxruntime_version": "1.27.0",
            "rapidocr_version": "3.9.2",
            "cuda_available": False,
            "effective_accelerator_device": "cpu",
            "external_hf_cache_configured": True,
            "redacted_hf_cache_location": "D: (redirected, path redacted)",
            "downloaded_model_families": ["docling-project/docling-layout-heron", "docling-project/docling-models"],
            "approx_model_storage_footprint_mb": 506,
        },
        "total_fixtures": 2,
        "total_elapsed_seconds": 12.34,
        "status_counts": {"success": 1, "partial": 1},
        "diagnostics_by_category": {"docx_pagination_unavailable": 1},
        "diagnostics_by_severity": {"info": 1},
        "diagnostics_by_affects_fidelity": {"fidelity_affecting": 1, "non_fidelity_affecting": 0},
        "determinism_results": {
            "parity/PARITY_001.pdf": determinism_all_equal,
            "parity/PARITY_001.docx": determinism_partial_mismatch,
        },
        "fixtures": [fixture_a, fixture_b],
    }


def test_baseline_markdown_reflects_the_same_results_object():
    results = _synthetic_results()
    markdown = render_baseline_markdown(results)

    assert "2.114.0" in markdown
    assert "2.87.1" in markdown

    for fixture in results["fixtures"]:
        assert fixture["fixture"] in markdown
        assert fixture["conversion_status"] in markdown
        assert f"{fixture['elapsed_ms']}ms" in markdown

    assert f"**{results['total_elapsed_seconds']} seconds.**" in markdown
    assert "`success`: 1" in markdown
    assert "`partial`: 1" in markdown
    assert "`docx_pagination_unavailable`" in markdown
    assert "1 fidelity-affecting" in markdown
    assert "0 non-fidelity-affecting" in markdown
    assert markdown.count("\n") > 0  # sanity: this is multi-line markdown, not a repr

    # Stage 5A.2 item 3: restored environment evidence must appear verbatim.
    env = results["environment_evidence"]
    for value in (
        env["python_version"], env["os_platform"], env["torch_version"],
        env["torchvision_version"], env["onnxruntime_version"], env["rapidocr_version"],
        env["redacted_hf_cache_location"],
    ):
        assert str(value) in markdown
    assert "False" in markdown  # cuda_available
    for family in env["downloaded_model_families"]:
        assert family in markdown
    assert f"~{env['approx_model_storage_footprint_mb']} MB" in markdown


def test_baseline_markdown_reflects_structured_determinism_results():
    """Stage 5A.2 item 2: every determinism sub-comparison is reported
    individually, and a partial mismatch (all_equal=False despite most
    sub-comparisons passing) must be visible as a failure, never
    collapsed into a misleading overall pass."""
    results = _synthetic_results()
    markdown = render_baseline_markdown(results)

    assert "Canonical JSON equal" in markdown
    assert "Canonical hash equal" in markdown
    assert "Chunk JSON equal" in markdown
    assert "Chunk IDs equal" in markdown
    assert "Chunk content hashes equal" in markdown
    assert "All equal" in markdown

    determinism_section = markdown.split("## 4. Determinism results", 1)[1].split("## 5.", 1)[0]
    determinism_lines = determinism_section.splitlines()

    docx_row = next(line for line in determinism_lines if line.startswith("| parity/PARITY_001.docx |"))
    assert docx_row.count("**NO**") == 2  # canonical_json_equal and all_equal are False
    assert docx_row.count("**Yes**") == 4

    pdf_row = next(line for line in determinism_lines if line.startswith("| parity/PARITY_001.pdf |"))
    assert "**NO**" not in pdf_row
    assert pdf_row.count("**Yes**") == 6


def test_baseline_markdown_never_contains_an_absolute_windows_path():
    results = _synthetic_results()
    markdown = render_baseline_markdown(results)
    assert "C:\\" not in markdown
    assert "C:/Users" not in markdown
