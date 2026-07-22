# Implementation Walkthrough — Enterprise Document-Ingestion Benchmark

This document explains **what has actually been implemented**, stage by
stage, with pointers to real source paths, symbols, and tests. It does not
repeat the *why* — see `docs/POC_DECISION_LOG.md` for that.

Convention used throughout: `[IMPLEMENTED]` means the code exists and is
tested in this repository today. `[PLANNED]` means it is architecturally
decided (in `fixtures/BENCHMARK_CONTRACT.md` or `docs/POC_DECISION_LOG.md`)
but has no corresponding code yet. Nothing in this document should be read
as claiming a planned step has run against real data.

---

## Stage 1 — Benchmark contract and frozen manifest `[IMPLEMENTED]`

**Files:** `fixtures/reference_manifest.json`, `fixtures/BENCHMARK_CONTRACT.md`

`reference_manifest.json` (`manifest_version: "1.2.1"`, `status:
"approved_frozen"`) is hand-authored, synthetic, and organized into two
suites:

- **`parity_suite`** (`doc_id: "PARITY_001"`) — the same semantic content
  rendered natively in DOCX, PDF, and PPTX, split into two logical units
  (unit 0: text/distractors/table; unit 1: picture/caption) with a hard
  page/slide break between them. Contains: 3 headings (`H_001`–`H_003`),
  5 paragraphs (`P_001`–`P_005`), 4 target identifiers with 9 curated
  occurrences plus 2 distractor identifiers with 3 occurrences, 2
  distractor facts (`D_001`, `D_002`), 1 table (`T_001`, 4×2), 1 caption
  (`CAP_001`), 1 picture (`PIC_001`) with 3 expected OCR tokens, 3 diagram
  nodes and 2 diagram edges recoverable only via vision enrichment, and 1
  "visual distractor fact" (`VD_001`) — a plausible but false diagram claim.
- **`stress_suite`** — six independent, format-specific fixtures, each
  targeting one extraction capability: `docx_nested_structure` (3-level
  heading hierarchy + 3-level nested lists), `pdf_complex_layout`
  (two-column reading order + a merged-cell table), `pptx_overlapping_textboxes`
  (two overlapping text boxes with different `z_order`, one stale), `pptx_native_diagram`
  (native PPTX shapes/connectors — an *exploratory* capability with five
  independent sub-metrics, no capability assumed), `chart_visual_stress`
  (a bar chart with 6 supported numeric/comparative visual facts and 1
  deliberately unsupported claim), and `scanned_pdf_ocr_stress` (a
  single-page PDF with **no digital text layer at all**, forcing OCR).

**Why positive and negative claims both exist:** every suite pairs true
facts with deliberately false or confusable ones — distractor identifiers
(`APP-224499` vs. `APP-224510`; `C-88a` vs. `C-88`, a literal substring
stress case), a distractor table row, a "visual distractor fact," and an
"unsupported claim" in the chart suite. This is what makes deterministic
scoring meaningful without an LLM grader (decision D-004): a correct
extractor must recover the positive facts *and* must not assert the
negative ones.

`fixtures/BENCHMARK_CONTRACT.md` is the self-contained companion contract:
it defines the four parser lanes, the `VisionEnricher` protocol shape, the
complete canonical-model field inventory (as a spec, mirrored by the real
implementation in Stage 2), portability/hashing rules, and the evaluation
metrics an evaluator is expected to compute. It is frozen with one
post-freeze amendment already folded in (the `BenchmarkBinding` split,
decision D-003) and a recorded Stage 2.1 validation-hardening pass.

---

## Stage 2 — Canonical model and hashing `[IMPLEMENTED]`

**Files:** `src/ingestion_bench/canonical/model.py`, `annotations.py`,
`extraction_run.py`, `hashing.py`, `src/ingestion_bench/benchmark_binding.py`

### `canonical/model.py`

Defines the source-preserving structural core: `NormalizedBoundingBox`,
`BoundingBox`, `CanonicalUnit`, `CanonicalHeading`, `CanonicalParagraph`,
`CanonicalListItem`, `CanonicalCaption`, `CanonicalTableCell`/`CanonicalTable`,
`CanonicalPicture`, `ProvenanceEntry`, and `CanonicalDocument` itself.

`CanonicalDocument` has nine `model_validator(mode="after")` methods
enforcing whole-document referential integrity — none of them silently
repairs bad data, all of them raise:

| Validator | Invariant |
|---|---|
| `_validate_unique_unit_indices` | No two `CanonicalUnit`s share a `unit_index`. |
| `_validate_unit_references` | Every element's `unit_index` resolves to a real `CanonicalUnit`, with or without a `bbox`. |
| `_validate_caption_targets` | `CanonicalCaption.target_picture_id` resolves to a real `CanonicalPicture`. |
| `_validate_list_item_parents` | `CanonicalListItem.parent_block_id`, when set, resolves to another list item. |
| `_validate_annotation_target_refs` | Every `Annotation.target_ref` resolves to a real block/table/picture. |
| `_validate_provenance_element_ids` | Every `ProvenanceEntry.element_id` resolves to a real element or annotation. |
| `_validate_table_cell_bounds` | Every cell (+ span) fits within its table's `n_rows`/`n_cols`. |
| `_validate_unique_ids` | `block_id`/`table_id`/`picture_id` share one namespace; `annotation_id` and diagram `node_id` are each their own namespace. |
| `_validate_bbox_coordinate_systems` | Every `bbox`/`node_bbox` matches its owning unit's `coordinate_unit`/`coordinate_origin` — the model validates conversion, it never performs it. |

**Failure behavior:** every validator raises a Pydantic `ValidationError`
with a descriptive message identifying the offending element id — there is
no silent-repair path anywhere in this file.

**Tests:** `tests/test_canonical_schema.py` (87 tests) — one or more per
validator, e.g. `test_bbox_coordinate_unit_mismatch_rejected`,
`test_duplicate_picture_id_rejected`, `test_table_cell_span_exceeds_bounds_rejected`.

### `canonical/annotations.py`

