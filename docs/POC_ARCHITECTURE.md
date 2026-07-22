# POC Architecture — Enterprise Document-Ingestion Benchmark

This document describes the **intended end-to-end architecture** of the
document-ingestion benchmark POC, and states plainly which parts of it exist
in the repository today versus which parts are architecturally decided but
not yet built.

This POC lives alongside, but is **architecturally independent of**, the
original ER GraphRAG POC described in the repository root `README.md`
(`src/create_schema.py`, `seed_documents.py`, `seed_graph.py`,
`build_graph_artifacts.py`, `vector_retriever.py`,
`graph_enriched_retriever.py`, `compare_retrieval.py`). That POC uses a
tiny, **hand-seeded** corpus and hand-seeded graph relationships — it does
not consume `CanonicalDocument` or `CanonicalChunk` output, and nothing in
this document changes it. See section G for how the two relate.

---

## End-to-end intended pipeline

```
Source documents (DOCX / PDF / PPTX)
        |
        v
+-------------------------------------------------------------+
| Parser Adapter                                    [PLANNED] |
|   Path A  DOCLING_STANDARD_LOCAL                             |
|   Path B  DOCLING_STANDARD_LOCAL + selective OpenAI vision   |
|           enrichment (VisionEnricher)                        |
|   Path C  OpenAI vendor-native whole-document input          |
|   Path D  DOCLING_STANDARD_LOCAL + local Granite Vision       |
|           enrichment            [OPTIONAL / DEFERRED]        |
+-------------------------------------------------------------+
        |
        v
+-------------------------------------------------------------+
| CanonicalDocument                              [IMPLEMENTED] |
|   stable, hashed, parser-neutral, provenance-preserving       |
|   + Annotation[]  (extracted vs. model_derived)                |
|   + ProvenanceEntry[]                                          |
+-------------------------------------------------------------+
| ExtractionRun                    [MODEL IMPLEMENTED, UNUSED] |
|   volatile, never hashed, never populated by a real adapter  |
|   yet (no adapter exists to produce one)                     |
+-------------------------------------------------------------+
        |
        v
+-------------------------------------------------------------+
| DocumentRevisionContext                        [IMPLEMENTED] |
|   logical_document_id, document_revision_id,                  |
|   source_document_sha256, version_label, revision_number      |
+-------------------------------------------------------------+
        |
        v
+-------------------------------------------------------------+
| Deterministic Canonical Chunking                [IMPLEMENTED] |
|   chunk_document(document, config, revision_context)          |
|   -> CanonicalChunk[]                                          |
+-------------------------------------------------------------+
        |
        v
+-------------------------------------------------------------+
| Embedding / Knowledge Projections                [NOT STARTED]|
|   vector index | graph projection | wiki-style pages          |
+-------------------------------------------------------------+
        |
        v
+-------------------------------------------------------------+
| Retrieval                                        [NOT STARTED |
|   (for this pipeline; a separate, unrelated vector-vs-graph   |
|   POC already exists in src/ — see section G)                 |
+-------------------------------------------------------------+
        |
        v
+-------------------------------------------------------------+
| Agent (e.g. ADK)                                 [OUT OF SCOPE|
|                                                    for this POC|
+-------------------------------------------------------------+
        |
        v
+-------------------------------------------------------------+
| Objective Evaluation against reference_manifest.json          |
|                                                   [NOT STARTED,|
|   an evaluator that scores CanonicalDocument/CanonicalChunk    |
|   output against the frozen manifest has not been implemented]|
+-------------------------------------------------------------+
```

An ASCII diagram is used here because no document in this repository
currently establishes Mermaid as an accepted format; if the documentation
host is later confirmed to render Mermaid, this diagram can be translated
without any change in meaning.

---

## A. Parser adapters

Four parser lanes are architecturally defined (`fixtures/BENCHMARK_CONTRACT.md`
section 1). **None of the four has an implementation in this repository.**
There is no `src/ingestion_bench/adapters/` package, no `vision/` package,
and no `VisionEnricher` implementation on disk — only the protocol shape
documented in the contract.

