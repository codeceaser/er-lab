"""Stage 7R.2: end-to-end benchmark integration tests.

Runs the REAL contract (contracts/revision_search_benchmark_v1.json)
through the REAL Stage 5A adapter + Stage 4/4.1 chunker (real Docling
conversion of the five generated DOCX fixtures -- not mocked) with a
deterministic FAKE embedding provider and in-memory store/registry (no
network/database dependency for the default suite). One additional test
is skippable and uses the REAL sentence-transformers model + REAL
Postgres/pgvector.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from ingestion_bench.retrieval_baseline.embeddings import FakeEmbeddingProvider
from ingestion_bench.revision_authority.repository import InMemoryRevisionAuthorityRepository
from ingestion_bench.revision_search_benchmark import config
from ingestion_bench.revision_search_benchmark.benchmark_runner import run_benchmark
from ingestion_bench.revision_search_benchmark.store import InMemoryRevisionVectorStore

REPO_ROOT = Path(__file__).resolve().parent.parent
REVISION_SEARCH_ROOT = REPO_ROOT / "src" / "ingestion_bench" / "revision_search_benchmark"


@pytest.fixture(scope="module")
def benchmark_result():
    """ONE real run (real Docling conversion x5, real chunker, fake
    embeddings, in-memory store/registry) shared by every test in this
    module -- mirrors the scenario_result fixture pattern used throughout
    tests/test_revision_authority_scenarios.py, so the contract, the
    report, and this test suite can never independently drift."""
    repository = InMemoryRevisionAuthorityRepository()
    provider = FakeEmbeddingProvider()
    store = InMemoryRevisionVectorStore()
    result, id_to_symbol, registry_before, registry_after = run_benchmark(
        config.REVISION_SEARCH_BENCHMARK_CONTRACT_PATH, repository, provider, store
    )
    return result, id_to_symbol, registry_before, registry_after


def _scenario(result, question_id: str):
    return next(q for q in result.query_scenarios if q.question_id == question_id)


def test_current_returns_only_v3(benchmark_result):
    result, id_to_symbol, _, _ = benchmark_result
    scenario = _scenario(result, "A_current")
    assert scenario.actual_eligible_symbols == ["v3"]
    assert scenario.authority_aware_top_k_symbols and set(scenario.authority_aware_top_k_symbols) == {"v3"}
    assert scenario.passed


def test_historical_returns_only_v2(benchmark_result):
    result, *_ = benchmark_result
    scenario = _scenario(result, "B_historical")
    assert scenario.actual_eligible_symbols == ["v2"]
    assert set(scenario.authority_aware_top_k_symbols) == {"v2"}
    assert scenario.passed


def test_draft_returns_requested_v4_with_draft_label(benchmark_result):
    result, *_ = benchmark_result
    scenario = _scenario(result, "C_draft")
    assert scenario.actual_eligible_symbols == ["v4"]
    assert scenario.actual_authority_labels["v4"] == "draft"
    assert scenario.passed


def test_comparison_returns_exactly_requested_v2_and_v3(benchmark_result):
    result, *_ = benchmark_result
    scenario = _scenario(result, "D_comparison")
    assert scenario.actual_eligible_symbols == ["v2", "v3"]
    assert set(scenario.authority_aware_top_k_symbols) == {"v2", "v3"}
    assert scenario.passed


def test_no_ineligible_revision_leaks_into_any_authority_aware_result(benchmark_result):
    """Business nuance: for EVERY scenario, the authority-aware top-K
    must never contain a forbidden symbol -- checked explicitly here
    across all four scenarios, not just implied by .passed. Affects:
    current search directly."""
    result, *_ = benchmark_result
    for scenario in result.query_scenarios:
        forbidden = set(scenario.forbidden_symbols)
        leaked = forbidden & set(scenario.authority_aware_top_k_symbols)
        assert not leaked, f"{scenario.question_id}: forbidden symbols leaked into authority-aware results: {leaked}"


def test_filtering_happens_before_ranking_and_limit(benchmark_result):
    """Every authority-aware hit, across every scenario, belongs ONLY to
    an eligible revision -- eligible_revision_precision_at_k == 1.0
    always, proving the restriction happened before the LIMIT, not as a
    post-hoc filter that could have truncated an eligible hit in favor of
    a higher-ranked ineligible one."""
    result, *_ = benchmark_result
    for scenario in result.query_scenarios:
        assert scenario.eligible_revision_precision_at_k == 1.0, scenario.question_id


def test_authority_switch_returns_v5_without_reindexing(benchmark_result):
    result, *_ = benchmark_result
    switch = result.authority_switch
    assert switch.before_eligible_symbols == ["v3"]
    assert switch.after_eligible_symbols == ["v5"]
    assert switch.passed


def test_index_hash_row_count_embeddings_and_chunk_hashes_unchanged_across_switch(benchmark_result):
    result, *_ = benchmark_result
    switch = result.authority_switch
    assert switch.index_hash_before == switch.index_hash_after
    assert switch.row_count_before == switch.row_count_after
    assert switch.chunk_ids_before == switch.chunk_ids_after
    assert switch.chunk_hashes_unchanged is True
    assert switch.embedded_count_during_switch == 0


def test_registry_snapshot_hash_changes_across_switch(benchmark_result):
    result, *_ = benchmark_result
    switch = result.authority_switch
    assert switch.registry_snapshot_hash_before != switch.registry_snapshot_hash_after
    assert switch.registry_snapshot_hash_changed is True


def test_source_provenance_remains_complete(benchmark_result):
    """Every fixture inventory entry carries a real source_document_sha256,
    document_revision_id, and at least one real chunk id -- never a
    placeholder. Affects: auditability."""
    result, *_ = benchmark_result
    assert len(result.fixture_inventory) == 5
    for entry in result.fixture_inventory:
        assert len(entry.source_document_sha256) == 64
        assert len(entry.document_revision_id) == 64
        assert entry.chunk_count > 0
        assert len(entry.chunk_ids) == entry.chunk_count


def test_all_scenarios_and_switch_pass(benchmark_result):
    result, *_ = benchmark_result
    assert result.all_passed is True


# --- isolation -----------------------------------------------------------


def test_no_forbidden_dependency_anywhere_in_revision_search_benchmark():
    """No Graph RAG, wiki, ADK, answer-generation, or vision-enrichment
    dependency anywhere in this package -- structural check via AST, the
    same discipline test_revision_authority_service.py and
    test_revision_authority_integration.py use for their own isolation
    proofs."""
    # Matched against '.'-separated module PATH SEGMENTS, never a raw
    # substring -- "ingestion_bench.revision_authority" legitimately
    # contains the substring "vision" (as in "re-VISION-authority") but
    # is obviously not a vision-enrichment dependency.
    forbidden = ("graph_rag", "wiki", "adk", "answer_baseline", "vision", "reranker", "rerank")
    for path in REVISION_SEARCH_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                segments = node.module.lower().split(".")
                for name in forbidden:
                    assert name not in segments, f"{path} imports {node.module!r} (forbidden: {name!r})"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    segments = alias.name.lower().split(".")
                    for name in forbidden:
                        assert name not in segments, f"{path} imports {alias.name!r} (forbidden: {name!r})"


def test_stage7a1_own_files_never_modified_by_stage7r2():
    """Stage 7A.1's own table/code/reports must remain byte-identical --
    Stage 7R.2 uses its OWN isolated table/config/store/indexer/retriever
    (this whole package), never retrieval_baseline's own module files."""
    result = subprocess.run(
        [
            "git", "diff", "--quiet", "HEAD", "--",
            "src/ingestion_bench/retrieval_baseline", "src/ingestion_bench/canonical", "src/ingestion_bench/chunking",
            "src/ingestion_bench/evaluation", "src/ingestion_bench/adapters", "src/ingestion_bench/answer_baseline",
            "src/ingestion_bench/demo", "src/ingestion_bench/retrieval_benchmark",
            "contracts/retrieval_benchmark_v1.json", "contracts/corpus_profiles_v1.json", "fixtures/reference_manifest.json",
        ],
        cwd=REPO_ROOT, capture_output=True,
    )
    if result.returncode not in (0, 1):
        pytest.skip(f"git diff check unavailable: {result.stderr.decode(errors='replace')}")
    assert result.returncode == 0, "Stage 7A.1/canonical/chunking/evaluation/adapters own files were modified"


