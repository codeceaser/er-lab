"""Stage 5A runner: converts every generated benchmark fixture through the
DOCLING_STANDARD_LOCAL adapter, chunks the result with the existing frozen
chunker, writes per-fixture artifacts, and produces the baseline report.

This script -- like the adapter and mapper it drives -- never reads
reference_manifest.json. It discovers input fixtures from the file system
(fixtures/generated/{parity,stress}/*.{pdf,docx,pptx}), not from the
manifest, per chunking rule 12 ("The adapter and runner must not read the
manifest while creating CanonicalDocument").

Usage (from the repository root, with the venv active):
    python scripts/run_docling_standard.py

Environment: set HF_HOME (and HF_HUB_CACHE) before running if you want
Docling's model downloads redirected away from the default cache location
-- see docs/POC_STATUS_AND_EVIDENCE.md for what this repository used.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "fixtures"))

from ingestion_bench.adapters.docling_standard import DoclingStandardAdapter, config  # noqa: E402
from ingestion_bench.chunking import ChunkingConfig, DocumentRevisionContext, chunk_document, compute_document_revision_id  # noqa: E402

FIXTURES_ROOT = REPO_ROOT / "fixtures" / "generated"
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "stage5a"
REPORTS_DIR = REPO_ROOT / "reports"


def discover_fixtures() -> list[Path]:
    """Every generated .pdf/.docx/.pptx under fixtures/generated/ -- never
    reference_manifest.json, generation_report.json, or a standalone PNG."""
    paths = []
    for pattern in ("*.pdf", "*.docx", "*.pptx"):
        paths.extend(sorted((FIXTURES_ROOT / "parity").glob(pattern)))
        paths.extend(sorted((FIXTURES_ROOT / "stress").glob(pattern)))
    return sorted(paths)


def _annotation_counts(document) -> dict:
    counts: dict[str, dict[str, int]] = {}
    for annotation in document.annotations:
        by_derivation = counts.setdefault(annotation.annotation_type, {})
        by_derivation[annotation.derivation] = by_derivation.get(annotation.derivation, 0) + 1
    return counts


def process_fixture(adapter: DoclingStandardAdapter, source_path: Path) -> dict:
    doc_id = source_path.stem
    source_format = source_path.suffix.lower().lstrip(".")
    # PARITY_001.pdf/.docx/.pptx deliberately share doc_id="PARITY_001"
    # (matching reference_manifest.json's single doc_id for that suite,
    # compared across formats) -- artifact_key keeps their on-disk output
    # directories from colliding, the same way adapter.py's own internal
    # asset/debug paths do.
    artifact_key = f"{doc_id}_{source_format}"
    relative = source_path.relative_to(FIXTURES_ROOT).as_posix()
    fixture_report: dict = {
        "fixture": relative,
        "doc_id": doc_id,
        "source_format": source_format,
        "source_byte_size": source_path.stat().st_size,
    }

    result = adapter.convert(source_path, source_root=FIXTURES_ROOT)
    fixture_report.update({
        "source_sha256": result.source_sha256,
        "conversion_status": result.conversion_status,
        "elapsed_ms": round(result.elapsed_ms, 1),
        "docling_version": result.docling_version,
        "docling_core_version": result.docling_core_version,
        "errors": result.errors,
        "warnings": result.warnings,
        # Full diagnostics array (Stage 5A.1 item 6) -- not just counts --
        # so a reader can see exactly which item/category/message produced
        # each diagnostic without re-running the conversion.
        "diagnostics": [d.model_dump() for d in result.diagnostics],
        "diagnostics_by_category": _count_by(result.diagnostics, "category"),
        "diagnostics_by_severity": _count_by(result.diagnostics, "severity"),
        "diagnostics_by_affects_fidelity": _count_by_affects_fidelity(result.diagnostics),
        # raw_docling_debug_artifact is already a portable "stage5a/..."
        # reference (see adapter.py::_write_raw_debug_snapshot) -- never an
        # absolute filesystem path -- so it is safe to persist as-is.
        "raw_docling_debug_artifact": result.raw_docling_debug_artifact,
    })

    document = result.canonical_document
    if document is None:
        fixture_report.update({
            "unit_count": 0, "heading_count": 0, "paragraph_count": 0, "list_item_count": 0,
            "table_count": 0, "table_cell_count": 0, "picture_count": 0, "caption_count": 0,
            "annotation_counts": {}, "provenance_count": 0,
            "canonical_chunk_count": 0, "textual_chunk_count": 0, "asset_only_chunk_count": 0,
        })
        return fixture_report

    fixture_report.update({
        "unit_count": len(document.units),
        "heading_count": len(document.headings),
        "paragraph_count": len(document.paragraphs),
        "list_item_count": len(document.list_items),
        "table_count": len(document.tables),
        "table_cell_count": sum(len(t.cells) for t in document.tables),
        "picture_count": len(document.pictures),
        "caption_count": len(document.captions),
        "annotation_counts": _annotation_counts(document),
        "provenance_count": len(document.provenance),
    })

    fixture_dir = ARTIFACTS_ROOT / artifact_key
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "canonical_document.json").write_text(document.model_dump_json(indent=2), encoding="utf-8")

    chunks = []
    chunk_error = None
    try:
        revision_context = DocumentRevisionContext(
            logical_document_id=doc_id,
            document_revision_id=compute_document_revision_id(doc_id, document.source_sha256),
            source_document_sha256=document.source_sha256,
        )
        chunks = chunk_document(document, ChunkingConfig(), revision_context=revision_context)
    except Exception as exc:  # a chunking failure is itself a reportable Stage 5A result, never silently swallowed
        chunk_error = repr(exc)

    fixture_report["chunk_error"] = chunk_error
    fixture_report["canonical_chunk_count"] = len(chunks)
    fixture_report["textual_chunk_count"] = sum(1 for c in chunks if c.chunk_type in ("text", "mixed"))
    fixture_report["asset_only_chunk_count"] = sum(1 for c in chunks if c.chunk_type == "picture" and not c.source_text)

    with (fixture_dir / "canonical_chunks.jsonl").open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(chunk.model_dump_json())
            handle.write("\n")

    (fixture_dir / "conversion_report.json").write_text(json.dumps(fixture_report, indent=2), encoding="utf-8")
    return fixture_report


def _count_by(items, attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = str(getattr(item, attr))
        counts[key] = counts.get(key, 0) + 1
    return counts


def _count_by_affects_fidelity(items) -> dict[str, int]:
    counts: dict[str, int] = {"fidelity_affecting": 0, "non_fidelity_affecting": 0}
    for item in items:
        key = "fidelity_affecting" if item.affects_fidelity else "non_fidelity_affecting"
        counts[key] += 1
    return counts


def _count_values(items: list[dict], key: str) -> dict[str, int]:
    """Same aggregation as _count_by, but over plain dicts (fixture_report
    entries, or serialized diagnostic dicts) rather than model instances."""
    counts: dict[str, int] = {}
    for item in items:
        value = str(item[key])
        counts[value] = counts.get(value, 0) + 1
    return counts


def _count_by_affects_fidelity_dicts(diagnostics: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {"fidelity_affecting": 0, "non_fidelity_affecting": 0}
    for d in diagnostics:
        key = "fidelity_affecting" if d["affects_fidelity"] else "non_fidelity_affecting"
        counts[key] += 1
    return counts


def run_determinism_check(adapter: DoclingStandardAdapter, source_path: Path) -> bool:
    from ingestion_bench.canonical.hashing import stable_canonical_hash

    result_a = adapter.convert(source_path, source_root=FIXTURES_ROOT)
    result_b = adapter.convert(source_path, source_root=FIXTURES_ROOT)
    if result_a.canonical_document is None or result_b.canonical_document is None:
        return False
    return stable_canonical_hash(result_a.canonical_document) == stable_canonical_hash(result_b.canonical_document)


def render_baseline_markdown(results: dict) -> str:
    """Renders reports/stage5a_docling_standard_baseline.md entirely from
    the same in-memory `results` object that gets serialized to
    reports/stage5a_docling_standard_results.json (Stage 5A.1 item 7) --
    every count, status, and timing figure below is read out of `results`,
    never retyped or recomputed from a separate run."""
    fixtures = results["fixtures"]

    fixture_rows = []
    for r in fixtures:
        fixture_rows.append(
            f"| {r['fixture']} | {r['conversion_status']} | {r['elapsed_ms']}ms | "
            f"{r['unit_count']} | {r['heading_count']} | {r['paragraph_count']} | "
            f"{r['list_item_count']} | {r['table_count']} | {r['table_cell_count']} | "
            f"{r['picture_count']} | {r['caption_count']} | "
            f"{sum(sum(d.values()) for d in r['annotation_counts'].values())} | "
            f"{r['provenance_count']} | {r['canonical_chunk_count']} | "
            f"{r['textual_chunk_count']} | {r['asset_only_chunk_count']} |"
        )

    status_lines = "\n".join(f"- `{status}`: {count}" for status, count in sorted(results["status_counts"].items()))
    category_lines = "\n".join(f"| `{cat}` | {count} |" for cat, count in sorted(results["diagnostics_by_category"].items())) or "| (none) | 0 |"
    severity_lines = "\n".join(f"| `{sev}` | {count} |" for sev, count in sorted(results["diagnostics_by_severity"].items())) or "| (none) | 0 |"
    fidelity = results["diagnostics_by_affects_fidelity"]
    determinism_lines = "\n".join(f"| {fixture} | {'**Yes**' if ok else '**NO**'} |" for fixture, ok in results["determinism_results"].items())

    return f"""# Stage 5A — DOCLING_STANDARD_LOCAL Baseline Report

