"""Stage 7R.1: Revision Authority Registry and Effective-Knowledge
Resolution.

This is NOT a document-management/version-control system. It does not
store or edit document binaries, provide check-in/check-out, manage
approval workflows, replace Documentum or a policy-governance platform,
or infer authority from filenames, upload time, or document text.

It persists authoritative revision metadata supplied by a consumer or
governance source (`service.py`) and uses it to resolve which
already-ingested document revisions are eligible for a query
(`resolver.py`), against exactly four query intents: current, as_of,
comparison, draft.

Canonical chunks are IMMUTABLE and untouched by this package: revision
IDENTITY is reused verbatim from `ingestion_bench.chunking`
(`DocumentRevisionContext`/`compute_document_revision_id`, Stage 4.1) --
never modified, never recomputed differently. Authority, effective-
period, and supersession metadata lives ONLY in this package's own
registry (`model.AuthorityMetadata`, `postgres_repository`'s
`edib_document_revision_registry`/`edib_authority_decision_event`
tables), never on `CanonicalChunk`.

Does not yet wire into retrieval -- that is Stage 7R.2, after review.
"""
