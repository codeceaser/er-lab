"""Stage 7R.2: authority-aware vector retrieval benchmark.

Proves revision authority (Stage 7R.1/7R.1a/7R.1b registry + resolver)
actually changes semantic-search results -- an isolated benchmark over
ONE logical document (POLICY-RETENTION-001), a separate index/table from
Stage 7A.1's own frozen baseline, and a narrow authority-aware retriever
that filters eligible revisions INSIDE the vector query, before ranking.

Never wired into Stage 7A.1's table/code, Stage 7R.1's registry/resolver
(read-only reuse only), Graph RAG, wiki retrieval, ADK, answer
generation, vision enrichment, hybrid retrieval, or reranking.
"""
