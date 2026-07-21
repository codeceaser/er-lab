# Ingestion Benchmark Contract — Approved (Stage 1, frozen alongside manifest v1.2.1)

Self-contained companion to `reference_manifest.json`. Authoritative source for
Stage 2 implementation.

Status: **approved — frozen**, with one post-freeze amendment applied during Stage 2
implementation: `CanonicalDocument.manifest_version`/`manifest_sha256` were removed
and replaced with a separate `BenchmarkBinding` model (section 3a), to keep three
responsibilities strictly separate — **`CanonicalDocument` says what was extracted;
`reference_manifest.json` says what should have been extracted; the evaluator
compares the two.** Neither `CanonicalDocument` nor `ExtractionRun` may ever carry
manifest identity, and `stable_canonical_hash()` must never depend on benchmark
metadata. Implementation-time clarifications (annotation discriminated union,
`CanonicalUnit` coordinate fields + bbox-coordinate-system validation, precise
portability/hashing rules, and this section's structural-validator/binding
amendment) are folded into the field inventory below rather than kept as a separate
diff, since this document is the single source of truth for Stage 2.

A further **Stage 2.1 validation-hardening patch** added stricter field-level and
cross-field constraints throughout (no fields, no architecture changed — same field
inventory as above, just tighter validation): `BoundingBox`/`NormalizedBoundingBox`
geometry ordering + finiteness; `CanonicalUnit.unit_index`/`width`/`height` bounds
and document-wide uniqueness; `order_index`/`heading.level`/`indent_level` bounds;
`CanonicalTable`/`CanonicalTableCell` primitive bounds; strict lowercase-hex SHA-256
format on every hash field (`CanonicalDocument.source_sha256`,
`CanonicalPicture.content_sha256`, `BenchmarkBinding.canonical_document_hash`,
`BenchmarkBinding.manifest_sha256`); `source_relative_path`/`artifact_ref` now also
reject empty strings and `..` traversal, and `source_filename` must be a basename;
`AnnotationBase` gained `unit_index >= 0`, `confidence` range-checking, and
`extra="forbid"`; fixed per-type `derivation` invariants (`OcrAnnotation` is always
`"extracted"`; `VisibleTextAnnotation`/`ImageDescriptionAnnotation`/
`VisualFactAnnotation` are always `"model_derived"`; `DiagramNodeAnnotation`/
`DiagramEdgeAnnotation` may be either); `IdentifierAnnotation.start_char`/`end_char`
must be both-or-neither, half-open (`text[start_char:end_char]`); `block_id`/
`table_id`/`picture_id` now share one uniqueness namespace (an `Annotation.
target_ref` can point at any of them); `ProvenanceEntry.element_id` must resolve to
a real core element or annotation id; a new `stable_element_id()` helper
(canonical-serialization + SHA-256, never `uuid4()`/built-in `hash()`) is available
for adapters to generate every deterministic id from.

---

## 1. Primary benchmark paths

- **A — `DOCLING_STANDARD_LOCAL`**: Docling's standard local pipeline only. No VLM,
  no vision enrichment. Text/layout/reading-order, native DOCX/PPTX tables, PDF
  TableFormer tables, picture extraction, OCR (RapidOCR), picture classification,
  captions, provenance. Produces `CanonicalPicture` records with no description.
- **B — `DOCLING_STANDARD_LOCAL` + selective OpenAI vision enrichment**: path A's
  output, then a separate `OpenAIVisionEnricher` pass over extracted
  `CanonicalPicture`s only (never whole pages, never tables).
- **C — OpenAI vendor-native document input**: the original file goes to OpenAI
  directly, mapped to the canonical model.
- **(Optional, deferred) D — local Granite Vision enrichment**: same
  `VisionEnricher` protocol as B, via `GraniteVisionEnricher`. Not required for the
  initial POC.

## 2. `VisionEnricher` protocol

```python
class VisionEnricher(Protocol):
    def enrich(
        self,
        picture: CanonicalPicture,
        caption: str | None,
        surrounding_text: str | None,
    ) -> list[Annotation]: ...
```

