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
    return {
        "docling_version": "2.114.0",
        "docling_core_version": "2.87.1",
        "effective_configuration": {"accelerator_device": "cpu", "enable_remote_services": False},
        "total_fixtures": 2,
        "total_elapsed_seconds": 12.34,
        "status_counts": {"success": 1, "partial": 1},
        "diagnostics_by_category": {"docx_pagination_unavailable": 1},
        "diagnostics_by_severity": {"info": 1},
        "diagnostics_by_affects_fidelity": {"fidelity_affecting": 1, "non_fidelity_affecting": 0},
        "determinism_results": {"parity/PARITY_001.pdf": True, "parity/PARITY_001.docx": True},
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


def test_baseline_markdown_never_contains_an_absolute_windows_path():
    results = _synthetic_results()
    markdown = render_baseline_markdown(results)
    assert "C:\\" not in markdown
    assert "C:/Users" not in markdown
