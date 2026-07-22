# Implementation Handoff Seed — Enterprise Document-Ingestion Benchmark

This is **not** the final handoff prompt. It is a concise source document
containing only validated, reusable information a future implementation
(by another engineer or another agent) can be built from, without
repeating this project's exploratory design process. It excludes
conversation history, abandoned alternatives, repeated debate, speculative
features, and any claim not verifiable from the repository itself.

Source of truth: `docs/POC_ARCHITECTURE.md`, `docs/POC_DECISION_LOG.md`,
`docs/IMPLEMENTATION_WALKTHROUGH.md`, `docs/POC_STATUS_AND_EVIDENCE.md`,
and the repository at Stage 5A (see `git log` for the exact commit once
made).

---

## Validated target architecture

```
Source documents (DOCX/PDF/PPTX)
  -> Parser Adapter (path A DONE; B/C/D not implemented — build next)
  -> CanonicalDocument                  [implemented — do not redesign]
  -> DocumentRevisionContext            [implemented — supplied by caller]
  -> chunk_document(...)                [implemented — do not redesign]
  -> CanonicalChunk[]
  -> Embedding / Knowledge Projections  [not implemented]
  -> Retrieval                          [not implemented, for this pipeline]
  -> Agent                              [out of scope]
  -> Evaluation vs. reference_manifest.json  [not implemented — build after Stage 6/7]
```

Final module boundaries:

- `src/ingestion_bench/canonical/` — `model.py`, `annotations.py`,
  `extraction_run.py`, `hashing.py`. Parser-neutral, hashed, no
  Docling/OpenAI/DOCX/PDF/PPTX imports.
- `src/ingestion_bench/benchmark_binding.py` — the *only* link between
  extracted content and manifest identity; stays outside `canonical/`.
- `src/ingestion_bench/chunking/` — `model.py`, `chunker.py`,
  `renderers.py`. Depends only on `ingestion_bench.canonical`.
- `src/ingestion_bench/adapters/` — **path A implemented.** `base.py`
  (`DocumentParserAdapter` protocol, `AdapterConversionResult`,
  `AdapterDiagnostic`); `docling_standard/` (`config.py`, `diagnostics.py`,
  `mapper.py`, `adapter.py`) — the only package that may import Docling/
  docling-core. `openai_adapter.py` (path C) does not exist yet.
- `src/ingestion_bench/vision/` — **does not exist yet.** Expected shape:
  a `VisionEnricher` protocol, `NoOpVisionEnricher`, `OpenAIVisionEnricher`
  (path B), optionally `GraniteVisionEnricher` (path D, deferred).
- `fixtures/` — `reference_manifest.json` (frozen), `BENCHMARK_CONTRACT.md`
  (frozen), `manifest_schema.py`, `generate_fixtures.py`, `diagram_image.py`.
- `src/` (repository root, outside `ingestion_bench/`) — the **separate**
  hand-seeded ER GraphRAG POC. Do not conflate it with this pipeline; do
  not modify it as part of ingestion-bench work.

## Existing contracts that must be preserved

- **Canonical contract**: `src/ingestion_bench/canonical/model.py` +
  `annotations.py` field inventory and every `model_validator` listed in
  `docs/IMPLEMENTATION_WALKTHROUGH.md` Stage 2. `CanonicalDocument` must
  never gain a `manifest_version`/`manifest_sha256` field.
  `stable_canonical_hash()` must never depend on benchmark metadata.
- **Chunking contract**: `src/ingestion_bench/chunking/model.py` +
  `chunker.py` public API — `chunk_document(document, config=None, *,
  revision_context)`, `ChunkingConfig`, `CanonicalChunk`, `ChunkSourceRef`,
  `ChunkAssetRef`, `TextFragment`, `DocumentRevisionContext`. `chunk_document`
  must remain pure and deterministic.
- **Manifest contract**: `fixtures/reference_manifest.json` (`manifest_version:
  "1.2.1"`, frozen — do not edit) and `fixtures/BENCHMARK_CONTRACT.md`
  (frozen, one amendment already folded in).
- **Artifact contract**: `fixtures/generated/generation_report.json`'s
  shape (per-file SHA-256 + size, `manifest_sha256`, `manifest_version`,
  excludes itself). Fixture generation must remain byte-deterministic.