`AnnotationBase` (`annotation_id`, `target_ref`, `unit_index`, `bbox`,
`derivation`, `extraction_method`, `confidence`) plus ten concrete
subtypes, unified as `Annotation = Annotated[Union[...], Field(discriminator="annotation_type")]`
— a Pydantic discriminated union, so a raw dict with the right
`annotation_type` parses into the correct concrete subtype automatically,
and an unrecognized `annotation_type` is rejected at validation time.
`IdentifierAnnotation.start_char`/`end_char` are validated both-or-neither,
half-open interval (`0 <= start_char <= end_char`).

### `canonical/extraction_run.py`

`ModelArtifact` (governance record for a *locally* invoked model),
`RemoteInferenceCall` (audit record for a remote API call — "Never contains
the API key or any other secret"), and `ExtractionRun` itself (`run_id`,
`doc_id`, `path_id: Literal["A","B","C","D"]`, parser identity, timing,
warnings, `raw_artifact_refs`, `canonical_document_hash`, and both lists
above). **This model has no code that constructs a real instance yet** —
no adapter exists to produce one.

### `canonical/hashing.py`

`stable_canonical_hash(document)` — SHA-256 over `CanonicalDocument`'s own
canonical JSON serialization. `compute_manifest_sha256(manifest)` — same
principle for `reference_manifest.json`, defensively excluding any
`manifest_sha256` key from its own input. `stable_element_id(doc_id,
element_type, unit_index, order_index=None, discriminator=None,
extra=None)` — the shared deterministic-id helper every adapter/generator
is expected to use instead of `uuid4()`/`hash()`.

**Tests:** `tests/test_canonical_hashing.py` (21 tests), including
`test_hashing_module_does_not_use_uuid4_or_builtin_hash`,
`test_stable_element_id_deterministic`.

### `benchmark_binding.py`

`BenchmarkBinding` (`doc_id`, `canonical_document_hash`, `run_id`,
`manifest_version`, `manifest_sha256`) — deliberately outside `canonical/`.
See decision D-003.

---

## Stage 3 — Deterministic fixtures `[IMPLEMENTED]`

**Files:** `fixtures/manifest_schema.py`, `fixtures/diagram_image.py`,
`fixtures/generate_fixtures.py`

### `manifest_schema.py`

A strict (`extra="forbid"` throughout) Pydantic schema describing
`reference_manifest.json`'s *own* shape — unrelated to `canonical/`, which
describes extracted content, not ground truth. `load_manifest_raw(path)`
returns the plain dict exactly as stored on disk (what
`compute_manifest_sha256` hashes); `load_manifest(path)` validates it
against `ReferenceManifest`.

### `diagram_image.py` / `generate_fixtures.py`

Pillow-based, deterministic image generators (fixed coordinates,
`ImageFont.load_default(size=X)`, no randomness) for the shared parity
diagram, the stress chart, and the scanned-text image. `generate_fixtures.py`
(≈556 lines) is the orchestrator: it reads the frozen manifest and produces

- `fixtures/generated/parity/PARITY_001.{docx,pdf,pptx}`
- `fixtures/generated/stress/STRESS_{DOCX_001,PDF_001,PPTX_001,PPTX_002,CHART_001,SCANNED_001}.{docx,pdf,pptx}`
- `fixtures/generated/images/{diagram_v1,chart_v1,scanned_text_v1}.png`
- `fixtures/generated/generation_report.json` — a manifest of every
  generated file's SHA-256 and byte size, plus the manifest's own
  `manifest_sha256`/`manifest_version`, excluding itself from its own
  inventory.

**`fixtures/generated/` is gitignored** — it is not committed and must be
regenerated locally (`docs/README.md` has the exact command).

Determinism is engineered explicitly, not assumed: a custom `reportlab`
canvasmaker forces `Canvas(invariant=1)` (fixed creation/mod dates, fixed
file ID); DOCX/PPTX `core_properties` are set to fixed values; every ZIP
entry in the saved `.docx`/`.pptx` is rewritten with a fixed `date_time`
after save. Native-format fidelity is engineered directly (real DOCX
paragraph/table objects, real PPTX shapes/connectors with `lxml`-patched
arrowheads) rather than rasterized, **except** where a raster image is the
deliberate test subject (`scanned_pdf_ocr_stress`, which has *no* digital
text layer at all — verified by counting actual glyph-showing PDF content-
stream operators, not a substring check, since `reportlab` emits a
boilerplate empty `BT...ET` block even with zero `drawString()` calls).

### What the fixture tests prove

`tests/test_fixture_generation.py` (38 tests) proves: every fixture file
exists and matches the manifest schema; native DOCX headings/paragraphs/
table cells match manifest text; PDF text (via a hand-written content-
stream parser, decision D-027) includes manifest facts; PPTX table cells
and both overlapping text boxes (with correct `z_order`) are present and
geometrically distinct (`test_stress_pptx_overlapping_textboxes_rectangles_intersect`,
`_positions_not_identical`); PPTX native diagram connectors reference the
correct shapes and have arrowheads; the shared diagram image is byte- or
pixel-identical across DOCX/PPTX/PDF embeddings; the chart image's pixel
content matches the manifest's numeric facts and changes if those facts
change; the scanned PDF has zero glyph-showing operators and zero
extractable text fragments while the parity/stress PDFs *do* have glyph
operators; regeneration is byte-for-byte deterministic
(`test_regeneration_is_byte_deterministic`) and produces the same
`manifest_sha256`; the generator's own source has no LLM/network calls
(`test_generator_source_has_no_llm_or_network_calls`).

### What the fixture tests do not prove

They do not prove that any real parser (Docling, OpenAI, or otherwise) can
correctly extract this content — no parser has run against these fixtures
yet. They verify the fixtures themselves are a faithful, deterministic
rendering of the manifest, nothing about extraction quality.

---

## Stage 4 / 4.1 / 4.2 / 4.2a — Canonical chunking `[IMPLEMENTED]`

