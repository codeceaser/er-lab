# POC Status and Evidence — Enterprise Document-Ingestion Benchmark

Snapshot as of Stage 5A.2 (uncommitted at time of writing — see `git log`
for the actual commit once made) on branch `main`. Update this document
at the end of every subsequent stage — see the maintenance rules in
`docs/README.md`.

## Current test totals

**350 tests passed, 0 failed, 3 warnings** — full suite, all files
(`test_canonical_schema.py` 87, `test_canonical_hashing.py` 21,
`test_fixture_generation.py` 38, `test_chunking.py` 110,
`test_docling_standard_mapper.py` 28, `test_docling_standard_adapter.py`
10, `test_docling_standard_integration.py` 34, `test_adapters_base.py`
19, `test_run_docling_standard_report.py` 3). Full verbose output:
`reports/stage5a_pytest_output.txt` (this file is regenerated in place at
each Stage 5A/5A.1/5A.2 sub-stage, not renamed per sub-stage). The 3
warnings are pre-existing, unrelated deprecation warnings from Docling's
own dependencies (RapidOCR, docling-core's `ListItem` auto-grouping), not
from this project's own code. The Docling test files run real (small,
CPU) Docling conversions — they are not mocked. Progression across stages
(each report file is a real, committed snapshot):

| Report | Pass count |
|---|---|
| `reports/stage2_pytest_output.txt` | 108 |
| `reports/stage3_pytest_output.txt` | 136 |
| `reports/stage3_1_pytest_output.txt` | 146 |
| `reports/stage4_pytest_output.txt` | 185 |
| `reports/stage4_1_pytest_output.txt` | 220 |
| `reports/stage4_2_pytest_output.txt` | 244 |
| `reports/stage4_2a_pytest_output.txt` | 256 |
| `reports/stage5a_pytest_output.txt` (Stage 5A) | 322 |
| `reports/stage5a_pytest_output.txt` (Stage 5A.1) | 343 |
| `reports/stage5a_pytest_output.txt` (Stage 5A.2, current) | 350 |

## Stage status table

