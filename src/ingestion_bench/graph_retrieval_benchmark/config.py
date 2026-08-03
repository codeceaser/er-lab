"""Stage 7B.1: environment-driven configuration.

Reuses the SAME DATABASE_URL/embedding-model conventions and the same
OpenAI configuration idiom as the rest of the repository. Writes only to
this stage's OWN isolated Postgres tables (edib_stage7b1_graph_*), never
any other stage's tables. `OPENAI_API_KEY` is read implicitly by the
`openai` SDK -- this module never touches it directly. The extraction
model is environment-overridable and never hardcoded into calling code.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from ingestion_bench.retrieval_baseline.config import DATABASE_URL, EMBEDDING_MODEL

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[3]

# --- relationship extraction model (OpenAI) --------------------------------
DEFAULT_EXTRACTION_MODEL = "gpt-4o-mini"
EXTRACTION_MODEL = os.environ.get("INGESTION_BENCH_GRAPH_EXTRACTION_MODEL", DEFAULT_EXTRACTION_MODEL)
# Lowest-variance setting; a hosted model gives no true determinism
# guarantee, which is exactly why every extracted edge is mechanically
# validated (supporting_text must be an exact substring) rather than
# trusted.
EXTRACTION_TEMPERATURE = float(os.environ.get("INGESTION_BENCH_GRAPH_EXTRACTION_TEMPERATURE", "0"))

_PRICING_USD_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}


def estimate_cost_usd(model_identity: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
    if model_identity not in _PRICING_USD_PER_MILLION_TOKENS:
        return None
    if input_tokens is None or output_tokens is None:
        return None
    input_rate, output_rate = _PRICING_USD_PER_MILLION_TOKENS[model_identity]
    return (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate


# --- isolated Postgres graph tables ----------------------------------------
GRAPH_NODE_TABLE = os.environ.get("INGESTION_BENCH_GRAPH_NODE_TABLE", "edib_stage7b1_graph_node")
GRAPH_EDGE_TABLE = os.environ.get("INGESTION_BENCH_GRAPH_EDGE_TABLE", "edib_stage7b1_graph_edge_assertion")
GRAPH_EXTRACTION_RUN_TABLE = os.environ.get("INGESTION_BENCH_GRAPH_EXTRACTION_RUN_TABLE", "edib_stage7b1_graph_extraction_run")

# --- traversal ------------------------------------------------------------
# One fixed global maximum hop limit (spec item 7: no more than five).
MAX_HOP_LIMIT = int(os.environ.get("INGESTION_BENCH_GRAPH_MAX_HOPS", "5"))

# --- frozen Stage 7B.0 inputs (read-only) ----------------------------------
CONTRACTS_ROOT = REPO_ROOT / "contracts"
CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH = CONTRACTS_ROOT / "cross_document_relationship_benchmark_v1.json"

REPORTS_ROOT = REPO_ROOT / "reports"
STAGE7B0_VECTOR_RESULTS_PATH = REPORTS_ROOT / "stage7b0_cross_document_vector_results.json"

ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "stage7b1"

__all__ = [
    "DATABASE_URL",
    "EMBEDDING_MODEL",
    "EXTRACTION_MODEL",
    "EXTRACTION_TEMPERATURE",
    "estimate_cost_usd",
    "GRAPH_NODE_TABLE",
    "GRAPH_EDGE_TABLE",
    "GRAPH_EXTRACTION_RUN_TABLE",
    "MAX_HOP_LIMIT",
    "CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH",
    "STAGE7B0_VECTOR_RESULTS_PATH",
    "REPORTS_ROOT",
    "ARTIFACTS_ROOT",
]