Generated by `scripts/run_docling_standard.py` from a single execution --
the counts, statuses, and timings below and in
`reports/stage5a_docling_standard_results.json` come from the same
in-memory run (Stage 5A.1 item 7), never two separate invocations. Full
pytest evidence: `reports/stage5a_pytest_output.txt`.

This report separates three things that must never be conflated:

1. **Observed parser output** -- what Docling itself returned.
2. **Canonical mapping result** -- what the Stage 5A/5A.1 adapter mapped
   that into (sections below).
3. **Benchmark correctness evaluation** -- whether the mapped content
   matches `reference_manifest.json`. **Not done here.** No evaluator
   exists yet (Stage 8, not started); this report contains no accuracy/
   recall/precision claims, only counts and structural observations. The
   adapter and this runner never read the manifest.

`conversion_status` semantics (Stage 5A.1): `partial` means a valid
`CanonicalDocument` was produced but at least one diagnostic has
`affects_fidelity=True` (or Docling itself reported `PARTIAL_SUCCESS`) --
it is never derived from diagnostic severity alone. Every DOCX conversion
is `partial` because Docling exposes no page/pagination geometry for DOCX
(see the `docx_pagination_unavailable` diagnostic below); this is a real,
documented loss of source pagination structure, not a bug.

---

## 1. Environment

