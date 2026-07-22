"""Tests for the parser-neutral AdapterConversionResult/AdapterDiagnostic
contract (ingestion_bench.adapters.base) -- Stage 5A.1 item 5 validation
hardening. Independent of Docling: uses minimal hand-built
CanonicalDocument/ExtractionRun instances, the same way
test_canonical_schema.py does, never a real conversion.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ingestion_bench.adapters.base import AdapterConversionResult, AdapterDiagnostic
from ingestion_bench.canonical import CanonicalDocument, CanonicalUnit, ExtractionRun


def _valid_document() -> CanonicalDocument:
    unit = CanonicalUnit(unit_index=0, unit_type="page", width=612, height=792, coordinate_unit="pt", coordinate_origin="top-left")
    return CanonicalDocument(
        doc_id="DOC1", source_format="pdf", source_filename="doc1.pdf",
        source_relative_path="parity/doc1.pdf", source_sha256="a" * 64,
        units=[unit],
    )


def _valid_extraction_run() -> ExtractionRun:
    return ExtractionRun(
        run_id="run-1", doc_id="DOC1", path_id="A",
        parser_name="docling_standard_local", parser_version="2.114.0",
        generated_at=datetime.now(timezone.utc), elapsed_seconds=1.0,
        canonical_document_hash="b" * 64,
    )


def _base_kwargs(**overrides) -> dict:
    kwargs = dict(
        canonical_document=None, extraction_run=None, conversion_status="failed",
        elapsed_ms=1.0, docling_version="2.114.0", docling_core_version="2.87.1",
        input_format="pdf", source_relative_path="parity/doc1.pdf", source_sha256="a" * 64,
    )
    kwargs.update(overrides)
    return kwargs


def test_failed_status_accepts_none_document_and_run():
    result = AdapterConversionResult(**_base_kwargs())
    assert result.conversion_status == "failed"
    assert result.canonical_document is None
    assert result.extraction_run is None


def test_failed_status_rejects_a_present_document():
    with pytest.raises(ValidationError):
        AdapterConversionResult(**_base_kwargs(canonical_document=_valid_document()))


def test_success_status_requires_both_document_and_run():
    with pytest.raises(ValidationError):
        AdapterConversionResult(**_base_kwargs(conversion_status="success"))


def test_success_status_accepts_both_present():
    result = AdapterConversionResult(**_base_kwargs(
        conversion_status="success", canonical_document=_valid_document(), extraction_run=_valid_extraction_run(),
    ))
    assert result.conversion_status == "success"


def test_partial_status_requires_both_document_and_run():
    with pytest.raises(ValidationError):
        AdapterConversionResult(**_base_kwargs(conversion_status="partial", canonical_document=_valid_document()))


def test_partial_status_accepts_both_present():
    result = AdapterConversionResult(**_base_kwargs(
        conversion_status="partial", canonical_document=_valid_document(), extraction_run=_valid_extraction_run(),
    ))
    assert result.conversion_status == "partial"


def test_elapsed_ms_must_be_nonnegative():
    with pytest.raises(ValidationError):
        AdapterConversionResult(**_base_kwargs(elapsed_ms=-0.1))


def test_source_sha256_must_be_lowercase_hex_sha256():
    with pytest.raises(ValidationError):
        AdapterConversionResult(**_base_kwargs(source_sha256="A" * 64))
    with pytest.raises(ValidationError):
        AdapterConversionResult(**_base_kwargs(source_sha256="not-hex"))
    with pytest.raises(ValidationError):
        AdapterConversionResult(**_base_kwargs(source_sha256="a" * 63))


@pytest.mark.parametrize("bad_path", ["C:\\abs\\path.pdf", "/abs/path.pdf", "../escape.pdf", ""])
def test_source_relative_path_must_be_portable_and_relative(bad_path):
    with pytest.raises(ValidationError):
        AdapterConversionResult(**_base_kwargs(source_relative_path=bad_path))


def test_source_relative_path_accepts_portable_posix_relative_path():
    result = AdapterConversionResult(**_base_kwargs(source_relative_path="parity/PARITY_001.pdf"))
    assert result.source_relative_path == "parity/PARITY_001.pdf"


def test_diagnostic_severity_and_affects_fidelity_are_independent_axes():
    info_but_fidelity_affecting = AdapterDiagnostic(category="docx_pagination_unavailable", severity="info", message="m", affects_fidelity=True)
    warning_but_not_fidelity_affecting = AdapterDiagnostic(category="skipped_furniture", severity="info", message="m")
    assert info_but_fidelity_affecting.affects_fidelity is True
    assert warning_but_not_fidelity_affecting.affects_fidelity is False


def test_diagnostic_affects_fidelity_defaults_false():
    diagnostic = AdapterDiagnostic(category="skipped_furniture", severity="info", message="m")
    assert diagnostic.affects_fidelity is False
