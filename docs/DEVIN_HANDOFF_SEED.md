# Implementation Handoff Seed — Enterprise Document-Ingestion Benchmark

This is **not** the final handoff prompt. It is a concise source document
containing only validated, reusable information a future implementation
(by another engineer or another agent) can be built from, without
repeating this project's exploratory design process. It excludes
conversation history, abandoned alternatives, repeated debate, speculative
features, and any claim not verifiable from the repository itself.

Source of truth: `docs/POC_ARCHITECTURE.md`, `docs/POC_DECISION_LOG.md`,
`docs/IMPLEMENTATION_WALKTHROUGH.md`, `docs/POC_STATUS_AND_EVIDENCE.md`,
and the repository at Stage 5A.2 (see `git log` for the exact commit once
made).

---

## Validated target architecture

```
Source documents (DOCX/PDF/PPTX)
  -> Parser Adapter (path A DONE, frozen; B/C/D not implemented — Stage 8A/8B/D)
  -> CanonicalDocument                  [implemented — do not redesign]
  -> DocumentRevisionContext            [implemented — supplied by caller]
  -> chunk_document(...)                [implemented — do not redesign]
  -> CanonicalChunk[]                   [common evidence substrate — D-040]
  -> Ingestion-fidelity evaluator vs. reference_manifest.json  [not implemented — Stage 6A, NEXT]
  -> Gold fact-to-chunk evidence-alignment catalog              [not implemented — Stage 6A output]
  -> Retrieval benchmark contract + gold evidence set            [not implemented — Stage 6B]
  -> Knowledge Projections (vector / graph / wiki), independently
     derived from the SAME CanonicalDocument/CanonicalChunk corpus
     and the SAME Stage 6A evidence-alignment catalog (D-040)      [not implemented — Stage 7A/7B/7C]
  -> Agent                              [out of scope]
  -> Cross-lane quality/cost/latency/ROI comparison               [not implemented — Stage 9]
```

Two independent benchmark dimensions (see D-040 and
`docs/POC_STATUS_AND_EVIDENCE.md` "Benchmark dimensions"): **ingestion
approach** (Docling Standard Local / Docling + OpenAI vision enrichment /
OpenAI vendor-native / optional local vision) × **retrieval projection**
(vector RAG / Graph RAG / wiki retrieval). No stage before Stage 9
attempts to evaluate a combination of both dimensions at once.

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
- **Adapter contract** (Stage 5A, hardened Stage 5A.1/5A.2): `src/ingestion_bench/adapters/base.py`'s
  `DocumentParserAdapter` protocol and `AdapterConversionResult` model —
  every future adapter (path B/C/D) must return this same shape,
  including its Stage 5A.1/5A.2 invariants (`elapsed_ms >= 0`;
  `source_sha256` lowercase-hex-64; `source_relative_path`
  portable/relative; `conversion_status` ↔ `canonical_document`/
  `extraction_run` presence; `conversion_status="success"` ↔ no
  fidelity-affecting diagnostic; all enforced by Pydantic validators, not
  just convention). Every `AdapterDiagnostic` a future adapter records
  must set `affects_fidelity` correctly (severity and fidelity impact are
  independent axes — see `docs/POC_DECISION_LOG.md` D-037) since
  `conversion_status` derivation depends on it. Docling/docling-core types
  must never appear outside `src/ingestion_bench/adapters/docling_standard/`.
- **Determinism-evidence contract** (Stage 5A.2, D-039): any runner that
  claims deterministic output must report the claim component by
  component — full serialized `CanonicalDocument` JSON, the stable
  canonical hash, full serialized `CanonicalChunk` list JSON, ordered
  `chunk_id`s, and ordered `content_sha256` values, each as its own
  boolean result — never one collapsed hash comparison presented as proof
  of full-output determinism. An aggregate `all_equal`-style field may
  exist only as a summary derived from the individual results, never as
  the sole reported figure.
- **Shared-evidence-substrate contract** (D-040): `CanonicalDocument` and
  `CanonicalChunk` are the one common, authoritative evidence layer every
  future knowledge projection (vector index, graph, wiki) is derived
  from. No projection-specific field (a graph edge weight, a wiki page
  slug, a vector-index id) may ever be added to `CanonicalDocument` or
  `CanonicalChunk`. Every projection must remain independently
  rebuildable from `CanonicalDocument`/`CanonicalChunk` alone, and every
  graph edge or wiki claim a future projection produces must retain
  supporting `CanonicalChunk` ids so it stays traceable back to this same
  evidence layer.

## Implementation order (validated stage sequence — corrected, Stage 5A.2)

**This sequence supersedes any earlier "Stage 6 = VisionEnricher" framing
found elsewhere in this project's history** (see D-040): the ingestion
evaluator and its gold evidence-alignment catalog must exist before
retrieval projections are worth comparing, and vision enrichment is one
more *ingestion* lane, not a prerequisite for retrieval work.