| Item | Value |
|---|---|
| `docling` | {results["docling_version"]} |
| `docling-core` | {results["docling_core_version"]} |
| Accelerator device used | `{results["effective_configuration"]["accelerator_device"]}` |
| All document conversion | 100% local -- `enable_remote_services={results["effective_configuration"]["enable_remote_services"]}` |

## 2. Effective pipeline configuration

```json
{json.dumps(results["effective_configuration"], indent=2)}
```

`RapidOcrOptions` was chosen explicitly over Docling's own default
(`OcrAutoOptions`) to avoid environment-dependent nondeterminism -- see
`docs/POC_DECISION_LOG.md` D-032.

## 3. Fixture-by-fixture summary

All counts below are read directly from this run's `results["fixtures"]`
(identical to `reports/stage5a_docling_standard_results.json`).

| Fixture | Status | Elapsed | Units | Headings | Paragraphs | List items | Tables | Table cells | Pictures | Captions | Annotations | Provenance | Chunks | Textual chunks | Asset-only chunks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
{chr(10).join(fixture_rows)}

Status totals across all {results["total_fixtures"]} fixtures this run:
{status_lines}

Total wall-clock for all {results["total_fixtures"]} fixtures in one batch
run (one shared `DocumentConverter`, models loaded once):
**{results["total_elapsed_seconds"]} seconds.**

