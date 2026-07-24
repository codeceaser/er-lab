"""Stage 6A.2b item 4: cross-process determinism tests.

Python's set iteration order for str elements is a function of
PYTHONHASHSEED, randomized per process by default (see
`_score_identifiers`'s former `all_identifiers` set, Stage 6A.2b item 1).
A same-process repeated-call test CANNOT detect this class of bug --
PYTHONHASHSEED is fixed for the lifetime of one process, so two calls in
the same process always see the same (accidental) order. These tests
spawn real CHILD PROCESSES with different PYTHONHASHSEED values and diff
their output byte-for-byte (via parsed JSON equality), which is the only
way to actually exercise hash-seed variance.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
FIXTURES_ROOT = REPO_ROOT / "fixtures"
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "stage5a"
REPORTS_DIR = REPO_ROOT / "reports"


def _skip_if_no_artifacts():
    if not (ARTIFACTS_ROOT / "PARITY_001_pdf" / "canonical_document.json").exists():
        pytest.skip("artifacts/stage5a/ not present -- run scripts/run_docling_standard.py first")
    if not (REPORTS_DIR / "stage5a_docling_standard_results.json").exists():
        pytest.skip("reports/stage5a_docling_standard_results.json not present -- run scripts/run_docling_standard.py first")


def _run_in_subprocess(hashseed: str, code: str) -> str:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hashseed
    env["PYTHONPATH"] = str(SRC_ROOT) + os.pathsep + str(FIXTURES_ROOT)
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, f"subprocess (PYTHONHASHSEED={hashseed}) failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    return result.stdout


# --- focused test around _score_identifiers ---------------------------------

_FOCUSED_IDENTIFIER_SCRIPT = """
import json
from ingestion_bench.evaluation.evaluator import _score_identifiers
from ingestion_bench.evaluation.matcher import TextElement

# Multiple identifiers, each with an extra/unconsumed occurrence in a
# SEPARATE distractor element -- deliberately many entries (not just one)
# so a hash-seed-driven reordering of the pre-fix `all_identifiers` set
# iteration would be very likely to surface across two different
# PYTHONHASHSEED values.
identifiers = ["Z-9", "A-1", "M-5", "Q-3", "B-7", "K-2", "Y-4", "C-6"]
target_facts = [
    {"fact_id": "ID_%d" % i, "normalized_value": ident, "occurrences": [{"raw_text": ident, "source_fact": "P_%d" % i}]}
    for i, ident in enumerate(identifiers)
]
elements = []
matched_element_by_fact_id = {}
for i, ident in enumerate(identifiers):
    # each identifier's OWN source paragraph does NOT contain it (forces a miss)
    e = TextElement("p%d_id" % i, "no mention here at all.", "paragraph", 0)
    elements.append(e)
    matched_element_by_fact_id["P_%d" % i] = e
    # a SEPARATE, unrelated distractor element contains it as an extra occurrence
    elements.append(TextElement("distractor_%d_id" % i, "unrelated mention of %s here." % ident, "paragraph", 0))

metrics, miss_records, unexpected, alignments = _score_identifiers(
    "parity/PARITY_001.pdf", target_facts, [], elements, {}, matched_element_by_fact_id, [], None,
)
payload = [
    {"fixture": u.fixture, "element_id": u.element_id, "element_type": u.element_type, "text": u.text, "reason": u.reason}
    for u in unexpected
]
print(json.dumps(payload))
"""


def test_score_identifiers_unexpected_observations_identical_across_hash_seeds():
    out1 = _run_in_subprocess("1", _FOCUSED_IDENTIFIER_SCRIPT)
    out2 = _run_in_subprocess("2", _FOCUSED_IDENTIFIER_SCRIPT)
    payload1 = json.loads(out1)
    payload2 = json.loads(out2)
    assert payload1 == payload2
    assert len(payload1) >= 8  # one extra occurrence per identifier, at minimum


# --- full-pipeline integration: evaluation_content_hash ---------------------

_FULL_EVALUATION_SCRIPT_TEMPLATE = """
import hashlib
import json
from pathlib import Path

from ingestion_bench.canonical.hashing import compute_manifest_sha256
from ingestion_bench.evaluation.aggregation import build_evaluation_run
from ingestion_bench.evaluation.evaluator import evaluate_fixture, load_fixture_artifacts, load_manifest

fixtures_root = Path(__FIXTURES_ROOT__)
artifacts_root = Path(__ARTIFACTS_ROOT__)
reports_dir = Path(__REPORTS_DIR__)

manifest = load_manifest(fixtures_root)
manifest_sha256 = compute_manifest_sha256(manifest)
stage5a_results_path = reports_dir / "stage5a_docling_standard_results.json"
stage5a_results_bytes = stage5a_results_path.read_bytes()
stage5a_results_sha256 = hashlib.sha256(stage5a_results_bytes).hexdigest()
determinism_by_fixture = json.loads(stage5a_results_bytes).get("determinism_results", {})

loaded = load_fixture_artifacts(artifacts_root, determinism_by_fixture=determinism_by_fixture)
fixture_results = [evaluate_fixture(f, manifest) for f in loaded]
run = build_evaluation_run(fixture_results, manifest, manifest_sha256, stage5a_results_sha256)

# fixture_results carries no runtime metadata of its own (generated_at
# lives only on EvaluationRun, excluded here) -- this is exactly the
# "stable fixture-result JSON excluding runtime metadata" comparison.
stable_fixture_results = [r.model_dump(mode="json") for r in run.fixture_results]
unexpected_by_fixture = {
    r.fixture: [u.model_dump(mode="json") for u in r.unexpected_observations]
    for r in run.fixture_results
}
print(json.dumps({
    "evaluation_content_hash": run.evaluation_content_hash,
    "input_bundle_hash": run.input_bundle_hash,
    "fixture_results": stable_fixture_results,
    "unexpected_observations": unexpected_by_fixture,
}))
"""


def _full_evaluation_script() -> str:
    return (
        _FULL_EVALUATION_SCRIPT_TEMPLATE
        .replace("__FIXTURES_ROOT__", repr(str(FIXTURES_ROOT)))
        .replace("__ARTIFACTS_ROOT__", repr(str(ARTIFACTS_ROOT)))
        .replace("__REPORTS_DIR__", repr(str(REPORTS_DIR)))
    )


def test_full_evaluation_content_hash_and_unexpected_observations_identical_across_hash_seeds():
    """Stage 6A.2b item 4: the complete evaluation pipeline, run against
    the real Stage 5A artifacts, produces byte-identical
    evaluation_content_hash, input_bundle_hash, stable fixture-result
    JSON, and unexpected_observations across two child processes with
    different PYTHONHASHSEED values."""
    _skip_if_no_artifacts()
    script = _full_evaluation_script()
    out1 = _run_in_subprocess("1", script)
    out2 = _run_in_subprocess("2", script)
    payload1 = json.loads(out1)
    payload2 = json.loads(out2)

    assert payload1["input_bundle_hash"] == payload2["input_bundle_hash"]
    assert payload1["evaluation_content_hash"] == payload2["evaluation_content_hash"]
    assert payload1["unexpected_observations"] == payload2["unexpected_observations"]
    assert payload1["fixture_results"] == payload2["fixture_results"]
