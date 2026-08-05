"""Stage 7B.2: environment-driven configuration + frozen-input paths.

The measured algorithm parameters and decision gates live in
`contracts/hybrid_retrieval_probe_v1.json` (loaded here), NOT hardcoded
per question. This module only resolves environment-specific values
(DATABASE_URL, embedding model, isolated table names) and the paths of
the frozen Stage 7B.0 / 7B.1 inputs this stage reads read-only.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ingestion_bench.retrieval_baseline.config import DATABASE_URL, EMBEDDING_MODEL

REPO_ROOT = Path(__file__).resolve().parents[3]

# Isolated Stage 7B.2 edge-embedding table (never any other stage's table).
EDGE_EMBEDDING_TABLE = os.environ.get("INGESTION_BENCH_HYBRID_EDGE_TABLE", "edib_stage7b2_edge_embedding")

CONTRACTS_ROOT = REPO_ROOT / "contracts"
HYBRID_PROBE_CONTRACT_PATH = CONTRACTS_ROOT / "hybrid_retrieval_probe_v1.json"
CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH = CONTRACTS_ROOT / "cross_document_relationship_benchmark_v1.json"

REPORTS_ROOT = REPO_ROOT / "reports"
STAGE7B0_VECTOR_RESULTS_PATH = REPORTS_ROOT / "stage7b0_cross_document_vector_results.json"
STAGE7B1_GRAPH_BUILD_RESULTS_PATH = REPORTS_ROOT / "stage7b1_graph_build_results.json"
STAGE7B1_GRAPH_RETRIEVAL_RESULTS_PATH = REPORTS_ROOT / "stage7b1_graph_retrieval_results.json"

ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "stage7b2"


def load_probe_config() -> dict:
    return json.loads(HYBRID_PROBE_CONTRACT_PATH.read_text(encoding="utf-8"))


__all__ = [
    "DATABASE_URL",
    "EMBEDDING_MODEL",
    "EDGE_EMBEDDING_TABLE",
    "HYBRID_PROBE_CONTRACT_PATH",
    "CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH",
    "STAGE7B0_VECTOR_RESULTS_PATH",
    "STAGE7B1_GRAPH_BUILD_RESULTS_PATH",
    "STAGE7B1_GRAPH_RETRIEVAL_RESULTS_PATH",
    "REPORTS_ROOT",
    "ARTIFACTS_ROOT",
    "load_probe_config",
]