- **Adapter contract** (new, Stage 5A): `src/ingestion_bench/adapters/base.py`'s
  `DocumentParserAdapter` protocol and `AdapterConversionResult` model —
  every future adapter (path B/C/D) must return this same shape. Docling/
  docling-core types must never appear outside
  `src/ingestion_bench/adapters/docling_standard/`.

## Implementation order (validated stage sequence)

1. Stage 1 — benchmark contract + frozen manifest. **Done.**
2. Stage 2 (+2.1) — canonical model + hashing. **Done.**
3. Stage 3 (+3.1) — deterministic fixture generation. **Done.**
4. Stage 4 (+4.1, 4.2, 4.2a) — canonical chunking. **Done.**
5. Stage 5A — Docling `DOCLING_STANDARD_LOCAL` adapter (path A). **Done.**
   `docling==2.114.0` installed and pinned; zero `VisionEnricher`
   dependency; all 9 generated fixtures convert successfully and chunk
   through the unmodified frozen chunker.
6. Stage 6 — `VisionEnricher` framework + `OpenAIVisionEnricher` (path B). **Next.**
7. Stage 7 — OpenAI vendor-native adapter (path C).
8. Stage 8 — evaluator, scoring `CanonicalDocument`/`CanonicalChunk`
   output against `reference_manifest.json` only (never LLM-grades-LLM).
9. Optional/deferred — local Granite Vision (path D), revisit only on a
   concrete local-only-deployment requirement.

## Acceptance tests another implementation must satisfy

At minimum, the full existing suite must continue to pass unmodified:
`tests/test_canonical_schema.py` (87), `tests/test_canonical_hashing.py`
(21), `tests/test_fixture_generation.py` (38), `tests/test_chunking.py`
(110), `tests/test_docling_standard_mapper.py` (28),
`tests/test_docling_standard_adapter.py` (8),
`tests/test_docling_standard_integration.py` (30) — 322 total. A new
adapter/evaluator implementation must add its own test files following
the same pattern (one file per concern, `pytest`, `pythonpath = src
fixtures` per `pytest.ini`) rather than modifying the existing ones.

Specific invariants a parser adapter must satisfy, verifiable by
constructing its output and running it through existing validators —
**already proven true for the Stage 5A Docling adapter**, and required of
any future adapter (path B/C/D) too:

- Every id it produces (`block_id`, `table_id`, `picture_id`,
  `annotation_id`, diagram `node_id`) must come from
  `canonical.hashing.stable_element_id()`, never `uuid4()`/`hash()`.
- Every path it writes onto `CanonicalDocument`/`CanonicalPicture` must be
  relative and POSIX-style; absolute paths belong only on
  `ExtractionRun.raw_artifact_refs`.
- Every `bbox` must be converted into its owning `CanonicalUnit`'s
  coordinate system before construction (the model validates, it does not
  convert).
- Tables must come from native structural parsing, never a
  `VisionEnricher`.
- The resulting `CanonicalDocument` must construct without raising —
  i.e. it must pass every validator in `canonical/model.py` unmodified.
- Passing the adapter's `CanonicalDocument` through the existing,
  unmodified `chunk_document()` must succeed.
- A missing/unrepresentable value is never fabricated — recorded as a
  diagnostic and either skipped or represented through the least-
  speculative valid canonical field, never invented (the Docling adapter's
  DOCX page-geometry fallback is the one deliberate, explicitly-diagnosed
  exception: a real value read from the source file itself via
  `python-docx`, never a fake Letter/A4 default).

## Enterprise constraints

- **Parser neutrality** — no adapter-specific type may leak into
  `canonical/` or `chunking/`.
- **No benchmark leakage into production models** — `reference_manifest.json`
  is never an input to a parser; a production document has no manifest.
- **Deterministic identities** — every id/hash is a pure function of
  stable inputs, never random, never wall-clock-dependent.
- **Auditability** — every extracted fact traces back to a source element
  via `ProvenanceEntry`/`ChunkSourceRef`; every annotation carries
  `extraction_method` and `derivation`.
- **Provenance** — bbox, unit index, z-order, and source-format-native
  references are preserved wherever the source format exposes them.
- **Separation of source-derived and model-derived content** — never
  merge OCR/native text with a model's generative reading/description in
  one field; never mix `source_text` and `model_derived_text`.
