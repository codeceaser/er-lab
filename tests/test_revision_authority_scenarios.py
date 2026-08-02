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


def test_historical_as_of_before_withdrawal_still_resolves_effective(scenario_result: ScenarioRunResult):
    """Business nuance (item 2/7): an as_of date BEFORE the withdrawal
    date, still within the old (now-closed) period, must resolve
    effective -- withdrawal is never retroactive. Affects: historical
    search directly."""
    scenario = _scenario(scenario_result, "H2_historical_as_of_before_withdrawal")
    assert scenario.passed
    assert scenario.actual_eligible_symbols == ["w1"]
    assert scenario.actual_states["w1"] == "effective"


def test_withdrawn_no_replacement_scenario_fails_closed(scenario_result: ScenarioRunResult):
    """Business nuance (item 2/7): current/as_of ON/AFTER the withdrawal
    date fails closed -- never a silent empty success. Affects: current
    search."""
    scenario = _scenario(scenario_result, "K_withdrawn_no_replacement")
    assert scenario.passed
    assert scenario.actual_integrity_error is not None
    assert scenario.actual_integrity_error_code == "no_effective_revision"


def test_overlapping_effective_revisions_scenario_fails_closed(scenario_result: ScenarioRunResult):
    scenario = _scenario(scenario_result, "L_overlapping_effective_revisions")
    assert scenario.passed
    assert scenario.actual_integrity_error is not None
    assert scenario.actual_integrity_error_code == "overlapping_effective_revisions"


def test_pre_effective_authority_correction_scenario(scenario_result: ScenarioRunResult):
    """Business nuance (item 3, renamed from Stage 7R.1's 'M'): v6 was
    approved-future then RETRACTED (closure_reason=correction, a
    zero-width period) before it ever took effect -- comparison shows it
    back in draft. Affects: auditability."""
    scenario = _scenario(scenario_result, "M_pre_effective_authority_correction")
    assert scenario.passed
    assert scenario.actual_states["v6_rollback_demo"] == "draft"


def test_post_effective_rollback_before_during_after(scenario_result: ScenarioRunResult):
    """Business nuance (item 3): the full post-effective rollback/
    reinstatement timeline in ONE test -- rv3 effective from 2023,
    superseded by rv5 from 2028, rv5 rolled back and rv3 REINSTATED
    (a second, disjoint authority period) from 2028-06-01. Failure this
    guards against: reinstatement silently overwriting/destroying rv3's
    EARLIER period, or the resolver being unable to represent a revision
    effective, then not, then effective again. Affects: current search
    and historical search (both periods must resolve correctly for
    their own date ranges)."""
    before = _scenario(scenario_result, "E2_post_effective_rollback_before")
    during = _scenario(scenario_result, "E2_post_effective_rollback_during")
    after = _scenario(scenario_result, "E2_post_effective_rollback_after")
    assert before.passed and before.actual_eligible_symbols == ["rv3"]
    assert during.passed and during.actual_eligible_symbols == ["rv5"]
    assert after.passed and after.actual_eligible_symbols == ["rv3"]


def test_under_review_requested_through_draft_intent(scenario_result: ScenarioRunResult):
    """Business nuance (item 7): under_review is ALSO a legitimate
    draft-intent result, not just 'draft' itself -- both pre-approval
    states share the same "never mixed into current results" treatment.
    Affects: current search (neither state may leak into default
    results) and auditability (a reviewer's queue should show both)."""
    scenario = _scenario(scenario_result, "J2_under_review_via_draft_intent")
    assert scenario.passed
    assert scenario.actual_eligible_symbols == ["v4_under_review"]
    assert scenario.actual_states["v4_under_review"] == "under_review"


def test_malformed_comparison_record_fails_closed_individually(scenario_result: ScenarioRunResult):
    """Business nuance (item 6/7): a revision with a genuine integrity
    violation (draft status + a real period) is EXCLUDED individually
    under comparison intent -- with reason_code=malformed_authority_record
    -- never returned as if it had a normal label, and never aborting
    the whole query. Affects: auditability."""
    scenario = _scenario(scenario_result, "malformed_record_excluded_not_fatal_comparison")
    assert scenario.passed
    assert scenario.actual_eligible_symbols == []
    assert scenario.actual_integrity_error is None


def test_malformed_draft_record_fails_closed_individually(scenario_result: ScenarioRunResult):
    scenario = _scenario(scenario_result, "malformed_record_excluded_not_fatal_draft")
    assert scenario.passed
    assert scenario.actual_eligible_symbols == []
    assert scenario.actual_integrity_error is None


def test_duplicate_requested_revision_ids_rejected_scenario(scenario_result: ScenarioRunResult):
    """Business nuance (item 6/7): requesting the same revision twice
    yields exactly one eligible entry plus one duplicate_request
    exclusion -- never two eligible entries. Affects: auditability (a
    caller bug must be visible, not silently doubled)."""
    scenario = _scenario(scenario_result, "duplicate_requested_revision_ids_rejected")
    assert scenario.passed
    assert scenario.actual_eligible_symbols == ["v3"]


def test_same_text_different_identity_scenario(scenario_result: ScenarioRunResult):
    scenario = _scenario(scenario_result, "N_same_text_different_identity")
    assert scenario.passed


def test_boundary_day_before_scenario(scenario_result: ScenarioRunResult):
    assert _scenario(scenario_result, "O_boundary_day_before").passed


def _transition(result: ScenarioRunResult, step_id: str):
    return next(t for t in result.transition_checks if t.step_id == step_id)


def test_self_supersession_rejected_scenario(scenario_result: ScenarioRunResult):
    """Business nuance (item 5/7): a revision cannot supersede itself --
    proven here as a contract-driven expected-failure step, the same
    code path the scorecard itself reports. Affects: current search and
    auditability."""
    check = _transition(scenario_result, "self_supersede_val1")
    assert check.passed
    assert check.raised


def test_cross_document_activation_rejected_scenario(scenario_result: ScenarioRunResult):
    """Business nuance (item 5/7): activation cannot supersede a
    revision belonging to another logical document -- proven here as a
    contract-driven expected-failure step. Affects: current search and
    auditability."""
    check = _transition(scenario_result, "cross_doc_val1")
    assert check.passed
    assert check.raised


def test_all_transition_checks_pass(scenario_result: ScenarioRunResult):
    failed = [c.step_id for c in scenario_result.transition_checks if not c.passed]
    assert not failed, f"transition checks failed: {failed}"


def test_all_query_scenarios_pass(scenario_result: ScenarioRunResult):
    failed = [q.scenario_id for q in scenario_result.query_scenarios if not q.passed]
    assert not failed, f"query scenarios failed: {failed}"
    assert scenario_result.all_passed
