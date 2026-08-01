"""Stage 7A.3: minimal local auditable-semantic-search demo.

A READ-ONLY viewer over the frozen Stage 7A.2/7A.2a answer baseline
(`reports/stage7a2_vector_answer_results.json`) -- no live retrieval, no
live inference, no new embeddings/pgvector/chunking/reranking/hybrid
search/query decomposition, no Graph RAG, wiki generation, vision
enrichment, or ADK. Renders a single, self-contained, escaped static
HTML file; every displayed field is copied verbatim from an
already-computed, already-validated `QuestionAnswerResult` -- there is
no live-input path through which a user-supplied chunk id or source
reference could be injected.
"""