| Stage | Objective | Status | Key artifacts | Test evidence | Open items |
|---|---|---|---|---|---|
| 1 | Freeze benchmark contract + manifest | **Completed** | `fixtures/reference_manifest.json`, `fixtures/BENCHMARK_CONTRACT.md` | N/A (no runtime code at this stage) | Evaluator-normalization open items listed in `BENCHMARK_CONTRACT.md` section 10 (text normalization, OCR matching strategy, numeric tolerance, edge-label matching key) |
| 2 | Canonical model + hashing | **Completed** | `canonical/model.py`, `annotations.py`, `extraction_run.py`, `hashing.py`, `benchmark_binding.py` | `tests/test_canonical_schema.py` (87), `tests/test_canonical_hashing.py` (21); `reports/stage2_pytest_output.txt` | None known |
| 2.1 | Validation hardening | **Completed** | Same files as Stage 2 (patch, not new files) | Folded into the same 108 tests above | None known |
| 3 | Deterministic fixture generation | **Completed** | `fixtures/manifest_schema.py`, `diagram_image.py`, `generate_fixtures.py`, `fixtures/generated/*` (gitignored, regenerable) | `tests/test_fixture_generation.py`; `reports/stage3_pytest_output.txt` | None known |
| 3.1 | Fixture layout/geometry fixes | **Completed** | Same files as Stage 3 | `reports/stage3_1_pytest_output.txt` | None known |
| 4 | Canonical chunking layer | **Completed with follow-up** (hardened in 4.1/4.2/4.2a) | `chunking/model.py`, `chunker.py`, `renderers.py`, `__init__.py` | `reports/stage4_pytest_output.txt` | Superseded by 4.1/4.2/4.2a fixes below |
| 4.1 | Chunking hardening (heading audit trail, structural tables, revision lineage) | **Completed with follow-up** (further hardened in 4.2/4.2a) | Same files as Stage 4 | `reports/stage4_1_pytest_output.txt` | Superseded by 4.2/4.2a fixes below |
| 4.2 | Chunking correctness patch (fragment provenance, heading content propagation, revision-id normalization) | **Completed with follow-up** (fragment coordinate-space bug fixed in 4.2a) | Same files as Stage 4 | `reports/stage4_2_pytest_output.txt` | Superseded by 4.2a fix below |
| 4.2a | Fragment-provenance correction (split against canonical element text, not combined rendered text) | **Completed** | Same files as Stage 4 | `reports/stage4_2a_pytest_output.txt` | None known |
| 5A | Docling `DOCLING_STANDARD_LOCAL` adapter (path A) | **Completed, frozen** (hardened by 5A.1/5A.2) | `src/ingestion_bench/adapters/{base.py,docling_standard/}`, `scripts/run_docling_standard.py` | `tests/test_docling_standard_{mapper,adapter,integration}.py`; `reports/stage5a_pytest_output.txt`, `reports/stage5a_docling_standard_baseline.md`, `reports/stage5a_docling_standard_results.json` | See "Current limitations" below — these are genuine Docling baseline findings, not open adapter defects |
| 5A.1 | Evidence/provenance hardening patch (diagnostic severity vs. fidelity impact, DOCX partial status, OCR annotation provenance, AdapterConversionResult validation, portable reports, single-execution dual report generation) | **Completed** | Same files as Stage 5A, patched — no new package | `tests/test_adapters_base.py` (15, new), `tests/test_run_docling_standard_report.py` (2, new), 4 new tests added to `test_docling_standard_integration.py`, 1 test updated in `test_docling_standard_mapper.py`; `reports/stage5a_pytest_output.txt` (regenerated in place) | None known — see decisions D-037, D-038 |
| 5A.2 | Evidence-contract correction (truthful conversion-status validation, component-level determinism evidence, restored environment/model-footprint evidence) | **Completed, frozen** | Same files as Stage 5A, patched, plus `src/ingestion_bench/adapters/docling_standard/environment.py` (new) | `tests/test_adapters_base.py` (+4), `tests/test_docling_standard_adapter.py` (+2), `tests/test_run_docling_standard_report.py` (+1, extended); `reports/stage5a_pytest_output.txt` (regenerated in place), `reports/stage5a_docling_standard_baseline.md`/`results.json` (regenerated from one execution) | None known — see decisions D-039, D-040 |
| 6A | Deterministic ingestion-fidelity evaluator (scores Stage 5A output against `reference_manifest.json`) | **Not started** | — | — | Produces the gold fact-to-chunk evidence-alignment catalog reused by Stage 6B+ (D-040) |
| 6B | Retrieval benchmark contract + gold evidence set (built on the Stage 6A alignment catalog) | **Not started** | — | — | — |
| 7A | Regular vector RAG projection + retrieval baseline | **Not started** | — | — | — |
| 7B | Graph-enriched RAG projection | **Not started** | — | — | — |
| 7C | Wiki page/link projection | **Not started** | — | — | — |
| 8A | Selective OpenAI vision enrichment (`VisionEnricher` framework + `OpenAIVisionEnricher`, path B) | **Not started** | — | — | No `vision/` package. Corrected roadmap position — no longer "Stage 6"; see D-040 and "Corrected roadmap" below |
| 8B | OpenAI vendor-native ingestion (path C) | **Not started** | — | — | — |
| 9 | Cross-lane quality, cost, latency, and ROI comparison | **Not started** | — | — | Depends on Stages 6A–8B |
| D | Local Granite Vision enrichment (path D) | **Deferred** (decision D-009) | — | — | Revisit only on a concrete local-only-deployment requirement |

## Generated fixture inventory

Per `fixtures/generated/generation_report.json` (regenerated locally, not
committed): 12 benchmark artifacts (3 parity format files + 6 stress
files + 3 shared images), each with a recorded SHA-256 and byte size, plus
`manifest_sha256: "9a58c2c52af0d2ebdad644cd71d81b25503191036b06083b36b5b1af978dee1a"`
pinned to `manifest_version: "1.2.1"`. Regeneration is verified
byte-deterministic by `tests/test_fixture_generation.py::test_regeneration_is_byte_deterministic`.

Screenshots verifying visual layout (captured via LibreOffice headless
rendering during Stage 3.1 review) are committed at
`reports/screenshots/{PARITY_001,PARITY_001_slide2,STRESS_PPTX_001,STRESS_PPTX_002}.png`.

Stage 5A additionally produced, per fixture, under `artifacts/stage5a/`
(not committed — regenerable via `python scripts/run_docling_standard.py`):
`<doc_id>_<format>/canonical_document.json`, `canonical_chunks.jsonl`,
`conversion_report.json`; `docling_raw/<doc_id>_<format>.json` (Docling's
own lossless `export_to_dict()`, debug evidence only, never canonical
input); `assets/<doc_id>_<format>/<picture_id>.png`.

