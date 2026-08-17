"""Stage 7C.0: environment-driven configuration.

Reuses the SAME DATABASE_URL / embedding-model conventions as Stage 7A.1's
retrieval_baseline/config.py (read-only import), exactly as Stage 7B.0 and
7B.1 do. Writes only to this stage's OWN isolated `edib_stage7c_*` tables,
never a predecessor stage's table.
"""

from __future__ import annotations

import os
from pathlib import Path

from ingestion_bench.retrieval_baseline.config import DATABASE_URL, EMBEDDING_MODEL

REPO_ROOT = Path(__file__).resolve().parents[3]

# Stage 7C's own isolated tables (Revision 6 SS10.3). Stage 7C.0 creates and
# uses ONLY the two projection tables; `facet`, `facet_embedding` and
# `compilation_audit` belong to Stage 7C.1 and are deliberately not created here.
ANCHOR_TABLE_NAME = os.environ.get("INGESTION_BENCH_STAGE7C_ANCHOR_TABLE", "edib_stage7c_anchor")
ANCHOR_POSTING_TABLE_NAME = os.environ.get("INGESTION_BENCH_STAGE7C_POSTING_TABLE", "edib_stage7c_anchor_posting")

CONTRACTS_ROOT = REPO_ROOT / "contracts"
WIKI_PROJECTION_CONTRACT_PATH = CONTRACTS_ROOT / "wiki_projection_v1.json"

# Read-only inputs, shared with the frozen Stage 7B.0 corpus.
CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH = CONTRACTS_ROOT / "cross_document_relationship_benchmark_v1.json"

ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "stage7c0"
REPORTS_ROOT = REPO_ROOT / "reports"

__all__ = [
    "DATABASE_URL",
    "EMBEDDING_MODEL",
    "ANCHOR_TABLE_NAME",
    "ANCHOR_POSTING_TABLE_NAME",
    "CONTRACTS_ROOT",
    "WIKI_PROJECTION_CONTRACT_PATH",
    "CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH",
    "ARTIFACTS_ROOT",
    "REPORTS_ROOT",
    "REPO_ROOT",
]