`docling_adapter.py` (path A) has **no dependency on any `VisionEnricher`**.
Enrichment is a separate, composable stage applied after extraction.
Implementations: `NoOpVisionEnricher` (path A — returns `[]`),
`OpenAIVisionEnricher` (path B), `GraniteVisionEnricher` (optional/deferred, path D).

**Table extraction is never routed through vision enrichment**, in any path.

### Structured enrichment schema

```
VisionEnrichmentResult:
  picture_class: str | None
  visible_text: list[str]              # multimodal model's own text reading —
                                        # NOT an OCR-engine result
  nodes: list[{node_id, label}]
  edges: list[{source_node_id, target_node_id, label, directed}]
  visual_facts: list[VisualFact]
  summary: str                          # free prose — human review ONLY, NEVER
                                        # scored deterministically
  uncertainties: list[str]
```

```
VisualFact:
  fact_type: Literal["numeric", "comparative", "categorical", "other"]
  subject: str
  relation: str                         # e.g. "equals", "greater_than", "less_than"
  object: str | None                    # for comparative facts
  value: float | str | None             # for numeric facts
  unit: str | None
  raw_text: str
```

### Mapping to Annotations

| Schema field | Annotation type |
|---|---|
| `picture_class` | `PictureClassAnnotation` |
| `visible_text` | `VisibleTextAnnotation` (**not** `OcrAnnotation`) |
| `nodes` | `DiagramNodeAnnotation` |
| `edges` | `DiagramEdgeAnnotation` |
| `visual_facts` | `VisualFactAnnotation` |
| `summary` | `ImageDescriptionAnnotation` (excluded from deterministic scoring) |
| `uncertainties` | `UncertaintyAnnotation`, one per caveat string |

Every annotation produced this way: `derivation="model_derived"`, carries its own
`target_ref`, `unit_index`, and `bbox` directly.

`OcrAnnotation` is reserved for actual OCR engines (RapidOCR / Docling's OCR
pipeline). `VisibleTextAnnotation` is for a multimodal model's own reading of an
image — kept distinct so metrics don't conflate the two error profiles.

## 3. Portability and identity rules (new this revision)

### Stable paths must be portable, not absolute

`CanonicalDocument` and `CanonicalPicture` must never contain an absolute
filesystem path — the stable, hashed document must be reproducible/comparable
regardless of which machine or directory it was processed on. Absolute runtime
paths belong only in `ExtractionRun.raw_artifact_refs` (volatile, machine-specific,
never hashed):

- `CanonicalDocument.source_filename: str` — e.g. `"PARITY_001.pdf"`
- `CanonicalDocument.source_relative_path: str` — relative to the fixtures root,
  e.g. `"parity/PARITY_001.pdf"` (not an absolute `C:\...` path)
- `CanonicalDocument.source_sha256: str` — hash of the source file's bytes
- `CanonicalDocument.manifest_sha256: str` — hash of the exact manifest content
  this document's expected facts correspond to (in addition to the human-readable
  `manifest_version`, for exact pinning even if a version string were reused)
- `CanonicalPicture.content_sha256: str` — hash of the picture's own image bytes
- `CanonicalPicture.artifact_ref: str` — relative/portable reference to where the
  picture bytes are stored (e.g. a path relative to the run's `artifacts/` root, or
  a content-addressed `sha256:<hash>` reference) — **never** an absolute path

### Deterministic canonical IDs

`block_id`, `table_id`, `picture_id`, `annotation_id`, and `node_id` (section 5)
must be **deterministically derived** from stable identity components — `doc_id`,
`unit_index`, `order_index`, element type, and (for annotations) `target_ref` +
`extraction_method` + an occurrence index — **never** `uuid4()` or other random
generation. Two runs of a deterministic parser over the same input must produce
byte-identical ids. Concretely: each id is a stable hash (or direct string
composition) of its identity-component tuple, e.g. conceptually
`block_id = stable_hash((doc_id, unit_index, order_index, block_type))` — the
precise hash function/truncation is a Stage 2 implementation detail, but the input
components and the "no randomness" rule are fixed here.