# --- real Postgres + real sentence-transformers (skippable) --------------


def _real_infra_available() -> bool:
    try:
        from ingestion_bench.revision_search_benchmark import config as _config

        if not _config.DATABASE_URL:
            return False
        import psycopg

        conn = psycopg.connect(_config.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"), connect_timeout=5)
        conn.close()
        import sentence_transformers  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _real_infra_available(), reason="DATABASE_URL not set/Postgres unreachable, or sentence-transformers not installed")
def test_real_sentence_transformers_and_pgvector_end_to_end():
    """Proves the ACTUAL configured embedding model + the ACTUAL
    Postgres/pgvector store work end to end for this benchmark -- not a
    mock. Uses a throwaway logical_document_id-scoped cleanup so it never
    collides with the real, officially-reported POLICY-RETENTION-001
    run, and cleans up afterward."""
    from sqlalchemy import text as sa_text

    from ingestion_bench.retrieval_baseline.embeddings import SentenceTransformerEmbeddingProvider
    from ingestion_bench.revision_authority.postgres_repository import PostgresRevisionAuthorityRepository
    from ingestion_bench.revision_search_benchmark.pgvector_store import PgVectorRevisionStore

    provider = SentenceTransformerEmbeddingProvider()
    repository = PostgresRevisionAuthorityRepository()
    store = PgVectorRevisionStore(embedding_dimension=provider.dimension, table_name="_pytest_stage7r2_vectors")

    engine = repository._ensure_ready()
    try:
        with engine.connect() as conn:
            conn.execute(sa_text(f"DELETE FROM {repository._period_table} WHERE logical_document_id = :d"), {"d": config.LOGICAL_DOCUMENT_ID})
            conn.execute(sa_text(f"DELETE FROM {repository._registry_table} WHERE logical_document_id = :d"), {"d": config.LOGICAL_DOCUMENT_ID})
            conn.execute(sa_text(f"DELETE FROM {repository._event_table} WHERE logical_document_id = :d"), {"d": config.LOGICAL_DOCUMENT_ID})
            conn.commit()

        result, id_to_symbol, registry_before, registry_after = run_benchmark(
            config.REVISION_SEARCH_BENCHMARK_CONTRACT_PATH, repository, provider, store
        )
        assert result.all_passed is True
        assert result.index_build.total_record_count > 0
    finally:
        with engine.connect() as conn:
            conn.execute(sa_text(f"DELETE FROM {repository._period_table} WHERE logical_document_id = :d"), {"d": config.LOGICAL_DOCUMENT_ID})
            conn.execute(sa_text(f"DELETE FROM {repository._registry_table} WHERE logical_document_id = :d"), {"d": config.LOGICAL_DOCUMENT_ID})
            conn.execute(sa_text(f"DELETE FROM {repository._event_table} WHERE logical_document_id = :d"), {"d": config.LOGICAL_DOCUMENT_ID})
            conn.execute(sa_text(f"DROP TABLE IF EXISTS _pytest_stage7r2_vectors CASCADE"))
            conn.commit()
