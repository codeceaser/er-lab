"""DOCLING_STANDARD_LOCAL adapter (path A): invokes Docling and returns an
AdapterConversionResult.

This module (together with mapper.py) is the ONLY place Docling types are
imported. It never calls the benchmark manifest, an evaluator, an
embedding model, a vector database, or any network API -- see
config.py::build_pdf_pipeline_options for the explicit pipeline
configuration that enforces "no remote services" at the Docling level too.
"""

from __future__ import annotations

import hashlib
import io
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from docling.datamodel.base_models import ConversionStatus as DoclingConversionStatus, InputFormat
from docling.document_converter import DocumentConverter
from docling_core.types.doc.document import DoclingDocument
from PIL.Image import Image as PILImage

from ingestion_bench.adapters.base import AdapterConversionResult
from ingestion_bench.canonical import ExtractionRun

from . import config
from .mapper import DocxPageFallback, DoclingToCanonicalMapper

_EXTENSION_TO_FORMAT = {".pdf": "pdf", ".docx": "docx", ".pptx": "pptx"}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _portable_relative_path(source_path: Path, source_root: Path) -> str:
    relative = source_path.resolve().relative_to(source_root.resolve())
    return PurePosixPath(relative.as_posix()).as_posix()


def _docx_page_fallback(source_path: Path) -> DocxPageFallback | None:
    """Docling's standard pipeline exposes no page geometry for DOCX (see
    mapper.py::DocxPageFallback). Reads the source file's OWN declared
    section page size via python-docx -- already a repository dependency
    (used by fixtures/generate_fixtures.py for a different purpose) --
    purely as a structural fallback, never to read document content."""
    import docx
    from docx.shared import Emu

    document = docx.Document(str(source_path))
    section = document.sections[0]
    width_pt = Emu(section.page_width).pt
    height_pt = Emu(section.page_height).pt
    return DocxPageFallback(width_pt=width_pt, height_pt=height_pt)