1. Stage 1 — benchmark contract + frozen manifest. **Done.**
2. Stage 2 (+2.1) — canonical model + hashing. **Done.**
3. Stage 3 (+3.1) — deterministic fixture generation. **Done.**
4. Stage 4 (+4.1, 4.2, 4.2a) — canonical chunking. **Done.**
5. Stage 5A (+5A.1 evidence/provenance hardening, +5A.2 evidence-contract
   correction) — Docling `DOCLING_STANDARD_LOCAL` adapter (path A).
   **Done, frozen.** `docling==2.114.0` installed and pinned; zero
   `VisionEnricher` dependency; all 9 generated fixtures produce a valid
   `CanonicalDocument` (7 `success`, 2 `partial` — DOCX, since Docling
   exposes no DOCX pagination geometry, D-037) and chunk through the
   unmodified frozen chunker; conversion determinism is backed by five
   independent component-level comparisons (D-039); `success` status
   cannot coexist with a fidelity-affecting diagnostic; environment/
   model-footprint evidence is collected live, never hand-typed.
6. Stage 6A — deterministic ingestion-fidelity evaluator, scoring
   `CanonicalDocument`/`CanonicalChunk` output against
   `reference_manifest.json` only (never LLM-grades-LLM). Produces the
   gold fact-to-chunk evidence-alignment catalog reused by every later
   retrieval projection (D-040). **Next.**
7. Stage 6B — retrieval benchmark contract + gold evidence set, built on
   the Stage 6A alignment catalog.
8. Stage 7A — regular vector RAG projection + retrieval baseline.
9. Stage 7B — graph-enriched RAG projection.
10. Stage 7C — wiki page/link projection.
11. Stage 8A — selective OpenAI vision enrichment, `VisionEnricher`
    framework + `OpenAIVisionEnricher` (path B).
12. Stage 8B — OpenAI vendor-native adapter (path C).
13. Stage 9 — cross-lane quality, cost, latency, and ROI comparison across
    every ingestion-approach × retrieval-projection combination.
14. Optional/deferred — local Granite Vision (path D), revisit only on a
    concrete local-only-deployment requirement.

## Acceptance tests another implementation must satisfy

At minimum, the full existing suite must continue to pass unmodified:
`tests/test_canonical_schema.py` (87), `tests/test_canonical_hashing.py`
(21), `tests/test_fixture_generation.py` (38), `tests/test_chunking.py`
(110), `tests/test_docling_standard_mapper.py` (28),
`tests/test_docling_standard_adapter.py` (10),
`tests/test_docling_standard_integration.py` (34),
`tests/test_adapters_base.py` (19),
`tests/test_run_docling_standard_report.py` (3) — 350 total, 3 warnings
(pre-existing Docling-dependency deprecation warnings, not this project's
own code). A new adapter/evaluator implementation must add its own test
files following the same pattern (one file per concern, `pytest`,
`pythonpath = src fixtures` per `pytest.ini`) rather than modifying the
existing ones.

Specific invariants a parser adapter must satisfy, verifiable by
constructing its output and running it through existing validators —
**already proven true for the Stage 5A/5A.1/5A.2 Docling adapter**, and
required of any future adapter (path B/C/D) too:

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
- Every `AdapterDiagnostic` sets `affects_fidelity` on its own merits, not
  copied from `severity` — `conversion_status` must be derived from
  `affects_fidelity` (plus the parser's own partial-success signal, if
  any), never from severity or warning/error counts alone (D-037).
- Every extracted-derivation annotation gets a matching `ProvenanceEntry`
  (`element_id` may resolve to the annotation's own `annotation_id`)
  whenever the parser actually supplies evidence for it — never a
  fabricated bbox/source reference when it doesn't (D-038).
- `conversion_status="success"` must never be constructible alongside a
  diagnostic with `affects_fidelity=True` — enforced by a Pydantic
  `model_validator` on `AdapterConversionResult`, not left to adapter-code
  discipline alone (D-037 continued, Stage 5A.2).
- Any claim of deterministic output must be backed by component-level
  evidence (full document JSON, stable hash, full chunk-list JSON,
  ordered chunk ids, ordered chunk content hashes — each reported
  separately), never a single collapsed comparison (D-039).

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
- **Canonical chunks as the common evidence substrate** (D-040) —
  `CanonicalDocument`/`CanonicalChunk` are the one shared, authoritative
  evidence layer for every future knowledge projection; no vector-,
  graph-, or wiki-specific field or metadata may ever enter either model.
- **Knowledge projections remain independently rebuildable** (D-040) —
  a future vector index, graph, or wiki must always be reconstructible
  from `CanonicalDocument`/`CanonicalChunk` alone; none of them is
  authoritative over another or over the canonical corpus.
- **Component-level determinism evidence** (D-039) — any future runner
  claiming deterministic output must report each comparison (document
  JSON, canonical hash, chunk-list JSON, chunk ids, chunk content hashes)
  independently, never as one collapsed pass/fail.

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
(artifact file-path keys format-qualified, distinct from `doc_id`), D-037
(`conversion_status` derived from a dedicated `affects_fidelity` axis,
never from diagnostic severity alone — and, since Stage 5A.2, `"success"`
is provably inconsistent with any fidelity-affecting diagnostic), D-038
(every `OcrAnnotation` Docling actually evidences gets a matching
`ProvenanceEntry`), D-039 (determinism reported component by component,
never as one collapsed hash comparison), D-040 (canonical chunks are the
common evidence substrate for every future knowledge projection; vector/
graph/wiki representations remain derived, never authoritative).

D-009 (Granite Vision optional/deferred), D-022 (effective-revision
retrieval policy), D-023 (upstream duplicate-upload rejection policy) are
Accepted as *decisions*/*policies* but have **no implementation** — do not
claim they are built; do implement against their stated semantics when the
relevant layer (path D, retrieval, ingestion entrypoint) is eventually
built.
