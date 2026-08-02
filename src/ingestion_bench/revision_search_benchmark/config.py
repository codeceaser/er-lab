"""Stage 7R.2: environment-driven configuration.

Reuses the SAME DATABASE_URL/embedding-model conventions as Stage 7A.1's
own retrieval_baseline/config.py (read-only import, never a copy) --
never hardcoded, never logged. Writes only to this benchmark's OWN
isolated table (INGESTION_BENCH_REVISION_SEARCH_TABLE), never Stage
7A.1's ingestion_bench_stage7a_vectors table or the separate ER GraphRAG
POC's document_chunks/documents/kg_* tables.
"""

from __future__ import annotations

import os
from pathlib import Path

from ingestion_bench.retrieval_baseline.config import DATABASE_URL, EMBEDDING_MODEL

REPO_ROOT = Path(__file__).resolve().parents[3]

VECTOR_TABLE_NAME = os.environ.get("INGESTION_BENCH_REVISION_SEARCH_TABLE", "ingestion_bench_stage7r2_vectors")

LOGICAL_DOCUMENT_ID = "POLICY-RETENTION-001"

FIXTURES_ROOT = REPO_ROOT / "fixtures" / "revision_search"
GENERATED_FIXTURES_DIR = FIXTURES_ROOT / "generated"

CONTRACTS_ROOT = REPO_ROOT / "contracts"
REVISION_SEARCH_BENCHMARK_CONTRACT_PATH = CONTRACTS_ROOT / "revision_search_benchmark_v1.json"

ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "stage7r2"
REPORTS_ROOT = REPO_ROOT / "reports"

__all__ = [
    "DATABASE_URL",
    "EMBEDDING_MODEL",
    "VECTOR_TABLE_NAME",
    "LOGICAL_DOCUMENT_ID",
    "FIXTURES_ROOT",
    "GENERATED_FIXTURES_DIR",
    "CONTRACTS_ROOT",
    "REVISION_SEARCH_BENCHMARK_CONTRACT_PATH",
    "ARTIFACTS_ROOT",
    "REPORTS_ROOT",
]