| Lane | Description | Status |
|---|---|---|
| A — `DOCLING_STANDARD_LOCAL` | Docling's standard local pipeline: text/layout/reading-order, native DOCX/PPTX tables, PDF TableFormer tables, picture extraction, OCR (RapidOCR), picture classification, captions, provenance. No VLM, no vision enrichment. | Architecturally decided, **not implemented**. `docling` is not present in `requirements.txt` or `constraints.txt`. |
| B — A + selective OpenAI vision enrichment | Path A's output, then a separate `OpenAIVisionEnricher` pass over already-extracted `CanonicalPicture`s only (never whole pages, never tables). | Architecturally decided, **not implemented**. |
| C — OpenAI vendor-native | The original file goes to OpenAI directly, mapped to the canonical model. | Architecturally decided, **not implemented**. |
| D — local Granite Vision enrichment | Same `VisionEnricher` protocol as B, run locally (`GraniteVisionEnricher`). | **Optional and explicitly deferred** — not required for the initial POC (`fixtures/BENCHMARK_CONTRACT.md` section 1). |

The `VisionEnricher` protocol shape (`enrich(picture, caption, surrounding_text) -> list[Annotation]`),
the `VisionEnrichmentResult` structured schema, and the mapping from that
schema to concrete `Annotation` subtypes are all documented in
`fixtures/BENCHMARK_CONTRACT.md` section 2 but have no corresponding
`.py` file yet. Table extraction is explicitly never routed through any
`VisionEnricher`, in any path — this rule is stated in the contract and
is already reflected in the chunking layer's design (native
`CanonicalTable` structures are chunked independently of pictures).

## B. CanonicalDocument

`CanonicalDocument` (`src/ingestion_bench/canonical/model.py`) represents
**what was extracted** from one source document — never *how* it was
extracted (that is `ExtractionRun`) and never *what should have been
extracted* (that is `reference_manifest.json`).

It is designed to remain:

- **Parser-neutral** — nothing in `canonical/` imports Docling, OpenAI, or
  any document-parsing library (`python-docx`, `python-pptx`, `reportlab`,
  `PIL`, `fitz`, `pypdf`). Enforced by
  `tests/test_chunking.py::test_chunking_source_has_no_forbidden_import_statements`
  for the chunking layer that consumes it; the canonical package itself has
  no such library as a dependency at all (see `requirements.txt`).
- **Independent of benchmark ground truth** — `CanonicalDocument` has no
  `manifest_version` or `manifest_sha256` field. That link is carried
  exclusively by `BenchmarkBinding` (`src/ingestion_bench/benchmark_binding.py`),
  a model deliberately kept outside `canonical/`. See section C.
- **Deterministic** — every id on the document (`block_id`, `table_id`,
  `picture_id`, `annotation_id`, diagram `node_id`) is derived via
  `stable_element_id()` (`canonical/hashing.py`) from stable identity
  components, never `uuid4()` or Python's built-in `hash()`.
- **Auditable and provenance-preserving** — every structural element and
  annotation carries `unit_index` and (optionally) a `bbox`; `ProvenanceEntry`
  additionally carries `z_order`, `source_element_ref`, and a free-form
  `source_locator` for parser-specific detail that doesn't fit a fixed field.

`CanonicalDocument`'s own construction-time validators (nine
`model_validator` methods in `canonical/model.py`) enforce referential
integrity across the whole document — e.g. every `Annotation.target_ref`
must resolve to a real block/table/picture id, every `bbox` must use its
owning `CanonicalUnit`'s coordinate system, every `CanonicalTableCell` must
fit within its table's declared bounds, and `block_id`/`table_id`/`picture_id`
share one global uniqueness namespace (since `target_ref` can point at any
of them). See `tests/test_canonical_schema.py` for the corresponding tests
(87 tests as of this writing).

## C. Reference manifest

`fixtures/reference_manifest.json` (currently `manifest_version: "1.2.1"`,
`status: "approved_frozen"`) is:

- **Synthetic benchmark ground truth** — a human-authored specification of
  facts (headings, paragraphs, identifiers, tables, pictures, diagram
  nodes/edges, visual facts, and deliberately-false "unsupported claims")
  for a fictional Enterprise Resilience domain, explicitly unrelated to the
  `src/` GraphRAG POC's corpus.
- **The fixture-generation specification** — `fixtures/generate_fixtures.py`
  reads this file and deterministically produces the DOCX/PDF/PPTX/PNG
  fixture files under `fixtures/generated/` (gitignored; regenerated
  on demand, not committed).
- **The evaluator's answer key** — intended to be the sole ground truth an
  (unimplemented) evaluator compares extracted `CanonicalDocument`/
  `CanonicalChunk` output against. No LLM is used to grade extraction
  quality (see decision D-004).
- **Not an input to any parser adapter.** A parser adapter never reads this
  file; it only ever sees the source document bytes.
