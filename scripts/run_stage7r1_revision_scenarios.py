"""Stage 7R.1/7R.1a/7R.1b runner: replays every scenario in
contracts/revision_authority_scenarios_v2.json against a fresh
InMemoryRevisionAuthorityRepository (never Postgres -- this report never
requires a database) and writes the scorecard/results from one execution.

Never touches Stage 5A/6A/6B/7A.1/7A.2/7A.2a/7A.3 code or artifacts, and
never performs retrieval or answer generation.

Usage (from the repository root, with the venv active):
    python scripts/run_stage7r1_revision_scenarios.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "fixtures"))

from ingestion_bench.revision_authority import config  # noqa: E402
from ingestion_bench.revision_authority.contract_runner import render_scorecard_markdown, run_contract  # noqa: E402


def main() -> None:
    result = run_contract(config.REVISION_AUTHORITY_SCENARIOS_CONTRACT_PATH)

    config.REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    (config.REPORTS_ROOT / "stage7r1_revision_authority_results.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )
    (config.REPORTS_ROOT / "stage7r1_revision_authority_scorecard.md").write_text(
        render_scorecard_markdown(result), encoding="utf-8"
    )

    print(f"Registration checks: {result.registration_checks_passed}/{result.registration_checks_total} passed")
    print(f"Transition checks: {result.transition_checks_passed}/{result.transition_checks_total} passed")
    print(f"Query scenarios: {result.query_scenarios_passed}/{result.query_scenarios_total} passed")
    print(f"All passed: {result.all_passed}")
    if not result.all_passed:
        for q in result.query_scenarios:
            if not q.passed:
                print(f"  FAILED: {q.scenario_id} -- expected {q.expected_eligible_symbols}, got {q.actual_eligible_symbols}")
        for c in result.registration_checks:
            if not c.passed:
                print(f"  FAILED: {c.step_id} -- expected is_new={c.expected_is_new}, got {c.actual_is_new}")
        for t in result.transition_checks:
            if not t.passed:
                print(f"  FAILED: {t.step_id} -- expect_error={t.expect_error}, raised={t.raised}, error={t.error_message}")
    print(f"\nScorecard: {config.REPORTS_ROOT / 'stage7r1_revision_authority_scorecard.md'}")
    print(f"Results: {config.REPORTS_ROOT / 'stage7r1_revision_authority_results.json'}")

    if not result.all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
