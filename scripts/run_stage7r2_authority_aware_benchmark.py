"""Stage 7R.2 runner: ingests/chunks/embeds the five POLICY-RETENTION-001
source documents ONCE (real Stage 5A Docling adapter, real Stage 4/4.1
chunker, real sentence-transformers embeddings), replays the contract's
declarative authority snapshot through Stage 7R.1's own service/resolver
(real Postgres), runs every query scenario through both the
authority-aware retriever and an unfiltered comparison search, runs the
authority-switch scenario (E), and writes the scorecard/results/
artifacts from that ONE execution.

Never modifies Stage 7A.1's own table/code, Stage 6B's contract, or
Stage 7R.1's registry/resolver code. Retrieval only -- no answer
generation.

Usage (from the repository root, with the venv active, and DATABASE_URL
pointing at a reachable Postgres + pgvector instance):
    python fixtures/revision_search/generate_fixtures.py   # once
    python scripts/run_stage7r2_authority_aware_benchmark.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "fixtures"))

from sqlalchemy import text  # noqa: E402

from ingestion_bench.retrieval_baseline.embeddings import SentenceTransformerEmbeddingProvider  # noqa: E402
from ingestion_bench.revision_authority.postgres_repository import PostgresRevisionAuthorityRepository  # noqa: E402
from ingestion_bench.revision_search_benchmark import config  # noqa: E402
from ingestion_bench.revision_search_benchmark.benchmark_runner import load_contract, run_benchmark  # noqa: E402
from ingestion_bench.revision_search_benchmark.pgvector_store import PgVectorRevisionStore  # noqa: E402
from ingestion_bench.revision_search_benchmark.report import render_results_json, render_scorecard_markdown  # noqa: E402


def _cleanup_prior_run(repository: PostgresRevisionAuthorityRepository, vector_store: PgVectorRevisionStore, embedding_model: str) -> None:
    """Makes this script safely re-runnable against the SAME real
    database: deletes any prior POLICY-RETENTION-001 registry/period/
    event rows (Stage 7R.1's own tables, scoped by logical_document_id --
    never any OTHER logical document) and any prior rows in this
    benchmark's OWN isolated vector table (scoped by embedding_model --
    never Stage 7A.1's table, which this module never even imports)."""
    engine = repository._ensure_ready()
    with engine.connect() as conn:
        conn.execute(text(f"DELETE FROM {repository._period_table} WHERE logical_document_id = :d"), {"d": config.LOGICAL_DOCUMENT_ID})
        conn.execute(text(f"DELETE FROM {repository._registry_table} WHERE logical_document_id = :d"), {"d": config.LOGICAL_DOCUMENT_ID})
        conn.execute(text(f"DELETE FROM {repository._event_table} WHERE logical_document_id = :d"), {"d": config.LOGICAL_DOCUMENT_ID})
        conn.commit()
    vector_store._ensure_ready()
    with vector_store._engine.connect() as conn:  # type: ignore[union-attr]
        conn.execute(
            text(f"DELETE FROM {vector_store._table_name} WHERE logical_document_id = :d AND embedding_model = :em"),
            {"d": config.LOGICAL_DOCUMENT_ID, "em": embedding_model},
        )
        conn.commit()


def main() -> None:
    embedding_provider = SentenceTransformerEmbeddingProvider()
    repository = PostgresRevisionAuthorityRepository()
    vector_store = PgVectorRevisionStore(embedding_dimension=embedding_provider.dimension)

    print(f"Embedding model: {embedding_provider.model_identity} (dim={embedding_provider.dimension})")
    print(f"Vector store: pgvector, table={vector_store._table_name!r} (isolated from Stage 7A.1's own table)")
    print(f"Revision authority repository: Postgres, tables={repository._registry_table!r}/{repository._period_table!r}/{repository._event_table!r}")

    _cleanup_prior_run(repository, vector_store, embedding_provider.model_identity)

    result, id_to_symbol, registry_before, registry_after = run_benchmark(
        config.REVISION_SEARCH_BENCHMARK_CONTRACT_PATH, repository, embedding_provider, vector_store
    )

    config.ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)
    (config.ARTIFACTS_ROOT / "query_results").mkdir(parents=True, exist_ok=True)

    index_manifest = {
        "embedding_model": result.embedding_model,
        "vector_table": vector_store._table_name,
        "logical_document_id": result.logical_document_id,
        "index_build": json.loads(result.index_build.model_dump_json()),
        "fixture_inventory": [json.loads(f.model_dump_json()) for f in result.fixture_inventory],
    }
    (config.ARTIFACTS_ROOT / "index_manifest.json").write_text(json.dumps(index_manifest, indent=2), encoding="utf-8")
    (config.ARTIFACTS_ROOT / "registry_before.json").write_text(json.dumps(registry_before, indent=2, sort_keys=True), encoding="utf-8")
    (config.ARTIFACTS_ROOT / "registry_after.json").write_text(json.dumps(registry_after, indent=2, sort_keys=True), encoding="utf-8")
    for q in result.query_scenarios:
        (config.ARTIFACTS_ROOT / "query_results" / f"{q.question_id}.json").write_text(q.model_dump_json(indent=2), encoding="utf-8")
    (config.ARTIFACTS_ROOT / "query_results" / "E_authority_switch.json").write_text(
        result.authority_switch.model_dump_json(indent=2), encoding="utf-8"
    )

    config.REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    (config.REPORTS_ROOT / "stage7r2_authority_aware_vector_results.json").write_text(render_results_json(result), encoding="utf-8")
    (config.REPORTS_ROOT / "stage7r2_authority_aware_vector_scorecard.md").write_text(render_scorecard_markdown(result), encoding="utf-8")

    print(f"\nIndex build: candidates={result.index_build.candidate_chunk_count} indexed={result.index_build.indexed_count} "
          f"total={result.index_build.total_record_count} hash={result.index_build.index_hash[:16]}...")
    print(f"Query scenarios: {result.query_scenarios_passed}/{result.query_scenarios_total} passed")
    for q in result.query_scenarios:
        print(f"  {q.question_id}: {'PASS' if q.passed else 'FAIL ' + str(q.failure_reasons)} "
              f"(leakage@K={q.ineligible_revision_leakage_at_k}, precision@K={q.eligible_revision_precision_at_k:.2f}, "
              f"hit@K={q.required_revision_hit_at_k})")
    print(f"Authority switch: {'PASS' if result.authority_switch.passed else 'FAIL ' + str(result.authority_switch.failure_reasons)}")
    print(f"all_passed: {result.all_passed}")
    print(f"\nScorecard: {config.REPORTS_ROOT / 'stage7r2_authority_aware_vector_scorecard.md'}")
    print(f"Results: {config.REPORTS_ROOT / 'stage7r2_authority_aware_vector_results.json'}")
    print(f"Artifacts: {config.ARTIFACTS_ROOT}")

    if not result.all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
