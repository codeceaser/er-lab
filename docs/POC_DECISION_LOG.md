# POC Decision Log — Enterprise Document-Ingestion Benchmark

Durable architectural decision log. Entries are sequential (`D-001`, `D-002`, ...)
and are never renumbered. A decision that is later reversed is marked
**Superseded** and links to its replacement — it is never silently rewritten.

Commit dates in this log all read `2026-07-21` per `git log --format=%ad`;
this repository's commits were made across a working session in an
environment whose local clock did not advance per calendar day of actual
work, so **commit dates should not be read as literal elapsed time between
stages** — commit hashes are the reliable ordering signal.

---

## D-001 — Use a parser-neutral Canonical Enterprise Document Model

**Status:** Accepted
**Stage:** Stage 2
**Date/commit:** `e1eff3d` (Stage 1-3 initial commit)

### Problem
Downstream consumers (chunking, evaluation, future embedding/retrieval)
need one document representation that works identically regardless of
which parser backend produced it, and that can be compared against
`reference_manifest.json` ground truth without understanding any parser's
native types.

### Alternatives considered
(a) Use Docling's own document type directly everywhere. (b) Build a
per-consumer thin translation layer instead of one shared canonical model.
(c) Build one parser-neutral canonical model shared by every adapter and
consumer.

### Decision
(c) — `CanonicalDocument` in `src/ingestion_bench/canonical/model.py`.

### Rationale
Every downstream stage must behave identically regardless of path (A/B/C/D),
and must be evaluable against one fixed ground truth without special-casing
per parser.

### Trade-offs and consequences
Every adapter must translate its native output into canonical shapes (extra
work, not yet done for any adapter). The canonical model must anticipate
the union of what different parsers can express, which is necessarily
speculative until real adapters exist.

### Deferred questions or reconsideration trigger
If the (not yet built) Docling adapter reveals structural output the
canonical model cannot represent losslessly, the model may need extension —
any such change should be logged as a new decision, not a silent edit.

### Implementation and evidence
`src/ingestion_bench/canonical/model.py`; `src/ingestion_bench/canonical/__init__.py`;
`tests/test_canonical_schema.py` (87 tests); `fixtures/BENCHMARK_CONTRACT.md`.

---

## D-002 — Treat Docling as an adapter rather than a downstream domain dependency

**Status:** Accepted
**Stage:** Stage 2 (isolation rule); Stage 5 (adapter itself — not started)
**Date/commit:** `e1eff3d`; isolation re-verified at every later chunking commit

### Problem
Should business logic (chunking, evaluation) ever import or assume Docling
types directly?

### Alternatives considered
(a) Let chunking/evaluation import Docling types directly. (b) Wrap Docling
behind an adapter boundary that only ever produces `CanonicalDocument`.

### Decision
(b). Docling (and OpenAI, and any DOCX/PDF/PPTX library) must never be
imported from `canonical/` or `chunking/`.

### Rationale
Keeps paths A/B/C/D swappable and keeps the chunking layer fully testable
against hand-built `CanonicalDocument` objects without Docling installed or
without parsing any real file — exactly how `tests/test_chunking.py` is
written today.

### Trade-offs and consequences
The (future) adapter layer must fully translate Docling's richer/different
model into canonical shapes, potentially needing new `source_locator`/
`source_element_ref` free-form detail, or canonical-model extension, to
avoid losing Docling-specific information.

### Deferred questions or reconsideration trigger
Revisit if/when the Docling adapter (Stage 5, not started) reveals fields
that cannot be represented in the canonical model.

