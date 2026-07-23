"""Stage 6A: deterministic ingestion-fidelity evaluator.

Compares reference_manifest.json against Stage 5A DOCLING_STANDARD_LOCAL
output. This is the ONLY package in the repository that reads
reference_manifest.json -- adapters/, canonical/, and chunking/ remain
manifest-independent (verified by tests/test_stage6a_integration.py).

No LLM calls, no OpenAI calls, no vision enrichment, no embeddings, no
pgvector, no Graph RAG, no wiki generation, no ADK agents, no
answer-generation evaluation, no semantic similarity supplied by an LLM.
"""

from .model import (
    AggregateEvaluationResult,
    EvaluationRun,
    EvidenceAlignment,
    FactExpectation,
    FactObservation,
    FixtureEvaluationResult,
    MetricResult,
    MissRecord,
    OperationalEvidence,
    UnexpectedObservation,
)

__all__ = [
    "AggregateEvaluationResult",
    "EvaluationRun",
    "EvidenceAlignment",
    "FactExpectation",
    "FactObservation",
    "FixtureEvaluationResult",
    "MetricResult",
    "MissRecord",
    "OperationalEvidence",
    "UnexpectedObservation",
]
