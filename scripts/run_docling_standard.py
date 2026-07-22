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

from ingestion_bench.adapters.docling_standard import DoclingStandardAdapter  # noqa: E402
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
        "diagnostics_by_category": _count_by(result.diagnostics, "category"),
        "diagnostics_by_severity": _count_by(result.diagnostics, "severity"),
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


def run_determinism_check(adapter: DoclingStandardAdapter, source_path: Path) -> bool:
    from ingestion_bench.canonical.hashing import stable_canonical_hash

    result_a = adapter.convert(source_path, source_root=FIXTURES_ROOT)
    result_b = adapter.convert(source_path, source_root=FIXTURES_ROOT)
    if result_a.canonical_document is None or result_b.canonical_document is None:
        return False
    return stable_canonical_hash(result_a.canonical_document) == stable_canonical_hash(result_b.canonical_document)


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

    results = {
        "docling_version": fixture_reports[0]["docling_version"] if fixture_reports else None,
        "docling_core_version": fixture_reports[0]["docling_core_version"] if fixture_reports else None,
        "total_fixtures": len(fixture_reports),
        "total_elapsed_seconds": round(total_elapsed_s, 2),
        "determinism_results": determinism_results,
        "fixtures": fixture_reports,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "stage5a_docling_standard_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"Processed {len(fixture_reports)} fixtures in {total_elapsed_s:.1f}s")
    for report in fixture_reports:
        print(f"  {report['fixture']:40s} status={report['conversion_status']:8s} "
              f"units={report['unit_count']} headings={report['heading_count']} "
              f"paras={report['paragraph_count']} tables={report['table_count']} "
              f"pictures={report['picture_count']} chunks={report['canonical_chunk_count']}")
    print(f"Determinism: {determinism_results}")
    print(f"Results written to {REPORTS_DIR / 'stage5a_docling_standard_results.json'}")


if __name__ == "__main__":
    main()
