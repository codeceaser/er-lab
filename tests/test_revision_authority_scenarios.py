"""Stage 7R.1: named scenario tests driven by the REAL, committed
contract (contracts/revision_authority_scenarios_v1.json) -- the same
contract the scorecard (reports/stage7r1_revision_authority_scorecard.md)
and scripts/run_stage7r1_revision_scenarios.py exercise, via the shared
contract_runner module. This means the contract, the scorecard, and this
test suite can never independently drift -- they are the same code path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion_bench.revision_authority import config
from ingestion_bench.revision_authority.contract_runner import ScenarioRunResult, run_contract

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def scenario_result() -> ScenarioRunResult:
    return run_contract(config.REVISION_AUTHORITY_SCENARIOS_CONTRACT_PATH)


def _scenario(result: ScenarioRunResult, scenario_id: str):
    return next(q for q in result.query_scenarios if q.scenario_id == scenario_id)


def test_contract_file_exists_and_is_loadable():
    assert config.REVISION_AUTHORITY_SCENARIOS_CONTRACT_PATH.exists()


def test_all_contract_registration_checks_pass(scenario_result: ScenarioRunResult):
    """The exact-duplicate/new-candidate assertions embedded in the
    contract's own registry_setup (Scenarios A, B, F, N) all hold."""
    failed = [c for c in scenario_result.registration_checks if not c.passed]
    assert not failed, f"registration checks failed: {[c.step_id for c in failed]}"


def test_newer_draft_does_not_replace_effective_revision(scenario_result: ScenarioRunResult):
    """Business nuance: Scenario C -- a draft (v4, proposing a 10-year
    retention period) coexists with the current effective revision (v3,
    7-year retention) without ever displacing it. Failure this guards
    against: any code path that treats 'a newer revision exists' as
    sufficient for currency, regardless of its own review status.
    Affects: current search -- a default query must never surface
    unreviewed content."""
    scenario = _scenario(scenario_result, "C_newer_draft_does_not_replace")
    assert scenario.passed
    assert scenario.actual_eligible_symbols == ["v3"]
    assert scenario.actual_states["v4"] == "draft"


def test_approved_future_is_ineligible_before_effective_date(scenario_result: ScenarioRunResult):
    """Business nuance: Scenario D -- v5 is fully approved with a real
    future effective_from (2028-01-01); one day before that date
    (2027-12-31) it must still be excluded, and v3 must still be the
    sole eligible revision. Failure this guards against: approval alone
    (without regard to the effective date) being mistaken for currency.
    Affects: current search directly."""
    scenario = _scenario(scenario_result, "D_approved_future_not_early")
    assert scenario.passed
    assert scenario.actual_eligible_symbols == ["v3"]
    assert scenario.actual_states["v5"] == "approved_future"


def test_approved_future_becomes_effective_on_boundary_date(scenario_result: ScenarioRunResult):
    """Business nuance: Scenario E -- on the EXACT effective_from date
    (2028-01-01), v5 flips to effective and v3 flips to superseded in
    the same query -- no lag, no separate 'activation' event needs to
    fire at that moment (the single activate_revision call already
    recorded both sides atomically, in advance). Failure this guards
    against: a scheduled/background-job model of activation that could
    be late, missed, or run twice. Affects: current search directly, on
    the exact day authority changes hands."""
    scenario = _scenario(scenario_result, "E_supersession_boundary_on")
    assert scenario.passed
    assert scenario.actual_eligible_symbols == ["v5"]
    assert scenario.actual_states["v3"] == "superseded"


def test_late_uploaded_old_revision_does_not_become_current(scenario_result: ScenarioRunResult):
    """Business nuance: Scenario F -- v0_late_upload is registered on
    2026-06-01 (long after v3 became effective in 2023) but never
    approved/activated; a query the very next day must still resolve
    v3, never v0_late_upload. Failure this guards against: any
    'most-recently-registered' or 'newest-by-timestamp' heuristic
    substituting for an actual governance decision. Affects: current
    search directly."""
    scenario = _scenario(scenario_result, "F_late_upload_old_revision")
    assert scenario.passed
    assert scenario.actual_eligible_symbols == ["v3"]
    assert scenario.actual_states["v0_late_upload"] == "draft"


def test_current_authoritative_query_scenario(scenario_result: ScenarioRunResult):
    assert _scenario(scenario_result, "G_current_authoritative_query").passed


def test_historical_as_of_query_scenario(scenario_result: ScenarioRunResult):
    assert _scenario(scenario_result, "H_historical_as_of_query").passed


def test_explicit_comparison_query_scenario(scenario_result: ScenarioRunResult):
    assert _scenario(scenario_result, "I_explicit_comparison_query").passed


def test_explicit_draft_query_scenario(scenario_result: ScenarioRunResult):
    assert _scenario(scenario_result, "J_explicit_draft_query").passed


def test_withdrawn_no_replacement_scenario_fails_closed(scenario_result: ScenarioRunResult):
    scenario = _scenario(scenario_result, "K_withdrawn_no_replacement")
    assert scenario.passed
    assert scenario.actual_integrity_error is not None


def test_overlapping_effective_revisions_scenario_fails_closed(scenario_result: ScenarioRunResult):
    scenario = _scenario(scenario_result, "L_overlapping_effective_revisions")
    assert scenario.passed
    assert scenario.actual_integrity_error is not None


def test_authority_correction_rollback_scenario(scenario_result: ScenarioRunResult):
    """Business nuance: Scenario M -- v6's approval is corrected back to
    draft via a SECOND authority decision, and the correction is visible
    purely by re-querying (comparison intent) after the fact; v3/v5's
    own effective windows are provably untouched (their states are
    identical to Scenario I/D's own results). Affects: auditability."""
    scenario = _scenario(scenario_result, "M_authority_correction_rollback")
    assert scenario.passed
    assert scenario.actual_states["v6_rollback_demo"] == "draft"
    assert scenario.actual_states["v3"] == "effective"


def test_same_text_different_identity_scenario(scenario_result: ScenarioRunResult):
    scenario = _scenario(scenario_result, "N_same_text_different_identity")
    assert scenario.passed


def test_boundary_day_before_scenario(scenario_result: ScenarioRunResult):
    assert _scenario(scenario_result, "O_boundary_day_before").passed


def test_all_query_scenarios_pass(scenario_result: ScenarioRunResult):
    failed = [q.scenario_id for q in scenario_result.query_scenarios if not q.passed]
    assert not failed, f"query scenarios failed: {failed}"
    assert scenario_result.all_passed
