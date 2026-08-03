"""Stage 7B.1: evidence-backed graph projection and Vector-vs-Graph
retrieval comparison.

Builds a graph projection from the EXACT Stage 7B.0 canonical chunks and
compares Graph retrieval with the frozen Stage 7B.0 Vector baseline under
Stage 7B.0's frozen fairness contract. Every graph edge is a
revision-scoped assertion that cites an existing Stage 7B.0 chunk; no
bare edge is ever evidence.

The stage is allowed to conclude that Graph does not add sufficient
value -- graph superiority is NEVER encoded as a test expectation.

Reuses (read-only, never modified): the frozen Stage 5A adapter, Stage
4/4.1 chunker, Stage 7R.1 resolver/service, Stage 7A.1 embedding
provider, and -- crucially, so Vector and Graph are scored identically --
the frozen Stage 7B.0 `build_evidence_alignment` + `_evaluate_question`
metric functions and the frozen Stage 7B.0 Vector results JSON as the
comparison baseline (never rerun, never rescored).

Never implements: answer generation, ADK, wiki, vision, query
decomposition, a retrieval router, Neo4j, a generic graph framework, or
workflow/state management.
"""