**Files:** `src/ingestion_bench/chunking/model.py`, `chunker.py`,
`renderers.py`, `__init__.py`; `tests/test_chunking.py` (110 tests)

### `chunking/model.py`

| Symbol | Purpose | Key invariants |
|---|---|---|
| `TextFragment` | One exact, lossless slice of a split oversized element's *canonical* text (`CanonicalParagraph.text`/`CanonicalListItem.text` — never a rendered/prefixed/annotation-appended form, Stage 4.2a): `text`, `fragment_index`, `start_char`, `end_char`. | `start_char <= end_char`; `len(text) == end_char - start_char` (Stage 4.2a); concatenating fragments in order reproduces the source text exactly. |
| `ChunkSourceRef` | Points at exactly one contributing canonical element (or one fragment of one). | `unit_index >= 0`; `order_index` `None` or `>= 0`; `element_type` is a closed `Literal`; `fragment_index`/`start_char`/`end_char` must be all `None` or all populated together (three-way check, strengthened Stage 4.2a — previously only `start_char`/`end_char` were paired), span valid. |
| `ChunkAssetRef` | Retains a picture's stored-artifact identity on its chunk even with no textual annotation. | `content_sha256` validated as lowercase 64-char hex. |
| `compute_document_revision_id(...)` | Deterministic SHA-256 over `logical_document_id` + `source_document_sha256` + normalized `version_label` + `revision_number`. | Pure function; normalization shared with the stored field via `_normalize_version_label`. |
| `DocumentRevisionContext` | Explicit revision identity supplied to `chunk_document()`. | `document_revision_id` re-derived and checked equal at construction (never freely chosen); `version_label` stored in normalized form, rejected if empty-after-strip; `logical_document_id` rejected if empty-after-strip. |
| `CanonicalChunk` | The output unit of chunking. | See table below. |
| `ChunkingConfig` | Chunking behavior knobs (`max_chars`, `include_heading_context`, `include_model_derived_annotations`, `cross_unit_boundaries`, `table_as_standalone_chunk`, `picture_as_standalone_chunk`, `oversized_element_policy`). | `max_chars > 0`; `extra="forbid"`. |

`CanonicalChunk`'s own validators (beyond per-field hash-format checks on
`chunk_id`, `document_revision_id`, `source_document_sha256`,
`content_sha256`, `chunking_config_hash`, and `embedding_input_sha256`
when present): `unit_indices` nonempty/nonnegative/sorted/unique;
`source_element_ids` and `annotation_ids` each unique within the chunk;
`contains_model_derived` must agree with `model_derived_text is not None`.

**Failure behavior:** every violation raises `pydantic.ValidationError` at
construction — there is no partially-valid `CanonicalChunk`.

### `chunking/chunker.py`

| Function | Purpose | Input → Output |
|---|---|---|
| `split_oversized_text(text, max_chars)` | Deterministic, lossless split of one oversized element's own canonical text: sentence boundaries first, falling back to word boundaries within an oversized sentence, never mid-word. Callers must pass the canonical element's own text (`raw_text`) — never a rendered/prefixed/annotation-appended string (Stage 4.2a). | `(str, int) -> list[TextFragment]` |
| `_pack_boundary_spans(text, start, end, boundary_re, max_chars)` | Greedy span packer shared by the sentence and word passes; returns contiguous, non-overlapping `[start, end)` spans. | Internal helper. |
| `_build_ordered_elements(document)` | Produces the single reading-order sequence of headings/paragraphs/list items/tables/pictures, sorted by `(unit_index, order_index, type-rank, stable id)` — captions are deliberately excluded (pulled in only via their target picture). | `CanonicalDocument -> list[_RenderedElement]` |
| `_render_annotations_for_element(annotations_by_target, element_id)` | Routes an element's annotations into extracted text / model-derived text / annotation-id list, by each annotation's own `derivation` field. `IdentifierAnnotation` is never rendered as text. | Internal helper. |
| `_positioned_identifier_spans(...)` | Extracts `(annotation_id, start_char, end_char)` for identifiers with concrete offsets, for later fragment routing. | Internal helper. |
| `_render_heading_frames_annotations(frames)` | Merges a heading stack's own annotation ids and rendered content (extracted vs. model-derived, each line labeled `"[Heading: <text>] ..."`). | Internal helper. |
| `chunk_document(document, config=None, *, revision_context)` | The public entry point. | `(CanonicalDocument, ChunkingConfig | None, DocumentRevisionContext) -> list[CanonicalChunk]` |

**`chunk_document` invariants:** pure (never mutates `document`, no I/O);
deterministic (same inputs → byte-identical serialized output); raises
`ValueError` immediately if `document.source_sha256 != revision_context.source_document_sha256`;
raises `ValueError` if it would otherwise emit two chunks with identical
`(source_element_ids, source_refs, content_sha256)` within one call (an
accidental-duplicate guard, span-aware since Stage 4.2 so it never
false-positives on a legitimately repeated sentence fragment); never emits
a chunk with empty `source_text`, empty `model_derived_text`, and empty
`asset_refs` all at once.

**Algorithm walkthrough:**