class DoclingStandardAdapter:
    """Implements ingestion_bench.adapters.base.DocumentParserAdapter for
    path A (DOCLING_STANDARD_LOCAL). One instance may be reused across
    many convert() calls -- the underlying DocumentConverter (and its
    lazily-loaded models) is built once in __init__, not per file."""

    def __init__(self, *, raw_debug_dir: Path | None = None, assets_dir: Path | None = None) -> None:
        self._converter: DocumentConverter = config.build_converter()
        self._raw_debug_dir = raw_debug_dir
        self._assets_dir = assets_dir
        self._docling_version = config.docling_version()
        self._docling_core_version = config.docling_core_version()

    def convert(self, source_path: Path, *, source_root: Path) -> AdapterConversionResult:
        start = time.monotonic()
        source_bytes = source_path.read_bytes()
        source_sha256 = _sha256_bytes(source_bytes)
        source_relative_path = _portable_relative_path(source_path, source_root)
        doc_id = source_path.stem
        input_format = _EXTENSION_TO_FORMAT.get(source_path.suffix.lower())
        # Used ONLY for artifact file paths, never for canonical identity:
        # the parity suite deliberately gives PARITY_001.pdf/.docx/.pptx
        # the same doc_id (matching reference_manifest.json's single
        # doc_id for that suite, compared across formats) -- so doc_id
        # alone is not a safe on-disk artifact key, or the three
        # conversions would silently overwrite each other's output.
        artifact_key = f"{doc_id}_{input_format}" if input_format else doc_id

        def fail(errors: list[str], *, diagnostics: list | None = None, raw_debug_path: str | None = None) -> AdapterConversionResult:
            return AdapterConversionResult(
                canonical_document=None, extraction_run=None, conversion_status="failed",
                diagnostics=diagnostics or [], warnings=[], errors=errors,
                elapsed_ms=(time.monotonic() - start) * 1000,
                docling_version=self._docling_version, docling_core_version=self._docling_core_version,
                input_format=input_format or source_path.suffix.lower().lstrip("."),
                source_relative_path=source_relative_path, source_sha256=source_sha256,
                raw_docling_debug_artifact=raw_debug_path,
            )

        if input_format is None:
            return fail([f"unsupported file extension: {source_path.suffix!r}"])

        try:
            docling_result = self._converter.convert(source_path)
        except Exception as exc:  # Docling itself raised -- never fabricate a document
            return fail([f"Docling conversion raised: {exc!r}"])

        if docling_result.status == DoclingConversionStatus.FAILURE:
            return fail([str(e) for e in docling_result.errors] or ["Docling reported FAILURE with no error detail"])

        docling_doc: DoclingDocument = docling_result.document

        docx_fallback = None
        if input_format == "docx":
            try:
                docx_fallback = _docx_page_fallback(source_path)
            except Exception:
                docx_fallback = None  # mapper will record a missing_geometry diagnostic and fail cleanly

        mapper = DoclingToCanonicalMapper(
            doc_id=doc_id, source_format=input_format,
            source_filename=source_path.name, source_relative_path=source_relative_path,
            source_sha256=source_sha256, docx_page_fallback=docx_fallback,
        )

        units_ok = mapper.build_units(docling_doc)
        raw_debug_path = self._write_raw_debug_snapshot(docling_doc, artifact_key)

        if not units_ok:
            return fail(
                ["no usable CanonicalUnit geometry could be established"],
                diagnostics=mapper.diagnostics.diagnostics, raw_debug_path=raw_debug_path,
            )

        mapper.map_document(docling_doc, self._save_picture(artifact_key))
        canonical_document = mapper.build()

        if canonical_document is None:
            return fail(
                ["CanonicalDocument construction failed validation; see diagnostics"],
                diagnostics=mapper.diagnostics.diagnostics, raw_debug_path=raw_debug_path,
            )

        elapsed_ms = (time.monotonic() - start) * 1000
        docling_warnings = [str(w) for w in getattr(docling_result, "errors", [])]
        adapter_warnings = [d.message for d in mapper.diagnostics.diagnostics if d.severity in ("warning", "error")]
        all_warnings = docling_warnings + adapter_warnings
        is_partial = (
            docling_result.status == DoclingConversionStatus.PARTIAL_SUCCESS
            or mapper.diagnostics.has_fidelity_impact()
        )

        extraction_run = ExtractionRun(
            run_id=str(uuid.uuid4()),  # run-identifying only; excluded from stable_canonical_hash, uuid4 is explicitly permitted here
            doc_id=doc_id,
            path_id="A",
            parser_name="docling_standard_local",
            parser_version=self._docling_version,
            vision_enricher_name=None,
            parser_config={
                "docling_core_version": self._docling_core_version,
                **config.effective_configuration_summary(),
            },
            generated_at=datetime.now(timezone.utc),
            elapsed_seconds=elapsed_ms / 1000,
            warnings=all_warnings,
            token_usage=None,
            raw_artifact_refs=[str(raw_debug_path)] if raw_debug_path else [],
            canonical_document_hash=_canonical_document_hash(canonical_document),
            model_artifacts=[],
            remote_inference_calls=[],
        )

        return AdapterConversionResult(
            canonical_document=canonical_document,
            extraction_run=extraction_run,
            conversion_status="partial" if is_partial else "success",
            diagnostics=mapper.diagnostics.diagnostics,
            warnings=all_warnings,
            errors=[],
            elapsed_ms=elapsed_ms,
            docling_version=self._docling_version, docling_core_version=self._docling_core_version,
            input_format=input_format, source_relative_path=source_relative_path, source_sha256=source_sha256,
            raw_docling_debug_artifact=raw_debug_path,
        )

    def _save_picture(self, artifact_key: str):
        def saver(picture_id: str, pil_image: PILImage) -> tuple[str, str]:
            buffer = io.BytesIO()
            pil_image.convert("RGB").save(buffer, format="PNG", optimize=False, compress_level=6)
            image_bytes = buffer.getvalue()
            content_sha256 = _sha256_bytes(image_bytes)
            relative_ref = f"stage5a/assets/{artifact_key}/{picture_id}.png"
            if self._assets_dir is not None:
                target = self._assets_dir / artifact_key / f"{picture_id}.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(image_bytes)
            return relative_ref, content_sha256
        return saver

    def _write_raw_debug_snapshot(self, docling_doc: DoclingDocument, artifact_key: str) -> str | None:
        """Writes Docling's own lossless public dictionary export
        (DoclingDocument.export_to_dict()) -- not model_dump_json() or any
        private serialization -- per the Stage 5A instruction to prefer
        documented public APIs. Debug evidence only: never read back in as
        canonical input, never part of canonical hashing."""
        if self._raw_debug_dir is None:
            return None
        self._raw_debug_dir.mkdir(parents=True, exist_ok=True)
        target = self._raw_debug_dir / f"{artifact_key}.json"
        target.write_text(json.dumps(docling_doc.export_to_dict(), ensure_ascii=False), encoding="utf-8")
        # Persisted/returned reference must be portable (Stage 5A.1 item 6):
        # never an absolute, machine-local filesystem path. Uses the same
        # "stage5a/<subdir>/..." convention as _save_picture's relative_ref.
        return f"stage5a/docling_raw/{artifact_key}.json"


def _canonical_document_hash(canonical_document) -> str:
    from ingestion_bench.canonical.hashing import stable_canonical_hash
    return stable_canonical_hash(canonical_document)