- **Not required for ordinary production documents.** This manifest exists
  solely to drive and score the synthetic benchmark corpus — a real
  production document has no equivalent file.
- **Not part of `CanonicalDocument` identity.** `stable_canonical_hash()`
  (`canonical/hashing.py`) never depends on this file or on
  `BenchmarkBinding`. See `tests/test_canonical_hashing.py::test_canonical_hash_independent_of_benchmark_binding`.

The architectural rule, stated verbatim in `fixtures/BENCHMARK_CONTRACT.md`:
**"`CanonicalDocument` says what was extracted; `reference_manifest.json`
says what should have been extracted; the evaluator compares the two."**
See decision D-003.

## D. Canonical chunking

Implemented in `src/ingestion_bench/chunking/` (`model.py`, `chunker.py`,
`renderers.py`), consuming only `ingestion_bench.canonical` types — enforced
by `tests/test_chunking.py::test_chunking_source_has_no_forbidden_import_statements`.

- **Structural, not generic token-stream chunking.** `chunk_document()`
  walks `CanonicalDocument`'s own structural elements (headings,
  paragraphs, list items, tables, pictures) in reading order — it never
  operates on a flattened text blob or a fixed token window.
- **Complete paragraphs/list items where possible** — text elements are
  packed into a buffer up to `ChunkingConfig.max_chars`; only an
  individual element that itself exceeds `max_chars` is split
  (`split_oversized_text`), and even then along sentence, then word,
  boundaries — never mid-word.
- **Standalone native tables** — `ChunkingConfig.table_as_standalone_chunk`
  defaults to `True`; a table's cells are rendered with fully explicit
  structural metadata (`row`, `col`, `header=true|false`, `rowspan`,
  `colspan` on every cell — never inferred from pipe-table position).
- **Pictures with captions and annotations** — a picture is chunked with
  its caption(s) and any OCR/model-derived annotation text; a picture with
  no textual annotation at all is still retained as an asset-only chunk via
  `ChunkAssetRef` (decision D-017).
- **Heading-context propagation** — every chunk carries `heading_path`
  (display breadcrumb) and `heading_source_element_ids`/`heading_source_refs`
  (auditable trace back to the actual `CanonicalHeading` elements), plus
  the active headings' own rendered annotation content, kept separate as
  extracted vs. model-derived text.
- **Page/slide boundaries by default** — `ChunkingConfig.cross_unit_boundaries`
  defaults to `False`; a chunk never spans two `CanonicalUnit`s unless
  explicitly configured to.
- **Source-derived / model-derived separation** — every chunk has a
  `source_text` field (never includes model-derived content) and a
  separate `model_derived_text` field, always populated when such
  annotations exist regardless of `ChunkingConfig.include_model_derived_annotations`
  (that flag only controls `retrieval_text` inclusion).
- **Deterministic IDs and hashes** — see section F.
- **No generic cross-chunk overlap.** See decision D-014.

## E. Document revision lineage

`DocumentRevisionContext` and the corresponding fields copied onto every
`CanonicalChunk` (`src/ingestion_bench/chunking/model.py`):

| Field | Meaning |
|---|---|
| `logical_document_id` | The document's identity across revisions — e.g. "this policy," independent of which specific upload or version. **Never derived from a filename.** |
| `document_revision_id` | Identity of *this specific revision* — deterministically derived (`compute_document_revision_id()`) from `logical_document_id`, `source_document_sha256`, a normalized `version_label`, and `revision_number`. Two revisions of the same logical document share `logical_document_id` but have different `document_revision_id`s. |
| `source_document_sha256` | Hash of the exact uploaded source file bytes for this revision. Must match `CanonicalDocument.source_sha256` — `chunk_document()` raises `ValueError` if they disagree. |
| `version_label` | Free-form human label (e.g. `"v2"`, a draft marker), canonically normalized (stripped, lower-cased) at storage time, not just at hash-input time — see decision D-029. |
| `revision_number` | Optional integer ordering hint. |

**Why mutable state does not belong on `CanonicalChunk`:** fields like
`is_latest`, `is_current`, `publication_status`, effective dates,
`superseded_by_revision_id`, or an ingestion timestamp describe the
*current retrieval-time status* of a revision — they can change without
the underlying extracted content changing at all. `CanonicalChunk` is a
stable, hashed, content-addressed record; if any of these fields
participated in its identity or hash, the same immutable content would
need a new chunk record every time its retrieval status changed, which
defeats the purpose of content-addressed identity. `CanonicalChunk`
deliberately has none of these fields
(`tests/test_chunking.py::test_no_mutable_revision_state_fields_on_canonical_chunk`
asserts this by name). They belong to a future document-revision registry
/ `ChunkIndexRecord` — **not implemented in this repository.**

