"""Stage 7A.1 runner: builds the configured corpus-profile vector
indexes (Postgres + pgvector, sentence-transformers/all-MiniLM-L6-v2)
over frozen Stage 5A CanonicalChunk artifacts, then runs the frozen
Stage 6B 12-question benchmark against the baseline_demo index and
writes the scorecard/results/artifacts.

Never modifies Stage 5A/6A/6B code or artifacts. Retrieval only -- no
answer generation.

Usage (from the repository root, with the venv active, AFTER running
scripts/run_docling_standard.py and scripts/run_stage6a_evaluation.py at
least once, and with DATABASE_URL pointing at a reachable Postgres +
pgvector instance):
    python scripts/run_stage7a_retrieval_baseline.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "fixtures"))

from ingestion_bench.evaluation.model import EvidenceAlignment  # noqa: E402
from ingestion_bench.retrieval_baseline.config import (  # noqa: E402
    ARTIFACTS_STAGE5A_ROOT,
    ARTIFACTS_STAGE7A_ROOT,
    CORPUS_PROFILES_PATH,
    DEFAULT_TOP_KS,
    EVIDENCE_ALIGNMENT_PATH,
    REPORTS_ROOT,
    RETRIEVAL_BENCHMARK_CONTRACT_PATH,
)
from ingestion_bench.retrieval_baseline.corpus import load_corpus_profile_set  # noqa: E402
from ingestion_bench.retrieval_baseline.embeddings import SentenceTransformerEmbeddingProvider  # noqa: E402
from ingestion_bench.retrieval_baseline.evaluation import run_evaluation  # noqa: E402
from ingestion_bench.retrieval_baseline.indexer import build_index  # noqa: E402
from ingestion_bench.retrieval_baseline.pgvector_store import PgVectorStore  # noqa: E402
from ingestion_bench.retrieval_baseline.report import render_index_manifest, render_scorecard_markdown  # noqa: E402
from ingestion_bench.retrieval_benchmark.model import load_contract  # noqa: E402


def main() -> None:
    catalog = [EvidenceAlignment.model_validate(e) for e in json.loads(EVIDENCE_ALIGNMENT_PATH.read_text(encoding="utf-8"))]
    contract = load_contract(RETRIEVAL_BENCHMARK_CONTRACT_PATH)
    corpus_profile_set = load_corpus_profile_set(CORPUS_PROFILES_PATH)

    embedding_provider = SentenceTransformerEmbeddingProvider()
    vector_store = PgVectorStore(embedding_dimension=embedding_provider.dimension)

    print(f"Embedding model: {embedding_provider.model_identity} (dim={embedding_provider.dimension})")
    print(f"Vector store: pgvector, table={vector_store._table_name!r}")

    index_builds = {}
    for profile_name, profile in corpus_profile_set.profiles.items():
        build = build_index(profile, ARTIFACTS_STAGE5A_ROOT, embedding_provider, vector_store)
        index_builds[profile_name] = build
        print(
            f"  [{profile_name}] candidates={build.candidate_chunk_count} indexed={build.indexed_count} "
            f"skipped_unchanged={build.skipped_unchanged_count} total={build.total_record_count} "
            f"latency={build.build_latency_seconds:.3f}s hash={build.index_hash[:16]}..."
        )

    ARTIFACTS_STAGE7A_ROOT.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS_STAGE7A_ROOT / "question_results").mkdir(parents=True, exist_ok=True)

    manifest = render_index_manifest(list(index_builds.values()))
    (ARTIFACTS_STAGE7A_ROOT / "index_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    primary_profile = corpus_profile_set.profiles["baseline_demo"]
    primary_build = index_builds["baseline_demo"]
    indexed_chunk_ids = vector_store.all_chunk_ids("baseline_demo", embedding_provider.model_identity)

    run = run_evaluation(
        contract,
        "baseline_demo",
        primary_profile.fixtures,
        catalog,
        indexed_chunk_ids,
        embedding_provider,
        vector_store,
        primary_build,
        list(DEFAULT_TOP_KS),
    )

    for qr in run.question_results:
        (ARTIFACTS_STAGE7A_ROOT / "question_results" / f"{qr.question_id}.json").write_text(
            qr.model_dump_json(indent=2), encoding="utf-8"
        )

    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    (REPORTS_ROOT / "stage7a_vector_retrieval_results.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")
    (REPORTS_ROOT / "stage7a_vector_retrieval_scorecard.md").write_text(render_scorecard_markdown(run), encoding="utf-8")

    print(f"\nEvaluated {len(run.question_results)} questions against corpus_profile={run.corpus_profile!r}")
    for k in run.ks:
        key = str(k)
        print(
            f"  K={k}: mean_coverage={run.aggregate.mean_coverage_at_k[key]}, "
            f"mean_recall={run.aggregate.mean_recall_at_k[key]}, "
            f"all_required_rate={run.aggregate.all_required_retrieved_rate_at_k[key]}, "
            f"forbidden_hit_rate={run.aggregate.mean_forbidden_hit_rate_at_k[key]}"
        )
    print(f"  mean_reciprocal_rank={run.aggregate.mean_reciprocal_rank:.3f}")
    print(f"  mean_retrieval_latency={run.aggregate.mean_retrieval_latency_seconds * 1000:.1f}ms")
    print(f"\nScorecard: {REPORTS_ROOT / 'stage7a_vector_retrieval_scorecard.md'}")
    print(f"Results: {REPORTS_ROOT / 'stage7a_vector_retrieval_results.json'}")
    print(f"Index manifest: {ARTIFACTS_STAGE7A_ROOT / 'index_manifest.json'}")
    print(f"Per-question artifacts: {ARTIFACTS_STAGE7A_ROOT / 'question_results'}")


if __name__ == "__main__":
    main()