### Implementation and evidence
`fixtures/BENCHMARK_CONTRACT.md` section 1 ("`docling_adapter.py` (path A)
has NO dependency on any `VisionEnricher`"); `tests/test_chunking.py::test_chunking_source_has_no_forbidden_import_statements`.
No `adapters/` package exists yet, so this boundary is verified only at the
import-hygiene level, not by a real adapter — **Needs confirmation** once
Stage 5 lands.

---

## D-003 — Keep reference_manifest.json outside CanonicalDocument

**Status:** Accepted
**Stage:** Stage 2 / Stage 2.1
**Date/commit:** `e1eff3d`

### Problem
An earlier draft of `CanonicalDocument` carried `manifest_version`/
`manifest_sha256` fields directly, coupling extracted content to benchmark
metadata.

### Alternatives considered
(a) Keep `manifest_version`/`manifest_sha256` on `CanonicalDocument`. (b)
Remove them and introduce a separate `BenchmarkBinding` model outside
`canonical/`.

### Decision
(b). `BenchmarkBinding` (`src/ingestion_bench/benchmark_binding.py`) carries
`doc_id`, `canonical_document_hash`, `run_id`, `manifest_version`,
`manifest_sha256`.

### Rationale
`stable_canonical_hash()` must never depend on benchmark metadata, and
`CanonicalDocument` must stay meaningful for real production documents that
have no manifest at all.

### Trade-offs and consequences
An evaluator now needs three things at once (`CanonicalDocument`,
`reference_manifest.json`, `BenchmarkBinding`) instead of one
self-describing document — more plumbing, but a cleaner boundary.

### Deferred questions or reconsideration trigger
None identified; treated as settled — `fixtures/BENCHMARK_CONTRACT.md` is
frozen with this amendment already folded in.

### Implementation and evidence
`src/ingestion_bench/benchmark_binding.py`; `canonical/model.py::CanonicalDocument`
docstring ("Deliberately NOT here: manifest_version / manifest_sha256");
`tests/test_canonical_hashing.py::test_canonical_hash_independent_of_benchmark_binding`;
`fixtures/BENCHMARK_CONTRACT.md` header note.

---

## D-004 — Use human-defined benchmark ground truth rather than one LLM grading another LLM

**Status:** Accepted
**Stage:** Stage 1
**Date/commit:** Needs confirmation (predates repository git history — this
decision was made during Stage 1 contract drafting, which the initial
commit `e1eff3d` bundles without a separate Stage-1-only commit)

### Problem
How can extraction quality be scored without a circular or unreliable
LLM-judges-LLM evaluation loop?

### Alternatives considered
(a) Use an LLM to grade another LLM's/parser's extraction quality. (b) Use
a frozen, human-authored ground-truth manifest scored by deterministic code.

### Decision
(b). `fixtures/reference_manifest.json` plus a deterministic evaluator
(planned, **not yet implemented**).

### Rationale
LLM-grades-LLM introduces its own unreliability and cost and cannot serve
as an objective baseline for comparing extraction paths.

### Trade-offs and consequences
Manifest authoring is manual and must be exhaustive/precise. Scoring is
necessarily narrower than open-ended LLM judgment — free prose (e.g.
`ImageDescriptionAnnotation`, manifest "summary" fields) is explicitly
marked human-review-only and is never scored.

### Deferred questions or reconsideration trigger
None — reinforced repeatedly throughout the manifest (`visual_distractor_facts`,
`unsupported_claims` sections exist specifically to test for false
positives under this deterministic scoring model).

### Implementation and evidence
`fixtures/reference_manifest.json` (`visual_distractor_facts`,
`chart_visual_stress.unsupported_claims`); `fixtures/BENCHMARK_CONTRACT.md`
section 9 (metrics). The evaluator itself does not exist — **Needs
confirmation** on the exact scoring algorithm once Stage 8 (evaluator) is
implemented.

---

## D-005 — Generate deterministic DOCX/PDF/PPTX benchmark fixtures from one frozen manifest

**Status:** Accepted
**Stage:** Stage 3 / Stage 3.1
**Date/commit:** `e1eff3d` (Stage 3), `ad557c8` (Stage 3.1 fixes)

### Problem
Extraction comparisons across parser paths must not be confounded by
fixture nondeterminism (different bytes on different machines/runs).

### Alternatives considered
(a) Hand-author fixture files directly, without a generator. (b) Generate
programmatically from the manifest but accept run-to-run nondeterminism
(timestamps, IDs). (c) Generate programmatically with explicit determinism
engineering.

### Decision
(c). `fixtures/generate_fixtures.py` generates all parity and stress
fixtures from `reference_manifest.json`.

### Rationale
Fixtures must be exactly regenerable by any engineer or CI run from the
manifest alone; hand-authored files can't be regenerated when the manifest
changes, and naive generation embeds nondeterministic metadata that would
make byte-level comparison and hashing meaningless.

### Trade-offs and consequences
Significant generator engineering (custom `reportlab` canvasmaker, ZIP
entry timestamp rewriting, `lxml`-level OOXML patching for connector
arrowheads). `fixtures/generated/` is gitignored and must be regenerated
locally — an extra setup step for a new engineer (see `docs/README.md`).

### Deferred questions or reconsideration trigger
None open — verified by regeneration tests.

### Implementation and evidence
`fixtures/generate_fixtures.py`; `tests/test_fixture_generation.py` (38
tests), specifically `test_regeneration_is_byte_deterministic`,
`test_regeneration_produces_same_manifest_sha256`; `reports/stage3_pytest_output.txt`,
`reports/stage3_1_pytest_output.txt`.

---

## D-006 — Preserve source-derived and model-derived information separately

**Status:** Accepted
**Stage:** Stage 2 (schema); Stage 4 (chunking routing)
**Date/commit:** `e1eff3d` (schema); `8a1db98` (chunking routing)

### Problem
Mixing OCR/native text with a vision model's own reading or description
into one field would make it impossible to trust or independently evaluate
either.

### Alternatives considered
(a) One merged "text" field per element, regardless of origin. (b) An
explicit `derivation` field on every annotation, plus a hard separation
between `source_text` and `model_derived_text` at the chunk level.

### Decision
(b).

### Rationale
An OCR engine's mechanical output and a multimodal model's generative
"reading" of the same image carry different, non-interchangeable trust
levels and error profiles; conflating them would make evaluation and
downstream trust decisions impossible.

### Trade-offs and consequences
More fields and routing logic throughout rendering, chunking, and hashing;
a doubled annotation-type surface (`OcrAnnotation` vs. `VisibleTextAnnotation`)
that exists purely to keep this distinction unambiguous.

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`canonical/annotations.py` (`OcrAnnotation` fixed `"extracted"`,
`VisibleTextAnnotation` fixed `"model_derived"`);
`chunking/chunker.py::_render_annotations_for_element`;
`tests/test_chunking.py::test_ocr_annotation_is_source_visible_text_annotation_is_model_derived`,
`test_source_text_and_model_derived_text_remain_separate`.

---

## D-007 — Preserve the original image as authoritative when semantic image descriptions are model-derived

**Status:** Accepted
**Stage:** Stage 2 / Stage 4.1
**Date/commit:** `e1eff3d` (`CanonicalPicture`); `1692325` (asset-only preservation)

### Problem
Once a vision model describes or labels a picture, what is the record of
truth for that picture — the model's description, or the picture itself?

### Alternatives considered
(a) Discard or replace raw picture bytes with a model-generated description.
(b) Always keep the original image as the authoritative artifact; treat any
description as a separate, clearly-labeled, non-authoritative annotation.

### Decision
(b). `CanonicalPicture` always stores `content_sha256` + `artifact_ref` to
the original image bytes; `ImageDescriptionAnnotation`/`VisualFactAnnotation`
are separate, `model_derived`-only annotations.

### Rationale
A generative description can hallucinate; the source image cannot. Losing
the original image would make re-verification, or re-enrichment with a
better model later, impossible.

### Trade-offs and consequences
Requires storage/retention of original image bytes and their portable
`artifact_ref`; `ChunkAssetRef` (D-017) exists specifically so a picture
with zero textual annotation is still retained, never dropped.

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`canonical/model.py::CanonicalPicture`; `canonical/annotations.py::ImageDescriptionAnnotation`
docstring ("Human-review only — never deterministically scored");
`chunking/model.py::ChunkAssetRef`;
`tests/test_chunking.py::test_picture_with_no_textual_annotations_still_emits_asset_only_chunk`.

---

## D-008 — Keep ordinary native-table extraction independent of vision models

**Status:** Accepted
**Stage:** Stage 1 (contract); Stage 2 (schema); Stage 4 (chunking)
**Date/commit:** `e1eff3d`

### Problem
Should a table ever be routed through a `VisionEnricher` (read as an
image) instead of parsed structurally?

### Alternatives considered
(a) Allow vision-model table reading as a fallback or enhancement. (b)
Require tables to always come from native structural parsing (DOCX/PPTX
native tables, PDF TableFormer) — never vision enrichment.

### Decision
(b), stated as a hard rule.

### Rationale
Native structural extraction is exact (row/col/span from the source
format's own table model); vision-based table reading is comparatively
unreliable and would blur the structural-vs-generative trust boundary this
project maintains everywhere else.

### Trade-offs and consequences
A table trapped inside a flat image (not a native table) cannot be
extracted under this rule at all — an accepted, explicit limitation rather
than a workaround.

### Deferred questions or reconsideration trigger
None — treated as a hard rule, not a temporary simplification.

### Implementation and evidence
`fixtures/reference_manifest.json` (parity table + PDF complex-layout table
notes: "Native table... never routed through vision enrichment");
`fixtures/BENCHMARK_CONTRACT.md` section 2 ("Table extraction is never
routed through vision enrichment, in any path").

---

## D-009 — Make local Granite Vision optional rather than mandatory for the initial POC

**Status:** Deferred (path D itself); the decision to defer it is Accepted
**Stage:** Pre-Stage-1 plan revision
**Date/commit:** Needs confirmation (plan revision predates recorded git history)

### Problem
An earlier plan revision made local Granite Vision (~6GB model, GPU/
storage/lifecycle governance) a required part of the initial POC.

### Alternatives considered
(a) Require Granite Vision on the critical path. (b) Make it an optional,
deferred fourth lane (path D), reachable through the same `VisionEnricher`
protocol as path B, revisited only if a local-only-deployment requirement
arises.

### Decision
(b).

### Rationale
Paths B/C need no local model download at all (they call OpenAI);
requiring Granite Vision up front adds governance work (`ModelArtifact`
records, model staging, offline-mode enforcement) not needed to reach a
first measurable comparison.

### Trade-offs and consequences
No local-only-deployment evaluation lane exists yet. If a hard local-only
requirement appears, the deferred governance/storage/lifecycle design must
be picked back up.

### Deferred questions or reconsideration trigger
A concrete local-only-deployment requirement, or evidence that OpenAI-based
paths are insufficient for evaluation purposes.

### Implementation and evidence
`fixtures/BENCHMARK_CONTRACT.md` section 1 ("(Optional, deferred) D — local
Granite Vision enrichment... Not required for the initial POC"). No
`vision/granite_enricher.py` or `vision/` package exists in the repository.

---

## D-010 — Use deterministic canonical IDs and hashes rather than UUID4 or Python hash()

**Status:** Accepted
**Stage:** Stage 2 / Stage 2.1
**Date/commit:** `e1eff3d`

### Problem
IDs and hashes must be reproducible across runs and machines for
comparison, diffing, and reprocessing to be meaningful.

### Alternatives considered
(a) `uuid4()` per element. (b) Python's built-in `hash()` (process-
randomized for `str` by default). (c) A shared deterministic helper over
stable identity components plus SHA-256.

### Decision
(c). `stable_element_id()` (`canonical/hashing.py`) and
`canonical_sha256()`/`text_sha256()` (`chunking/model.py`).

### Rationale
Two runs of a deterministic parser over the same input must produce
byte-identical `CanonicalDocument`/`CanonicalChunk` output, required for
diffing, caching, and the reproducibility guarantees tested throughout
this project.

### Trade-offs and consequences
Every adapter/generator must consistently call the shared helper rather
than inventing its own ID scheme; IDs are hex digests, not human-legible
sequential numbers.

### Deferred questions or reconsideration trigger
The exact hash truncation/format was an open item at Stage 1
(`fixtures/BENCHMARK_CONTRACT.md` section 3); resolved as full SHA-256 hex
by Stage 2 implementation — closed.

### Implementation and evidence
`canonical/hashing.py::stable_element_id` ("Never uses Python's built-in
hashing function... or a random UUID generator");
`tests/test_canonical_hashing.py::test_hashing_module_does_not_use_uuid4_or_builtin_hash`,
`test_stable_element_id_deterministic`.

---

## D-011 — Keep runtime paths and extraction-run metadata outside stable canonical identity

**Status:** Accepted
**Stage:** Stage 2 / Stage 2.1
**Date/commit:** `e1eff3d`

### Problem
Absolute filesystem paths and other run-specific detail would make
`CanonicalDocument` non-reproducible across machines if embedded directly.

### Alternatives considered
(a) Store absolute paths directly on `CanonicalDocument`/`CanonicalPicture`.
(b) Require portable, relative, POSIX-style paths on `CanonicalDocument`,
and push all absolute/run-specific data to `ExtractionRun.raw_artifact_refs`.

### Decision
(b).

### Rationale
A stable, hashed document must be reproducible and comparable regardless of
which machine or directory it was processed on.

### Trade-offs and consequences
Adapters must convert to relative/portable form before constructing
`CanonicalDocument` — the model only validates and rejects, it never
silently normalizes a bad path.

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`canonical/model.py::_validate_portable_relative_path`,
`CanonicalDocument.source_relative_path`/`CanonicalPicture.artifact_ref`
docstrings; `canonical/extraction_run.py::ExtractionRun.raw_artifact_refs`
docstring ("Absolute, machine-specific paths live here, never on
CanonicalDocument"); `tests/test_canonical_schema.py::test_absolute_source_relative_path_rejected`
and related path-rejection tests.

---

## D-012 — Separate CanonicalDocument from BenchmarkBinding/EvaluationContext as a general principle

**Status:** Accepted
**Stage:** Stage 2 / Stage 2.1
**Date/commit:** `e1eff3d`

### Problem
Beyond the one concrete fix in D-003, should any benchmark- or evaluation-
context concept ever be allowed to live inside the canonical model package
over time?

### Alternatives considered
(a) Let `canonical/` grow to include benchmark-scoring concerns as
convenient. (b) Hold a hard, standing boundary: `canonical/` describes
extracted content only, ever.

### Decision
(b), with `BenchmarkBinding` as the one deliberate exception model kept
outside `canonical/` specifically to preserve this boundary.

### Rationale
The same boundary violation D-003 fixed once could recur in a different
form (e.g. an "EvaluationContext" creeping into `ExtractionRun`); stating
it as a standing principle prevents that class of regression, not just the
one instance already found.

### Trade-offs and consequences
Any future benchmark/evaluation concept must pass a "does this leak into
`canonical/`?" review — an ongoing discipline cost, not a one-time fix.

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`src/ingestion_bench/benchmark_binding.py` module docstring;
`fixtures/BENCHMARK_CONTRACT.md` header note (explicit "three
responsibilities" framing).

---

## D-013 — Use structural chunking rather than generic sliding-window chunking

**Status:** Accepted
**Stage:** Stage 4
**Date/commit:** `8a1db98`

### Problem
A generic fixed-token sliding-window chunker (the default approach in most
RAG pipelines) was considered and rejected.

### Alternatives considered
(a) Generic fixed-size sliding-window token chunking with overlap. (b)
Structural chunking driven by `CanonicalDocument`'s own elements (headings,
paragraphs, list items, tables, pictures) walked in reading order.

### Decision
(b). `chunking/chunker.py::chunk_document` / `_build_ordered_elements`.

### Rationale
This project's premise is measuring how faithfully structure is extracted;
discarding that structure at chunk time (flattening into a token stream)
would throw away exactly the information the benchmark exists to evaluate,
and would produce chunks that split mid-table or mid-sentence
unpredictably.

### Trade-offs and consequences
Chunk sizes are less uniform than fixed-token chunking; the chunker must
handle every structural element type explicitly (more code, more test
surface — `tests/test_chunking.py` has 98 tests).

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`chunking/chunker.py::_build_ordered_elements` docstring ("Never depends
on dict insertion order or randomness: the sort key is fully explicit");
`tests/test_chunking.py::test_text_chunk_preserves_paragraph_order`,
`test_paragraph_order_independent_of_input_list_order`.

---

## D-014 — Do not use generic chunk overlap

**Status:** Accepted
**Stage:** Stage 4
**Date/commit:** `8a1db98`

### Problem
Many RAG chunkers duplicate a tail/head of text between adjacent chunks
("overlap") to reduce boundary-loss risk at retrieval time.

### Alternatives considered
(a) Generic fixed-size overlap between every adjacent chunk pair. (b) No
generic overlap — rely on auditable heading-context repetition, complete
structural elements retained where possible, and (deferred) sentence-
aligned overlap only within one oversized element's own forced split.

### Decision
(b).

### Rationale
Heading context is already repeated on every chunk in an auditable,
structured way (`heading_path`/`heading_source_element_ids`/
`heading_source_refs`) rather than as opaque duplicated prose. Complete
structural elements (a whole paragraph, a whole table) are retained
together wherever they fit, already reducing boundary loss. Generic
overlap would duplicate evidence across chunks and weaken provenance (two
chunks both "containing" the same sentence under different `chunk_id`s
complicates audit and retrieval-count metrics). A retriever can expand to
neighboring chunks at query time using `unit_indices`/`order_index` instead
of needing pre-baked overlap.

### Trade-offs and consequences
A genuine claim that happens to fall exactly at a forced split inside one
oversized element could still be harder to retrieve in a single chunk than
with overlap — the one case explicitly flagged as re-openable.

### Deferred questions or reconsideration trigger
Sentence-aligned overlap may be reconsidered, but *only* for fragments of
one oversized source element (never generic cross-chunk overlap), and only
if evaluation against `reference_manifest.json` shows measurable
boundary-loss failures once an evaluator exists.

### Implementation and evidence
`chunking/chunker.py::split_oversized_text`; `chunking/model.py::TextFragment`;
`tests/test_chunking.py::test_split_oversized_text_fragments_are_ordered_and_nonoverlapping`.

---

## D-015 — Keep captions with their target pictures and avoid duplicate standalone caption chunks

**Status:** Accepted
**Stage:** Stage 4
**Date/commit:** `8a1db98`

### Problem
A caption is its own `CanonicalCaption` element; should it also be
independently eligible to become its own text chunk?

### Alternatives considered
(a) Chunk captions independently, in reading order alongside paragraphs.
(b) Never chunk a caption standalone — pull it into its target picture's
chunk only.

### Decision
(b). `_build_ordered_elements` deliberately never includes
`CanonicalCaption` in the reading-order element list; captions are pulled
in only via the picture they target.

### Rationale
A caption's meaning is inseparable from the picture it describes; chunking
it separately would duplicate the same sentence into two different chunks
with no benefit and a real risk of double-counting in retrieval or
evaluation.

### Trade-offs and consequences
A caption can never appear in a chunk on its own — a future "captions
only" retrieval use case would need new chunking configuration, not
currently supported.

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`chunking/chunker.py::_build_ordered_elements` docstring ("never captions
-- those are only ever pulled in via their target picture, per chunking
rule 7"); `tests/test_chunking.py::test_caption_not_duplicated_as_standalone_chunk`.

---

## D-016 — Keep tables and pictures standalone by default

**Status:** Accepted
**Stage:** Stage 4
**Date/commit:** `8a1db98`

### Problem
Should a table or picture be allowed to merge into the surrounding text
buffer, or always get its own chunk?

### Alternatives considered
(a) Always merge tables/pictures into whatever text buffer surrounds them.
(b) Standalone by default, configurable off.

### Decision
(b). `ChunkingConfig.table_as_standalone_chunk`/`picture_as_standalone_chunk`
both default `True`; when set `False`, the element still packs atomically
(never split) into the buffer under the same rules as text.

### Rationale
A table or picture is a structurally distinct unit whose retrieval value
is usually self-contained; merging it into surrounding prose by default
would make it harder to retrieve, cite, or evaluate as a distinct
artifact.

### Trade-offs and consequences
Standalone-by-default can produce many small chunks for a document with
many small tables/pictures; the configuration escape hatch exists
precisely for that case.

### Deferred questions or reconsideration trigger
None — both directions are implemented and tested.

### Implementation and evidence
`chunking/model.py::ChunkingConfig`;
`tests/test_chunking.py::test_table_as_standalone_false_merges_with_surrounding_text`,
`test_table_becomes_standalone_chunk_with_all_cells_and_spans`.

---

## D-017 — Preserve asset-only pictures even when no textual annotation is available

**Status:** Accepted
**Stage:** Stage 4.1
**Date/commit:** `1692325`

### Problem
Stage 4's original `emit_chunk` logic dropped a picture chunk entirely if
it had no `source_text` and no `model_derived_text`, silently discarding a
picture with no caption/OCR/description.

### Alternatives considered
(a) Leave that behavior. (b) Add `ChunkAssetRef` and emit a chunk whenever
`source_text`, `model_derived_text`, OR `asset_refs` is non-empty.

### Decision
(b).

### Rationale
A picture with no textual annotation is still a real, retrievable/citable
artifact; silently dropping it broke the project's evidence-preservation
principle.

### Trade-offs and consequences
`retrieval_text` for such a chunk is empty and `embedding_input_sha256` is
`None` (closed by D-019/Stage 4.2) — a future retrieval/embedding layer
must handle that case explicitly rather than assume every chunk has
embeddable text.

### Deferred questions or reconsideration trigger
None — closed by the Stage 4.2 `embedding_input_sha256` nullability fix.

### Implementation and evidence
`chunking/model.py::ChunkAssetRef`; `chunking/chunker.py::emit_chunk`
("if not source_text and not model_derived_text and not asset_refs:
return"); `tests/test_chunking.py::test_picture_with_no_textual_annotations_still_emits_asset_only_chunk`.

---

## D-018 — Include provenance in chunk integrity hashing

**Status:** Accepted
**Stage:** Stage 4.1
**Date/commit:** `1692325`

### Problem
Stage 4's original `content_sha256` was computed from rendered text fields
only; a bbox or source-ordering change with identical rendered text
produced an identical hash, hiding a real provenance change.

### Alternatives considered
(a) Hash text-derived content only. (b) Fold serialized `source_refs`/
`heading_source_refs`/`asset_refs` into the hash payload too.

### Decision
(b).

### Rationale
`content_sha256` is meant to be an auditable integrity hash of the *full*
chunk, not just its rendered text; a provenance-only change is a real
content change from an audit standpoint and must be detectable.

### Trade-offs and consequences
`content_sha256` is now sensitive to details a naive reader might not
expect (two chunks with identical visible text can have different
`content_sha256`) — intentional, and documented explicitly in
`docs/POC_ARCHITECTURE.md` section F to avoid confusion.

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`chunking/chunker.py::emit_chunk` (`content_payload` construction);
`tests/test_chunking.py::test_changing_bbox_changes_content_hash_and_chunk_id_when_text_unchanged`,
`test_changing_heading_bbox_changes_content_hash_via_heading_source_refs`.

---

## D-019 — Separate chunk content identity from embedding-input identity

**Status:** Accepted
**Stage:** Stage 4.1 (introduced); Stage 4.2 (made nullable)
**Date/commit:** `1692325`; `c0cf2c3`

### Problem
After D-018 made `content_sha256` provenance-sensitive, using it as an
embedding-cache key would force unnecessary re-embedding whenever only
provenance changed, even though the text handed to the embedding model
didn't change.

### Alternatives considered
(a) Use `content_sha256` as the embedding cache key too. (b) Introduce a
separate `embedding_input_sha256` hashing only `retrieval_text`.

### Decision
(b).

### Rationale
Embeddings are expensive (API cost/latency) and are a pure function of
text; provenance changes should not force re-embedding, but should still
be visible as a `content_sha256`/`chunk_id` change for audit purposes.

### Trade-offs and consequences
Two different hashes must both be understood as semantically distinct by
any consumer of `CanonicalChunk` (documented in `docs/POC_ARCHITECTURE.md`
section F). `embedding_input_sha256` is `None` when `retrieval_text` is
empty, so an asset-only picture chunk never collapses onto `sha256("")`
(Stage 4.2 fix).

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`chunking/model.py::CanonicalChunk.embedding_input_sha256` docstring;
`tests/test_chunking.py::test_changing_only_provenance_changes_content_hash_but_not_embedding_hash`,
`test_asset_only_picture_chunk_has_no_embedding_input_hash`.

---

## D-020 — Preserve repeated clauses across policy revisions as separate chunk occurrences while allowing embedding reuse

**Status:** Accepted
**Stage:** Stage 4.1
**Date/commit:** `1692325`

### Problem
Two revisions of the same logical document can share large amounts of
identical text. Should the chunker deduplicate identical-text chunks
across revisions?

### Alternatives considered
(a) Deduplicate/collapse identical-text chunks across revisions into one
record. (b) Always keep a separate `CanonicalChunk` record per revision
(distinguished by `document_revision_id`, hence a distinct `chunk_id`),
while allowing the embedding layer to reuse an embedding when
`embedding_input_sha256` matches.

### Decision
(b).

### Rationale
Two revisions are different documents with different provenance and
lineage even where text coincides; collapsing them would make "which
revision does this chunk belong to" unanswerable, which is required for
effective-revision retrieval (D-022). Embedding reuse remains valid because
an embedding is a pure function of text.

### Trade-offs and consequences
More `CanonicalChunk` records accumulate over time than a deduplicated
scheme would produce; a future storage layer must handle this
multiplication deliberately (not yet designed).

### Deferred questions or reconsideration trigger
The storage-layer deduplication/embedding-cache implementation itself is
not built — this decision governs the model's identity semantics only.

### Implementation and evidence
`chunking/chunker.py::chunk_document` (`document_revision_id` folded into
`chunk_id`'s discriminator);
`tests/test_chunking.py::test_identical_chunk_text_across_revisions_differs_in_chunk_id_shares_embedding_hash`.

---

## D-021 — Keep mutable revision state outside CanonicalChunk

**Status:** Accepted
**Stage:** Stage 4.1
**Date/commit:** `1692325`

### Problem
Should `CanonicalChunk` carry `is_latest`/`is_current`/`publication_status`/
`superseded_by_revision_id`/an ingestion timestamp directly, for retrieval
convenience?

### Alternatives considered
(a) Add these fields directly to `CanonicalChunk`. (b) Keep `CanonicalChunk`
purely content-addressed/stable, and push this state to a future, separate
document-revision registry / `ChunkIndexRecord`.

### Decision
(b).

### Rationale
These fields describe retrieval-time status that can change without any
change to extracted content — mixing them into a stable, hashed record
would either force spurious re-hashing on pure status changes, or force
the hash to deliberately exclude some fields from an otherwise-complete
integrity hash (fragile, error-prone).

### Trade-offs and consequences
A retrieval layer cannot answer "is this the current revision" from
`CanonicalChunk` alone — it needs the (not yet implemented) registry. An
explicit, accepted layering cost.

### Deferred questions or reconsideration trigger
Implementation of the registry/`ChunkIndexRecord` itself.

### Implementation and evidence
`chunking/model.py::DocumentRevisionContext` docstring;
`tests/test_chunking.py::test_no_mutable_revision_state_fields_on_canonical_chunk`.

---

## D-022 — Retrieve the currently effective authoritative policy revision, not merely the latest uploaded revision

**Status:** Accepted (as documented policy); implementation **Not started**
**Stage:** Stage 4.1 (documented); retrieval layer not started
**Date/commit:** `1692325`

### Problem
Naive "most recent upload wins" retrieval can surface a draft or a
future-effective revision as current policy, or fail to prefer an
intentionally-backdated correction.

### Alternatives considered
(a) Always retrieve the most-recently-ingested revision for a logical
document. (b) Retrieve the currently *effective* authoritative revision;
exclude drafts/future-effective revisions from default retrieval;
historical revisions available only for explicit historical/comparison
queries.

### Decision
(b) — documented as the intended default policy.

### Rationale
"Most recently uploaded" and "currently authoritative" are different
concepts in any real document-governance setting; conflating them would
produce confidently wrong answers.

### Trade-offs and consequences
This is a documented policy only — **no retrieval code enforces it**,
since no retrieval layer or revision registry exists yet. Must not be
assumed done.

### Deferred questions or reconsideration trigger
Depends on the future document-revision registry (D-021) and a retrieval
layer (not started).

### Implementation and evidence
`chunking/model.py::DocumentRevisionContext` docstring, "Intended default
retrieval policy" section (verbatim four bullet points). No retrieval code
exists to verify enforcement.

---

## D-023 — Reject exact duplicate source uploads upstream using logical document identity plus source hash where appropriate

**Status:** Accepted (as documented policy); implementation **Not started**
**Stage:** Stage 4.1 (documented); ingestion entrypoint not started
**Date/commit:** `1692325`

### Problem
How should an ingestion pipeline avoid reprocessing/re-storing an
identical file uploaded twice under the same logical document?

### Alternatives considered
(a) Always reprocess and store every upload, even byte-identical repeats.
(b) Allow an upstream ingestion layer to skip processing when
`logical_document_id` and `source_document_sha256` both already match an
existing revision.

### Decision
(b) — documented as an allowed upstream optimization.

### Rationale
An exact repeat upload carries no new information; `document_revision_id`
is already fully deterministic from those two inputs (among others), so a
match is detectable cheaply before any parsing happens.

### Trade-offs and consequences
Not implemented — there is no upload/ingestion entrypoint in the
repository yet to apply this rule in.

### Deferred questions or reconsideration trigger
Implementation depends on a not-yet-built ingestion entrypoint. **Needs
confirmation** whether this remains the intended mechanism once that
entrypoint is designed.

### Implementation and evidence
`chunking/model.py::compute_document_revision_id` (deterministic from
exactly `logical_document_id` + `source_document_sha256` + normalized
`version_label` + `revision_number`). No ingestion entrypoint exists in the
repository.

---

## D-024 — Do not discard same-text chunks across different document revisions

**Status:** Accepted
**Stage:** Stage 4.1 (model semantics); Stage 4.2 (duplicate-guard fix)
**Date/commit:** `1692325`; `c0cf2c3`

### Problem
The negative-form restatement of D-020: under what conditions is it
acceptable to discard/merge two chunk records that share identical text?

### Alternatives considered
See D-020.

### Decision
Preserve separate `CanonicalChunk` records whenever `document_revision_id`
differs, source location differs, or provenance differs. Only reject
*accidental* duplicate occurrences *within one revision* (same
`document_revision_id`, same ordered source element ids, same source
references, same `content_sha256`) — enforced by `chunk_document()`'s own
duplicate-occurrence guard.

### Rationale
See D-020. The within-one-revision guard exists to catch a chunker/adapter
bug (e.g. the same element processed twice), not to catch legitimate
repeated text — which is why the guard is span-aware (Stage 4.2 fix,
D-028) rather than purely text-based.

### Trade-offs and consequences
See D-020.

### Deferred questions or reconsideration trigger
None beyond D-020's.

### Implementation and evidence
`chunking/chunker.py::chunk_document` (duplicate-occurrence guard at the
end of the function);
`tests/test_chunking.py::test_repeated_sentence_paragraph_splits_without_duplicate_occurrence_error`.

---

## D-025 — Keep Graph RAG and wiki projections derived and selective rather than treating them as authoritative source models

**Status:** Accepted (as principle); no projection implementation exists
**Stage:** Pre-Stage-1 plan; ongoing principle
**Date/commit:** Needs confirmation (principle predates recorded git
history; the existing `src/` GraphRAG POC referenced for contrast was
committed in `e1eff3d` but is architecturally unrelated — see Rationale)

### Problem
How should future vector/graph/wiki knowledge projections relate to the
canonical model — as independent sources of truth, or as derived views?

### Alternatives considered
(a) Let each projection (vector index, graph, wiki pages) maintain its own
independent notion of document truth. (b) Treat every projection as
strictly derived from `CanonicalDocument`/`CanonicalChunk`/provenance/
`ExtractionRun`, rebuildable from source at any time.

### Decision
(b).

### Rationale
If a graph or wiki projection could diverge from the canonical extracted
record, there would be two competing "truths" with no reconciliation path;
keeping projections derived means they can always be regenerated and
re-verified against the same auditable source.

### Trade-offs and consequences
No projection code exists yet to validate this in practice. The existing
`src/` GraphRAG POC (`build_graph_artifacts.py`, `graph_enriched_retriever.py`,
`vector_retriever.py`) is **explicitly not an example of this pattern** —
per the root `README.md` it is hand-seeded, not derived from any canonical
model, and must not be cited as evidence that a derived Graph RAG
projection of ingestion-bench output has been built.

### Deferred questions or reconsideration trigger
All projection implementation — see `docs/POC_STATUS_AND_EVIDENCE.md`,
"Explicitly deferred scope."

### Implementation and evidence
Root `README.md` (describes the hand-seeded `src/` POC explicitly); no
`src/ingestion_bench/` code produces a graph, vector index, or wiki page.

---

## D-026 — Engineer deterministic, byte-reproducible synthetic fixture generation

**Status:** Accepted
**Stage:** Stage 3 / Stage 3.1
**Date/commit:** `e1eff3d`; `ad557c8`

### Problem
Standard document-generation libraries (`reportlab`, `python-docx`,
`python-pptx`) embed nondeterministic metadata (creation timestamps, ZIP
entry timestamps, file IDs) by default, breaking byte-for-byte
reproducibility.

### Alternatives considered
(a) Accept nondeterministic fixtures and rely only on semantic (not
byte-level) comparison. (b) Explicitly engineer determinism: fixed
`reportlab` `Canvas(invariant=1)`, fixed DOCX/PPTX `core_properties`,
post-save ZIP entry timestamp normalization.

### Decision
(b).

### Rationale
Byte-level determinism enables strong regression tests and gives every
fixture a stable, citable `content_sha256`/`manifest_sha256` pairing
recorded in `fixtures/generated/generation_report.json` — important since
the benchmark's premise depends on fixtures being an exact, reproducible
rendering of the manifest.

### Trade-offs and consequences
Nontrivial engineering: custom canvasmaker, `lxml`-level OOXML patching for
connector arrowheads, ZIP rewriting — more code than a simpler approach
would need.

### Deferred questions or reconsideration trigger
None — verified.

### Implementation and evidence
`fixtures/generate_fixtures.py` (`_invariant_canvasmaker`,
`normalize_zip_timestamps`, `set_docx_core_properties`,
`set_pptx_core_properties`, `add_target_arrowhead`);
`tests/test_fixture_generation.py::test_regeneration_is_byte_deterministic`,
`test_regeneration_produces_same_manifest_sha256`.

---

## D-027 — Verify fixtures with lightweight custom parsers instead of adding new parsing dependencies

**Status:** Accepted
**Stage:** Stage 3 / Stage 3.1
**Date/commit:** `e1eff3d`; `ad557c8`

### Problem
Verifying PDF glyph/text-layer/embedded-image properties in tests would
normally call for a PDF-parsing dependency (e.g. `pypdf`/`fitz`), which
would also need to be excluded from the chunking layer's forbidden-import
list, adding surface area.

### Alternatives considered
(a) Add a PDF-parsing library as a test dependency. (b) Write small,
dependency-free content-stream parsers directly in the test suite.

### Decision
(b).

### Rationale
Keeps the project's whole dependency surface minimal and avoids a library
whose own parsing choices could mask or introduce bugs unrelated to what's
actually being verified (e.g. whether the generated PDF has real
glyph-showing operators).

### Trade-offs and consequences
More custom test code to maintain; less battle-tested than a real PDF
library for edge cases outside this project's own generator output.

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`tests/test_fixture_generation.py` (PDF content-stream helper functions);
`test_scanned_pdf_has_no_glyph_showing_operators`,
`test_scanned_pdf_has_no_extractable_text_fragments`.

---

## D-028 — Add fragment-level provenance for oversized-element splitting

**Status:** Accepted
**Stage:** Stage 4.2
**Date/commit:** `c0cf2c3`

### Problem
Stage 4.1's duplicate-occurrence guard (D-018/D-024) could false-positive
on a legitimately split paragraph whose repeated sentences produced
byte-identical fragments with no way to distinguish them.

### Alternatives considered
(a) Special-case the duplicate guard to ignore split fragments. (b) Give
every split fragment its own exact `(start_char, end_char)` provenance
span, so fragments are distinguishable by position even when their text is
identical, letting the existing span-aware duplicate guard work unmodified.

### Decision
(b).

### Rationale
(b) is more general: it also enables correct per-fragment identifier
routing (an `IdentifierAnnotation` with character offsets can be
attributed to the specific fragment containing it, rather than always
defaulting to fragment 0) and gives auditors an exact source span per
fragment.

### Trade-offs and consequences
`split_oversized_text`'s return type changed from `list[str]` to
`list[TextFragment]` — a breaking API change requiring every caller/test to
update; the span-tracking algorithm (`_pack_boundary_spans`) is more
complex than simple string concatenation.

### Deferred questions or reconsideration trigger
Identifier-offset routing is exact only when the split element has no
*other* extracted-derivation annotation text appended ahead of it —
documented as a known scope limit, not yet exercised by any fixture.

**Resolved by D-031 (Stage 4.2a):** this scope limit is closed —
`split_oversized_text` no longer runs against text that could have
anything appended ahead of it, because it now runs against the canonical
element's own text exclusively.

### Implementation and evidence
`chunking/model.py::TextFragment`, `ChunkSourceRef.fragment_index`/
`start_char`/`end_char`; `chunking/chunker.py::split_oversized_text`,
`_pack_boundary_spans`;
`tests/test_chunking.py::test_repeated_sentence_paragraph_splits_without_duplicate_occurrence_error`,
`test_identifier_annotation_routed_to_later_fragment_by_offset`.

---

## D-029 — Canonicalize the stored version_label, not just the hash-input version_label

**Status:** Accepted
**Stage:** Stage 4.2
**Date/commit:** `c0cf2c3`

### Problem
Stage 4.1's `compute_document_revision_id()` normalized `version_label`
(strip/lower-case) only for hashing purposes; the *stored*
`DocumentRevisionContext.version_label` field kept the caller's raw
string, so `"Draft"` and `"draft"` produced the same `document_revision_id`/
`chunk_id` but different serialized `version_label` values on otherwise-
identical chunks.

### Alternatives considered
(a) Leave the raw string stored, normalize only for hashing (status quo).
(b) Normalize and store the canonical form, rejecting empty-after-strip
input.

### Decision
(b).

### Rationale
If two contexts hash identically, every other serialized field they
produce should also be identical — otherwise the hash equivalence is
misleading to an auditor.

### Trade-offs and consequences
The caller-supplied original casing/whitespace of `version_label` is no
longer recoverable from the stored model — accepted as correct, since the
normalized form is what actually participates in identity.

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`chunking/model.py::_normalize_version_label`,
`DocumentRevisionContext` field validator on `version_label`;
`tests/test_chunking.py::test_equal_normalized_version_label_gives_identical_stored_lineage_and_chunk_metadata`.

---

## D-030 — Make table metadata fully explicit and never positionally inferred

**Status:** Accepted
**Stage:** Stage 4.1 (partial); Stage 4.2 (completed)
**Date/commit:** `1692325`; `c0cf2c3`

### Problem
An early table-rendering format only noted header/span status when true or
greater-than-one, and relied on a cell's position within a Markdown
pipe-table row to imply its column — which silently misattributes column
identity for a sparse table (a row missing a cell due to a rowspan
elsewhere shifts what a purely positional reading implies).

### Alternatives considered
(a) Keep the compact, position-implied Markdown rendering. (b) Require
every cell to always state `row`, `col`, `header=true|false`, `rowspan`,
`colspan` explicitly, regardless of whether the value is a "default."

### Decision
(b).

### Rationale
The benchmark's premise is verifying structural fidelity; a rendering that
itself requires positional inference to recover structure would undermine
that goal and could hide real extraction/rendering bugs.

### Trade-offs and consequences
More verbose rendered text per table cell.

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`chunking/renderers.py::render_table_text`;
`tests/test_chunking.py::test_sparse_table_renders_explicit_row_col_for_missing_cells`,
`test_table_rendering_always_includes_header_and_span_defaults`.

---

## D-031 — Split against the canonical element's own text, never combined rendered text

**Status:** Accepted
**Stage:** Stage 4.2a
**Date/commit:** `47fad5f`

### Problem
Stage 4.2's `split_oversized_text()` operated on
`_RenderedElement.source_text`, which combines the canonical element's own
text with a list item's display prefix (`"  - "`) and any extracted-
annotation rendering appended via `"\n"`. This put fragment
`start_char`/`end_char` in a different coordinate space than
`IdentifierAnnotation.start_char`/`end_char`, which
`fixtures/BENCHMARK_CONTRACT.md` section 6 defines as offsets "within the
source block's text" — i.e. the canonical `paragraph.text`/`list_item.text`
itself. This was flagged as a known scope limit when D-028 was accepted.

### Alternatives considered
(a) Leave splitting against the combined `source_text` and document the
coordinate-space mismatch as a permanent limitation. (b) Split against the
canonical element's own raw text only, decoupling the list-item display
prefix and the element's own extracted-annotation rendering so both are
applied strictly after splitting, never before it.

### Decision
(b).

### Rationale
Identifier-offset semantics are only meaningful if fragment spans and
annotation offsets share one coordinate space. (a) would have left a
permanent, silent misattribution risk for exactly the combination of
features (an oversized list item, or an oversized paragraph carrying an
extracted annotation) that D-028's fragment-level provenance was meant to
support correctly.

### Trade-offs and consequences
Display-only concerns (list indentation/`"- "`, the element's own
extracted-annotation text) are now applied *after* splitting via a new
`_RenderedElement.fragment_display_prefix` field and by reusing
`extra_source_text` at emission time — a small amount of additional
plumbing in `chunker.py`'s oversized-split branch.
`ChunkSourceRef`/`TextFragment` both gained stricter validation (three-way
all-or-nothing fragment provenance; text/span length equality) as a direct
consequence of making span semantics load-bearing. `CHUNKER_VERSION`
bumped `1.1.0 -> 1.2.0` (a splitting/rendering rule change), which changes
every `chunk_id` in a corpus on the next run, split or not — see the
worked example note in `docs/IMPLEMENTATION_WALKTHROUGH.md`.

### Deferred questions or reconsideration trigger
None open — this closes the scope limit noted in D-028.

### Implementation and evidence
`chunking/chunker.py` (oversized-split branch; `_RenderedElement.raw_text`/
`fragment_display_prefix`); `chunking/renderers.py::render_list_item_prefix`;
`chunking/model.py::ChunkSourceRef._validate_fragment_provenance`,
`TextFragment._validate_span`;
`tests/test_chunking.py::test_annotation_rendering_does_not_affect_fragment_spans`,
`test_fragment_spans_reconstruct_original_list_item_text_exactly`,
`test_oversized_list_item_identifier_routed_to_later_fragment_despite_prefix`,
`test_oversized_paragraph_with_extracted_annotation_splits_correctly`.

---

## D-032 — Confine Docling to the adapter boundary

**Status:** Accepted
**Stage:** Stage 5A
**Date/commit:** Needs confirmation (assigned at Stage 5A implementation time; see `git log` for the actual Stage 5A commit once made)

### Problem
Once a real Docling adapter exists, how far should `DoclingDocument` (and
any other Docling/docling-core type) be allowed to travel through the
rest of the system?

### Alternatives considered
(a) Let `DoclingDocument` (or fragments of it) flow into the chunking
layer, a future indexing/retrieval layer, or a future agent layer, where
convenient. (b) Confine every Docling/docling-core import and type to
`src/ingestion_bench/adapters/docling_standard/` (specifically
`mapper.py` and `adapter.py`); everything downstream ever sees only
`CanonicalDocument`/`CanonicalChunk`.

### Decision
(b). `DoclingDocument` is never propagated into `canonical/`, `chunking/`,
or any future indexing/retrieval/agent layer.

### Rationale
This is the entire point of D-001/D-002 (parser-neutral canonical model;
Docling as an adapter, not a domain dependency) actually being exercised
by a real parser for the first time. If `DoclingDocument` leaked past the
adapter boundary even once, every downstream consumer would need to know
about Docling's types, defeating the reason the canonical model exists.

### Trade-offs and consequences
Every Docling-derived value the mapper cannot faithfully carry through
`CanonicalDocument`'s frozen fields is either dropped (with a diagnostic)
or represented through the least-speculative valid canonical field
available (e.g. `ProvenanceEntry.source_locator` for Docling's own label
string) — never smuggled through as an opaque blob "just in case."

### Deferred questions or reconsideration trigger
None — this is intended as a permanent boundary, re-verified by every
future adapter (OpenAI vendor-native, path C; any future path).

### Implementation and evidence
`tests/test_docling_standard_mapper.py::test_canonical_and_chunking_packages_have_no_docling_imports`
(greps `canonical/` and `chunking/` source for actual `import docling`/
`import docling_core` statements); `src/ingestion_bench/adapters/docling_standard/mapper.py`
and `adapter.py` docstrings ("This is the ONLY module... that imports
Docling/docling-core types").

---

## D-033 — Use explicit RapidOcrOptions, never Docling's default OCR auto-selection

**Status:** Accepted
**Stage:** Stage 5A
**Date/commit:** Needs confirmation

### Problem
Docling 2.114.0's own `PdfPipelineOptions()` default (`OcrAutoOptions`)
resolves to whichever OCR engine happens to be importable in the current
environment at pipeline-construction time.

### Alternatives considered
(a) Leave the default `OcrAutoOptions` in place. (b) Set `RapidOcrOptions`
explicitly.

### Decision
(b).

### Rationale
Environment-dependent engine selection is exactly the kind of
nondeterminism this project avoids everywhere else (D-010: deterministic
IDs/hashes; D-026: deterministic fixture generation) — the *conversion
algorithm itself* (which OCR engine ran) should not silently vary by
which optional packages happen to be installed. RapidOCR was chosen
because it is what `docling[standard]`'s own dependency set actually
installs (`easyocr`/`tesseract` are not installed dependencies of this
project).

### Trade-offs and consequences
`onnxruntime` (RapidOCR's inference backend) is not pulled in
automatically by `docling[standard]` and had to be installed as an
explicit additional dependency (`requirements.txt`) — discovered directly
during the Stage 5A compatibility spike (first conversion attempt raised
`ImportError: onnxruntime is not installed.`).

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`src/ingestion_bench/adapters/docling_standard/config.py::build_pdf_pipeline_options`;
`tests/test_docling_standard_adapter.py::test_effective_configuration_disables_every_remote_and_vlm_option`;
`reports/stage5a_docling_standard_baseline.md` section 1 (environment).

---

## D-034 — Read DOCX page geometry from python-docx as a documented fallback, never fabricate it

**Status:** Accepted
**Stage:** Stage 5A
**Date/commit:** Needs confirmation

### Problem
Docling's standard pipeline exposes no page geometry for DOCX at all
(`DoclingDocument.pages` is empty; every item's `.prov` is `[]`) —
discovered empirically during the Stage 5A API-inspection spike, not
assumed from memory. `CanonicalUnit.width`/`height` are required (`> 0`,
frozen canonical contract) and the Stage 5A instructions explicitly
forbid silently inserting a fake Letter/A4 default when geometry is
unavailable.

### Alternatives considered
(a) Fail every DOCX conversion outright, since Docling itself provides no
geometry. (b) Read the source `.docx` file's own declared section
`page_width`/`page_height` via `python-docx` (already a repository
dependency, used elsewhere only for fixture generation) as a narrow,
explicitly-diagnosed structural fallback — never touching document
content, only the one missing structural field.

### Decision
(b).

### Rationale
(a) would have made Stage 5A's DOCX lane useless for exactly the fixtures
(`docs_nested_structure` etc.) the benchmark most wants to exercise, over
a single structural field that has a real, non-fabricated answer sitting
in the file itself. This is not "inventing a fake Letter/A4 size" — it is
reading the file's own true declared page size through a different (non-
Docling) accessor, and recording a `docling_page_geometry_unavailable`
diagnostic every time it happens so the fallback is never silent.

### Trade-offs and consequences
Every canonical element extracted from a DOCX source has `bbox=None`
(Docling never provides one) even though the *unit* itself has real
geometry — DOCX-sourced `CanonicalDocument`s are therefore always
provenance-poorer at the element level than PDF/PPTX-sourced ones. This
is documented, not hidden (see
`reports/stage5a_docling_standard_baseline.md` section 6.1).

### Deferred questions or reconsideration trigger
Revisit only if a future Docling release exposes DOCX page/section
geometry through its own public API, at which point this fallback should
be removed in favor of the real source.

### Implementation and evidence
`src/ingestion_bench/adapters/docling_standard/mapper.py::DocxPageFallback`,
`DoclingToCanonicalMapper.build_units`; `adapter.py::_docx_page_fallback`;
`tests/test_docling_standard_mapper.py::test_docx_page_fallback_produces_valid_unit_with_diagnostic`,
`test_docx_missing_page_geometry_without_fallback_fails_cleanly`.

**Addendum (Stage 5A.1):** the diagnostic category this fallback records
was renamed `docling_page_geometry_unavailable` -> `docx_pagination_unavailable`
and now carries `affects_fidelity=True` (see D-037) — every DOCX
conversion's `conversion_status` is therefore `"partial"`, never
`"success"`, because collapsing all DOCX content onto one
`CanonicalUnit` is a real, unrecoverable loss of source pagination
structure, not merely an informational note. This is a rename/severity
correction only; the underlying fallback mechanism (read section geometry
via `python-docx`, never fabricate Letter/A4) is unchanged.

---

## D-035 — Detect OCR-origin text structurally (nested under a picture), never by which fixture is being processed

**Status:** Accepted
**Stage:** Stage 5A
**Date/commit:** Needs confirmation

### Problem
Docling 2.114.0's public API gives no per-item OCR-origin signal
(`TextItem.source` is `[]` for every text item observed, OCR or not) —
so how should the adapter ever justify creating an `OcrAnnotation` rather
than a plain `CanonicalParagraph`?

### Alternatives considered
(a) Create an `OcrAnnotation` whenever converting a fixture known (from
its filename or the benchmark's own framing) to be OCR-derived, e.g. the
scanned-PDF stress fixture. (b) Use only a real, general structural
signal available on every document regardless of which fixture it is:
whether a `TextItem`'s parent in the Docling document tree is a
`PictureItem`. (c) Never create `OcrAnnotation` at all in Stage 5A.

### Decision
(b).

### Rationale
(a) is exactly the kind of fixture-specific inference the Stage 5A
instructions explicitly forbid ("Do not infer an OcrAnnotation solely
because the input file is the scanned fixture"). (b) is real, general
evidence: native page text is never a child of a picture in any fixture
observed; only OCR-detected text-within-an-image-region is. (c) would
silently lose exactly the kind of evidence
(`expected_ocr_tokens` in the manifest) the benchmark most wants
extracted.

### Trade-offs and consequences
Body-level OCR text with no picture wrapper (the scanned-PDF stress
fixture, where the whole page is one OCR pass) has no signal under (b)
either, and is mapped as an ordinary `CanonicalParagraph` — a real,
documented gap in OCR-origin granularity, not silently smoothed over
(`reports/stage5a_docling_standard_baseline.md` section 6.6).

### Deferred questions or reconsideration trigger
Revisit if a future Docling release exposes real per-item OCR provenance
(e.g. a `source`/confidence field actually populated).

### Implementation and evidence
`src/ingestion_bench/adapters/docling_standard/mapper.py::map_picture_ocr_child`
docstring; `tests/test_docling_standard_mapper.py::test_ocr_annotation_only_for_picture_nested_text_not_body_text`;
`tests/test_docling_standard_integration.py::test_scanned_pdf_produces_no_model_derived_annotation`.

---

## D-036 — Artifact file-path keys must be format-qualified, distinct from doc_id

**Status:** Accepted
**Stage:** Stage 5A
**Date/commit:** Needs confirmation

### Problem
`reference_manifest.json`'s parity suite deliberately gives
`PARITY_001.pdf`/`.docx`/`.pptx` the SAME `doc_id` ("PARITY_001"), since
the manifest treats them as one logical benchmark unit compared across
formats. An early runner implementation used `doc_id` alone as the
on-disk artifact directory name for `artifacts/stage5a/<key>/` and
`artifacts/stage5a/assets/<key>/`, so the three format conversions
silently overwrote each other's `canonical_document.json`/picture PNGs —
caught only by inspecting the actual artifact directory after a batch
run, not by any test (none of the unit/integration tests happened to
run all three formats in the same process against the same output
directory).

### Alternatives considered
(a) Give `PARITY_001.pdf`/`.docx`/`.pptx` different `doc_id`s so file
paths never collide. (b) Keep `doc_id` shared (matching the manifest's
own intent), and derive a separate, format-qualified `artifact_key`
(`f"{doc_id}_{source_format}"`) used only for on-disk paths, never for
canonical identity.

### Decision
(b).

### Rationale
`doc_id` is meant to answer "which document is this," which for the
parity suite is genuinely "the same one, in three renderings" — changing
it to disambiguate would misrepresent the benchmark's own structure.
File-path collision is a distinct, purely mechanical concern that
`artifact_key` solves without touching identity semantics.

### Trade-offs and consequences
Two different keys must be kept straight throughout the adapter/runner
(`doc_id` for `CanonicalDocument.doc_id` and revision context;
`artifact_key` for every on-disk path) — a small but real discipline
cost, worth it to avoid silent data loss.

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`src/ingestion_bench/adapters/docling_standard/adapter.py::convert`
(`artifact_key` computed once, threaded through `_save_picture`/
`_write_raw_debug_snapshot`); `scripts/run_docling_standard.py::process_fixture`;
verified directly by inspecting `artifacts/stage5a/` after a full batch
run (`PARITY_001_pdf/`, `PARITY_001_docx/`, `PARITY_001_pptx/` all
present and distinct).

---

## D-037 — Derive conversion_status from a dedicated affects_fidelity axis, never from diagnostic severity alone

**Status:** Accepted
**Stage:** Stage 5A.1
**Date/commit:** Needs confirmation (assigned at Stage 5A.1 implementation time)

### Problem
Stage 5A's original `AdapterDiagnostic` had only one axis, `severity`
(`info`/`warning`/`error`), and `DoclingStandardAdapter.convert()` derived
`conversion_status="partial"` from `mapper.diagnostics.has_errors() or
bool(adapter_warnings)`. This conflated two genuinely different questions:
"how alarming is this to an operator" (severity) and "was source content,
structure, provenance, or a relationship actually lost or degraded"
(fidelity impact). It also meant every DOCX conversion was reported
`"success"` even though the DOCX pagination fallback (D-034) is a real,
guaranteed loss of page-boundary information on every single DOCX
conversion — its diagnostic was `severity="info"`, so the old rule never
flagged it as partial.

### Alternatives considered
(a) Keep one `severity` axis and redefine `"partial"` as `severity in
("warning", "error")` present. (b) Add a second, independent boolean field
`affects_fidelity` on `AdapterDiagnostic`, and derive `conversion_status`
from `affects_fidelity` exclusively (plus Docling's own
`PARTIAL_SUCCESS` status), never from `severity`.

### Decision
(b).

### Rationale
Severity and fidelity impact are not correlated in practice: the DOCX
pagination fallback is low-alarm (`info`) but always fidelity-affecting;
by contrast a `missing_provenance` `warning` on one stray element does
affect fidelity for that element specifically, while `skipped_furniture`
(`info`) never does (a page header/footer is intentionally excluded, not
lost). Collapsing these onto one axis made `conversion_status` either
over-report `"success"` (Stage 5A's actual bug, for DOCX) or would have
forced treating every routine informational diagnostic as fidelity-
affecting if severity had been widened instead.

### Trade-offs and consequences
Every diagnostic call site in `mapper.py` (~15 of them) needed an explicit
`affects_fidelity=` decision, not just a default — reviewed one by one
rather than inferred from severity. `DiagnosticCollector.has_errors()` is
now unused by `conversion_status` derivation (still available for callers
that specifically want severity-based filtering) — `has_fidelity_impact()`
is what `adapter.py` actually reads.

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`src/ingestion_bench/adapters/base.py::AdapterDiagnostic.affects_fidelity`,
`ConversionStatus` docstring; `docling_standard/diagnostics.py::DiagnosticCollector.has_fidelity_impact`;
`docling_standard/adapter.py::convert` (`is_partial` derivation);
`tests/test_adapters_base.py::test_diagnostic_severity_and_affects_fidelity_are_independent_axes`;
`tests/test_docling_standard_integration.py::test_parity_docx_is_a_valid_but_partial_document_with_one_explicit_unit`.

---

## D-038 — Attach a ProvenanceEntry to every OcrAnnotation Docling actually evidences

**Status:** Accepted
**Stage:** Stage 5A.1
**Date/commit:** Needs confirmation (assigned at Stage 5A.1 implementation time)

### Problem
Stage 5A's `map_picture_ocr_child` created an `OcrAnnotation` for every
picture-child OCR `TextItem` (D-035) but never a matching
`ProvenanceEntry` — every other canonical element (headings, paragraphs,
tables, pictures, captions) gets one, so OCR annotations were the one
extracted-content type with no auditable source-evidence record at all,
even though Docling's own `TextItem.prov` bbox and `self_ref` were
available and simply not being carried through.

### Alternatives considered
(a) Leave `OcrAnnotation` without provenance, as in Stage 5A. (b) Add a
`ProvenanceEntry` per `OcrAnnotation`, with `element_id` set to the
annotation's own `annotation_id` — `ProvenanceEntry.element_id` already
supports resolving to an annotation id, not just a block/table/picture id
(`canonical/model.py::_validate_provenance_element_ids`), so this needed
no canonical-model change at all.

### Decision
(b).

### Rationale
Withholding provenance from exactly the annotation type most likely to be
scored for OCR-token recall by a future evaluator (Stage 8) would leave
that scoring unauditable — a reader couldn't verify which bbox/element on
the source page an `OcrAnnotation`'s text actually came from. Since the
frozen canonical contract already anticipates annotation-id-valued
provenance, this is additive population of an existing, underused
capability rather than new modeling.

### Trade-offs and consequences
`OcrAnnotation` has no `order_index` field of its own (frozen contract),
so its `ProvenanceEntry.order_index` is always `None` — this is
intentional, not a bug: the chunker's picture-order fallback logic
(`chunking/chunker.py`) only reads provenance entries with a non-`None`
`order_index`, so OCR-annotation provenance entries are correctly ignored
by that lookup and never collide with a picture's own provenance entry.
An `ocr_sequence` field was added to `source_locator` to disambiguate
multiple OCR lines under one picture, but it reflects `doc.texts` scan
order, not necessarily true visual reading order within the picture
region — documented as a continuing Stage 5A/5A.1 limitation, not
resolved by this decision.

### Deferred questions or reconsideration trigger
True in-picture OCR reading order would require geometry-based sorting
(e.g. by bbox top-to-bottom/left-to-right) that Stage 5A.1 does not
attempt — revisit if a future stage needs ordered OCR text within one
picture.

### Implementation and evidence
`src/ingestion_bench/adapters/docling_standard/mapper.py::map_picture_ocr_child`
(`ProvenanceEntry` construction, `ocr_sequence` parameter);
`map_document` (`ocr_sequence_by_picture` counter);
`tests/test_docling_standard_integration.py::test_parity_pdf_picture_ocr_annotations_resolve_to_provenance_entries`,
`test_chart_fixture_ocr_annotations_resolve_to_provenance_entries`.

---

## D-039 — Report determinism component by component, never as one collapsed hash comparison

**Status:** Accepted
**Stage:** Stage 5A.2
**Date/commit:** Needs confirmation (assigned at Stage 5A.2 implementation time)

### Problem
Stage 5A/5A.1's `run_determinism_check` converted a fixture twice and
compared only `stable_canonical_hash()`, returning one collapsed boolean.
A single canonical hash comparison was insufficient evidence for the
broader claim this project actually makes in its reports — that "the
complete canonical and chunk outputs are deterministic" — since a hash
match does not by itself demonstrate that the full serialized
`CanonicalDocument`, the full serialized `CanonicalChunk` list, chunk
identity, and chunk content hashing are *all* independently stable.

### Alternatives considered
(a) Keep the single collapsed `stable_canonical_hash()` comparison and
continue describing it as proof of full-output determinism. (b) Compare
every claim independently — full serialized `CanonicalDocument` JSON,
`stable_canonical_hash()`, full serialized `CanonicalChunk` list JSON,
ordered `chunk_id`s, and ordered `content_sha256` values — and report
each result separately, with one `all_equal` field as a summary only.

### Decision
(b).

### Rationale
Report each comparison independently and retain an aggregate `all_equal`
field only as a summary, never as the sole reported figure. A hash
collision (astronomically unlikely but not the point) or a hash function
that happened not to be sensitive to some field would previously have
been invisible; independent component comparisons make each specific
claim ("chunk ids are stable," "chunk content hashes are stable")
separately falsifiable and separately auditable.

### Trade-offs and consequences
- A partial mismatch can no longer be concealed by one passing hash —
  `run_determinism_check` now returns a structured dict
  (`canonical_json_equal`, `canonical_hash_equal`, `chunk_json_equal`,
  `chunk_ids_equal`, `chunk_content_hashes_equal`, `all_equal`) instead of
  a single `bool`, and `all_equal` is true only when every component
  comparison is true.
- Reports state only comparisons that were actually executed — the
  Markdown table (`reports/stage5a_docling_standard_baseline.md` section
  4) now has one column per comparison rather than one "Identical across
  two runs" column, so a reader never has to trust an unstated aggregation
  rule.
- Future adapters (path B/C/D) must provide equivalent determinism
  evidence in this same structured shape — a future adapter's own runner
  may not regress to a single collapsed boolean.
- Chunking is now invoked twice as often during the determinism check
  (once per conversion) — negligible cost at this fixture count, accepted.

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`scripts/run_docling_standard.py::run_determinism_check` (returns the
structured dict), `_chunk_document` (shared helper so `process_fixture`
and `run_determinism_check` build chunks identically),
`render_baseline_markdown` (section 4 rendering, one column per
comparison); `tests/test_run_docling_standard_report.py::test_baseline_markdown_reflects_structured_determinism_results`
(asserts a deliberate partial mismatch is visible as `**NO**`, never
hidden behind a passing aggregate).

---

## D-040 — Canonical chunks are the common evidence substrate for multiple knowledge projections

**Status:** Accepted
**Stage:** Stage 5A.2 (recorded alongside the roadmap correction that follows from it)
**Date/commit:** Needs confirmation (assigned at Stage 5A.2 implementation time)

### Problem
The original working plan implicitly treated "path A/B/C/D ingestion" and
"retrieval" as one linear pipeline, without stating explicitly how
multiple different retrieval *projections* (a regular vector index, a
graph-enriched index, a wiki page/link structure) should relate to the
same underlying extracted content, or to each other.

### Decision
Regular vector indexes, graph structures, and wiki pages will be
independently derived from the same `CanonicalDocument` and
`CanonicalChunk` corpus. No projection is authoritative over another;
`CanonicalDocument`/`CanonicalChunk` (Stage 2/Stage 4, frozen) remain the
one shared, hashed, provenance-carrying evidence layer every projection
reads from.

### Rationale
This preserves a common authoritative evidence layer and allows retrieval
approaches to be compared without changing the underlying extracted
knowledge — exactly the same principle D-025 already established for
Graph RAG/wiki projections in general, now stated as a concrete
consequence for how the ingestion-fidelity evaluator's gold evidence set
(Stage 6A) is meant to be reused: the same expected-fact-to-chunk
alignment that scores Docling's ingestion fidelity is also the gold
evidence set later used to score vector RAG, Graph RAG, and wiki
retrieval, so all three retrieval projections are compared on identical
grounds rather than each inventing its own notion of "the right answer."

### Trade-offs and consequences
- Vector-, graph-, and wiki-specific fields do not enter
  `CanonicalDocument` or `CanonicalChunk` — those models stay parser-
  neutral and projection-neutral, per D-001/D-002/D-025; a graph edge
  weight or a wiki page slug is projection state, not extracted content.
- Every graph edge and wiki claim must retain supporting chunk IDs, so a
  projection's assertions remain traceable back to the same auditable
  `CanonicalChunk` evidence the ingestion evaluator already scored.
- All projections use the same revision lineage
  (`DocumentRevisionContext`/`document_revision_id`) and the same
  provenance (`ProvenanceEntry`/`ChunkSourceRef`) — no projection may
  invent its own document-identity or provenance scheme.
- All retrieval approaches must eventually be evaluated through one
  common benchmark query contract (not yet designed — a Stage 6B
  deliverable), so scores are comparable across projections.
- Vector, graph, and wiki representations remain derived projections,
  never authoritative source records — rebuilding any of them from
  `CanonicalDocument`/`CanonicalChunk` alone must always be possible.

### Deferred questions or reconsideration trigger
The common benchmark query contract itself (Stage 6B) and the concrete
storage/index design for each projection (Stages 7A/7B/7C) are not yet
built — this decision fixes the relationship between them and the shared
evidence layer, not their implementation.

### Implementation and evidence
No projection code exists yet. This decision governs the design of the
Stage 6A gold evidence-alignment catalog (`artifacts/stage6a/evidence_alignment.json`,
implemented in Stage 6A — see D-041/D-042) and constrains Stages 6B/7A/7B/7C
when they are built — see the corrected roadmap in
`docs/POC_STATUS_AND_EVIDENCE.md` and `docs/DEVIN_HANDOFF_SEED.md`.

---

## D-041 — Score primarily against CanonicalDocument; raw Docling output only attributes an already-established miss, never scores

**Status:** Accepted
**Stage:** Stage 6A
**Date/commit:** Needs confirmation (assigned at Stage 6A implementation time)

### Problem
The Stage 6A evaluator has three candidate representations it could score
against: raw Docling debug JSON (`artifacts/stage5a/docling_raw/`),
`CanonicalDocument`/`CanonicalChunk` (Stage 5A's mapped output), or some
blend of both. Scoring against raw Docling output would measure Docling's
own capability, not this project's actual mapped, chunked, retrievable
output — and would reintroduce a Docling-shaped dependency into the one
package explicitly allowed to be parser-agnostic evaluation logic.

### Alternatives considered
(a) Score against raw Docling debug JSON directly (fastest to implement,
but measures the wrong thing — Docling's capability, not this project's
mapping/chunking fidelity). (b) Score exclusively against
`CanonicalDocument`, treating any miss as unattributed. (c) Score against
`CanonicalDocument` (primary) and `CanonicalChunk` (downstream evidence/
chunk-alignment availability), and consult raw Docling debug JSON ONLY to
classify the ORIGIN of an already-established miss —
`parser_content_loss` (never reached Docling's own output) vs.
`mapper_loss` (reached Docling's raw output but the Stage 5A mapper did
not carry it into `CanonicalDocument`).

### Decision
(c).

### Rationale
`CanonicalDocument`/`CanonicalChunk` are what every downstream consumer
(chunker, future retrieval projections) actually sees — scoring against
anything else would produce a "baseline" nobody's real pipeline uses.
Raw Docling output is real, useful *evidence* for attributing a miss
(distinguishing a Docling capability gap from a Stage 5A mapper bug), but
must never become the scored representation itself, or the evaluator
would silently start measuring Docling instead of this project's output.

### Trade-offs and consequences
`mapper_loss` may only ever be assigned when `raw_docling_references` is
non-empty — enforced as a `MissRecord` Pydantic invariant, not just
convention (`src/ingestion_bench/evaluation/model.py::MissRecord`), so a
future evaluator change cannot silently claim `mapper_loss` on suspicion
alone. When no raw debug artifact is available at all, the evaluator
records `failure_class="unresolved"`, `confidence="unresolved"` rather
than guessing. Raw-Docling-JSON parsing is confined to
`classification.py` and is read-only, debug-evidence use only.

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`src/ingestion_bench/evaluation/classification.py` (the only module that
reads raw Docling debug JSON); `model.py::MissRecord._validate_mapper_loss_has_raw_evidence`;
`tests/test_evaluation_models.py::test_miss_record_mapper_loss_requires_raw_docling_reference`;
real measured example: `reports/stage6a_docling_miss_ledger.json`'s two
`mapper_loss` entries (DOCX/PPTX caption text present as a paragraph, not
linked — both carry a real `#/texts/N` raw Docling reference).

---

## D-042 — The Stage 6A evaluator's gold fact-to-chunk evidence-alignment catalog is the reusable retrieval-evaluation asset, not a byproduct

**Status:** Accepted
**Stage:** Stage 6A
**Date/commit:** Needs confirmation (assigned at Stage 6A implementation time)

### Problem
D-040 established the *principle* that vector/graph/wiki retrieval
projections must be evaluated against the same expected facts and
supporting chunks. Stage 6A needed to decide what that shared asset
actually IS, concretely, and how it is produced.

### Decision
The ingestion evaluator produces a gold fact-to-chunk evidence alignment
(`artifacts/stage6a/evidence_alignment.json`, one `EvidenceAlignment`
record per expected manifest fact that Stage 5A output could be matched
against) that will be reused, unmodified, by every future retrieval
projection's evaluation (Stage 6B onward) — this catalog, not the
scorecard or miss ledger, is the primary reusable output of Stage 6A.
Each entry carries the expected value/location, every matched canonical
element id / annotation id / chunk id, unit indexes, source references,
a `source_derived`/`model_derived` classification, and a coarse,
deterministically-assigned `expected_retrieval_difficulty` tag
(`direct`/`relational`/`multi_hop`/`consolidation`/`distractor_sensitive`)
— never an invented retrieval question (explicitly out of scope until
Stage 6B).

### Rationale
Building the evidence-alignment catalog as a first-class, independently
consumable artifact (rather than an internal implementation detail of the
scorecard) is what makes D-040's principle actually usable: Stage 6B can
build a retrieval benchmark query contract directly on top of this
catalog's `fact_id -> matched_chunk_ids` mapping without re-deriving
fact-to-evidence matching from scratch, and without re-reading the
manifest itself (retrieval-projection code must remain manifest-
independent too, same as adapters/canonical/chunking — see
`tests/test_stage6a_integration.py::test_evaluation_package_is_the_only_package_referencing_the_manifest`).

### Trade-offs and consequences
The catalog only contains entries for facts that were actually matched or
partially matched (`match_status="missing"` entries are recorded too, for
distractor identifiers specifically, but a fully-missed non-distractor
fact appears in the miss ledger, not the catalog, since there is no
evidence to align it to) — Stage 6B must treat catalog absence and
miss-ledger presence as two views of the same underlying fact set, not
merge them naively. The `expected_retrieval_difficulty` heuristic is
coarse and explicitly documented as such
(`evaluator.py::_difficulty_for`) — it is a reusable difficulty *tag*, not
a validated retrieval-question difficulty; Stage 6B may need to refine it
once real retrieval questions exist.

### Deferred questions or reconsideration trigger
Once Stage 6B designs the actual retrieval benchmark query contract, the
`expected_retrieval_difficulty` heuristic should be revisited against real
authored questions, not just this coarse fact-type-based tag.

### Implementation and evidence
`src/ingestion_bench/evaluation/model.py::EvidenceAlignment`;
`evaluator.py` (every `EvidenceAlignment(...)` construction site, plus the
`unit_indexes`/`source_references` backfill pass in `evaluate_fixture`);
`aggregation.py::build_evidence_alignment_catalog`;
`artifacts/stage6a/evidence_alignment.json` (77 real entries as of the
Stage 6A baseline run);
`tests/test_stage6a_report_generation.py::test_every_matched_expected_fact_has_an_evidence_alignment_entry_in_the_catalog`.

---

## D-043 — Stage 6A implementation deviations (short note)

**Status:** Accepted (record only — no reversible decision made)
**Stage:** Stage 6A
**Date/commit:** Needs confirmation (assigned at Stage 6A implementation time)

Three points raised during Stage 6A review that were not otherwise
captured in a persisted file, recorded here per that review:

1. **`caption_text_recall` was broadened mid-implementation.** The first
   pass matched only against real `CanonicalCaption` elements, which
   scored the known DOCX/PPTX "caption present as an unlinked paragraph"
   case as total content loss (`parser_content_loss`) — wrong, since the
   text genuinely is present. Fixed to match `CanonicalCaption` OR
   `CanonicalParagraph` text, so text recovery is scored independently of
   linkage (`caption_linkage_accuracy` covers linkage separately). See
   `evaluator.py::_score_pictures_captions`.
2. **`EvidenceAlignment.unit_indexes`/`source_references` are populated by
   a single backfill pass** in `evaluate_fixture` (looking up each matched
   element's own `unit_index`/`ProvenanceEntry.source_element_ref` after
   all alignments are collected), not threaded individually through each
   of the ~12 `EvidenceAlignment(...)` construction sites — simpler and
   less error-prone than repeating the same lookup at every site.
3. **Zero unresolved parser/mapper attribution.** Every one of the 24
   misses in the current baseline run (`reports/stage6a_docling_miss_ledger.json`)
   has `confidence` of `"certain"` or `"supported"` — none is
   `"unresolved"`. No `MissRecord` in this run needed the "no raw debug
   artifact available" fallback path
   (`classification.py::unresolved_classification`).

### Implementation and evidence
`src/ingestion_bench/evaluation/evaluator.py::_score_pictures_captions`,
`evaluate_fixture` (backfill pass); `reports/stage6a_docling_miss_ledger.json`
(zero `"confidence": "unresolved"` entries, verifiable directly by
inspection or `grep -c unresolved reports/stage6a_docling_miss_ledger.json`).

---

## D-044 — The gold evidence-alignment catalog is complete and occurrence-aware, never a matched-only summary

**Status:** Accepted
**Stage:** Stage 6A.1
**Date/commit:** Needs confirmation (assigned at Stage 6A.1 implementation time)

### Problem
Stage 6A's original evaluator had two related gaps caught in review:
(1) identifier occurrence recall was computed by counting every
boundary-safe appearance of an identifier GLOBALLY across the whole
document and capping the total at the manifest's declared occurrence
count -- this could not distinguish "every expected occurrence was found
where expected" from "some unrelated extra appearance happened to make
the total add up," and one observed occurrence could effectively satisfy
two different expected occurrences. (2) `artifacts/stage6a/evidence_alignment.json`
only ever contained an entry for a fact once it MATCHED -- a missing
expected fact (heading never found, table cell never found, identifier
occurrence never found) had no catalog entry at all, so a future
retrieval evaluation reading this catalog could not distinguish "this
fact was never ingested" from "this fact was ingested but is simply
absent from the catalog for an unrelated reason."

### Alternatives considered
For (1): (a) keep the global-count-and-cap approach, accepting the
ambiguity. (b) Treat every manifest-declared occurrence
(`identifiers.target_identifiers[*].occurrences[*]`) as its OWN
expectation (`<identifier_fact_id>_occ_<index>`), resolved via the
occurrence's own `source_fact` metadata to a SPECIFIC canonical element,
and matched one-to-one (a consumed span can never satisfy a second
expectation).
For (2): (a) keep catalog entries matched-only, relying on the separate
miss ledger for everything else. (b) Emit exactly one
`EvidenceAlignment` per expected manifest fact, always, with
`match_status` of `matched`/`partial`/`missing`/`not_applicable` --
`missing`/`not_applicable` entries carry empty evidence-id lists but
remain present.

### Decision
(b) for both.

### Rationale
Occurrence-level, source-fact-resolved matching is the only way to
actually prove "every expected mention was found in its expected place"
rather than "the right NUMBER of mentions exist somewhere" -- the two are
not the same claim, and only the former is useful evidence for a future
retrieval benchmark (D-042) that needs to know exactly which chunk
contains which occurrence. A complete catalog (matched AND missing AND
not_applicable) is what makes the catalog usable as the single source of
truth for "was this fact ingested at all" -- a future retrieval-quality
evaluation (Stage 6B+) must be able to tell ingestion loss apart from
retrieval loss, which requires knowing a fact was expected in the first
place, not just that it happened to match something.

### Trade-offs and consequences
The evidence-alignment catalog roughly doubled in size (77 -> 147 entries
in the real baseline run) since every table cell, identifier occurrence,
and previously-uncatalogued fact type now gets its own record. Building
the occurrence-level resolution required computing text/heading/caption
matches BEFORE identifier scoring (a real ordering dependency introduced
into `evaluate_fixture`) so identifier occurrences can resolve their
`source_fact` against already-matched elements. Extra (unconsumed)
identifier occurrences beyond every expected occurrence's one-to-one
resolution are recorded as `UnexpectedObservation`s, never silently
absorbed into a different expectation's count.

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`src/ingestion_bench/evaluation/evaluator.py::_score_identifiers` (occurrence
resolution, one-to-one span consumption), every `_score_*` function
(complete alignment emission on both the matched and missing paths);
`tests/test_evaluation_identifier_occurrence.py` (the exact "missing
occurrence not satisfied by an extra distractor occurrence" regression
scenario); `tests/test_stage6a_report_generation.py::test_every_matched_expected_fact_has_an_evidence_alignment_entry_in_the_catalog`.

---

## D-045 — mapper_loss for a missing RELATIONSHIP requires explicit raw evidence of that relationship, never inferred from text presence alone

**Status:** Accepted
**Stage:** Stage 6A.1
**Date/commit:** Needs confirmation (assigned at Stage 6A.1 implementation time)

### Problem
Stage 6A's original caption-linkage attribution classified the DOCX/PPTX
"caption text present as an unlinked paragraph" case as `mapper_loss`
whenever the matched paragraph had ANY raw Docling `self_ref` -- but a
`self_ref` only proves the TEXT reached Docling's output, it says nothing
about whether Docling itself ever exposed the CAPTION RELATIONSHIP for
the Stage 5A mapper to preserve. Direct inspection of real raw Docling
debug JSON confirmed this was a real misclassification: for both DOCX and
PPTX, the raw picture object's own `captions` list is `[]` -- Docling
never exposed the relationship at all for these formats -- yet the
original evaluator reported `mapper_loss` (implying the mapper's fault)
for both.

### Alternatives considered
(a) Keep classifying any present-but-unlinked text as `mapper_loss` when
a `self_ref` exists, accepting the imprecision. (b) Attribute the missing
relationship by inspecting the SPECIFIC raw relation field directly
(e.g. `raw_debug["pictures"][i]["captions"]`) for a reference to the
child element's own `self_ref`: `mapper_loss` only if that field
explicitly contains it (Docling exposed the relationship, mapper dropped
it); `parser_relationship_loss` if the field is empty or absent (Docling
never exposed it to begin with).

### Decision
(b).

### Rationale
A raw `self_ref` is evidence of content existence, not of relationship
exposure -- conflating the two systematically over-blames the Stage 5A
mapper for gaps that are actually genuine Docling parser limitations.
Verified directly against real data before implementing: `docling_raw/PARITY_001_pdf.json`'s
picture object has `"captions": [{"$ref": "#/texts/10"}]` (Docling DOES
expose it for PDF, and the mapper DOES preserve it there -- no miss at
all for PDF); `docling_raw/PARITY_001_docx.json`/`PARITY_001_pptx.json`'s
picture objects both have `"captions": []` (Docling never exposes it for
either format) -- so both are correctly `parser_relationship_loss` after
this fix, not `mapper_loss`.

### Trade-offs and consequences
`classification.py::classify_relationship_absence` is a new, general
attribution helper (parent collection, parent self_ref, relation field,
child self_ref) reusable for any future relationship-loss attribution
(table structure, list hierarchy, etc.), not just captions. When the
parent object itself cannot be found in raw Docling at all, the result is
`("parser_relationship_loss", "unresolved", [])` -- never guessed as
`mapper_loss` for lack of evidence either way.

### Deferred questions or reconsideration trigger
Heading-level/list-hierarchy/table-structure misses already used
`parser_classification_loss`/`parser_structure_loss`/`parser_relationship_loss`
(never `mapper_loss`) even before this patch, and were verified directly
against real raw Docling data to confirm those classifications remain
correct (e.g. PPTX heading text's raw Docling `label` is `"paragraph"`,
never a heading-classifying label) -- no further correction was needed
for those categories in this pass.

### Implementation and evidence
`src/ingestion_bench/evaluation/classification.py::classify_relationship_absence`;
`evaluator.py::_score_pictures_captions` (caption-as-paragraph branch);
real measured result: both DOCX/PPTX caption-linkage misses in
`reports/stage6a_docling_miss_ledger.json` now read
`"failure_class": "parser_relationship_loss"` (previously `"mapper_loss"`).

---

## D-046 — expected_retrieval_difficulty stays unclassified (None) throughout Stage 6A

**Status:** Accepted (closes D-042's own deferred reconsideration trigger)
**Stage:** Stage 6A.1
**Date/commit:** Needs confirmation (assigned at Stage 6A.1 implementation time)

### Problem
Stage 6A's original `EvidenceAlignment.expected_retrieval_difficulty`
assigned a heuristic tag (e.g. "an identifier with more than one
occurrence is multi_hop") directly from ingestion-side signals. D-042
itself flagged this as coarse and only provisionally acceptable,
"revisited... once real retrieval questions exist." Review confirmed this
inference was premature: occurrence count is an ingestion-side property,
not a property of any actual retrieval question, and assigning a
difficulty label that looks authoritative invites Stage 6B to treat it as
validated when it was never grounded in a real question.

### Decision
`expected_retrieval_difficulty` is now `RetrievalDifficulty | None`,
always `None` in Stage 6A. No heuristic inference of any kind runs in
this stage. Stage 6B assigns real difficulty to concrete benchmark
questions built on top of this catalog.

### Rationale
An unclassified field is honest about what Stage 6A actually knows
(nothing about retrieval difficulty, by design -- it doesn't build
retrieval questions); a coarse heuristic field looks like evidence but
isn't. This directly closes the reconsideration trigger D-042 itself
recorded.

### Trade-offs and consequences
The evidence-alignment catalog carries one less dimension of (previously
speculative) information; Stage 6B must design its own difficulty
assignment from real questions rather than inheriting anything from
Stage 6A.

### Deferred questions or reconsideration trigger
None -- Stage 6B owns this entirely from here.

### Implementation and evidence
`src/ingestion_bench/evaluation/model.py::EvidenceAlignment.expected_retrieval_difficulty`;
`evaluator.py::_alignment` (always passes `None`); the former
`_difficulty_for` heuristic function was deleted entirely, not merely
unused; `tests/test_stage6a_integration.py::test_no_evidence_alignment_ever_has_a_retrieval_difficulty_assigned`.

---

## D-047 — Identifier-occurrence miss ATTRIBUTION is scoped to that occurrence's own expected context, never a whole-document raw-text search

**Status:** Accepted
**Stage:** Stage 6A.2
**Date/commit:** Needs confirmation (assigned at Stage 6A.2 implementation time)

### Problem
D-044/Stage 6A.1 made identifier occurrence *matching* (against
CanonicalDocument) occurrence-aware and one-to-one, but the occurrence
*miss attribution* path (`classify_identifier_absence(identifier,
raw_text_blob)`, used only after a matching failure to decide
`mapper_loss` vs. `parser_content_loss`) still searched the identifier
anywhere in the WHOLE-document raw text blob. Direct inspection of real
data proved this was a real bug: for both DOCX and PPTX,
`ID_004_occ_2` (source_fact `VF_NODE_003`, expected only inside the
parity image's own OCR content) was classified `mapper_loss` citing
`#/texts/4` (the unrelated body paragraph P_004) and the caption's own
text item as "evidence" -- neither is the occurrence's own expected
context. Both DOCX and PPTX's raw picture object actually has
`"children": []` -- Docling captured zero OCR text for that picture in
either format -- so the correct classification is `parser_content_loss`.

### Alternatives considered
(a) Keep the whole-document search, accepting that an unrelated mention
elsewhere can manufacture a false `mapper_loss`. (b) Resolve the specific
raw Docling item(s) relevant to THIS occurrence's own `source_fact`
before searching: a matched paragraph/heading/caption element's own
`source_element_ref`; an unmatched one's raw counterpart identified by
CONTENT (its own expected text, never the identifier); a visual-node/OCR
occurrence's own picture's raw `texts[].parent.$ref` children only.
Search only within that scoped set.

### Decision
(b).

### Rationale
An identifier's mere presence somewhere in the document is not evidence
about a SPECIFIC expected occurrence's own context -- the whole point of
occurrence-level expectations (D-044) is that each occurrence is tied to
one place. Attribution must honor that same discipline: `mapper_loss` may
only be assigned when the occurrence's OWN expected context, in raw
Docling, explicitly contains the identifier and the mapper failed to
carry it forward -- otherwise it's `parser_content_loss` (context
resolved, raw evidence absent there) or `unresolved` (context itself
couldn't be resolved in raw Docling at all).

### Trade-offs and consequences
`evaluator.py::_score_identifiers` now requires `raw_debug`,
`source_ref_by_id` (element_id -> raw self_ref), `fact_text_by_id`
(paragraph/heading/caption fact_id -> expected text), and
`matched_picture_ids` -- all computed earlier in `evaluate_fixture` than
before (the element-id -> self_ref mapping used to be built only in the
post-hoc alignment backfill pass; it is now built before identifier
scoring and reused, unchanged, by that same backfill pass). Real
baseline impact: the two DOCX/PPTX `ID_004_occ_2` misses changed from
`mapper_loss` to `parser_content_loss` (total miss count unchanged at 56,
since these were already counted as misses -- only the classification,
and therefore the parser-vs-mapper attribution story, changed).

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`src/ingestion_bench/evaluation/classification.py::classify_identifier_occurrence_absence`
(new); `evaluator.py::_scoped_raw_items_for_occurrence` (new); real raw
Docling verification (`artifacts/stage5a/docling_raw/PARITY_001_{docx,pptx}.json`
`pictures[0].children == []`);
`tests/test_evaluation_identifier_occurrence.py::test_missing_visual_node_occurrence_is_not_mapper_loss_from_an_unrelated_paragraph_mention`
(the exact required regression) and
`::test_missing_visual_node_occurrence_is_mapper_loss_when_picture_child_ocr_explicitly_has_it`
(contrast case); real measured result in
`reports/stage6a_docling_miss_ledger.json`.

---

## D-048 — unsupported_visual_claim_absence is scored per claim, via structured matching, never from the mere presence of any other visual fact

**Status:** Accepted
**Stage:** Stage 6A.2
**Date/commit:** Needs confirmation (assigned at Stage 6A.2 implementation time)

### Problem
Stage 6A's original `unsupported_visual_claim_absence` used
`any(a.annotation_type == "visual_fact" for a in document.annotations)`
as a BLANKET signal: if ANY VisualFactAnnotation existed at all, EVERY
unsupported claim in the fixture was marked as incorrectly asserted
(`missing`). A single correct visual fact (e.g. "Q4 pass rate = 95%")
would therefore have wrongly failed an unrelated unsupported claim (e.g.
"Q2 pass rate exceeded 95%, which is false") even though that specific
false claim was never actually asserted.

### Alternatives considered
(a) Keep the blanket check, since path A never produces
VisualFactAnnotation today so the bug is currently latent/unobservable in
the real baseline. (b) Match each unsupported claim's OWN structured
content (`fact_type`/`subject`/`relation`/`object`/`value`/`unit` --
exactly the shape both `unsupported_claims` and `visual_facts` share in
the manifest, and exactly `VisualFactAnnotation`'s own field shape)
against actual `VisualFactAnnotation` output; only a structural match of
THAT claim's own content counts as a failure for it.

### Decision
(b).

### Rationale
The Stage 6A.1 gold-catalog discipline (D-044) already requires per-fact
evidence, not aggregate signals; the same discipline belongs here. This
bug is latent only because path A never produces `VisualFactAnnotation` --
but the evaluator's OWN internal correctness must not depend on that
being true forever (Stage 8A's vision-enrichment path will produce
these annotations for real, and the evaluator must already be correct
before that happens, not patched reactively then).

### Trade-offs and consequences
`evaluator.py::_visual_fact_matches_claim` is a new structured-equality
helper (numeric `value` compared with a `float()` fallback to normalized
string comparison for non-numeric values). No change to the real Stage
6A/6A.1/6A.2 baseline numbers (`unsupported_visual_claim_absence` remains
100% for `STRESS_CHART_001` in every format, since path A still produces
zero `VisualFactAnnotation`s) -- this is a forward-looking correctness
fix, verified by new unit tests using hand-built `VisualFactAnnotation`
instances rather than real Stage 5A output (which cannot exercise this
path yet).

### Deferred questions or reconsideration trigger
Revisit once Stage 8A's vision-enrichment path actually produces
`VisualFactAnnotation` output and this metric's real baseline value can
move off 100% for the first time -- at that point, confirm the per-claim
match is discriminating correctly against real (not hand-built) model
output.

### Implementation and evidence
`src/ingestion_bench/evaluation/evaluator.py::_visual_fact_matches_claim`,
`_score_visual_facts_and_unsupported_claims` (rewritten);
`tests/test_evaluation_visual_claims.py` (new file; the exact two
required scenarios -- a correct supported fact not failing an unrelated
claim, and the claim itself being present failing only that claim -- plus
a third two-claims-one-asserted test).

---

## D-049 — MetricResult.supporting_misses must resolve to a real MissRecord with the same fixture, metric, and fact_id -- never an id borrowed from a different metric's bookkeeping

**Status:** Accepted
**Stage:** Stage 6A.2
**Date/commit:** Needs confirmation (assigned at Stage 6A.2 implementation time)

### Problem
`provenance_coverage_overall`/`provenance_bbox_coverage_overall`'s
`supporting_misses` were populated from the UNION of every per-category
accumulator's misses (e.g. `provenance_coverage_heading`'s misses,
`provenance_coverage_paragraph`'s misses, ...) -- element ids that only
ever appear in `MissRecord`s carrying the PER-CATEGORY metric name (e.g.
`metric="provenance_coverage_heading"`), never
`metric="provenance_coverage_overall"`. A reader following
`supporting_misses` on the overall metric to find its `MissRecord` would
find nothing under that exact (metric, fact_id) pair. Auditing the rest
of the evaluator for the same pattern also found two smaller, currently-
dormant instances: `_score_tables`'s "no candidate table" branch recorded
`table_cell_text_recall` misses in the accumulator without ever emitting
the corresponding per-cell `MissRecord`s; `column_reading_order_correct`
and `no_invented_diagram_relationships` (both built via the raw `_metric()`
helper, not `_MetricAcc`) never populated `supporting_misses` at all even
when a real, already-recorded miss existed for them.

### Alternatives considered
For the provenance overall metrics: (a) duplicate every per-category
`MissRecord` a second time under the overall metric name (redundant
double-bookkeeping). (b) Reference only the overall metric's OWN single
summary `MissRecord` (already created, one per overall metric, when a
deficit exists) in `supporting_misses`.

### Decision
(b) for the provenance overall metrics; the two table/structural-stress
gaps found during the same audit were fixed directly (added the missing
`MissRecord`s and/or referenced the ones that already existed).

### Rationale
Referential integrity of `supporting_misses` is what makes the miss
ledger trustworthy as a navigable index, not just an aggregate count --
"look up this id to find out why" must always resolve. Duplicating every
per-category record under the overall metric name too would have worked
but adds bookkeeping surface for no benefit when a single summary record
already exists and is the natural target.

### Trade-offs and consequences
No change to the real Stage 6A.1 -> 6A.2 total miss count (both
provenance-overall gaps and the table/structural-stress gaps were latent
correctness bugs, not baseline-affecting misclassifications -- the table
"no candidate table" and reading-order/diagram gaps never actually
trigger against the real 9 fixtures). The referential-integrity test
(`test_supporting_misses_on_metric_result_reference_real_miss_records`)
was strengthened from "supporting_misses is non-empty" to "every id in
supporting_misses resolves to an actual MissRecord with the same
fixture/metric/fact_id," which would have caught this bug directly had
it existed at Stage 6A.1 time.

### Deferred questions or reconsideration trigger
None -- the strengthened test now runs against the real baseline on
every future change to this module, so a regression here would be caught
immediately.

### Implementation and evidence
`src/ingestion_bench/evaluation/evaluator.py::_score_provenance` (overall
metrics' `misses=` now reference only their own summary MissRecord's
fact_id), `_score_tables` (added the missing per-cell MissRecords in the
no-candidate-table branch), `_score_structural_stress`
(`column_reading_order_correct`/`no_invented_diagram_relationships` now
populate `supporting_misses`);
`tests/test_stage6a_integration.py::test_supporting_misses_on_metric_result_reference_real_miss_records`
(strengthened).

---

## D-050 — evaluation_content_hash is a separate deterministic content identity from run_id/input_bundle_hash, and every hash-shaped field is now validated as lowercase 64-hex

**Status:** Accepted
**Stage:** Stage 6A.2
**Date/commit:** Needs confirmation (assigned at Stage 6A.2 implementation time)

### Problem
`run_id`/`input_bundle_hash` (D-044-era Stage 6A.1 fields) identify WHICH
INPUTS a run scored, not what it CONCLUDED -- two runs of a genuinely
non-deterministic evaluator over the same inputs would share the same
`run_id` even if their actual metrics/misses/alignments differed. There
was no separate identity for "this run's actual output content," and no
field in this module validated that a value claiming to be a SHA-256
digest actually was one (wrong length, uppercase, or non-hex characters
were all silently accepted).

### Alternatives considered
For content identity: (a) leave `run_id`/`input_bundle_hash` as the only
identity fields, relying on separate determinism tests to catch output
drift. (b) Add `evaluation_content_hash`, a SHA-256 over every STABLE
`EvaluationRun` field (`input_bundle_hash`, `evaluator_version`, every
fixture result, `aggregate`) excluding `generated_at` (mutable
runtime/report metadata) and the hash field itself.
For hash validation: (a) leave hash-shaped fields as unconstrained `str`.
(b) Validate every hash-shaped field (`run_id`, `input_bundle_hash`,
`evaluation_content_hash`, `manifest_sha256`, `stage5a_results_sha256`,
every `OperationalEvidence` artifact hash when present,
`canonical_document_hash`) as a lowercase 64-character hex string.

### Decision
(b) for both.

### Rationale
`input_bundle_hash` answers "did the inputs change"; `evaluation_content_hash`
answers "did the conclusions change" -- these are genuinely different
questions (a non-deterministic bug could change the second while leaving
the first identical), and Stage 6A's own determinism-verification
practice (re-running the evaluator and comparing outputs, established
since Stage 5A.1/D-039) deserves a first-class field to compare against
directly rather than diffing entire JSON files. Validating every hash
field as real lowercase hex turns a malformed identity from a silent,
undetected data-quality issue into an immediate, loud `ValidationError`
at construction time -- consistent with this project's "fail loud, never
silently accept malformed identity" discipline used everywhere else
(portable fixture-ref validation, mapper_loss's raw-evidence
requirement, D-046's null-difficulty enforcement).

### Trade-offs and consequences
Several existing tests across `test_evaluation_aggregation.py` and
`test_stage6a_report_generation.py` used non-hex placeholder strings
(`"m" * 64`, `"s" * 64`) for `manifest_sha256`/`stage5a_results_sha256` --
all corrected to valid hex placeholders (`"1" * 64`, `"2" * 64`) as part
of this change; this is a test-only correction, not a behavior change.
`run_id` is itself a SHA-256 hex digest already (D-044-era), so this
validation is enforcement of an existing invariant, not a new one for
that field.

### Deferred questions or reconsideration trigger
None.

### Implementation and evidence
`src/ingestion_bench/evaluation/aggregation.py::_compute_evaluation_content_hash`
(new), `build_evaluation_run` (computes and threads it through);
`src/ingestion_bench/evaluation/model.py::_validate_sha256_hex` (new
shared helper), `EvaluationRun._validate_hash_fields`,
`OperationalEvidence._validate_hash_fields`;
`tests/test_evaluation_aggregation.py` (six new
`test_evaluation_content_hash_*` tests: stability, `generated_at`
insensitivity, and sensitivity to a metric/evidence-alignment/input-
artifact/evaluator-version change); `tests/test_evaluation_models.py`
(new parametrized malformed-hash-rejection tests for every validated
field); real measured `evaluation_content_hash` in
`reports/stage6a_docling_baseline_results.json`.