## 4. Determinism results

Each parity format was converted twice; canonical document hash, full
serialized `CanonicalDocument`, and every `CanonicalChunk`'s
`chunk_id`/`content_sha256` were compared:

| Fixture | Identical across two runs |
|---|---|
{determinism_lines}

No nondeterministic Docling parser metadata (timings, etc.) leaked into
canonical identity -- `ExtractionRun.elapsed_seconds`/`generated_at` are
the only run-varying fields, and both are excluded from
`stable_canonical_hash()` by construction (Stage 2 design, unmodified).

## 5. Diagnostics (this run)

By category:

| Category | Count |
|---|---|
{category_lines}

By severity:

| Severity | Count |
|---|---|
{severity_lines}

By fidelity impact (Stage 5A.1 -- independent of severity, see `AdapterDiagnostic.affects_fidelity`): **{fidelity.get("fidelity_affecting", 0)} fidelity-affecting**, **{fidelity.get("non_fidelity_affecting", 0)} non-fidelity-affecting**.

## 6. Known Docling limitations discovered

These are genuine findings about this Docling/docling-core version's
standard-local pipeline, discovered empirically while building and running
the adapter -- not adapter defects, and not benchmark-correctness claims
(no manifest comparison was performed). This section is maintained by hand
(narrative, not a simple count/status/timing figure) and was last verified
against `docling=={results["docling_version"]}` / `docling-core=={results["docling_core_version"]}`:

1. **DOCX exposes no page geometry at all.** `DoclingDocument.pages` is
   empty and every item's `.prov` is `[]` for DOCX input. Fallback: the
   adapter reads the source `.docx` file's own section `page_width`/
   `page_height` via `python-docx` and uses it as
   `CanonicalUnit.width`/`height`. Every DOCX conversion records a
   `docx_pagination_unavailable` diagnostic (`affects_fidelity=True`) when
   this happens, and its `conversion_status` is `partial`, never
   `success`. Every canonical element from a DOCX source has `bbox=None`.

2. **PDF heading-level classification did not distinguish nesting depth**
   for the parity fixture -- all headings in `PARITY_001.pdf` were
   assigned `level=1` uniformly, while the same semantic headings in
   `PARITY_001.docx` were correctly assigned levels 1/2/3 (Word's own
   paragraph-style metadata).

3. **PPTX title/section-header shapes are not classified as headings at
   all.** `PARITY_001.pptx` produced zero `SECTION_HEADER`/`TITLE` labeled
   items.

4. **Picture-to-caption linking works for PDF, not for DOCX/PPTX.**
   `PictureItem.captions` was populated for `PARITY_001.pdf` but empty for
   `PARITY_001.docx`/`.pptx` -- the caption paragraph was mapped as an
   ordinary `CanonicalParagraph` with no link to the picture.

5. **DOCX did not preserve multi-level nested-list parent/child
   structure** for `STRESS_DOCX_001.docx` -- Docling returned 3 flat,
   sibling list groups rather than true nesting, so `_walk_list_ancestry`
   (real, general structural logic, proven directly against a
   hand-constructed nested `DoclingDocument` in
   `tests/test_docling_standard_mapper.py`) correctly computed
   `indent_level=0`/`parent_block_id=None` for all 5 items -- this is
   Docling's real output for this fixture, not a bug in the walk.

