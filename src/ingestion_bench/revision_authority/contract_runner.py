"""Stage 7R.1/7R.1a: interpreter for
`contracts/revision_authority_scenarios_v1.json`.

Not a generic contract/plug-in framework -- a one-shot interpreter for
this ONE JSON schema, used by both the scenario runner script and the
pytest suite (so "the contract" and "the scorecard" and "the tests" all
exercise literally the same code path, never three independently-
drifting implementations of the same scenarios).

registry_setup ops: register, activate, reinstate, decide, withdraw,
corrupt_period (a raw, low-level repository write used ONLY to
construct deliberately inconsistent data -- e.g. Scenario L's
overlapping-effective-revisions precondition, which Stage 7R.1a's own
pre-activation validation now correctly prevents via ordinary service
calls). Any step may carry `expect_error: true` (+ optional
`expect_error_substring`) to assert it FAILS -- used for the
cross-document/self-supersession rejection scenarios.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from ingestion_bench.revision_authority.model import AuthorityMetadata, AuthorityPeriod, compute_document_revision_id
from ingestion_bench.revision_authority.repository import InMemoryRevisionAuthorityRepository, RevisionAuthorityRepository
from ingestion_bench.revision_authority.resolver import QueryIntent
from ingestion_bench.revision_authority.service import RevisionAuthorityService

DEFAULT_AUTHORITY_SOURCE = "governance-system"


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value is not None else None


def _parse_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class RegistrationCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    scenario_id: str | None
    symbol: str
    logical_document_id: str
    document_revision_id: str
    expected_is_new: bool
    actual_is_new: bool
    passed: bool


class TransitionCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    scenario_id: str | None
    op: str
    logical_document_id: str
    expect_error: bool
    expect_error_substring: str | None
    raised: bool
    error_message: str | None
    passed: bool


class ExclusionCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    expected_reason_code: str
    actual_reason_code: str | None
    matched: bool


class QueryScenarioResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    description: str
    logical_document_id: str
    query_intent: QueryIntent
    as_of_date: date
    requested_symbols: list[str]

    expected_eligible_symbols: list[str]
    actual_eligible_symbols: list[str]
    expected_excluded: list[ExclusionCheck]
    expected_states: dict[str, str]
    actual_states: dict[str, str | None]
    integrity_error_expected: bool
    expected_integrity_error_code: str | None
    actual_integrity_error: str | None
    actual_integrity_error_code: str | None
    resolution_explanation: str
    registry_snapshot_hash: str
    passed: bool


class ScenarioRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    generated_at: str
    registration_checks: list[RegistrationCheckResult]
    transition_checks: list[TransitionCheckResult]
    query_scenarios: list[QueryScenarioResult]
    registration_checks_passed: int
    registration_checks_total: int
    transition_checks_passed: int
    transition_checks_total: int
    query_scenarios_passed: int
    query_scenarios_total: int
    all_passed: bool


def _run_registry_setup(
    repository: RevisionAuthorityRepository,
    service: RevisionAuthorityService,
    logical_document: dict[str, Any],
    revision_by_symbol: dict[str, dict[str, Any]],
    symbol_to_id: dict[str, str],
    id_to_symbol: dict[str, str],
    registration_checks: list[RegistrationCheckResult],
    transition_checks: list[TransitionCheckResult],
) -> None:
    logical_document_id = logical_document["logical_document_id"]
    for step in logical_document["registry_setup"]:
        op = step["op"]
        recorded_at = _parse_datetime(step["recorded_at"])
        expect_error = step.get("expect_error", False)
        expect_error_substring = step.get("expect_error_substring")

        if op == "register":
            revision = revision_by_symbol[step["symbol"]]
            result = service.register_revision(
                logical_document_id=logical_document_id,
                source_document_sha256=revision["source_document_sha256"],
                version_label=revision["version_label"],
                revision_number=revision["revision_number"],
                authority_source=DEFAULT_AUTHORITY_SOURCE,
                authority_reference=step["step_id"],
                authority_recorded_by="contract-runner",
                recorded_at=recorded_at,
            )
            symbol_to_id[step["symbol"]] = result.identity.document_revision_id
            if result.is_new_revision or result.identity.document_revision_id not in id_to_symbol:
                id_to_symbol[result.identity.document_revision_id] = step["symbol"]
            registration_checks.append(
                RegistrationCheckResult(
                    step_id=step["step_id"], scenario_id=step.get("scenario_id"), symbol=step["symbol"],
                    logical_document_id=logical_document_id, document_revision_id=result.identity.document_revision_id,
                    expected_is_new=step["expected_is_new"], actual_is_new=result.is_new_revision,
                    passed=(result.is_new_revision == step["expected_is_new"]),
                )
            )
            continue

        raised = False
        error_message: str | None = None
        try:
            if op == "activate":
                service.activate_revision(
                    new_revision_id=symbol_to_id[step["new"]],
                    old_revision_id=symbol_to_id[step["old"]] if step["old"] is not None else None,
                    effective_from=_parse_date(step["effective_from"]),
                    authority_source=DEFAULT_AUTHORITY_SOURCE, authority_reference=step["step_id"],
                    authority_recorded_by="contract-runner", recorded_at=recorded_at,
                )
            elif op == "reinstate":
                service.reinstate_revision(
                    new_revision_id=symbol_to_id[step["new"]],
                    old_revision_id=symbol_to_id[step["old"]] if step["old"] is not None else None,
                    effective_from=_parse_date(step["effective_from"]),
                    authority_source=DEFAULT_AUTHORITY_SOURCE, authority_reference=step["step_id"],
                    authority_recorded_by="contract-runner", recorded_at=recorded_at,
                )
            elif op == "decide":
                service.record_authority_decision(
                    document_revision_id=symbol_to_id[step["symbol"]],
                    publication_status=step["publication_status"],
                    authority_source=DEFAULT_AUTHORITY_SOURCE, authority_reference=step["step_id"],
                    authority_recorded_by="contract-runner", recorded_at=recorded_at,
                )
            elif op == "withdraw":
                service.withdraw_revision(
                    document_revision_id=symbol_to_id[step["symbol"]],
                    withdrawal_effective_date=_parse_date(step["withdrawal_effective_date"]),
                    closure_reason=step.get("closure_reason", "withdrawn"),
                    authority_source=DEFAULT_AUTHORITY_SOURCE, authority_reference=step["step_id"],
                    authority_recorded_by="contract-runner", recorded_at=recorded_at,
                )
            elif op == "corrupt_metadata":
                # Raw, low-level repository write -- sets publication_status
                # directly (bypassing record_authority_decision's own
                # "revision must already exist" happy path) so a
                # corrupt_period companion step can construct a SPECIFIC
                # single integrity violation (e.g. overlap) without
                # ALSO tripping the unrelated "draft with a period"
                # violation.
                repository.save_metadata(
                    symbol_to_id[step["symbol"]],
                    AuthorityMetadata(
                        publication_status=step["publication_status"],
                        approved_at=recorded_at,
                        authority_source=DEFAULT_AUTHORITY_SOURCE, authority_reference=step["step_id"],
                        authority_recorded_at=recorded_at, authority_recorded_by="contract-runner",
                    ),
                )
            elif op == "corrupt_period":
                # Raw, low-level repository write -- deliberately bypasses
                # service.py's own validation to construct inconsistent
                # data no ordinary (even careless) service call could
                # produce anymore.
                repository.save_period(
                    AuthorityPeriod(
                        authority_period_id=0, logical_document_id=logical_document_id,
                        document_revision_id=symbol_to_id[step["symbol"]],
                        effective_from=_parse_date(step["effective_from"]), effective_to=_parse_date(step.get("effective_to")),
                        predecessor_revision_id=None, opening_event_id=1,
                        authority_source=DEFAULT_AUTHORITY_SOURCE, authority_reference=step["step_id"],
                        recorded_at=recorded_at, recorded_by="contract-runner",
                    )
                )
            else:
                raise ValueError(f"unknown registry_setup op: {op!r}")
        except Exception as exc:  # noqa: BLE001
            raised = True
            error_message = str(exc)
            if not expect_error:
                raise

        if expect_error:
            passed = raised and (expect_error_substring is None or expect_error_substring in (error_message or ""))
            transition_checks.append(
                TransitionCheckResult(
                    step_id=step["step_id"], scenario_id=step.get("scenario_id"), op=op,
                    logical_document_id=logical_document_id, expect_error=True,
                    expect_error_substring=expect_error_substring, raised=raised, error_message=error_message,
                    passed=passed,
                )
            )


def run_contract(contract_path: Path, service: RevisionAuthorityService | None = None) -> ScenarioRunResult:
    contract = json.loads(Path(contract_path).read_text(encoding="utf-8"))
    repository: RevisionAuthorityRepository
    if service is None:
        repository = InMemoryRevisionAuthorityRepository()
        service = RevisionAuthorityService(repository)
    else:
        repository = service._repository  # type: ignore[attr-defined]

    symbol_to_id: dict[str, str] = {}
    id_to_symbol: dict[str, str] = {}
    registration_checks: list[RegistrationCheckResult] = []
    transition_checks: list[TransitionCheckResult] = []

    for logical_document in contract["logical_documents"]:
        revision_by_symbol = {r["symbol"]: r for r in logical_document["revisions"]}
        for revision in logical_document["revisions"]:
            expected_id = compute_document_revision_id(
                logical_document_id=logical_document["logical_document_id"],
                source_document_sha256=revision["source_document_sha256"],
                version_label=revision["version_label"],
                revision_number=revision["revision_number"],
            )
            revision["_expected_document_revision_id"] = expected_id
        _run_registry_setup(
            repository, service, logical_document, revision_by_symbol, symbol_to_id, id_to_symbol,
            registration_checks, transition_checks,
        )

    query_results: list[QueryScenarioResult] = []
    for scenario in contract["query_scenarios"]:
        requested_ids = [symbol_to_id[s] for s in scenario["requested_symbols"]]
        result = service.resolve_query_scope(
            logical_document_id=scenario["logical_document_id"],
            query_intent=scenario["query_intent"],
            as_of_date=_parse_date(scenario["as_of_date"]),
            requested_revision_ids=requested_ids or None,
        )

        actual_eligible_symbols = sorted(id_to_symbol.get(rid, rid) for rid in result.eligible_revision_ids)
        expected_eligible_symbols = sorted(scenario["expected_eligible_symbols"])

        actual_states = {
            id_to_symbol.get(rid, rid): label.derived_state
            for rid, label in result.authority_labels.items()
            if id_to_symbol.get(rid, rid) in scenario["expected_states"]
        }

        excluded_by_symbol: dict[str, str] = {}
        for exclusion in result.excluded:
            sym = id_to_symbol.get(exclusion.revision_id, exclusion.revision_id)
            excluded_by_symbol.setdefault(sym, exclusion.reason_code)
        exclusion_checks = [
            ExclusionCheck(
                symbol=expected["symbol"], expected_reason_code=expected["reason_code"],
                actual_reason_code=excluded_by_symbol.get(expected["symbol"]),
                matched=(excluded_by_symbol.get(expected["symbol"]) == expected["reason_code"]),
            )
            for expected in scenario["expected_excluded"]
        ]

        passed = (
            actual_eligible_symbols == expected_eligible_symbols
            and actual_states == scenario["expected_states"]
            and (result.integrity_error is not None) == scenario["integrity_error_expected"]
            and result.integrity_error_code == scenario["expected_integrity_error_code"]
            and all(c.matched for c in exclusion_checks)
        )

        query_results.append(
            QueryScenarioResult(
                scenario_id=scenario["scenario_id"], description=scenario["description"],
                logical_document_id=scenario["logical_document_id"], query_intent=scenario["query_intent"],
                as_of_date=_parse_date(scenario["as_of_date"]), requested_symbols=scenario["requested_symbols"],
                expected_eligible_symbols=expected_eligible_symbols, actual_eligible_symbols=actual_eligible_symbols,
                expected_excluded=exclusion_checks, expected_states=scenario["expected_states"], actual_states=actual_states,
                integrity_error_expected=scenario["integrity_error_expected"],
                expected_integrity_error_code=scenario["expected_integrity_error_code"],
                actual_integrity_error=result.integrity_error, actual_integrity_error_code=result.integrity_error_code,
                resolution_explanation=result.resolution_explanation, registry_snapshot_hash=result.registry_snapshot_hash,
                passed=passed,
            )
        )

    reg_passed = sum(1 for c in registration_checks if c.passed)
    trans_passed = sum(1 for c in transition_checks if c.passed)
    query_passed = sum(1 for q in query_results if q.passed)
    return ScenarioRunResult(
        contract_version=contract["contract_version"],
        generated_at=datetime.now(timezone.utc).isoformat(),
        registration_checks=registration_checks,
        transition_checks=transition_checks,
        query_scenarios=query_results,
        registration_checks_passed=reg_passed,
        registration_checks_total=len(registration_checks),
        transition_checks_passed=trans_passed,
        transition_checks_total=len(transition_checks),
        query_scenarios_passed=query_passed,
        query_scenarios_total=len(query_results),
        all_passed=(
            reg_passed == len(registration_checks)
            and trans_passed == len(transition_checks)
            and query_passed == len(query_results)
        ),
    )


def render_scorecard_markdown(result: ScenarioRunResult) -> str:
    reg_rows = "\n".join(
        f"| {c.step_id} | {c.scenario_id or '—'} | {c.symbol} | {c.logical_document_id} | "
        f"{c.expected_is_new} | {c.actual_is_new} | {'PASS' if c.passed else 'FAIL'} |"
        for c in result.registration_checks
    )
    trans_rows = "\n".join(
        f"| {c.step_id} | {c.scenario_id or '—'} | {c.op} | {c.logical_document_id} | "
        f"{c.raised} | {c.error_message or ''} | {'PASS' if c.passed else 'FAIL'} |"
        for c in result.transition_checks
    )
    query_rows = "\n".join(
        f"| {q.scenario_id} | {q.query_intent} | {q.as_of_date} | "
        f"{', '.join(q.actual_eligible_symbols) or '(none)'} | "
        f"{'yes' if q.actual_integrity_error else 'no'} | {'PASS' if q.passed else 'FAIL'} |"
        for q in result.query_scenarios
    )
    detail_sections = "\n\n".join(
        f"### {q.scenario_id}\n\n"
        f"{q.description}\n\n"
        f"- query_intent: `{q.query_intent}`, as_of_date: `{q.as_of_date}`\n"
        f"- requested: `{q.requested_symbols}`\n"
        f"- expected eligible: `{q.expected_eligible_symbols}` / actual: `{q.actual_eligible_symbols}`\n"
        f"- expected exclusions: `{[(c.symbol, c.expected_reason_code) for c in q.expected_excluded]}` / "
        f"actual: `{[(c.symbol, c.actual_reason_code) for c in q.expected_excluded]}`\n"
        f"- expected states: `{q.expected_states}` / actual: `{q.actual_states}`\n"
        f"- integrity_error expected: `{q.integrity_error_expected}` (code `{q.expected_integrity_error_code}`) / "
        f"actual: `{q.actual_integrity_error}` (code `{q.actual_integrity_error_code}`)\n"
        f"- resolution_explanation: {q.resolution_explanation}\n"
        f"- registry_snapshot_hash: `{q.registry_snapshot_hash}`\n"
        f"- **{'PASS' if q.passed else 'FAIL'}**"
        for q in result.query_scenarios
    )

    return f"""# Stage 7R.1/7R.1a -- Revision Authority Scenario Scorecard

