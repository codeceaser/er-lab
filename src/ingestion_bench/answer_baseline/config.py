"""Stage 7A.2: environment-driven configuration.

Every credential-shaped or environment-specific value is read from an
environment variable, never hardcoded, and never written to any report
or artifact this package produces. This module never logs or serializes
the resolved values themselves (only field NAMES appear in error
messages). `OPENAI_API_KEY` is read implicitly by the `openai` SDK
itself (standard convention) -- this module never touches it directly.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[3]

# The one configured real answer model.
DEFAULT_ANSWER_MODEL = "gpt-4o-mini"
ANSWER_MODEL = os.environ.get("INGESTION_BENCH_ANSWER_MODEL", DEFAULT_ANSWER_MODEL)

# Deterministic/low-variance generation settings (Stage 7A.2 item 1) --
# temperature=0 is the lowest-variance setting OpenAI's chat completion
# API supports; there is no true seed/determinism guarantee across calls
# for a hosted model, which is exactly why this stage still requires
# mechanical, non-LLM validation of every answer produced (item 4), never
# trusting the model's own determinism.
ANSWER_TEMPERATURE = 0

# Estimated USD cost per 1,000,000 tokens, input/output, for the models
# this stage might realistically be configured with. "Estimated cost
# where available" (Stage 7A.2 item 2) -- a model not in this table
# reports cost as None, never a fabricated number.
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


CONTRACTS_ROOT = REPO_ROOT / "contracts"
RETRIEVAL_BENCHMARK_CONTRACT_PATH = CONTRACTS_ROOT / "retrieval_benchmark_v1.json"

REPORTS_ROOT = REPO_ROOT / "reports"
STAGE7A_RETRIEVAL_RESULTS_PATH = REPORTS_ROOT / "stage7a_vector_retrieval_results.json"

ARTIFACTS_STAGE7A2_ROOT = REPO_ROOT / "artifacts" / "stage7a2"

# The exact 5-fixture subset item 5 explicitly calls out as exposing the
# two real Stage 7A.1 findings -- used only to annotate/highlight the
# scorecard, never to change which questions are actually run (all 12
# always run).
HIGHLIGHTED_QUESTION_IDS: tuple[str, ...] = (
    "Q_DIRECT_001",
    "Q_DIRECT_003",
    "Q_DISTRACTOR_001",
    "Q_DISTRACTOR_002",
    "Q_DISTRACTOR_003",
    "Q_MULTIHOP_001",
    "Q_CONSOLIDATION_001",
)