## Determinism contract (Stage 5A.2)

`scripts/run_docling_standard.py::run_determinism_check` converts each
parity fixture twice and reports five independent comparisons, never one
collapsed boolean (D-039):

- `canonical_json_equal` — full serialized `CanonicalDocument` JSON,
  byte-for-byte.
- `canonical_hash_equal` — `stable_canonical_hash()`.
- `chunk_json_equal` — full serialized `CanonicalChunk` list JSON,
  byte-for-byte.
- `chunk_ids_equal` — ordered `chunk_id` values.
- `chunk_content_hashes_equal` — ordered `content_sha256` values.
- `all_equal` — true only when every comparison above is true; a summary
  field, never the only reported figure.

Both `reports/stage5a_docling_standard_results.json` and
`reports/stage5a_docling_standard_baseline.md` section 4 report all five
comparisons per parity fixture, generated from the same execution. Any
future adapter (path B/C/D) must provide equivalent structured
determinism evidence — a single collapsed hash comparison is no longer
sufficient evidence for a "deterministic output" claim in this project.

## Benchmark dimensions (corrected roadmap)

This benchmark has two independent dimensions, and it must eventually
evaluate combinations of both — no stage before Stage 9 attempts that
combination yet:

**Dimension 1 — ingestion approach:**
- Docling Standard Local (path A — **implemented, frozen**)
- Docling plus selective OpenAI vision enrichment (path B — Stage 8A, not started)
- OpenAI vendor-native document processing (path C — Stage 8B, not started)
- Optional local vision lane (path D — deferred, D-009)

**Dimension 2 — retrieval projection:**
- Regular vector RAG (Stage 7A, not started)
- Graph-enriched RAG (Stage 7B, not started)
- Wiki page/link retrieval (Stage 7C, not started)

Per D-040, every retrieval projection is independently derived from the
same `CanonicalDocument`/`CanonicalChunk` corpus and the same Stage 6A
gold fact-to-chunk evidence-alignment catalog — no projection is
authoritative over another, and none of vector-, graph-, or wiki-specific
state may enter `CanonicalDocument`/`CanonicalChunk`.