Generated from a single in-memory `ScenarioRunResult` -- this Markdown
and `reports/stage7r1_revision_authority_results.json` come from the
SAME execution, replaying `contracts/revision_authority_scenarios_v1.json`
against `InMemoryRevisionAuthorityRepository` (never Postgres -- this
report never requires a database).

`contract_version`: `{result.contract_version}`
`generated_at`: `{result.generated_at}`
`registration_checks`: {result.registration_checks_passed}/{result.registration_checks_total} passed
`transition_checks`: {result.transition_checks_passed}/{result.transition_checks_total} passed
`query_scenarios`: {result.query_scenarios_passed}/{result.query_scenarios_total} passed
`all_passed`: **{result.all_passed}**

## Registration checks (exact-duplicate / new-candidate behavior)

| Step | Scenario | Symbol | Logical document | Expected new | Actual new | Result |
|---|---|---|---|---|---|---|
{reg_rows}

## Transition checks (expected-to-fail validation)

| Step | Scenario | Op | Logical document | Raised | Error | Result |
|---|---|---|---|---|---|---|
{trans_rows}

## Query scenarios

| Scenario | Intent | As of | Eligible | Integrity error | Result |
|---|---|---|---|---|---|
{query_rows}

## Scenario detail

{detail_sections}

## What this report does NOT establish

- Any wiring into Stage 7A.1 retrieval -- this stage never filters or
  reranks a real search result; that is Stage 7R.2, after review.
- Real Postgres persistence -- see the separate, skippable
  `test_real_postgres_revision_authority_repository` integration test
  for that (not exercised by this report).
"""