`run_id` (on `ExtractionRun`) **may remain random** (`uuid4()` is fine) — it is
run-identifying, not document-identifying, and `ExtractionRun` is excluded from
`stable_canonical_hash` entirely.

### `stable_canonical_hash` requirements

Must use **canonical serialization**: deterministic key ordering (e.g. sorted
keys), fixed float formatting, no non-deterministic whitespace — then SHA-256 of
that serialization. Operates only over `CanonicalDocument`'s fields (never
`ExtractionRun`), and only over the now-portable path fields above (never an
absolute path, which would make the hash machine-dependent).

## 4. Diagram node identity fix

`DiagramNodeAnnotation` (extends the `Annotation` base, section 6) now has its own
identity, not just a label:
- `node_id: str` — stable, deterministic (section 3)
- `label: str`
- `node_bbox: BoundingBox | None`

`DiagramEdgeAnnotation.source_node_id` / `target_node_id` **must resolve to a real
`node_id`** from a `DiagramNodeAnnotation` in the same extraction run — not to a
raw label string. (Matching extracted edges against manifest ground-truth edges,
which are keyed by manifest `fact_id` rather than a runtime `node_id`, is exactly
the "edge matching by normalized node labels" open item in section 7 — the
runtime identity is now unambiguous; how it's *compared back to the manifest* is
still open.)

## 5. `ProvenanceEntry` extended

- `element_id: str`, `unit_index: int`, `order_index: int | None`,
  `bbox: BoundingBox | None` (unchanged)
- `z_order: int | None` — **new**, stacking order where the source format exposes
  one (e.g. PPTX shape z-order) — required to represent the
  `pptx_overlapping_textboxes` stress fixture, whose manifest ground truth already
  declares `z_order` per text box
- `source_element_ref: str | None` — **new**, the parser-native reference/id for
  the source element (e.g. Docling's internal element ref, or a python-pptx shape
  id), preserved for audit/debugging even though it's parser-specific
- `source_locator: dict | None` — **new**, free-form, parser-namespaced locator
  bag for anything not covered by the fixed fields (e.g.
  `{"pptx_shape_id": 12, "slide_id": 3}`)

## 6. `IdentifierAnnotation` extended

- `raw_text: str`, `normalized_value: str` (unchanged)
- `start_char: int | None` — **new**
- `end_char: int | None` — **new**

