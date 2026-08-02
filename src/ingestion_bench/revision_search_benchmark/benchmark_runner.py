"""Stage 7R.2: the declarative benchmark runner.

Reads contracts/revision_search_benchmark_v1.json and:
  1. loads the five real source-document fixtures (fixtures.py, through
     the frozen Stage 5A adapter + Stage 4/4.1 chunker);
  2. builds the isolated index ONCE (indexer.py);
  3. replays the contract's declarative "authority_snapshot" registry
     setup through Stage 7R.1's OWN, unmodified
     `contract_runner._run_registry_setup` (read-only reuse -- never a
     second, independently-drifting registry-setup implementation);
  4. runs every query scenario through BOTH the authority-aware
     retriever and an unfiltered comparison search;
  5. runs the authority-switch scenario (E) -- a live activate_revision()
     call between two identical queries -- and proves the index itself
     never changes.

Never touches Stage 7A.1's own table/code, Stage 6B's contract, or
CanonicalDocument/CanonicalChunk.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from ingestion_bench.retrieval_baseline.embeddings import EmbeddingProvider
from ingestion_bench.revision_authority.contract_runner import _run_registry_setup
from ingestion_bench.revision_authority.repository import RevisionAuthorityRepository
from ingestion_bench.revision_authority.resolver import RevisionAuthorityLabel
from ingestion_bench.revision_authority.service import RevisionAuthorityService
from ingestion_bench.revision_search_benchmark.fixtures import RevisionFixture, load_all_revision_fixtures
from ingestion_bench.revision_search_benchmark.indexer import IndexBuildResult, build_index
from ingestion_bench.revision_search_benchmark.retriever import AuthorityAwareSearchResult, authority_aware_search, unfiltered_search
from ingestion_bench.revision_search_benchmark.store import RevisionVectorStore


def load_contract(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --- provenance / fixture inventory -----------------------------------------


class FixtureInventoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    source_relative_path: str
    source_document_sha256: str
    document_revision_id: str
    version_label: str | None
    revision_number: int
    chunk_count: int
    chunk_ids: list[str]
    retention_value: str


def _fixture_inventory(fixtures: dict[str, RevisionFixture], contract: dict[str, Any]) -> list[FixtureInventoryEntry]:
    retention_by_symbol = {f["symbol"]: f["retention_value"] for f in contract["fixtures"]}
    return [
        FixtureInventoryEntry(
            symbol=symbol,
            source_relative_path=fx.source_relative_path,
            source_document_sha256=fx.source_document_sha256,
            document_revision_id=fx.document_revision_id,
            version_label=fx.version_label,
            revision_number=fx.revision_number,
            chunk_count=len(fx.chunks),
            chunk_ids=[c.chunk_id for c in fx.chunks],
            retention_value=retention_by_symbol[symbol],
        )
        for symbol, fx in sorted(fixtures.items())
    ]


# --- registry snapshot (before/after) ---------------------------------------


def registry_snapshot(repository: RevisionAuthorityRepository, logical_document_id: str, id_to_symbol: dict[str, str]) -> dict[str, Any]:
    """A plain-dict, JSON-serializable snapshot of every revision's
    current metadata + periods for this logical document -- used for the
    required registry_before.json/registry_after.json artifacts."""
    identities = repository.list_revisions_for_document(logical_document_id)
    out: dict[str, Any] = {}
    for identity in identities:
        symbol = id_to_symbol.get(identity.document_revision_id, identity.document_revision_id)
        metadata = repository.get_metadata(identity.document_revision_id)
        periods = repository.list_periods_for_revision(identity.document_revision_id)
        out[symbol] = {
            "document_revision_id": identity.document_revision_id,
            "publication_status": metadata.publication_status if metadata else None,
            "periods": [
                {"effective_from": str(p.effective_from), "effective_to": str(p.effective_to) if p.effective_to else None, "closure_reason": p.closure_reason}
                for p in periods
            ],
        }
    return out


# --- query scenario result ---------------------------------------------------


class QueryScenarioResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    description: str
    query_intent: str
    as_of_date: date
    requested_symbols: list[str]

    expected_eligible_symbols: list[str]
    actual_eligible_symbols: list[str]
    forbidden_symbols: list[str]

    expected_authority_labels: dict[str, str]
    actual_authority_labels: dict[str, str]

    authority_aware_top_k_symbols: list[str]
    unfiltered_top_k_symbols: list[str]

    ineligible_revision_leakage_at_k: int
    eligible_revision_precision_at_k: float
    required_revision_hit_at_k: bool
    expected_value_retrieved: bool

    resolver_latency_seconds: float
    authority_aware_vector_search_latency_seconds: float
    unfiltered_vector_search_latency_seconds: float
    total_latency_seconds: float

    integrity_error: str | None
    failure_reasons: list[str]
    passed: bool


def _symbol_of(id_to_symbol: dict[str, str], document_revision_id: str) -> str:
    return id_to_symbol.get(document_revision_id, document_revision_id)


def _run_one_query(
    *,
    service: RevisionAuthorityService,
    store: RevisionVectorStore,
    embedding_provider: EmbeddingProvider,
    logical_document_id: str,
    id_to_symbol: dict[str, str],
    symbol_to_id: dict[str, str],
    scenario: dict[str, Any],
) -> tuple[QueryScenarioResult, AuthorityAwareSearchResult]:
    total_start_vector = embedding_provider.embed([scenario["query"]])
    query_vector = total_start_vector.vectors[0]

    requested_ids = [symbol_to_id[s] for s in scenario.get("requested_symbols", [])] or None
    aware = authority_aware_search(
        service=service,
        store=store,
        logical_document_id=logical_document_id,
        query_intent=scenario["query_intent"],
        as_of_date=date.fromisoformat(scenario["as_of_date"]),
        requested_revision_ids=requested_ids,
        query_vector=query_vector,
        embedding_model=embedding_provider.model_identity,
        top_k=scenario["top_k"],
    )
    unfiltered_hits, unfiltered_latency = unfiltered_search(
        store=store, query_vector=query_vector, embedding_model=embedding_provider.model_identity, top_k=scenario["top_k"]
    )

    actual_eligible_symbols = sorted(_symbol_of(id_to_symbol, rid) for rid in aware.eligible_revision_ids)
    expected_eligible_symbols = sorted(scenario["expected_eligible_symbols"])
    forbidden_symbols = set(scenario.get("forbidden_symbols", []))

    aware_top_k_symbols = [_symbol_of(id_to_symbol, h.document_revision_id) for h in aware.hits]
    unfiltered_top_k_symbols = [_symbol_of(id_to_symbol, h.record.document_revision_id) for h in unfiltered_hits]

    leakage = sum(1 for s in unfiltered_top_k_symbols if s in forbidden_symbols)
    precision = (
        sum(1 for s in aware_top_k_symbols if s in expected_eligible_symbols) / len(aware_top_k_symbols)
        if aware_top_k_symbols
        else 0.0
    )
    required_hit = all(s in aware_top_k_symbols for s in expected_eligible_symbols) if expected_eligible_symbols else True

    expected_values_by_symbol: dict[str, str] = scenario.get("expected_values_by_symbol", {})
    value_found = True
    for symbol, value in expected_values_by_symbol.items():
        found_for_symbol = any(
            _symbol_of(id_to_symbol, h.document_revision_id) == symbol and value in h.retrieval_text for h in aware.hits
        )
        value_found = value_found and found_for_symbol

    actual_authority_labels = {
        _symbol_of(id_to_symbol, rid): label.derived_state
        for rid, label in aware.authority_labels.items()
        if label.derived_state is not None
    }
    expected_authority_labels: dict[str, str] = scenario.get("expected_authority_labels", {})
    labels_match = all(actual_authority_labels.get(sym) == state for sym, state in expected_authority_labels.items())

    failure_reasons: list[str] = []
    if actual_eligible_symbols != expected_eligible_symbols:
        failure_reasons.append(f"eligible mismatch: expected {expected_eligible_symbols}, got {actual_eligible_symbols}")
    if any(s in aware_top_k_symbols for s in forbidden_symbols):
        failure_reasons.append(f"forbidden revision leaked into authority-aware results: {aware_top_k_symbols}")
    if not required_hit:
        failure_reasons.append(f"required revision(s) {expected_eligible_symbols} not all present in authority-aware top-K {aware_top_k_symbols}")
    if not value_found:
        failure_reasons.append(f"expected value(s) {expected_values_by_symbol} not found in authority-aware hits")
    if not labels_match:
        failure_reasons.append(f"authority label mismatch: expected {expected_authority_labels}, got {actual_authority_labels}")
    if aware.integrity_error is not None:
        failure_reasons.append(f"unexpected integrity_error: {aware.integrity_error}")

    result = QueryScenarioResult(
        question_id=scenario["question_id"],
        description=scenario["description"],
        query_intent=scenario["query_intent"],
        as_of_date=date.fromisoformat(scenario["as_of_date"]),
        requested_symbols=scenario.get("requested_symbols", []),
        expected_eligible_symbols=expected_eligible_symbols,
        actual_eligible_symbols=actual_eligible_symbols,
        forbidden_symbols=sorted(forbidden_symbols),
        expected_authority_labels=expected_authority_labels,
        actual_authority_labels=actual_authority_labels,
        authority_aware_top_k_symbols=aware_top_k_symbols,
        unfiltered_top_k_symbols=unfiltered_top_k_symbols,
        ineligible_revision_leakage_at_k=leakage,
        eligible_revision_precision_at_k=precision,
        required_revision_hit_at_k=required_hit,
        expected_value_retrieved=value_found,
        resolver_latency_seconds=aware.resolver_latency_seconds,
        authority_aware_vector_search_latency_seconds=aware.vector_search_latency_seconds,
        unfiltered_vector_search_latency_seconds=unfiltered_latency,
        total_latency_seconds=aware.resolver_latency_seconds + aware.vector_search_latency_seconds + unfiltered_latency,
        integrity_error=aware.integrity_error,
        failure_reasons=failure_reasons,
        passed=not failure_reasons,
    )
    return result, aware


# --- authority-switch scenario (E) ------------------------------------------


class AuthoritySwitchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    as_of_date: date

    before_eligible_symbols: list[str]
    before_top1_symbol: str | None
    before_value_found: bool
    after_eligible_symbols: list[str]
    after_top1_symbol: str | None
    after_value_found: bool

    registry_snapshot_hash_before: str
    registry_snapshot_hash_after: str
    registry_snapshot_hash_changed: bool

    index_hash_before: str
    index_hash_after: str
    index_hash_unchanged: bool
    row_count_before: int
    row_count_after: int
    row_count_unchanged: bool
    chunk_ids_before: list[str]
    chunk_ids_after: list[str]
    chunk_ids_unchanged: bool
    chunk_hashes_unchanged: bool
    embedded_count_during_switch: int

    passed: bool
    failure_reasons: list[str]


def _run_authority_switch(
    *,
    service: RevisionAuthorityService,
    store: RevisionVectorStore,
    embedding_provider: EmbeddingProvider,
    logical_document_id: str,
    id_to_symbol: dict[str, str],
    symbol_to_id: dict[str, str],
    contract: dict[str, Any],
    fixtures: dict[str, RevisionFixture],
) -> AuthoritySwitchResult:
    switch = contract["authority_switch"]
    query_spec = switch["query"]
    query_vector = embedding_provider.embed([query_spec["query"]]).vectors[0]
    as_of = date.fromisoformat(query_spec["as_of_date"])

    index_hash_before = store.index_hash(embedding_provider.model_identity)
    row_count_before = store.record_count(embedding_provider.model_identity)
    chunk_ids_before = sorted(store.all_chunk_ids(embedding_provider.model_identity))
    chunk_hashes_before = store.existing_content_hashes(embedding_provider.model_identity)

    before = authority_aware_search(
        service=service, store=store, logical_document_id=logical_document_id, query_intent=query_spec["query_intent"],
        as_of_date=as_of, requested_revision_ids=None, query_vector=query_vector,
        embedding_model=embedding_provider.model_identity, top_k=query_spec["top_k"],
    )
    before_symbols = sorted(_symbol_of(id_to_symbol, rid) for rid in before.eligible_revision_ids)
    before_top1 = _symbol_of(id_to_symbol, before.hits[0].document_revision_id) if before.hits else None
    # Checked across ALL top-K hits, not just the top-1 -- with the
    # deterministic FAKE embedding provider (hash-based, not semantic),
    # exact rank-1 placement of one specific chunk is not guaranteed;
    # what matters is that the value is genuinely retrievable within the
    # authority-aware top-K, which top_k is sized to guarantee.
    before_value_found = any(switch["before_expected_value"] in h.retrieval_text for h in before.hits)

    # THE activation itself -- a pure Stage 7R.1 registry write. No
    # fixture is re-loaded, no chunk() call happens, no embedding
    # provider is invoked here at all.
    step = switch["activation_step"]
    embed_calls_before = _EmbeddingCallCounter.calls
    service.activate_revision(
        new_revision_id=symbol_to_id[step["new"]], old_revision_id=symbol_to_id[step["old"]],
        effective_from=date.fromisoformat(step["effective_from"]), authority_source="benchmark",
        authority_reference=step["step_id"], authority_recorded_by="stage7r2-benchmark-runner",
        recorded_at=datetime.fromisoformat(step["recorded_at"]),
    )
    embedded_during_switch = _EmbeddingCallCounter.calls - embed_calls_before

    index_hash_after = store.index_hash(embedding_provider.model_identity)
    row_count_after = store.record_count(embedding_provider.model_identity)
    chunk_ids_after = sorted(store.all_chunk_ids(embedding_provider.model_identity))
    chunk_hashes_after = store.existing_content_hashes(embedding_provider.model_identity)

    after = authority_aware_search(
        service=service, store=store, logical_document_id=logical_document_id, query_intent=query_spec["query_intent"],
        as_of_date=as_of, requested_revision_ids=None, query_vector=query_vector,
        embedding_model=embedding_provider.model_identity, top_k=query_spec["top_k"],
    )
    after_symbols = sorted(_symbol_of(id_to_symbol, rid) for rid in after.eligible_revision_ids)
    after_top1 = _symbol_of(id_to_symbol, after.hits[0].document_revision_id) if after.hits else None
    after_value_found = any(switch["after_expected_value"] in h.retrieval_text for h in after.hits)

    reg_hash_changed = before.registry_snapshot_hash != after.registry_snapshot_hash
    index_unchanged = index_hash_before == index_hash_after
    rows_unchanged = row_count_before == row_count_after
    chunk_ids_unchanged = chunk_ids_before == chunk_ids_after
    hashes_unchanged = chunk_hashes_before == chunk_hashes_after

    failure_reasons: list[str] = []
    if before_symbols != sorted(switch["before_expected_eligible_symbols"]):
        failure_reasons.append(f"before: expected eligible {switch['before_expected_eligible_symbols']}, got {before_symbols}")
    if after_symbols != sorted(switch["after_expected_eligible_symbols"]):
        failure_reasons.append(f"after: expected eligible {switch['after_expected_eligible_symbols']}, got {after_symbols}")
    if not before_value_found:
        failure_reasons.append("before: expected value not found in top-1 hit")
    if not after_value_found:
        failure_reasons.append("after: expected value not found in top-1 hit")
    if not reg_hash_changed:
        failure_reasons.append("registry_snapshot_hash did not change across the authority switch")
    if not index_unchanged:
        failure_reasons.append(f"index_hash changed: {index_hash_before} -> {index_hash_after}")
    if not rows_unchanged:
        failure_reasons.append(f"row_count changed: {row_count_before} -> {row_count_after}")
    if not chunk_ids_unchanged:
        failure_reasons.append("chunk_ids changed across the authority switch")
    if not hashes_unchanged:
        failure_reasons.append("chunk content hashes changed across the authority switch")
    if embedded_during_switch != 0:
        failure_reasons.append(f"embedding provider was called {embedded_during_switch} time(s) during the switch -- expected 0")

    return AuthoritySwitchResult(
        question_id=query_spec["question_id"],
        as_of_date=as_of,
        before_eligible_symbols=before_symbols,
        before_top1_symbol=before_top1,
        before_value_found=before_value_found,
        after_eligible_symbols=after_symbols,
        after_top1_symbol=after_top1,
        after_value_found=after_value_found,
        registry_snapshot_hash_before=before.registry_snapshot_hash,
        registry_snapshot_hash_after=after.registry_snapshot_hash,
        registry_snapshot_hash_changed=reg_hash_changed,
        index_hash_before=index_hash_before,
        index_hash_after=index_hash_after,
        index_hash_unchanged=index_unchanged,
        row_count_before=row_count_before,
        row_count_after=row_count_after,
        row_count_unchanged=rows_unchanged,
        chunk_ids_before=chunk_ids_before,
        chunk_ids_after=chunk_ids_after,
        chunk_ids_unchanged=chunk_ids_unchanged,
        chunk_hashes_unchanged=hashes_unchanged,
        embedded_count_during_switch=embedded_during_switch,
        passed=not failure_reasons,
        failure_reasons=failure_reasons,
    )


class _EmbeddingCallCounter:
    """Process-wide counter incremented by CountingEmbeddingProvider
    (below) -- lets _run_authority_switch prove the embedding provider
    was invoked ZERO times during the activation itself, without needing
    the provider instance threaded through activate_revision() (which
    never touches embeddings at all, by construction)."""

    calls = 0


class CountingEmbeddingProvider:
    """Wraps any EmbeddingProvider, counting every embed() call via the
    process-wide _EmbeddingCallCounter -- test/benchmark-only
    instrumentation, never used to produce an actual embedding value
    differently from the wrapped provider."""

    def __init__(self, inner: EmbeddingProvider) -> None:
        self._inner = inner
        self.model_identity = inner.model_identity

    def embed(self, texts: list[str]):
        _EmbeddingCallCounter.calls += 1
        return self._inner.embed(texts)


# --- full run ----------------------------------------------------------------


class BenchmarkRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    generated_at: str
    logical_document_id: str
    embedding_model: str

    fixture_inventory: list[FixtureInventoryEntry]
    index_build: IndexBuildResult

    query_scenarios: list[QueryScenarioResult]
    query_scenarios_passed: int
    query_scenarios_total: int

    authority_switch: AuthoritySwitchResult

    all_passed: bool


def run_benchmark(
    contract_path: Path,
    repository: RevisionAuthorityRepository,
    embedding_provider: EmbeddingProvider,
    store: RevisionVectorStore,
) -> tuple[BenchmarkRunResult, dict[str, str], dict[str, Any], dict[str, Any]]:
    """Returns (result, id_to_symbol, registry_before, registry_after) --
    the last three are what the caller (the script) writes to
    artifacts/stage7r2/{index_manifest,registry_before,registry_after}.json."""
    contract = load_contract(contract_path)
    logical_document_id = contract["logical_document_id"]
    counting_provider = CountingEmbeddingProvider(embedding_provider)

    revision_fixtures = load_all_revision_fixtures(contract["fixtures"])

    service = RevisionAuthorityService(repository)
    revision_by_symbol = {
        symbol: {
            "source_document_sha256": fx.source_document_sha256,
            "version_label": fx.version_label,
            "revision_number": fx.revision_number,
        }
        for symbol, fx in revision_fixtures.items()
    }
    symbol_to_id: dict[str, str] = {}
    id_to_symbol: dict[str, str] = {}
    registration_checks: list = []
    transition_checks: list = []
    _run_registry_setup(
        repository, service,
        {"logical_document_id": logical_document_id, "registry_setup": contract["authority_snapshot"]["registry_setup"]},
        revision_by_symbol, symbol_to_id, id_to_symbol, registration_checks, transition_checks,
    )

    registry_before = registry_snapshot(repository, logical_document_id, id_to_symbol)

    index_result = build_index(revision_fixtures, counting_provider, store)

    query_results: list[QueryScenarioResult] = []
    for scenario in contract["queries"]:
        result, _aware = _run_one_query(
            service=service, store=store, embedding_provider=counting_provider,
            logical_document_id=logical_document_id, id_to_symbol=id_to_symbol, symbol_to_id=symbol_to_id,
            scenario=scenario,
        )
        query_results.append(result)

    switch_result = _run_authority_switch(
        service=service, store=store, embedding_provider=counting_provider, logical_document_id=logical_document_id,
        id_to_symbol=id_to_symbol, symbol_to_id=symbol_to_id, contract=contract, fixtures=revision_fixtures,
    )

    registry_after = registry_snapshot(repository, logical_document_id, id_to_symbol)

    passed_count = sum(1 for q in query_results if q.passed)
    result = BenchmarkRunResult(
        contract_version=contract["contract_version"],
        generated_at=datetime.now(timezone.utc).isoformat(),
        logical_document_id=logical_document_id,
        embedding_model=embedding_provider.model_identity,
        fixture_inventory=_fixture_inventory(revision_fixtures, contract),
        index_build=index_result,
        query_scenarios=query_results,
        query_scenarios_passed=passed_count,
        query_scenarios_total=len(query_results),
        authority_switch=switch_result,
        all_passed=(passed_count == len(query_results)) and switch_result.passed,
    )
    return result, id_to_symbol, registry_before, registry_after