**Intended default retrieval policy** (documented on `DocumentRevisionContext`,
not yet enforced by any implemented retrieval code, since no retrieval
layer exists yet): retrieve the currently effective authoritative
revision; do not merely boost the most recently uploaded revision; drafts
and future-effective revisions must not supersede the current active
revision; historical revisions are included only for explicit historical
or comparison queries.

## F. Hash identities

Six distinct hash-shaped identities exist in this codebase. They serve
different purposes and are validated as separate lowercase 64-character
SHA-256 hex fields wherever they appear as a model field — they must never
be treated as interchangeable:

| Identity | Computed by | Purpose |
|---|---|---|
| `source_document_sha256` | caller (hash of uploaded file bytes) | Exact uploaded source identity for one revision. Also appears as `CanonicalDocument.source_sha256`; the two must agree. |
| Canonical document hash | `canonical/hashing.py::stable_canonical_hash(document)` | Content-derived hash of the *entire* `CanonicalDocument` — pins an exact extracted-content version (used by `ExtractionRun.canonical_document_hash` and `BenchmarkBinding.canonical_document_hash`). |
| `CanonicalChunk.content_sha256` | `chunker.py::emit_chunk` via `canonical_sha256()` | Integrity hash of one chunk's *full auditable content*, including provenance (`source_refs`, `heading_source_refs`, `asset_refs`) — changes if bbox, source order, or asset identity changes, even when rendered text does not. |
| `CanonicalChunk.embedding_input_sha256` | `chunker.py::emit_chunk` via `text_sha256()` | Hash of the exact `retrieval_text` handed to an embedding model, for embedding reuse/deduplication. `None` when `retrieval_text` is empty (e.g. an asset-only picture chunk) — deliberately does not collapse onto `sha256("")`. |
| `CanonicalChunk.chunk_id` | `canonical/hashing.py::stable_element_id(...)` | Unique chunk **occurrence** identity within one document revision — its discriminator folds in the chunker version, the chunking-config hash, and `document_revision_id`, so identical text across two revisions still produces different `chunk_id`s. |
| `manifest_sha256` | `canonical/hashing.py::compute_manifest_sha256(manifest)` | Hash of `reference_manifest.json`'s own canonical JSON serialization — pins an exact frozen manifest revision. Used by `BenchmarkBinding.manifest_sha256` and recorded in `fixtures/generated/generation_report.json`. Deliberately excludes any `manifest_sha256` key from its own input (a hash of the manifest cannot include itself), and the frozen file does not embed it. |

Why they must not be conflated: `content_sha256` changing does not imply
`embedding_input_sha256` changed (provenance-only edits change the former,
not the latter — see `tests/test_chunking.py::test_changing_only_provenance_changes_content_hash_but_not_embedding_hash`).
`source_document_sha256` identifies the *source file*; the canonical
document hash identifies the *extracted content*, which could in
principle differ across two extraction runs of the same source file if
the parser or its configuration changed. `chunk_id` identifies an
*occurrence*, not content — the same `content_sha256` can legitimately
appear under two different `chunk_id`s across two document revisions
(decision D-020).

## G. Future knowledge projections

Vector indexes, graph projections, and wiki-style pages are intended to be
**derived retrieval projections**, never the authoritative source of
truth. The authoritative sources remain, in this order:

1. The original source document.
2. The extracted `CanonicalDocument` (and its `CanonicalChunk[]`).
3. Provenance (`ProvenanceEntry`, `ChunkSourceRef`, `ChunkAssetRef`).
4. `ExtractionRun` metadata (which parser, which config, which model
   artifacts/remote calls produced this content).

**No projection of any kind has been implemented for this pipeline yet.**
`src/ingestion_bench/` contains no embedding, vector-store, or graph-build
code. The **existing** `src/build_graph_artifacts.py` /
`graph_enriched_retriever.py` / `vector_retriever.py` files are part of the
**separate, earlier ER GraphRAG POC** described in the root `README.md` —
they operate over a small hand-seeded corpus with hand-seeded graph
relationships, entirely independent of `CanonicalDocument`/`CanonicalChunk`.
They are not "the" knowledge projection for this benchmark and must not be
read as evidence that a Graph RAG projection of ingestion-bench output
exists. See decision D-025.