**Corrected roadmap** (supersedes any earlier "Stage 6 = VisionEnricher"
framing in this project's history — vision enrichment moved to Stage 8A):

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

## Current limitations

- No evaluator exists — extraction quality has never been measured against
  `reference_manifest.json` (Stage 6A, not started — see "Corrected
  roadmap" above). Stage 5A produces counts and structural observations
  only — see `reports/stage5a_docling_standard_baseline.md`.
- Paths B, C, D (OpenAI vision enrichment, OpenAI vendor-native, local
  Granite Vision) are not implemented — only path A
  (`DOCLING_STANDARD_LOCAL`) exists.
- No embedding, vector index, graph projection, or retrieval code exists
  for this pipeline (the unrelated, hand-seeded `src/` GraphRAG POC is a
  separate proof of concept — see `docs/POC_ARCHITECTURE.md` section G).
- `ModelArtifact`/`RemoteInferenceCall` remain implemented models with no
  code that constructs a real instance (`ExtractionRun` itself is now
  populated by the Docling adapter for every successful/partial
  conversion — the local Docling models it invokes are not yet recorded
  as `ModelArtifact` governance entries, since no model-download/staging
  step exists yet for them; they are simply already-cached HF Hub
  downloads).
- Heading annotation content is merged into **every** chunk beneath an
  active heading (every buffer flush, every split fragment) — flagged in
  the Stage 4.2 report as worth revisiting if a heading carries very long
  annotation text under many descendant chunks.
- **Genuine Docling 2.114.0/docling-core 2.87.1 baseline findings**
  (not adapter defects — see `reports/stage5a_docling_standard_baseline.md`
  section 6 and decisions D-033–D-035, D-037, D-038 for full detail):
  - DOCX exposes no page geometry via Docling's public API at all; the
    adapter falls back to reading it from the source file directly via
    `python-docx` (a real, non-fabricated value, but not Docling's own).
    As of Stage 5A.1, this is recorded as a `docx_pagination_unavailable`
    diagnostic with `affects_fidelity=True`, so **every DOCX conversion's
    `conversion_status` is `"partial"`, never `"success"`** (D-037) — this
    is a status correction, not a new limitation; the underlying fallback
    mechanism is unchanged from Stage 5A.
  - PDF heading-level classification did not distinguish nesting depth
    for the parity fixture (all headings got `level=1`); PPTX
    title/section-header shapes were not classified as headings at all
    (zero `CanonicalHeading`s from `PARITY_001.pptx`).
  - Picture-to-caption linking worked for PDF but not for DOCX/PPTX in
    this Docling version.
  - DOCX did not preserve multi-level nested-list parent/child structure
    for the `STRESS_DOCX_001` fixture (3 flat sibling list groups instead
    of one nested list).
  - OCR-origin detection is possible only via structural nesting under a
    `PictureItem` — body-level OCR text (the scanned-PDF fixture) has no
    distinguishing signal and is mapped as plain paragraph text. As of
    Stage 5A.1, every `OcrAnnotation` that IS produced now also carries a
    matching `ProvenanceEntry` (bbox, `self_ref`, an `ocr_sequence`
    disambiguating multiple OCR lines under one picture) whenever Docling
    supplies evidence (D-038) — OCR text *ordering* within one picture
    remains a documented limitation (`ocr_sequence` reflects scan order,
    not verified visual reading order).

## Known non-goals (see also "Explicitly deferred scope" below)

Real extraction accuracy of any kind, retrieval relevance, answer quality,
and production deployment readiness are all explicitly out of scope for
what exists today — none of the code in this repository attempts to
measure them yet.

## Pending Stage 4.x corrections

None open. Stage 4 → 4.1 → 4.2 → 4.2a is a closed, four-part sequence;
every issue identified during that sequence (heading annotation loss,
missing provenance in hashing, asset-only picture loss, table rendering
ambiguity, duplicate-occurrence false positives, `embedding_input_sha256`
collision risk, `version_label` normalization inconsistency, and finally
the Stage 4.2a fragment coordinate-space bug — fragment `start_char`/
`end_char` were computed against combined rendered text instead of the
canonical element's own text) has a corresponding fix and test — see
`docs/POC_DECISION_LOG.md` D-017 through D-031.

## Next critical implementation step

Per the corrected roadmap above, the next step is **Stage 6A — the
deterministic ingestion-fidelity evaluator**, building on the now-complete,
now-frozen Stage 5A/5A.1/5A.2 Docling adapter. Vision enrichment
(previously described as "Stage 6" earlier in this project's history) is
now Stage 8A — see D-040 and "Benchmark dimensions" above for why the
evaluator and the retrieval-projection work come first: the Stage 6A
evaluator's gold fact-to-chunk evidence-alignment catalog is the shared
evidence set every later retrieval projection (Stage 7A/7B/7C) will be
scored against, so it must exist before those projections are worth
comparing. Stage 5A/5A.1/5A.2 is complete: `docling==2.114.0` is installed
and pinned, the adapter converts all 9 generated fixtures to a valid
`CanonicalDocument` (7 `success`, 2 `partial` — DOCX, per D-037), its
output chunks through the existing frozen `chunk_document()` unmodified,
and conversion determinism is now backed by five independent
component-level comparisons (D-039), not one collapsed hash.

---

## What the existing tests prove

- **Canonical schema validity and referential integrity** —
  `tests/test_canonical_schema.py` (87 tests): every cross-reference
  (annotation→target, caption→picture, list-item→parent, table-cell→bounds,
  bbox→unit coordinate system) is validated and rejected when broken; ID
  uniqueness and path portability are enforced.
- **Deterministic hashing** — `tests/test_canonical_hashing.py` (21
  tests): `stable_canonical_hash`, `compute_manifest_sha256`, and
  `stable_element_id` are all proven deterministic, content-sensitive, and
  free of `uuid4()`/built-in `hash()`.
- **Benchmark fixture correctness** — fixtures match the manifest's
  declared headings, paragraphs, table cells, and text, across DOCX/PDF/
  PPTX.
- **Deterministic fixture regeneration** — byte-for-byte reproducible
  regeneration and a stable `manifest_sha256`.
- **Native Office structure** — real DOCX page breaks, PPTX slide counts,
  PPTX native shapes/connectors with correct arrowheads and z-order, not
  rasterized substitutes (except the deliberately rasterized scanned-PDF
  fixture).
- **Scanned PDF genuinely lacks a digital text layer** — proven by
  counting actual glyph-showing content-stream operators, not a substring
  heuristic.
- **Deterministic, parser-independent chunking** — `tests/test_chunking.py`
  (110 tests): identical input always produces byte-identical serialized
  chunks; changing config changes chunk boundaries and hashes; ordering is
  independent of input list order.
- **Source/model-derived separation** — OCR vs. multimodal "visible text"
  reading are never conflated; `IdentifierAnnotation` is tracked but never
  duplicated into rendered text.
- **Fragment provenance is exact** — an oversized paragraph's or list
  item's split fragments carry `start_char`/`end_char` spans that
  reconstruct the canonical element's own text exactly
  (`original_text[start_char:end_char]`, concatenated across fragments);
  an `IdentifierAnnotation` is routed to the correct later fragment
  regardless of a list item's display prefix or another annotation's
  rendered text (Stage 4.2a).
- **Revision-lineage behavior** — two revisions of one logical document
  share `logical_document_id` but get different `document_revision_id`s
  and `chunk_id`s even with identical text, while sharing
  `embedding_input_sha256`; a source-hash mismatch between
  `CanonicalDocument` and `DocumentRevisionContext` is rejected; no mutable
  retrieval-state field participates in a chunk's hash or id.
- **Docling produces real, structurally valid `CanonicalDocument`s** —
  `tests/test_docling_standard_integration.py` (34 tests, real Docling
  conversions, not mocked): all 9 generated fixtures convert to a valid
  `CanonicalDocument` (7 `"success"`, 2 `"partial"` — the two DOCX
  fixtures, per D-037) and validate against every frozen canonical
  invariant; native table cells, at least one picture, and the target
  identifiers/paragraph text are present in the mapped output for every
  parity format; the resulting `CanonicalDocument`s chunk successfully
  through the unmodified frozen `chunk_document()` with nonempty
  `retrieval_text` on every textual chunk.
- **AdapterConversionResult validation is enforced, not just documented**
  — `tests/test_adapters_base.py` (15 tests, no Docling/real conversion
  needed): `conversion_status="failed"` rejects a present
  `canonical_document`/`extraction_run`; `"success"`/`"partial"` reject a
  missing one; `elapsed_ms` rejects negative values; `source_sha256`
  rejects anything that isn't lowercase 64-hex; `source_relative_path`
  rejects absolute paths, backslashes, and `..` traversal.
- **OCR annotations carry real provenance, never fabricated** —
  `test_parity_pdf_picture_ocr_annotations_resolve_to_provenance_entries`,
  `test_chart_fixture_ocr_annotations_resolve_to_provenance_entries`: every
  `OcrAnnotation` produced from a picture-child `TextItem` has a matching
  `ProvenanceEntry` keyed by `annotation_id`, with a real
  `docling_rapidocr` `source_locator` and a distinguishing `ocr_sequence`;
  `test_scanned_pdf_whole_page_ocr_stays_a_paragraph_not_an_annotation`
  confirms body-level OCR text with no picture wrapper still produces zero
  annotations, never a fabricated one.
- **The two persisted Stage 5A reports come from one execution** —
  `tests/test_run_docling_standard_report.py` (3 tests): given a
  synthetic `results` dict, `render_baseline_markdown()` reproduces every
  count/status/timing figure from that same dict verbatim, the rendered
  Markdown never contains an absolute Windows path, and a deliberate
  partial determinism mismatch in the synthetic data renders as a visible
  `**NO**`, never hidden behind a passing aggregate.
- **`conversion_status="success"` cannot coexist with a fidelity-affecting
  diagnostic** (Stage 5A.2, D-037 continued) —
  `tests/test_adapters_base.py::test_success_status_rejects_a_fidelity_affecting_diagnostic`:
  `AdapterConversionResult` itself raises `ValidationError` if a diagnostic
  with `affects_fidelity=True` is attached to a `"success"` result;
  `"partial"` remains valid both with and without one (a parser may
  independently report `PARTIAL_SUCCESS` with zero adapter diagnostics).
- **Docling conversion is deterministic at every level independently, not
  just by hash** (Stage 5A.2, D-039) — `run_determinism_check` compares
  full `CanonicalDocument` JSON, `stable_canonical_hash()`, full
  `CanonicalChunk` list JSON, ordered `chunk_id`s, and ordered
  `content_sha256` values as five separate results, for all three parity
  formats; all five are `true` for every parity fixture in the current
  baseline run.
- **Environment and model-footprint evidence is restored and regenerated
  live** (Stage 5A.2) — `tests/test_docling_standard_adapter.py::test_environment_evidence_never_contains_an_absolute_path`,
  `test_environment_evidence_has_expected_shape`: Python/OS/package
  versions, CUDA availability, effective accelerator, whether an external
  Hugging Face cache is configured, a redacted (drive/mount-only) cache
  location, downloaded Docling model families, and an approximate storage
  footprint are collected fresh on every run — never hand-typed, never an
  absolute filesystem path.
- **Docling is confined to the adapter boundary** — `canonical/` and
  `chunking/` source contain zero `import docling`/`import docling_core`
  statements, verified the same way (real import-statement grepping, not
  substring matching) as the pre-existing Docling/OpenAI isolation tests.
- **No model-derived content is produced by Stage 5A** — every annotation
  the Docling adapter can produce is `OcrAnnotation` with
  `derivation="extracted"`; no `VisualFactAnnotation`,
  `ImageDescriptionAnnotation`, `SemanticClaimAnnotation`, or
  model-derived `DiagramNode`/`EdgeAnnotation` is ever created.

## What the existing tests do not prove

- Whether Docling's extraction is *correct* against
  `reference_manifest.json` — no evaluator exists (Stage 6A, corrected
  roadmap). Stage 5A tests check structural presence (a table exists, an
  identifier substring is present, a picture was retained) never
  accuracy/recall/precision.
- OCR *accuracy* — Stage 5A confirms OCR-derived text is extracted at all
  (e.g. the scanned PDF's OCR text is nonempty, the diagram's 3 OCR tokens
  and the chart's 9 OCR tokens are captured as `OcrAnnotation`s) but never
  checks whether the transcribed text is correct.
- Table-*cell-value* extraction accuracy against expected content.
- Visual-semantic accuracy (picture classification, diagram node/edge
  recovery, visual-fact accuracy) — no `VisionEnricher` exists; Stage 5A
  explicitly proves the *absence* of invented visual facts, not the
  presence of correct ones.
- OpenAI extraction/comparison quality (paths B/C) — not implemented.
- Retrieval relevance or answer quality — no retrieval layer exists for
  this pipeline.
- Production scalability, latency, or cost under real load (Stage 5A's
  timings are for 9 small synthetic fixtures on one CPU-only laptop-class
  machine, not a load test).
- OpenShift (or any) deployment readiness.

---

## POC critical path to first measurable drop

Using the repository's actual state (not aspirational), the path is:

```
chunk contract frozen (Stage 4.2a, done)
        -> Docling Standard Local adapter (Stage 5A, DONE; hardened by Stage 5A.1/5A.2, DONE)
        -> process the controlled Stage 3 fixtures (DONE -- all 9 produce a valid CanonicalDocument; 7 success, 2 partial)
        -> produce valid CanonicalDocuments (DONE)
        -> produce deterministic CanonicalChunks (DONE -- existing chunker, unmodified; determinism now backed by 5 independent component comparisons, D-039)
        -> compare output against reference_manifest.json ground truth (NOT STARTED -- Stage 6A)
        -> report extraction metrics + gold fact-to-chunk evidence alignment (per BENCHMARK_CONTRACT.md section 9) (NOT STARTED -- Stage 6A)
        -> retrieval benchmark contract + vector/graph/wiki projections (NOT STARTED -- Stages 6B/7A/7B/7C)
        -> add selective vision/vendor-native comparison (paths B/C) as time permits (NOT STARTED -- Stages 8A/8B)
        -> cross-lane quality/cost/latency/ROI comparison (NOT STARTED -- Stage 9)
```

The remaining gap to a first *measurable* result (accuracy/recall against
the manifest, not just "did conversion succeed") is the evaluator
(Stage 6A, corrected roadmap — see "Benchmark dimensions" above) — Stage
5A intentionally stops at producing baseline counts and structural
observations (`reports/stage5a_docling_standard_baseline.md`), never
manifest comparison.

## Explicitly deferred scope

- ADK (or any) agent orchestration.
- Graph RAG integration for this pipeline specifically (the existing `src/`
  GraphRAG POC is separate and unrelated — see `docs/POC_ARCHITECTURE.md`
  section G).
- Production database/index design for embeddings or chunks.
- A production document-revision registry / `ChunkIndexRecord`
  (decisions D-021–D-023 describe the intended semantics only).
- OpenShift or any other production deployment.
- Local Granite Vision model deployment (path D — decision D-009).
- Any UI.
- Generalized enterprise workflow integration.
