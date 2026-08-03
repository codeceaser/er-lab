"""Stage 7B.2: Hybrid Vector-Graph retrieval value probe.

A bounded decision experiment closing the Graph investigation. It tests
whether Vector-assisted graph seeding, semantic edge matching, semantic
path ranking, and deterministic Vector/Graph fusion can expose Graph's
latent multi-hop value WITHOUT increasing the final evidence budget,
introducing authority leakage, or adding a query-time LLM.

Five frozen modes are compared -- V (frozen authority-aware Vector), G
(frozen Stage 7B.1 simple Graph), H0 (V+G fusion), H1 (H0 + Vector/
semantic-edge seeds), H2 (H1 + semantic path ranking) -- over TWO graph
conditions (the frozen real Stage 7B.1 graph snapshot and the
deterministic perfect FakeRelationshipExtractor graph). The stage is
allowed to conclude Hybrid Graph does not justify further investment;
Hybrid superiority is NEVER encoded as a test expectation.

Reuses (read-only): the frozen Stage 5A adapter, Stage 4/4.1 chunker,
Stage 7R resolver, Stage 7A.1 embedding provider, the frozen Stage 7B.0
Vector results + `build_evidence_alignment` + `_evaluate_question`
scorer, and the frozen Stage 7B.1 graph builder/retriever/models.

No query-time LLM. No answer generation, ADK, wiki, vision, Neo4j,
generic graph framework, query planner/router, or new extraction prompts.
"""