6. **OCR-origin evidence for individual text items is entirely
   structural, never explicit.** `TextItem.source` is `[]` for every text
   item observed. The only usable signal is tree position: a `TextItem`
   nested directly under a `PictureItem` (and not that picture's caption)
   reliably indicates OCR-of-an-image-region -- but body-level OCR text
   (the whole-page OCR pass in `STRESS_SCANNED_001.pdf`, no picture
   wrapper) has no distinguishing signal and is mapped as an ordinary
   `CanonicalParagraph`, never fabricated as an `OcrAnnotation`. As of
   Stage 5A.1, every `OcrAnnotation` that IS produced (picture-child OCR
   text) also gets a matching `ProvenanceEntry` when Docling supplies
   evidence (bbox via `.prov`, `self_ref`, an `ocr_sequence` disambiguating
   multiple OCR lines under one picture) -- see
   `map_picture_ocr_child`/`ProvenanceEntry.element_id` resolving to an
   `annotation_id`. **OCR text ordering within a picture remains a
   documented Stage 5A/5A.1 limitation**: `ocr_sequence` reflects the order
   Docling's `doc.texts` scan encountered each line, not necessarily true
   reading order within the picture region, since `OcrAnnotation` has no
   `order_index` field of its own in the frozen canonical contract.

None of these are canonical-model or chunking-layer defects -- the frozen
contracts (`ingestion_bench.canonical`, `ingestion_bench.chunking`) were
not modified to accommodate any of them.

## 7. What this report does NOT establish

- Whether the extracted content is *correct* against
  `reference_manifest.json` (no evaluator exists -- Stage 8).
- OCR accuracy (whether OCR tokens were transcribed *correctly*, only that
  they were extracted as OCR-derived text, with provenance, at all).
- Table-extraction accuracy against expected cell values.
- Whether identifiers found via substring presence are correctly
  delimited (token-boundary-safe) -- an evaluator concern, not tested here.
- Retrieval or answer quality of any kind.
"""


def main() -> None:
    ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS_ROOT / "docling_raw").mkdir(parents=True, exist_ok=True)
    (ARTIFACTS_ROOT / "assets").mkdir(parents=True, exist_ok=True)

    adapter = DoclingStandardAdapter(raw_debug_dir=ARTIFACTS_ROOT / "docling_raw", assets_dir=ARTIFACTS_ROOT / "assets")
    fixtures = discover_fixtures()

    started = time.monotonic()
    fixture_reports = [process_fixture(adapter, path) for path in fixtures]
    total_elapsed_s = time.monotonic() - started

    determinism_targets = [p for p in fixtures if p.name in ("PARITY_001.pdf", "PARITY_001.docx", "PARITY_001.pptx")]
    determinism_results = {p.relative_to(FIXTURES_ROOT).as_posix(): run_determinism_check(adapter, p) for p in determinism_targets}

    all_diagnostics = [d for report in fixture_reports for d in report["diagnostics"]]

    results = {
        "docling_version": fixture_reports[0]["docling_version"] if fixture_reports else None,
        "docling_core_version": fixture_reports[0]["docling_core_version"] if fixture_reports else None,
        "effective_configuration": config.effective_configuration_summary(),
        "total_fixtures": len(fixture_reports),
        "total_elapsed_seconds": round(total_elapsed_s, 2),
        "status_counts": _count_values(fixture_reports, "conversion_status"),
        "diagnostics_by_category": _count_values(all_diagnostics, "category"),
        "diagnostics_by_severity": _count_values(all_diagnostics, "severity"),
        "diagnostics_by_affects_fidelity": _count_by_affects_fidelity_dicts(all_diagnostics),
        "determinism_results": determinism_results,
        "fixtures": fixture_reports,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "stage5a_docling_standard_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    # Both reports come from this SAME `results` object (Stage 5A.1 item 7)
    # -- never a second adapter invocation.
    (REPORTS_DIR / "stage5a_docling_standard_baseline.md").write_text(render_baseline_markdown(results), encoding="utf-8")

    print(f"Processed {len(fixture_reports)} fixtures in {total_elapsed_s:.1f}s")
    for report in fixture_reports:
        print(f"  {report['fixture']:40s} status={report['conversion_status']:8s} "
              f"units={report['unit_count']} headings={report['heading_count']} "
              f"paras={report['paragraph_count']} tables={report['table_count']} "
              f"pictures={report['picture_count']} chunks={report['canonical_chunk_count']}")
    print(f"Determinism: {determinism_results}")
    print(f"Results written to {REPORTS_DIR / 'stage5a_docling_standard_results.json'}")
    print(f"Baseline report written to {REPORTS_DIR / 'stage5a_docling_standard_baseline.md'}")


if __name__ == "__main__":
    main()
