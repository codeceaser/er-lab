# POC Status and Evidence — Enterprise Document-Ingestion Benchmark

Snapshot as of commit `47fad5f` (Stage 4.2a) on branch `main`. Update this
document at the end of every subsequent stage — see the maintenance rules
in `docs/README.md`.

## Current test totals

**256 tests passed, 0 failed** — full suite, all files (`test_canonical_schema.py`
87, `test_canonical_hashing.py` 21, `test_fixture_generation.py` 38,
`test_chunking.py` 110). Full verbose output: `reports/stage4_2a_pytest_output.txt`.
Progression across stages (each report file is a real, committed snapshot):

| Report | Pass count |
|---|---|
| `reports/stage2_pytest_output.txt` | 108 |
| `reports/stage3_pytest_output.txt` | 136 |
| `reports/stage3_1_pytest_output.txt` | 146 |
| `reports/stage4_pytest_output.txt` | 185 |
| `reports/stage4_1_pytest_output.txt` | 220 |
| `reports/stage4_2_pytest_output.txt` | 244 |
| `reports/stage4_2a_pytest_output.txt` | 256 |

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
| 5 | Docling `DOCLING_STANDARD_LOCAL` adapter (path A) | **Not started** | — | — | No `adapters/` package; `docling` not in `requirements.txt`/`constraints.txt` |
| 6 | `VisionEnricher` framework + `OpenAIVisionEnricher` (path B) | **Not started** | — | — | No `vision/` package |
| 7 | OpenAI vendor-native adapter (path C) | **Not started** | — | — | — |
| 8 | Evaluator (scores extraction against `reference_manifest.json`) | **Not started** | — | — | Depends on Stages 5–7 producing real `CanonicalDocument`/`CanonicalChunk` output |
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

## Current limitations

- No parser adapter exists — every `CanonicalDocument` used in this
  repository's own tests is hand-constructed in Python, not produced by
  parsing a real file.
- No evaluator exists — extraction quality has never been measured against
  `reference_manifest.json`.
- No embedding, vector index, graph projection, or retrieval code exists
  for this pipeline (the unrelated, hand-seeded `src/` GraphRAG POC is a
  separate proof of concept — see `docs/POC_ARCHITECTURE.md` section G).
- `ExtractionRun`/`ModelArtifact`/`RemoteInferenceCall` are implemented
  models with no code that constructs a real instance.
- Heading annotation content is merged into **every** chunk beneath an
  active heading (every buffer flush, every split fragment) — flagged in
  the Stage 4.2 report as worth revisiting if a heading carries very long
  annotation text under many descendant chunks.

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

Per the working plan referenced throughout this project's history, the
next step is the **Docling `DOCLING_STANDARD_LOCAL` adapter (path A)** —
Stage 5. It has not been started: no dependency has been added, no
`adapters/` package exists, and no code has attempted to parse any Stage 3
fixture.

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

## What the existing tests do not prove

- Actual Docling (or any real parser) extraction quality — no parser has
  run.
- OCR accuracy — no OCR engine has run; `expected_ocr_tokens`/
  `expected_ocr_text` in the manifest are unverified ground truth, not
  measured results.
- Table-extraction accuracy against a real parser.
- Visual-semantic accuracy (picture classification, diagram node/edge
  recovery, visual-fact accuracy) — no `VisionEnricher` exists.
- OpenAI extraction/comparison quality (paths B/C) — not implemented.
- Retrieval relevance or answer quality — no retrieval layer exists for
  this pipeline.
- Production scalability, latency, or cost under real load.
- OpenShift (or any) deployment readiness.

---

## POC critical path to first measurable drop

Using the repository's actual state (not aspirational), the path is:

```
chunk contract frozen (Stage 4.2a, done)
        -> Docling Standard Local adapter (Stage 5, not started)
        -> process the controlled Stage 3 fixtures
        -> produce valid CanonicalDocuments
        -> produce deterministic CanonicalChunks (existing chunker, unmodified)
        -> compare output against reference_manifest.json ground truth
        -> report extraction metrics (per BENCHMARK_CONTRACT.md section 9)
        -> add selective vision/vendor-native comparison (paths B/C) as time permits
```

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
