"""Stage 7B.0: environment-driven configuration.

Reuses the SAME DATABASE_URL/embedding-model conventions as Stage 7A.1's
retrieval_baseline/config.py (read-only import). Writes only to this
benchmark's OWN isolated table (INGESTION_BENCH_CROSS_DOCUMENT_TABLE),
never Stage 7A.1's or Stage 7R.2's tables, and never the separate ER
GraphRAG POC's tables.
"""

from __future__ import annotations

import os
from pathlib import Path

from ingestion_bench.retrieval_baseline.config import DATABASE_URL, EMBEDDING_MODEL

REPO_ROOT = Path(__file__).resolve().parents[3]

VECTOR_TABLE_NAME = os.environ.get("INGESTION_BENCH_CROSS_DOCUMENT_TABLE", "ingestion_bench_stage7b0_vectors")

FIXTURES_ROOT = REPO_ROOT / "fixtures" / "cross_document"
GENERATED_FIXTURES_DIR = FIXTURES_ROOT / "generated"
GENERATION_MANIFEST_PATH = FIXTURES_ROOT / "generation_manifest.json"

CONTRACTS_ROOT = REPO_ROOT / "contracts"
CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH = CONTRACTS_ROOT / "cross_document_relationship_benchmark_v1.json"

ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "stage7b0"
REPORTS_ROOT = REPO_ROOT / "reports"

__all__ = [
    "DATABASE_URL",
    "EMBEDDING_MODEL",
    "VECTOR_TABLE_NAME",
    "FIXTURES_ROOT",
    "GENERATED_FIXTURES_DIR",
    "GENERATION_MANIFEST_PATH",
    "CONTRACTS_ROOT",
    "CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH",
    "ARTIFACTS_ROOT",
    "REPORTS_ROOT",
]
