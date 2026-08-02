"""Stage 7B.0: projection-neutral cross-document relationship holdout and
Vector baseline.

Qualifies a benchmark that can fairly determine whether an
evidence-backed graph projection adds measurable retrieval value beyond
Vector RAG -- WITHOUT implementing Graph RAG. The current relationship
chain is deliberately distributed one hop per logical document, so a
Vector baseline can be measured on how much of each multi-hop chain it
recovers.

Reuses (read-only, never modified): the frozen Stage 5A adapter, the
frozen Stage 4/4.1 chunker, the Stage 7R.1 authority registry/resolver,
the Stage 7A.1 embedding provider, and the Stage 7R.2 provenance-rich
`RevisionVectorRecord` schema. Never imports or modifies Graph RAG, wiki
retrieval, ADK, answer generation, or vision code -- none exist here.
"""
