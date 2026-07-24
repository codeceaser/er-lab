"""Stage 6B: minimal, deterministic retrieval benchmark contract.

Defines a small, frozen set of benchmark questions (`model.py`) over
facts already proven real by the Stage 6A evaluator's gold evidence-
alignment catalog, and a deterministic resolver (`resolver.py`) that
maps a question's required fact ids to the matched chunk ids available
in a supplied `EvidenceAlignment` catalog for one ingestion lane.

This package defines the CONTRACT only. It contains no embeddings, no
pgvector, no retrieval execution, no Graph RAG, no wiki generation, no
vision enrichment, no ADK agent, and no answer generation -- those are
later stages (7A/7B/7C/8A/8B/9), not this one.
"""

from .model import BenchmarkQuestion, QuestionDifficulty, RetrievalBenchmarkContract, load_contract
from .resolver import FactResolution, FactResolutionStatus, resolve_question_facts

__all__ = [
    "BenchmarkQuestion",
    "FactResolution",
    "FactResolutionStatus",
    "QuestionDifficulty",
    "RetrievalBenchmarkContract",
    "load_contract",
    "resolve_question_facts",
]