- **Revision lineage** — `logical_document_id` is never derived from a
  filename; `document_revision_id` is always deterministic
  (`compute_document_revision_id`); mutable retrieval state (`is_latest`,
  `publication_status`, etc.) never belongs on `CanonicalChunk`.
- **Effective-revision retrieval behavior** — any future retrieval layer
  must implement the documented default policy (retrieve the currently
  effective revision, never merely the most recent upload) — see
  `docs/POC_ARCHITECTURE.md` section E.
- **No secret logging** — `RemoteInferenceCall` and every audit record
  must never contain an API key or other secret; `.env` must never be
  read/printed/committed.
- **No unapproved model/data egress** — only synthetic fixtures may ever
  be sent to a remote model (OpenAI paths B/C); no organizational document
  may be sent to any external API from this codebase.

## Explicit non-goals (for the first reproduction)

- Any UI.
- A production document-revision registry or `ChunkIndexRecord`
  implementation (only the model semantics that anticipate it).
- A production vector/graph/wiki store or index.
- Retrieval-relevance or answer-quality evaluation.
- Production scalability, load testing, or cost optimization.
- OpenShift or any deployment target.
- Local Granite Vision (path D) unless a concrete local-only-deployment
  requirement is given.
- Generalized enterprise workflow integration.
- Modifying the existing hand-seeded `src/` GraphRAG POC.

## Required evidence from the reproducing agent

At the end of each implementation stage, report:

- Files changed (full paths).
- Full `pytest` output (all files, not just new ones) and the resulting
  total test count.
- Extraction metrics against `reference_manifest.json`, once an evaluator
  exists (per `fixtures/BENCHMARK_CONTRACT.md` section 9 — text/structure
  recall, identifier recall split by unique vs. occurrence, visual/vision
  metrics where applicable).
- Latency (cold and warm, where relevant).
- API token/cost usage report for any remote call (OpenAI paths B/C).
- Deliberate deviations from this seed's contracts, stated explicitly.
- Unresolved issues, marked `Needs confirmation` rather than guessed.
- Deployment assumptions made (target OS, Python version, GPU
  availability, model storage location).

## Decisions the reproducing agent must not reopen

Every decision in `docs/POC_DECISION_LOG.md` marked **Accepted**,
specifically:

D-001 (parser-neutral canonical model), D-002 (Docling as adapter, not
domain dependency), D-003 (manifest kept outside `CanonicalDocument`),
D-004 (human-defined ground truth, not LLM-grades-LLM), D-005
(deterministic fixture generation), D-006 (source/model-derived
separation), D-007 (original image authoritative over description), D-008
(native table extraction independent of vision models), D-010
(deterministic IDs/hashes, never UUID4/`hash()`), D-011 (runtime paths
outside stable identity), D-012 (canonical/benchmark separation as a
standing principle), D-013 (structural, not sliding-window, chunking),
D-014 (no generic chunk overlap), D-015 (captions never standalone
chunks), D-016 (tables/pictures standalone by default), D-017 (asset-only
pictures preserved), D-018 (provenance included in chunk hashing), D-019
(content identity separate from embedding-input identity), D-020/D-024
(same-text chunks preserved across revisions, embeddings reusable), D-021
(mutable revision state outside `CanonicalChunk`), D-025 (knowledge
projections derived, not authoritative), D-026 (deterministic fixture
engineering), D-027 (dependency-free fixture verification), D-028
(fragment-level split provenance), D-029 (`version_label` canonicalization
at storage), D-030 (fully explicit table metadata), D-031 (splitting must
run against the canonical element's own text, never combined rendered
text), D-032 (Docling confined to the adapter boundary), D-033 (explicit
`RapidOcrOptions`, never Docling's OCR auto-selection), D-034 (DOCX page
geometry read from `python-docx` as a documented fallback, never
fabricated), D-035 (OCR-origin detected structurally via picture-child
nesting, never inferred from which fixture is being processed), D-036
(artifact file-path keys format-qualified, distinct from `doc_id`).

D-009 (Granite Vision optional/deferred), D-022 (effective-revision
retrieval policy), D-023 (upstream duplicate-upload rejection policy) are
Accepted as *decisions*/*policies* but have **no implementation** — do not
claim they are built; do implement against their stated semantics when the
relevant layer (path D, retrieval, ingestion entrypoint) is eventually
built.
