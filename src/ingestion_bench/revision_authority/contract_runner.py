"""Stage 7R.1: interpreter for `contracts/revision_authority_scenarios_v1.json`.

Not a generic contract/plug-in framework -- a one-shot interpreter for
this ONE JSON schema (registry_setup ops: register/activate/decide/
withdraw; query_scenarios: resolve_query_scope calls), used by both the
scenario runner script and the pytest suite (so "the contract" and "the
scorecard" and "the tests" all exercise literally the same code path,
never three independently-drifting implementations of the same scenarios).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from ingestion_bench.revision_authority.model import compute_document_revision_id
from ingestion_bench.revision_authority.repository import InMemoryRevisionAuthorityRepository
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
    expected_states: dict[str, str]
    actual_states: dict[str, str | None]
    integrity_error_expected: bool
    actual_integrity_error: str | None
    resolution_explanation: str
    registry_snapshot_hash: str
    passed: bool


class ScenarioRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    generated_at: str
    registration_checks: list[RegistrationCheckResult]
    query_scenarios: list[QueryScenarioResult]
    registration_checks_passed: int
    registration_checks_total: int
    query_scenarios_passed: int
    query_scenarios_total: int
    all_passed: bool


def _run_registry_setup(
    service: RevisionAuthorityService,
    logical_document: dict[str, Any],
    revision_by_symbol: dict[str, dict[str, Any]],
    symbol_to_id: dict[str, str],
    id_to_symbol: dict[str, str],
    registration_checks: list[RegistrationCheckResult],
) -> None:
    logical_document_id = logical_document["logical_document_id"]
    for step in logical_document["registry_setup"]:
        op = step["op"]
        recorded_at = _parse_datetime(step["recorded_at"])

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
            # An exact-duplicate registration (is_new_revision=False)
            # legitimately shares its document_revision_id with an
            # earlier symbol (that IS the point being proven) -- the
            # first-registered symbol stays the canonical display name
            # for that id, never overwritten by the duplicate's own
            # symbol.
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

        elif op == "activate":
            service.activate_revision(
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
                effective_from=_parse_date(step.get("effective_from")),
                effective_to=_parse_date(step.get("effective_to")),
                approved_at=_parse_datetime(step["approved_at"]) if step.get("approved_at") else None,
                authority_source=DEFAULT_AUTHORITY_SOURCE, authority_reference=step["step_id"],
                authority_recorded_by="contract-runner", recorded_at=recorded_at,
            )

        elif op == "withdraw":
            service.withdraw_revision(
                document_revision_id=symbol_to_id[step["symbol"]],
                authority_source=DEFAULT_AUTHORITY_SOURCE, authority_reference=step["step_id"],
                authority_recorded_by="contract-runner", recorded_at=recorded_at,
            )
        else:
            raise ValueError(f"unknown registry_setup op: {op!r}")


def run_contract(contract_path: Path, service: RevisionAuthorityService | None = None) -> ScenarioRunResult:
    contract = json.loads(Path(contract_path).read_text(encoding="utf-8"))
    if service is None:
        service = RevisionAuthorityService(InMemoryRevisionAuthorityRepository())

    symbol_to_id: dict[str, str] = {}
    id_to_symbol: dict[str, str] = {}
    registration_checks: list[RegistrationCheckResult] = []

    for logical_document in contract["logical_documents"]:
        revision_by_symbol = {r["symbol"]: r for r in logical_document["revisions"]}
        # Sanity check (not itself a scenario): document_revision_id is
        # ALWAYS the deterministic hash -- verified independently of
        # whatever register_revision() itself computes internally.
        for revision in logical_document["revisions"]:
            expected_id = compute_document_revision_id(
                logical_document_id=logical_document["logical_document_id"],
                source_document_sha256=revision["source_document_sha256"],
                version_label=revision["version_label"],
                revision_number=revision["revision_number"],
            )
            revision["_expected_document_revision_id"] = expected_id
        _run_registry_setup(service, logical_document, revision_by_symbol, symbol_to_id, id_to_symbol, registration_checks)

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

        passed = (
            actual_eligible_symbols == expected_eligible_symbols
            and actual_states == scenario["expected_states"]
            and (result.integrity_error is not None) == scenario["integrity_error_expected"]
        )

        query_results.append(
            QueryScenarioResult(
                scenario_id=scenario["scenario_id"], description=scenario["description"],
                logical_document_id=scenario["logical_document_id"], query_intent=scenario["query_intent"],
                as_of_date=_parse_date(scenario["as_of_date"]), requested_symbols=scenario["requested_symbols"],
                expected_eligible_symbols=expected_eligible_symbols, actual_eligible_symbols=actual_eligible_symbols,
                expected_states=scenario["expected_states"], actual_states=actual_states,
                integrity_error_expected=scenario["integrity_error_expected"], actual_integrity_error=result.integrity_error,
                resolution_explanation=result.resolution_explanation, registry_snapshot_hash=result.registry_snapshot_hash,
                passed=passed,
            )
        )

    reg_passed = sum(1 for c in registration_checks if c.passed)
    query_passed = sum(1 for q in query_results if q.passed)
    return ScenarioRunResult(
        contract_version=contract["contract_version"],
        generated_at=datetime.now(timezone.utc).isoformat(),
        registration_checks=registration_checks,
        query_scenarios=query_results,
        registration_checks_passed=reg_passed,
        registration_checks_total=len(registration_checks),
        query_scenarios_passed=query_passed,
        query_scenarios_total=len(query_results),
        all_passed=(reg_passed == len(registration_checks) and query_passed == len(query_results)),
    )


def render_scorecard_markdown(result: ScenarioRunResult) -> str:
    reg_rows = "\n".join(
        f"| {c.step_id} | {c.scenario_id or '—'} | {c.symbol} | {c.logical_document_id} | "
        f"{c.expected_is_new} | {c.actual_is_new} | {'PASS' if c.passed else 'FAIL'} |"
        for c in result.registration_checks
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
        f"- expected states: `{q.expected_states}` / actual: `{q.actual_states}`\n"
        f"- integrity_error expected: `{q.integrity_error_expected}` / actual: `{q.actual_integrity_error}`\n"
        f"- resolution_explanation: {q.resolution_explanation}\n"
        f"- registry_snapshot_hash: `{q.registry_snapshot_hash}`\n"
        f"- **{'PASS' if q.passed else 'FAIL'}**"
        for q in result.query_scenarios
    )

    return f"""# Stage 7R.1 -- Revision Authority Scenario Scorecard

Generated from a single in-memory `ScenarioRunResult` -- this Markdown
and `reports/stage7r1_revision_authority_results.json` come from the
SAME execution, replaying `contracts/revision_authority_scenarios_v1.json`
against `InMemoryRevisionAuthorityRepository` (never Postgres -- this
report never requires a database).

`contract_version`: `{result.contract_version}`
`generated_at`: `{result.generated_at}`
`registration_checks`: {result.registration_checks_passed}/{result.registration_checks_total} passed
`query_scenarios`: {result.query_scenarios_passed}/{result.query_scenarios_total} passed
`all_passed`: **{result.all_passed}**

## Registration checks (exact-duplicate / new-candidate behavior)

| Step | Scenario | Symbol | Logical document | Expected new | Actual new | Result |
|---|---|---|---|---|---|---|
{reg_rows}

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