Character offsets within the source block's text, needed to distinguish multiple
occurrences of the same identifier within one block (a block-level match alone is
ambiguous if an identifier appears twice in the same paragraph). Computed at
extraction time — not manifest ground truth (offsets depend on exact rendering,
which varies by format, so they're not meaningfully pre-declarable per source).

## 7. Remote inference call tracking (new — separate from `ModelArtifact`)

`ModelArtifact` (unchanged from before) stays reserved for **locally stored/invoked
model artifacts only** (path A's Docling models; path D's Granite Vision if
revisited). A new, separate record covers remote API calls (paths B and C):

```
RemoteInferenceCall:
  provider: str            # e.g. "openai"
  model_id: str
  prompt_version: str | None
  request_id: str
  input_mode: str          # e.g. "file_upload" | "inline_content" | "vision_picture_crop"
  token_usage: dict | None
  elapsed_seconds: float
```

`ExtractionRun.remote_inference_calls: list[RemoteInferenceCall]` — one entry per
remote call made during that run (path B: one per enriched picture via
`OpenAIVisionEnricher`; path C: one or more for the whole-document OpenAI adapter
call). Never contains the API key — same rule as everywhere else in this project.

## 8. Complete canonical model field inventory

### `CanonicalDocument` (stable — hashed, never includes run OR benchmark metadata)
`doc_id: str`, `source_format: Literal["docx","pdf","pptx"]`,
`source_filename: str`, `source_relative_path: str`, `source_sha256: str`,
`units: list[CanonicalUnit]`,
`headings: list[CanonicalHeading]`, `paragraphs: list[CanonicalParagraph]`,
`list_items: list[CanonicalListItem]`, `captions: list[CanonicalCaption]`,
`tables: list[CanonicalTable]`, `pictures: list[CanonicalPicture]`,
`annotations: list[Annotation]`, `provenance: list[ProvenanceEntry]`

**No `manifest_version`/`manifest_sha256` here (removed post-freeze) — see
`BenchmarkBinding` (section 3a) for how a document's content is linked to a
manifest version without either side depending on the other.

Construction-time validators (all raise on violation, none silently repair):
unit_index references resolve to a real `CanonicalUnit` for every element
(regardless of whether it has a `bbox`); every `bbox`/`node_bbox` matches its
owning `CanonicalUnit`'s `coordinate_unit`/`coordinate_origin`;
`CanonicalCaption.target_picture_id` resolves to a real `CanonicalPicture`;
`CanonicalListItem.parent_block_id`, when set, resolves to another list item;
`Annotation.target_ref` resolves to a real block/table/picture;
`DiagramEdgeAnnotation.source_node_id`/`target_node_id` resolve to a real
`DiagramNodeAnnotation.node_id`; `CanonicalTableCell` row/col (+ spans) fit
within the table's `n_rows`/`n_cols`; `block_id`/`table_id`/`picture_id`/
`annotation_id`/`node_id` are each unique within the document (deterministic
IDs colliding indicates an upstream adapter bug).

### `BenchmarkBinding` (section 3a — separate from CanonicalDocument/ExtractionRun)
`doc_id: str`, `canonical_document_hash: str` (pins exact content, not just
`doc_id`), `run_id: str`, `manifest_version: str`, `manifest_sha256: str`. Lives
in `ingestion_bench/benchmark_binding.py`, outside `canonical/`, specifically so
neither `CanonicalDocument` nor `ExtractionRun` needs to know a manifest exists.
The evaluator (Stage 8) is the only consumer that needs all three of
`CanonicalDocument`, `reference_manifest.json`, and `BenchmarkBinding` at once.

### `CanonicalUnit`
`unit_index: int`, `unit_type: Literal["page","slide"]`, `width: float`,
`height: float`, `rotation: float = 0.0`,
`coordinate_unit: Literal["pt","px","emu"]` (**new**),
`coordinate_origin: Literal["top-left","bottom-left"]` (**new**) — every element's
`bbox` within this unit must use this unit's `coordinate_unit`/`coordinate_origin`;
`CanonicalDocument` validates this at construction time (any adapter must convert
bounding boxes into the owning unit's coordinate system *before* constructing
`CanonicalDocument` — the model itself never converts, it only validates and
rejects a mismatch).

### `BoundingBox`
`x0: float`, `y0: float`, `x1: float`, `y1: float`,
`coordinate_unit: Literal["pt","px","emu"]`,
`coordinate_origin: Literal["top-left","bottom-left"]`, `rotation: float = 0.0`,
`normalized: NormalizedBoundingBox | None`

### `NormalizedBoundingBox`
`nx0: float`, `ny0: float`, `nx1: float`, `ny1: float` (each in `[0, 1]`)

### `CanonicalHeading` / `CanonicalParagraph`
`block_id: str` (deterministic), `unit_index: int`, `order_index: int`,
`text: str`, `bbox: BoundingBox | None` (+ `level: int` on `CanonicalHeading`)

### `CanonicalListItem`
`block_id: str`, `unit_index: int`, `order_index: int`, `text: str`,
`bbox: BoundingBox | None`, `list_id: str`, `indent_level: int`,
`parent_block_id: str | None`

### `CanonicalCaption`
`block_id: str`, `unit_index: int`, `order_index: int`, `text: str`,
`bbox: BoundingBox | None`, `target_picture_id: str`

### `CanonicalTable` / `CanonicalTableCell`
`table_id: str` (deterministic), `unit_index: int`, `order_index: int`,
`bbox: BoundingBox | None`, `n_rows: int`, `n_cols: int`,
`cells: list[CanonicalTableCell]`; cell: `row: int`, `col: int`,
`row_span: int = 1`, `col_span: int = 1`, `text: str`, `is_header: bool`

### `CanonicalPicture`
`picture_id: str` (deterministic), `unit_index: int`, `bbox: BoundingBox | None`,
`content_sha256: str`, `artifact_ref: str` — portable (section 3): must not be an
absolute path (validated); must not embed a `run_id` (guaranteed by construction,
not by string validation — `CanonicalPicture`/`CanonicalDocument` have no `run_id`
field anywhere in their model tree, so one cannot leak in even by accident)

### `ProvenanceEntry`
`element_id: str`, `unit_index: int`, `order_index: int | None`,
`bbox: BoundingBox | None`, `z_order: int | None`, `source_element_ref: str | None`,
`source_locator: dict | None` (section 5)

### `ExtractionRun` (volatile — never hashed, one per adapter invocation)
`run_id: str` (random ok), `doc_id: str`, `path_id: Literal["A","B","C","D"]`,
`parser_name: str`, `parser_version: str`, `vision_enricher_name: str | None`,
`parser_config: dict`, `generated_at: datetime`, `elapsed_seconds: float`,
`warnings: list[str]`, `token_usage: dict | None`, `raw_artifact_refs: list[str]`
(absolute paths live here, not in `CanonicalDocument`), `canonical_document_hash: str`,
`model_artifacts: list[ModelArtifact]` (local models only),
`remote_inference_calls: list[RemoteInferenceCall]` (remote API calls only —
section 7)

### `ModelArtifact` (local models only)
`model_repo_id: str`, `revision: str`, `file_hashes: dict[str,str]`,
`license: str`, `local_artifact_path: str`, `downloaded_size_bytes: int`,
`inference_runtime: str`, `torch_dtype: str | None`,
`device: Literal["cpu","cuda","mps"]`, `prompt_version: str | None`

### `RemoteInferenceCall` (remote API calls only)
See section 7.

### `Annotation` (base — implemented as a Pydantic discriminated union, new)
`annotation_id: str` (deterministic), `annotation_type: str` (**new** — the
discriminator; each concrete subtype fixes this to its own `Literal`, e.g.
`Literal["identifier"]`), `target_ref: str`, `unit_index: int`,
`bbox: BoundingBox | None`, `derivation: Literal["extracted","model_derived"]`,
`extraction_method: str`, `confidence: float | None`. `Annotation` itself is
`Annotated[Union[<all concrete types below>], Field(discriminator="annotation_type")]`
— parsing a raw dict into the right concrete subtype is automatic and validated by
Pydantic, no manual dispatch needed, and an unrecognized `annotation_type` value is
rejected at validation time.

### Concrete annotation types (each fixes its own `annotation_type` Literal)
- **`IdentifierAnnotation`** (`annotation_type="identifier"`): `raw_text`,
  `normalized_value`, `start_char: int | None`, `end_char: int | None` (section 6)
- **`OcrAnnotation`** (`annotation_type="ocr"`): `text: str` — OCR-engine output only
- **`VisibleTextAnnotation`** (`annotation_type="visible_text"`): `text: str` —
  multimodal-model text reading only
- **`PictureClassAnnotation`** (`annotation_type="picture_class"`): `picture_class: str`
- **`VisualFactAnnotation`** (`annotation_type="visual_fact"`): `fact_type`,
  `subject`, `relation`, `object`, `value`, `unit`, `raw_text`
- **`DiagramNodeAnnotation`** (`annotation_type="diagram_node"`): `node_id: str`,
  `label: str`, `node_bbox: BoundingBox | None` (section 4)
- **`DiagramEdgeAnnotation`** (`annotation_type="diagram_edge"`): `source_node_id: str`,
  `target_node_id: str` (must resolve to real `node_id`s present in the same
  `CanonicalDocument` — validated), `label: str | None`, `directed: bool`
- **`ImageDescriptionAnnotation`** (`annotation_type="image_description"`):
  `description: str` — prose, human-review only, never deterministically scored
- **`UncertaintyAnnotation`** (`annotation_type="uncertainty"`): `note: str`
- **`SemanticClaimAnnotation`** (`annotation_type="semantic_claim"`): `claim: str` —
  free-form, path C document-level

## 8a. Portability and hashing precision (implementation clarification)

- `source_relative_path` uses **normalized POSIX-style separators** (`/`, never
  `\`) — validated; a Windows-style path with backslashes is rejected rather than
  silently normalized, so the adapter is responsible for producing a
  POSIX-style path in the first place.
- `artifact_ref` must be **stable** (deterministic given the same picture content
  and document identity — not, e.g., including a timestamp) and must **not**
  contain an absolute path (validated: rejected if it parses as an absolute POSIX
  or Windows path) or a `run_id` (guaranteed structurally, not by string matching —
  see the `CanonicalPicture` entry above).
- `manifest_sha256` is computed over the **canonical JSON serialization** of the
  frozen manifest: `json.dumps(data, sort_keys=True, separators=(",", ":"),
  ensure_ascii=False)`, UTF-8 encoded, then SHA-256. The hash function defensively
  excludes any `manifest_sha256` key from the input even if present, so it can
  never be computed over itself — and the frozen `reference_manifest.json` file
  does not embed its own hash (a hash of the manifest cannot include itself).

## 9. Evaluation metrics

### Text / structure (all paths)
text fact recall, unsupported fact count, table cell accuracy, row/column fidelity,
page/slide provenance coverage, canonical schema validity, normalized-output
stability across five runs, latency, token usage/cost where available, audit
artifact availability, reprocess/versioning ability.

### Identifier metrics
- Unique identifier recall (4 distinct target `normalized_value`s).
- Occurrence-level identifier recall (9 curated target occurrences).
- Identifier false-merge/false-normalization rate — exact token-boundary matching
  (`C-88` never matches inside `C-88a`), independently verified against the
  manifest text.
- With `start_char`/`end_char` now available, occurrence-level recall can also be
  scored per-position within a block, not just per-block — relevant if a future
  fixture repeats an identifier within one block (current manifest doesn't, but the
  schema now supports it).

### Visual / vision-enrichment metrics (path-dependent)
picture detection/extraction coverage, image provenance coverage, OCR accuracy
(`OcrAnnotation` vs. `expected_ocr_tokens`/`expected_ocr_text`), picture-class
accuracy, visual fact accuracy (`VisualFactAnnotation`, split by `fact_type`),
unsupported visual claims (structured types only, never `ImageDescriptionAnnotation`
prose), diagram structural capability (five independent sub-metrics — node-label
extraction, shape detection, connector detection, source/target linkage, direction
— exploratory, no capability assumed), structured-field stability across runs
(prose exempt), cold-load/warm-latency/peak-RAM-VRAM (generic to whichever
path/enricher is under test), total local storage footprint (path A's own models
by default).

## 10. Open items for Stage 2 (evaluator normalization decisions)

- Text normalization (case folding, whitespace, punctuation) before fact-text
  comparison.
- OCR token/phrase matching strategy (exact vs. fuzzy, phrase- vs. word-level).
- Exact identifier boundary rule is *decided* (section on identifier metrics) —
  open item is only its precise implementation (regex vs. tokenizer-based).
- Edge matching: runtime `node_id` identity is now unambiguous (section 4); how
  extracted edges are compared back to manifest ground truth (keyed by manifest
  `fact_id`) — by normalized label, position, or another key — is still open.
- Numeric tolerance for `VisualFactAnnotation.value` (exact vs. tolerance band).
- Precise deterministic-id hash function/truncation (section 3 fixes the input
  components and "no randomness" rule; the exact function is still open).
- Confirm Docling's actual picture-classifier label taxonomy against
  `expected_picture_class: "diagram"` / `"chart"` (currently provisional).
