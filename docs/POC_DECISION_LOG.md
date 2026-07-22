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
