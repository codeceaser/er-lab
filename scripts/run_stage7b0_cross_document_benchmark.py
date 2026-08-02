"""Stage 7B.0 runner: ingests/chunks/embeds the cross-document corpus
ONCE (real Stage 5A Docling adapter, real Stage 4/4.1 chunker, real
sentence-transformers embeddings), replays each document's authority
setup through Stage 7R.1's own service/resolver (real Postgres), runs
every question through the cross-document authority-aware retriever plus
its unfiltered comparison, evaluates against the held-out fact/question
truth, and writes the scorecard/results/artifacts from that ONE
execution.

Retrieval only -- NO answer generation, NO graph construction. Never
modifies Stage 7A.1, Stage 7R.1, or Stage 7R.2 code.

Usage (from the repository root, venv active, DATABASE_URL set):
    python fixtures/cross_document/generate_fixtures.py   # once
    python scripts/run_stage7b0_cross_document_benchmark.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "fixtures"))

from sqlalchemy import text  # noqa: E402

from ingestion_bench.cross_document_benchmark import config  # noqa: E402
from ingestion_bench.cross_document_benchmark.benchmark_runner import run_benchmark  # noqa: E402
from ingestion_bench.cross_document_benchmark.pgvector_store import PgVectorCrossDocumentStore  # noqa: E402
from ingestion_bench.cross_document_benchmark.report import render_results_json, render_scorecard_markdown  # noqa: E402
from ingestion_bench.retrieval_baseline.embeddings import SentenceTransformerEmbeddingProvider  # noqa: E402
from ingestion_bench.revision_authority.postgres_repository import PostgresRevisionAuthorityRepository  # noqa: E402


def _cleanup_prior_run(repository: PostgresRevisionAuthorityRepository, vector_store: PgVectorCrossDocumentStore, corpus_logical_document_ids: list[str]) -> None:
    """Makes this script safely re-runnable against the SAME real
    database: deletes any prior registry/period/event rows for THIS
    benchmark's own logical documents (never any other logical document),
    and DROPS this benchmark's OWN isolated vector table outright (its
    columns evolved during development; CREATE TABLE IF NOT EXISTS would
    otherwise keep an old shape forever). The table holds no data any
    other consumer depends on."""
    engine = repository._ensure_ready()
    with engine.connect() as conn:
        for logical_document_id in corpus_logical_document_ids:
            conn.execute(text(f"DELETE FROM {repository._period_table} WHERE logical_document_id = :d"), {"d": logical_document_id})
            conn.execute(text(f"DELETE FROM {repository._registry_table} WHERE logical_document_id = :d"), {"d": logical_document_id})
            conn.execute(text(f"DELETE FROM {repository._event_table} WHERE logical_document_id = :d"), {"d": logical_document_id})
        conn.commit()
        conn.execute(text(f"DROP TABLE IF EXISTS {vector_store._table_name} CASCADE"))
        conn.commit()


def main() -> None:
    contract = json.loads(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH.read_text(encoding="utf-8"))
    corpus_logical_document_ids = sorted({f["logical_document_id"] for f in contract["fixtures"]})

    embedding_provider = SentenceTransformerEmbeddingProvider()
    repository = PostgresRevisionAuthorityRepository()
    vector_store = PgVectorCrossDocumentStore(embedding_dimension=embedding_provider.dimension)

    print(f"Embedding model: {embedding_provider.model_identity} (dim={embedding_provider.dimension})")
    print(f"Vector store: pgvector, table={vector_store._table_name!r} (isolated from Stage 7A.1 / 7R.2 tables)")
    print(f"Corpus documents: {corpus_logical_document_ids}")

    _cleanup_prior_run(repository, vector_store, corpus_logical_document_ids)

    result, id_to_symbol, evidence = run_benchmark(
        config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH, repository, embedding_provider, vector_store
    )

    config.ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)
    (config.ARTIFACTS_ROOT / "query_results").mkdir(parents=True, exist_ok=True)

    fixture_manifest = {
        "corpus_id": result.corpus_id,
        "embedding_model": result.embedding_model,
        "fixtures": [json.loads(f.model_dump_json()) for f in result.fixture_inventory],
    }
    (config.ARTIFACTS_ROOT / "fixture_manifest.json").write_text(json.dumps(fixture_manifest, indent=2), encoding="utf-8")
    (config.ARTIFACTS_ROOT / "evidence_alignment.json").write_text(
        json.dumps([json.loads(e.model_dump_json()) for e in result.fact_evidence], indent=2), encoding="utf-8"
    )
    vector_index_manifest = {
        "vector_table": vector_store._table_name,
        "embedding_model": result.embedding_model,
        "index_build": json.loads(result.index_build.model_dump_json()),
    }
    (config.ARTIFACTS_ROOT / "vector_index_manifest.json").write_text(json.dumps(vector_index_manifest, indent=2), encoding="utf-8")
    for q in result.question_results:
        (config.ARTIFACTS_ROOT / "query_results" / f"{q.question_id}.json").write_text(q.model_dump_json(indent=2), encoding="utf-8")

    config.REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    (config.REPORTS_ROOT / "stage7b0_cross_document_vector_results.json").write_text(render_results_json(result), encoding="utf-8")
    (config.REPORTS_ROOT / "stage7b0_cross_document_vector_scorecard.md").write_text(render_scorecard_markdown(result), encoding="utf-8")

    print(f"\nIndex build: {result.index_build.total_record_count} records across {len(result.index_build.logical_document_ids)} documents, hash={result.index_build.index_hash[:16]}...")
    print(f"Authority correct: {result.authority_correct_count}/{result.questions_total} (must be all)")
    print(f"Vector outcomes: solved={result.vector_solved_count}, partial={result.vector_partial_count}, failed={result.vector_failed_count}")
    for q in result.question_results:
        print(f"  {q.question_id} [{q.question_type}] coverage@{q.top_k}={q.required_fact_coverage_at_k:.2f} "
              f"outcome={q.vector_outcome} auth_ok={q.authority_correct}"
              + ("" if q.authority_correct else f" FAILURES={q.failure_reasons}"))
    print(f"\nall_authority_correct: {result.all_authority_correct}")
    print(f"Scorecard: {config.REPORTS_ROOT / 'stage7b0_cross_document_vector_scorecard.md'}")
    print(f"Results: {config.REPORTS_ROOT / 'stage7b0_cross_document_vector_results.json'}")
    print(f"Artifacts: {config.ARTIFACTS_ROOT}")

    if not result.all_authority_correct:
        sys.exit(1)


if __name__ == "__main__":
    main()