1. **Reading-order construction** — `_build_ordered_elements` (see table).
2. **Heading-stack behavior** — `chunk_document` maintains a stack of
   `_HeadingFrame`s. A new heading pops any sibling/deeper heading off the
   stack first (`pop_headings_to_level`); a popped heading with no
   following content becomes its own standalone chunk, carrying its own
   (and any remaining ancestor's) annotation ids *and* rendered content —
   fixed in Stage 4.1 after a bug where this was silently dropped. Every
   chunk emitted while a heading is active carries `heading_path`
   (breadcrumb text), `heading_source_element_ids`/`heading_source_refs`
   (auditable trace), and the heading's own extracted/model-derived
   annotation content merged into the chunk's `source_text`/
   `model_derived_text` (Stage 4.2).
3. **Paragraph/list packing** — text elements accumulate in a buffer up to
   `max_chars`, flushed on a unit-boundary crossing (unless
   `cross_unit_boundaries=True`) or when the next element would exceed
   `max_chars`.
4. **Oversized-element splitting** — `split_oversized_text` runs against
   `_RenderedElement.raw_text` — the canonical `paragraph.text`/
   `item.text` alone, never the combined `source_text` that includes a
   list item's `"  - "` display prefix or the element's own extracted-
   annotation rendering (Stage 4.2a; previously Stage 4/4.1/4.2 split
   against `source_text`, which put fragment offsets in the wrong
   coordinate space whenever either of those was present). It produces
   `TextFragment`s; each becomes its own chunk carrying a `ChunkSourceRef`
   stamped with that fragment's own `fragment_index`/`start_char`/
   `end_char` (via `ChunkSourceRef.model_copy(update=...)`). A positioned
   `IdentifierAnnotation` — whose offsets are defined against the
   canonical element's own text — is routed to every fragment whose span
   contains or overlaps it; other (unpositioned) annotations on the
   element default to fragment 0 only. The list-item display prefix
   (`renderers.py::render_list_item_prefix`) and the element's own
   extracted-annotation text (`extra_source_text`, fragment 0 only) are
   both applied strictly *after* the split, when building each fragment's
   `source_text` — never before it, so neither can shift a character
   offset.
5. **Table rendering** — `renderers.py::render_table_text` (below).
6. **Picture/caption handling** — a picture's caption(s) and any
   OCR/model-derived annotation text are folded into one chunk together;
   the picture's `ChunkAssetRef` is always retained, even with no text at
   all (Stage 4.1).
7. **Source/model-derived routing** — see `_render_annotations_for_element`.
8. **Chunk provenance** — `source_refs`, `heading_source_refs`,
   `asset_refs`, all serialized into `content_sha256`'s payload.
9. **Revision context** — `logical_document_id`/`document_revision_id`/
   `source_document_sha256`/`version_label`/`revision_number` copied onto
   every emitted chunk.
10. **`content_sha256`** — SHA-256 over a canonical-JSON payload of
    `chunk_type`, `unit_indices`, `heading_path`, `source_element_ids`,
    `annotation_ids`, `source_text`, `model_derived_text`, and serialized
    `source_refs`/`heading_source_refs`/`asset_refs`.
11. **`embedding_input_sha256`** — SHA-256 of `retrieval_text` exactly, or
    `None` if `retrieval_text` is empty.
12. **`chunk_id`** — `stable_element_id(doc_id, "chunk", unit_indices[0],
    order_index=chunk_index, discriminator=f"{CHUNKER_VERSION}:{config_hash}:{document_revision_id}",
    extra={source_element_ids, annotation_ids, content_sha256})`.
13. **Duplicate handling** — the end-of-function guard described above.
14. **No-overlap** — see decision D-014; there is no code path that
    duplicates text across two chunks by design.

### `chunking/renderers.py`

`render_list_item_prefix` (the indentation + `"- "` marker alone, 2 spaces
per level — Stage 4.2a, factored out specifically so a split list item's
display prefix can be applied to every fragment independently of where
splitting occurs), `render_list_item` (`render_list_item_prefix(item)` +
`item.text`), `render_table_text` (every cell states `row`, `col`,
`header=true|false`, `rowspan`, `colspan` explicitly, sorted by
`(row, col)` — never inferred from pipe-table position), `render_visual_fact`,
`render_diagram_node`, `render_diagram_edge`,
`render_model_derived_annotation`/`render_extracted_annotation` (dispatch
by concrete annotation type).

### `chunking/__init__.py`

Public surface: `CHUNKER_VERSION`, `chunk_document`, `split_oversized_text`,
`CanonicalChunk`, `ChunkAssetRef`, `ChunkingConfig`, `ChunkSourceRef`,
`DocumentRevisionContext`, `TextFragment`, `canonical_sha256`,
`compute_chunking_config_hash`, `compute_document_revision_id`,
`text_sha256`.

### Tests

`tests/test_chunking.py` uses **only** manually constructed
`CanonicalDocument` objects — it deliberately never parses the Stage 3
DOCX/PDF/PPTX fixtures (no Docling adapter exists to do that parsing).
Dependency isolation is enforced by
`test_chunking_source_has_no_forbidden_import_statements`, which greps for
actual `import`/`from` statements (not bare substrings, to avoid a false
positive on this module's own docstrings naming Docling/OpenAI to explain
what they don't depend on).

---

## Worked example: CanonicalDocument → DocumentRevisionContext → chunk_document(...) → CanonicalChunk[]

This is real output from running the actual implementation (not
hand-written/invented) against a small, manually constructed
`CanonicalDocument` modeled on one real fact from the parity manifest
(`P_001` / `ID_001` in `reference_manifest.json`), using the real parity
PDF's `source_sha256` from `fixtures/generated/generation_report.json`.

**Input `CanonicalDocument`** (abbreviated to the fields that matter for
this example): one `CanonicalUnit` (`unit_index=0`, `page`), one
`CanonicalHeading` (`"Recovery Objectives"`, level 2), one
`CanonicalParagraph` (`"Application APP-224510 supports the Payment
Settlement business service."`), one `IdentifierAnnotation` targeting that
paragraph at `start_char=12, end_char=22` (the `"APP-224510"` span).

**`DocumentRevisionContext`:**

```json
{
  "logical_document_id": "PARITY_001",
  "document_revision_id": "4ebeff21f9e16b7a598cc8d4d0799fa49b2c1b3bc537b24de926539aa6755761",
  "source_document_sha256": "cd3c7994aacc452a685f0a0c136469fc422c13af4e948c01eff65e45cc38062c",
  "version_label": "v1",
  "revision_number": 1
}
```

**`chunk_document(document, ChunkingConfig(), revision_context=rc)` produced
exactly one `CanonicalChunk`:**

```json
{
  "chunk_id": "95983fe37edda3fd039777ea06075ea3123dcb300f9471c80ebf670351b78272",
  "doc_id": "PARITY_001",
  "logical_document_id": "PARITY_001",
  "document_revision_id": "4ebeff21f9e16b7a598cc8d4d0799fa49b2c1b3bc537b24de926539aa6755761",
  "source_document_sha256": "cd3c7994aacc452a685f0a0c136469fc422c13af4e948c01eff65e45cc38062c",
  "version_label": "v1",
  "revision_number": 1,
  "chunk_index": 0,
  "chunk_type": "text",
  "unit_indices": [0],
  "heading_path": ["Recovery Objectives"],
  "heading_source_element_ids": ["h1"],
  "heading_source_refs": [
    {"element_id": "h1", "unit_index": 0, "order_index": 0, "bbox": null,
     "element_type": "heading", "fragment_index": null, "start_char": null, "end_char": null}
  ],
  "source_element_ids": ["p1"],
  "annotation_ids": ["a1"],
  "source_refs": [
    {"element_id": "p1", "unit_index": 0, "order_index": 1, "bbox": null,
     "element_type": "paragraph", "fragment_index": null, "start_char": null, "end_char": null}
  ],
  "asset_refs": [],
  "source_text": "Application APP-224510 supports the Payment Settlement business service.",
  "model_derived_text": null,
  "retrieval_text": "Recovery Objectives\n\nApplication APP-224510 supports the Payment Settlement business service.",
  "contains_model_derived": false,
  "content_sha256": "cb6cca2b87a7a4c4b244070bb3a699cb66f8b0fd5e2f4b9b0dbb4df7ad2043d7",
  "embedding_input_sha256": "237d6aa9224cd40363762bf92c93fd932f1fdddc9e9958530ef293140e3b7e87",
  "chunker_version": "1.2.0",
  "chunking_config_hash": "217ae232d0d5b859613f45e73df3cf690e30c9894bab782892881e398cf2bf07"
}
```

**How the identities relate:** `chunk_id` is unique to this occurrence
within revision `4ebeff21...`; `content_sha256` integrity-covers the full
payload including `source_refs`/`heading_source_refs` (both `fragment_index`/
`start_char`/`end_char` are `null` here because nothing was split);
`embedding_input_sha256` is `sha256(retrieval_text)` exactly — if a second
revision of this same logical document produced identical `retrieval_text`,
it would share this same `embedding_input_sha256` while still getting its
own `chunk_id` (because `document_revision_id` differs), per decision
D-020. `IdentifierAnnotation a1` is tracked in `annotation_ids` for audit
but — per decision D-006 — never duplicated into `source_text` itself.

Note: `chunker_version` and `chunk_id` are the only two values in this
example that changed between Stage 4.2 and Stage 4.2a, even though this
particular document is never split — `CHUNKER_VERSION` is folded into
`chunk_id`'s discriminator for *every* chunk, split or not, so bumping it
(`1.1.0 -> 1.2.0`, reflecting the Stage 4.2a splitting/rendering rule
change) changes every `chunk_id` in the corpus on the next run, by design.
`content_sha256`, `embedding_input_sha256`, and `chunking_config_hash` are
unaffected here because this example has no oversized element to split.

---

## Stage 5A — Docling `DOCLING_STANDARD_LOCAL` adapter (path A) `[IMPLEMENTED]`

**Files:** `src/ingestion_bench/adapters/base.py`,
`src/ingestion_bench/adapters/docling_standard/{__init__.py,config.py,diagnostics.py,mapper.py,adapter.py}`,
`scripts/run_docling_standard.py`;
`tests/test_docling_standard_{mapper,adapter,integration}.py`

This section describes Stage 5A as hardened by the Stage 5A.1 patch (see
the dedicated Stage 5A.1 section immediately below for exactly what
changed and why) — it is not a Stage-5A-only snapshot.

Dependencies added: `docling==2.114.0` and `onnxruntime` (RapidOCR's
inference backend — not pulled in automatically by `docling[standard]`,
discovered during the compatibility spike and pinned explicitly), both in
`requirements.txt`/`constraints.txt`.

```
Source fixture (e.g. fixtures/generated/parity/PARITY_001.pdf)
        |
        v
Docling standard-local conversion                          [IMPLEMENTED]
   config.py::build_converter() -- one DocumentConverter, PDF/DOCX/PPTX
   only, do_ocr=True (RapidOcrOptions explicit), do_table_structure=True
   (ACCURATE), generate_picture_images=True, every VLM/remote/chart/
   picture-description option explicitly False, AcceleratorDevice.CPU
        |
        v
DoclingDocument (docling-core)                              [parser-
                                                              specific,
                                                              never leaves
                                                              this package]
        |
        v
Docling-to-CEDM mapping                                     [IMPLEMENTED]
   mapper.py::DoclingToCanonicalMapper.map_document() -- single pass over
   iterate_items() in Docling's own reading order; see the mapping table
   below
        |
        v
CanonicalDocument                                            [reuses the
                                                               Stage 2
                                                               model,
                                                               unmodified]
        |
        v
CanonicalChunk[]  (via the existing chunk_document())         [reuses the
                                                                Stage 4
                                                                chunker,
                                                                unmodified]
        |
        v
Evaluation against reference_manifest.json                   [PLANNED --
                                                                Stage 8,
                                                                no
                                                                evaluator
                                                                exists]
```

### Adapter interface (`adapters/base.py`)

`AdapterConversionResult` — the parser-neutral result every adapter (this
one, and any future one) returns: `canonical_document`,
`extraction_run` (reuses `ingestion_bench.canonical.ExtractionRun` for
run identity/timing/warnings/`canonical_document_hash` — `None` exactly
when `conversion_status == "failed"`), `conversion_status` (`"success" |
"partial" | "failed"`), `diagnostics: list[AdapterDiagnostic]`,
`warnings`, `errors`, plus fields that must survive even a failed
conversion (`elapsed_ms`, `docling_version`, `docling_core_version`,
`input_format`, `source_relative_path`, `source_sha256`,
`raw_docling_debug_artifact`). `DocumentParserAdapter` is the `Protocol`
every adapter implements: `convert(source_path, *, source_root) ->
AdapterConversionResult`.

### Docling → Canonical mapping table

| Docling | Canonical | Notes |
|---|---|---|
| `DoclingDocument.pages[page_no]` | `CanonicalUnit` | PDF/PPTX only. `page_no` confirmed 1-based empirically; `unit_index = page_no - 1`. **DOCX: Docling exposes no page geometry at all** — see the DOCX fallback note below. |
| `TitleItem` / `SectionHeaderItem` | `CanonicalHeading` | `level` preserved when Docling provides one (defaults to 1 otherwise — see the "known limitations" list, PDF did not distinguish heading levels for the parity fixture). |
| `TextItem` (label `TEXT`/`PARAGRAPH`) | `CanonicalParagraph` | Text preserved exactly — no bullets/Markdown/OCR labels added (those are the frozen renderer's job, per chunking rule). |
| `TextItem` (label `FORMULA`/`CODE`) | `CanonicalParagraph` | Reduced-fidelity mapping (no dedicated canonical type); `reduced_fidelity_mapping` diagnostic recorded. |
| `TextItem` (label `PAGE_HEADER`/`PAGE_FOOTER`/`FOOTNOTE`) | *(skipped)* | Treated as furniture; `skipped_furniture` diagnostic. |
| `ListItem` | `CanonicalListItem` | `indent_level`/`list_id`/`parent_block_id` computed by walking the real Docling group-ancestry chain (`_walk_list_ancestry`) — never guessed. |
| `TextItem` referenced by `PictureItem.captions` | `CanonicalCaption` | Linked to its picture, never duplicated as a body paragraph. Confirmed working for PDF; **not** populated by Docling for DOCX/PPTX in this version (caption text becomes a plain paragraph instead — see limitations). |
| `TableItem.data.table_cells` | `CanonicalTable`/`CanonicalTableCell` | Read from the structural grid directly (`start_row_offset_idx`/`start_col_offset_idx`/`row_span`/`col_span`/`column_header`/`row_header`) — never from exported Markdown/pandas. Out-of-bounds cells are dropped with a `malformed_table_cell` diagnostic, never silently included. |
| `PictureItem` (with retrievable image bytes) | `CanonicalPicture` | Image obtained via the public `PictureItem.get_image(doc)`; saved as PNG; `content_sha256` computed from the saved bytes. No image bytes available → the picture (and any caption/OCR text pointed at it) is skipped with a `missing_picture_bytes` diagnostic, never invented. |
| `TextItem` whose parent is a `PictureItem` (and not that picture's caption) | `OcrAnnotation` (`derivation="extracted"`) + a matching `ProvenanceEntry` | The *only* annotation type Stage 5A ever produces. Since Stage 5A.1, every such `OcrAnnotation` also gets a `ProvenanceEntry` (`element_id` = the annotation's own `annotation_id`) whenever Docling supplies evidence — see "OCR-origin detection" below. |
| Any other `DocItemLabel` (`DOCUMENT_INDEX`, `CHECKBOX_*`, `FORM`, `KEY_VALUE_REGION`, `GRADING_SCALE`, `HANDWRITTEN_TEXT`, `EMPTY_VALUE`, `REFERENCE`, `FIELD_*`, `MARKER`) | *(skipped)* | `unsupported_label` diagnostic. |

No `ImageDescriptionAnnotation`, `VisualFactAnnotation`,
`SemanticClaimAnnotation`, or model-derived `DiagramNode`/`EdgeAnnotation`
is ever produced — enforced by
`tests/test_docling_standard_mapper.py::test_no_model_derived_annotations_are_ever_produced`
and the integration-level
`test_chart_fixture_never_produces_a_visual_fact_annotation`.

### Key design points (see `docs/POC_DECISION_LOG.md` D-032–D-036 for full rationale)

- **Bounding-box coordinate conversion** — Docling's PDF/PPTX bboxes use a
  bottom-left origin (`CoordOrigin.BOTTOMLEFT`); `mapper.py::_convert_bbox`
  normalizes every one into the canonical model's top-left origin
  (`y0 = page_height - top`, `y1 = page_height - bottom`) before
  construction — never copied as-is.
- **DOCX page-geometry fallback** — Docling exposes none; the adapter
  reads the real declared section size from the source file itself via
  `python-docx` (`adapter.py::_docx_page_fallback`), records a
  `docx_pagination_unavailable` diagnostic (`affects_fidelity=True`, see
  D-037) every time, and never fabricates a Letter/A4 default. Every DOCX
  conversion's `conversion_status` is therefore `"partial"`, never
  `"success"` (Stage 5A.1).
- **OCR-origin detection** — no per-item OCR confidence/source field
  exists in this Docling version; the mapper uses the one real structural
  signal available (a `TextItem` nested under a `PictureItem`) rather than
  inferring OCR-origin from which fixture is being processed. Since Stage
  5A.1, each resulting `OcrAnnotation` also gets a `ProvenanceEntry`
  (bbox via `.prov` when available, `self_ref`, an `ocr_sequence`
  disambiguating multiple OCR lines under one picture) — see D-038. OCR
  text *ordering* within one picture remains unresolved: `ocr_sequence`
  reflects `doc.texts` scan order, not verified visual reading order.
- **Reading order is assigned in exactly one pass** — every element type
  (headings, paragraphs, list items, tables, pictures, captions) gets its
  `order_index` from a single walk over `iterate_items()`, never from a
  separate pre/post pass, so provenance ordering can never be scrambled
  relative to Docling's own traversal order.
- **`doc_id` vs. artifact file paths** — `PARITY_001.pdf`/`.docx`/`.pptx`
  intentionally share `doc_id="PARITY_001"` (matching the manifest's own
  shared identity for that suite); on-disk artifact paths use a separate,
  format-qualified `artifact_key` so the three conversions' output files
  never collide.

### Failure/partial handling

`ConversionStatus` is `"success"` (fully valid document, no
fidelity-affecting diagnostic), `"partial"` (valid document, but Docling
reported `PARTIAL_SUCCESS` or at least one diagnostic has
`affects_fidelity=True` — **never derived from diagnostic severity alone**,
see D-037), or `"failed"` (no `CanonicalDocument` at all — Docling itself
raised, Docling reported `FAILURE`, no usable unit geometry could be
established, or the assembled document failed a frozen canonical
invariant). A failed conversion never produces a fake or empty
`CanonicalDocument` — `mapper.py::DoclingToCanonicalMapper.build()`
catches the `pydantic.ValidationError` from final construction, records a
`canonical_document_construction_failed` diagnostic, and returns `None`;
`adapter.py` propagates that as `conversion_status="failed"`.
`AdapterConversionResult` itself enforces the success/partial/failed ↔
`canonical_document`/`extraction_run` presence invariant as a Pydantic
`model_validator` (Stage 5A.1) — it is not just an adapter-code
convention, a mismatched construction raises `ValidationError` directly.

`AdapterDiagnostic.severity` (operational alarm level) and
`AdapterDiagnostic.affects_fidelity` (whether source content/structure/
provenance was actually lost or degraded) are deliberately independent
axes — `DiagnosticCollector.has_fidelity_impact()` is what
`conversion_status` derivation reads, never `has_errors()`/severity. See
D-037 for the full rationale (the DOCX pagination diagnostic is the
motivating example: `severity="info"`, but always `affects_fidelity=True`).

### Runner (`scripts/run_docling_standard.py`)

Discovers every `.pdf`/`.docx`/`.pptx` under `fixtures/generated/{parity,stress}/`
by filesystem glob — **never** reads `reference_manifest.json`. For each:
converts via the adapter, writes `canonical_document.json`, builds an
explicit `DocumentRevisionContext` (logical_document_id = the file's own
stem — this is the runner's job, not the adapter's, per the Stage 5A
scope boundary), chunks via the unmodified `chunk_document()`, writes
`canonical_chunks.jsonl`, and writes a per-fixture `conversion_report.json`
(now including the full serialized `diagnostics` array and
category/severity/`affects_fidelity` summary counts, Stage 5A.1) plus one
in-memory `results` object from which `main()` writes **both**
`reports/stage5a_docling_standard_results.json` **and**
`reports/stage5a_docling_standard_baseline.md`
(`render_baseline_markdown(results)`) — the same execution, never two
separate runs, so the two files can never silently disagree (Stage 5A.1
item 7). `_write_raw_debug_snapshot` returns a portable
`"stage5a/docling_raw/<artifact_key>.json"` reference, never the absolute
filesystem path it actually writes to — no absolute Windows path is ever
persisted into a report.

### Real baseline results

All 9 generated fixtures produce a valid `CanonicalDocument` — 7
`conversion_status="success"`, 2 `conversion_status="partial"` (the two
DOCX fixtures, per D-037's `docx_pagination_unavailable` diagnostic);
determinism verified for all three parity formats (identical
`stable_canonical_hash()` and chunk `content_sha256`/`chunk_id` across two
runs). Full counts, timings, and every discovered Docling limitation:
`reports/stage5a_docling_standard_baseline.md`. This is real, measured
output — not aspirational.

---

## Stage 5A.1 — Evidence/provenance hardening patch `[IMPLEMENTED]`

Same files as Stage 5A, patched in place — no new package, no new
adapter, no Stage 5B/6 functionality. Adds `tests/test_adapters_base.py`
and `tests/test_run_docling_standard_report.py`.

1. **`affects_fidelity` axis** — `adapters/base.py::AdapterDiagnostic`
   gained `affects_fidelity: bool = False`, independent of `severity`.
   `conversion_status` derivation moved from
   `has_errors() or bool(adapter_warnings)` to
   `mapper.diagnostics.has_fidelity_impact()` (plus Docling's own
   `PARTIAL_SUCCESS`) — see D-037.
2. **DOCX category rename + partial status** — `mapper.py`'s
   `docling_page_geometry_unavailable` diagnostic (recorded once per DOCX
   conversion in `build_units`) is now `docx_pagination_unavailable`,
   `affects_fidelity=True`. Every DOCX conversion is therefore `partial`.
   No fake second page/unit is ever created — still exactly one
   `CanonicalUnit` per DOCX document, per the frozen D-034 fallback.
3. **Fidelity-accurate diagnostics throughout the mapper** — roughly a
   dozen other call sites in `mapper.py` (missing geometry, missing
   provenance, malformed bbox/table cell, missing picture bytes, reduced-
   fidelity mapping, ambiguous caption relationship, unsupported label)
   now pass `affects_fidelity=True`; `skipped_furniture` deliberately
   stays `affects_fidelity=False` (furniture exclusion is intentional, not
   a loss).
4. **OCR annotation provenance** — `mapper.py::map_picture_ocr_child` now
   also appends a `ProvenanceEntry` per `OcrAnnotation` (see D-038);
   `map_document` tracks an `ocr_sequence_by_picture` counter so multiple
   OCR lines under one picture get a distinguishing `ocr_sequence` in
   `source_locator`.
5. **`AdapterConversionResult` validation hardening** — `elapsed_ms`
   constrained `>= 0`; `source_sha256` validated via the shared
   `validate_sha256_hex` helper (`canonical/model.py`, imported, not
   duplicated); `source_relative_path` validated by a locally-reimplemented
   portable-path check (`adapters/base.py::_validate_portable_relative_path`
   — reimplemented rather than reaching into `canonical.model`'s private
   helper, since `canonical` is frozen and this package must not depend on
   its non-public surface); a `model_validator` enforces
   `conversion_status` ↔ `canonical_document`/`extraction_run` presence.
6. **Portable, complete reports** — every `conversion_report.json` and the
   aggregate JSON now include the full `diagnostics` array (not just
   counts) and a `diagnostics_by_affects_fidelity` summary;
   `_write_raw_debug_snapshot` returns a portable `"stage5a/docling_raw/..."`
   reference instead of an absolute path.
7. **Single-execution dual report generation** — `run_docling_standard.py::main()`
   builds one `results` dict and passes it to both the JSON writer and
   `render_baseline_markdown(results)`.
8. **Tests** — `tests/test_adapters_base.py` (15, validation hardening);
   `tests/test_run_docling_standard_report.py` (2, report consistency);
   4 new tests in `test_docling_standard_integration.py` (DOCX partial
   status with exactly one unit; parity-picture and chart OCR-annotation
   provenance; scanned-PDF whole-page OCR stays a paragraph); 1 updated
   test in `test_docling_standard_mapper.py` for the category rename.

343 tests pass (up from 322 at Stage 5A) — see `reports/stage5a_pytest_output.txt`.

---

## Stage 5A.2 — Evidence-contract correction `[IMPLEMENTED]`

Same files as Stage 5A/5A.1, patched in place, plus one new module
(`environment.py`) — no new adapter, no Stage 6+ functionality.

1. **`conversion_status="success"` cannot coexist with a fidelity-affecting
   diagnostic.** `adapters/base.py::AdapterConversionResult` gained a
   second `model_validator`: if `conversion_status == "success"` and any
   `AdapterDiagnostic` has `affects_fidelity=True`, construction raises
   `ValidationError`. `"partial"` is unaffected — it remains valid with
   zero fidelity-affecting diagnostics (a parser may independently report
   `PARTIAL_SUCCESS`) or with one or more.
2. **Component-level determinism evidence.**
   `scripts/run_docling_standard.py::run_determinism_check` no longer
   returns one collapsed `bool` — it now returns a structured dict with
   five independent comparisons (`canonical_json_equal`,
   `canonical_hash_equal`, `chunk_json_equal`, `chunk_ids_equal`,
   `chunk_content_hashes_equal`) plus a summary `all_equal` — see D-039.
   A new `_chunk_document(document, doc_id)` helper is shared between
   `process_fixture` and `run_determinism_check` so both build chunks
   identically.
3. **Restored environment/model-footprint evidence.** New module
   `adapters/docling_standard/environment.py::collect_environment_evidence()`
   — read-only, never imports Docling document types (only
   `importlib.metadata`/`platform`/`torch.cuda.is_available()` and
   `config.py`'s existing version helpers) — collects Python version,
   OS/platform, docling/docling-core/torch/torchvision/onnxruntime/
   rapidocr versions, CUDA availability, effective accelerator, whether an
   external Hugging Face cache is configured, a **redacted** cache
   location (drive letter/mount point only, e.g. `"D: (redirected, path
   redacted)"` — never the full path), the downloaded Docling model
   families (filtered to repo ids containing `"docling"`, so an unrelated
   cached model like the separate GraphRAG POC's
   `sentence-transformers/all-MiniLM-L6-v2` is never misreported as a
   Docling download), and an approximate storage footprint in MB (summed
   from each repo's `blobs/` directory only — summing `snapshots/` too
   would double-count the same physical bytes on this filesystem, a real
   bug caught and fixed during implementation).
4. **Report rendering updated.** `render_baseline_markdown` section 1
   (Environment) now reads from `results["environment_evidence"]` instead
   of hand-typed prose; section 4 (Determinism results) now renders one
   column per comparison instead of one "Identical across two runs"
   column.
5. **Tests** — 4 new tests in `test_adapters_base.py` (success/fidelity
   consistency); 2 new tests in `test_docling_standard_adapter.py`
   (environment evidence has no absolute path, has the expected shape); 1
   new test plus extended synthetic fixture data in
   `test_run_docling_standard_report.py` (structured determinism
   rendering, including a deliberate partial-mismatch case that must
   render as a visible failure).

350 tests pass (up from 343 at Stage 5A.1) — see
`reports/stage5a_pytest_output.txt`. 3 warnings, all pre-existing
deprecation warnings from Docling's own dependencies, not this project's
code.

---

## Corrected roadmap (Stage 5A.2)

Vision enrichment is **not** the next stage. An earlier framing of this
project's plan (visible in older commit history and in decision D-009)
described the next step as "Stage 6 — `VisionEnricher` framework." That
sequencing is superseded — see D-040 for the rationale (the ingestion
evaluator's gold fact-to-chunk evidence-alignment catalog must exist
before retrieval projections are worth comparing, and vision enrichment
is one more *ingestion* lane, not a retrieval concern):

```
Stage 6A  Deterministic ingestion-fidelity evaluator          <- NEXT
Stage 6B  Retrieval benchmark contract + gold evidence set
Stage 7A  Regular vector RAG projection + retrieval baseline
Stage 7B  Graph-enriched RAG projection
Stage 7C  Wiki page/link projection
Stage 8A  Selective OpenAI vision enrichment (path B)
Stage 8B  OpenAI vendor-native ingestion (path C)
Stage 9   Cross-lane quality, cost, latency, and ROI comparison
```

See `docs/POC_STATUS_AND_EVIDENCE.md` "Benchmark dimensions (corrected
roadmap)" for the full two-dimension framing (ingestion approach ×
retrieval projection) this sequence is derived from.

## Future walkthrough (Stage 6A+) — `[PLANNED, none of this exists yet]`

```
CanonicalPicture (already extracted, path A)
        |
        v
VisionEnricher.enrich(picture, caption, surrounding_text)     [PLANNED --
   src/ingestion_bench/vision/ -- does not exist; protocol shape only      Stage 8A]
   documented in fixtures/BENCHMARK_CONTRACT.md section 2
        |
        v
list[Annotation]  (model_derived: ImageDescriptionAnnotation,           [PLANNED]
   VisualFactAnnotation, DiagramNode/EdgeAnnotation, ...)
        |
        v
Merged back into the SAME CanonicalDocument the path-A adapter produced  [PLANNED]
        |
        v
Evaluation against reference_manifest.json, comparing path A vs. path B  [PLANNED --
                                                                            Stage 6A
                                                                            evaluator
                                                                            reused]
```

Every step above is planned, not implemented. No `vision/` package
exists; no `OpenAIVisionEnricher`, no OpenAI vendor-native adapter (path
C), no evaluator. Treat any claim to the contrary — in this document or
elsewhere — as inaccurate.
