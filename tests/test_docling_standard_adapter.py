"""Tests for DoclingStandardAdapter's own orchestration logic (Stage 5A):
source identity, portable paths, failure handling, and ExtractionRun
population. Mapper structural logic is covered by
test_docling_standard_mapper.py; fixture-by-fixture conversion results are
covered by test_docling_standard_integration.py. These tests run real
(but small/cheap) Docling conversions -- there is no meaningful way to
test "the adapter invokes Docling correctly" without actually invoking it.

The successful-conversion result is computed ONCE per module (session-cost
of a Docling conversion is dominated by one-time model load, but repeating
convert() calls still costs real wall-clock time) and reused read-only
across every test that doesn't specifically need a fresh conversion.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ingestion_bench.adapters.docling_standard import DoclingStandardAdapter

FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "generated"


@pytest.fixture(scope="module")
def adapter(tmp_path_factory) -> DoclingStandardAdapter:
    debug_dir = tmp_path_factory.mktemp("docling_raw")
    assets_dir = tmp_path_factory.mktemp("assets")
    return DoclingStandardAdapter(raw_debug_dir=debug_dir, assets_dir=assets_dir)


@pytest.fixture(scope="module")
def parity_pdf_result(adapter):
    path = FIXTURES_ROOT / "parity" / "PARITY_001.pdf"
    return adapter.convert(path, source_root=FIXTURES_ROOT)


def test_source_sha256_matches_exact_file_bytes(parity_pdf_result):
    path = FIXTURES_ROOT / "parity" / "PARITY_001.pdf"
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert parity_pdf_result.source_sha256 == expected
    assert parity_pdf_result.canonical_document.source_sha256 == expected


def test_source_relative_path_is_portable_posix_relative_to_source_root(parity_pdf_result):
    assert parity_pdf_result.source_relative_path == "parity/PARITY_001.pdf"
    assert "\\" not in parity_pdf_result.source_relative_path
    assert not Path(parity_pdf_result.source_relative_path).is_absolute()


def test_unsupported_extension_fails_cleanly_without_calling_docling(adapter, tmp_path):
    bogus = tmp_path / "not_a_real_format.xyz"
    bogus.write_bytes(b"irrelevant")
    result = adapter.convert(bogus, source_root=tmp_path)
    assert result.conversion_status == "failed"
    assert result.canonical_document is None
    assert result.extraction_run is None
    assert result.errors
    assert "unsupported file extension" in result.errors[0]


def test_successful_conversion_populates_extraction_run(parity_pdf_result):
    assert parity_pdf_result.conversion_status in ("success", "partial")
    run = parity_pdf_result.extraction_run
    assert run is not None
    assert run.path_id == "A"
    assert run.parser_name == "docling_standard_local"
    assert run.parser_version == parity_pdf_result.docling_version
    assert run.vision_enricher_name is None
    assert run.model_artifacts == []  # Stage 5A records no local model governance yet
    assert run.remote_inference_calls == []  # no remote calls of any kind
    assert run.canonical_document_hash  # a real sha256 hex string


def test_extraction_run_hash_matches_stable_canonical_hash(parity_pdf_result):
    from ingestion_bench.canonical.hashing import stable_canonical_hash

    assert parity_pdf_result.extraction_run.canonical_document_hash == stable_canonical_hash(parity_pdf_result.canonical_document)


def test_result_never_contains_an_api_key_or_secret(parity_pdf_result):
    serialized = parity_pdf_result.model_dump_json()
    assert "sk-" not in serialized
    assert "OPENAI_API_KEY" not in serialized


def test_effective_configuration_disables_every_remote_and_vlm_option():
    """The actual enforcement point for "no remote services / no VLM" is
    the pipeline configuration itself (config.py), not a runtime network
    intercept (which risks false failures from unrelated local traffic,
    e.g. huggingface_hub's own cache-freshness check). Assert directly on
    the configuration the adapter actually built and used."""
    from docling.datamodel.accelerator_options import AcceleratorDevice

    from ingestion_bench.adapters.docling_standard import config

    summary = config.effective_configuration_summary()
    assert summary["enable_remote_services"] is False
    assert summary["do_picture_description"] is False
    assert summary["do_chart_extraction"] is False
    assert summary["do_picture_classification"] is False
    assert summary["accelerator_device"] == AcceleratorDevice.CPU


def test_deterministic_conversion_same_canonical_document_hash(adapter, parity_pdf_result):
    from ingestion_bench.canonical.hashing import stable_canonical_hash

    path = FIXTURES_ROOT / "parity" / "PARITY_001.pdf"
    result_b = adapter.convert(path, source_root=FIXTURES_ROOT)
    assert stable_canonical_hash(parity_pdf_result.canonical_document) == stable_canonical_hash(result_b.canonical_document)


def test_environment_evidence_never_contains_an_absolute_path():
    """Stage 5A.2 item 3: environment.collect_environment_evidence() must
    restore version/footprint evidence without ever exposing the user's
    absolute filesystem paths."""
    from ingestion_bench.adapters.docling_standard import environment

    evidence = environment.collect_environment_evidence()
    serialized = str(evidence)
    assert "C:\\" not in serialized
    assert str(Path.home()) not in serialized


def test_environment_evidence_has_expected_shape():
    from ingestion_bench.adapters.docling_standard import environment

    evidence = environment.collect_environment_evidence()
    assert evidence["docling_version"]
    assert evidence["docling_core_version"]
    assert evidence["python_version"]
    assert evidence["os_platform"]
    assert isinstance(evidence["cuda_available"], bool)
    assert isinstance(evidence["external_hf_cache_configured"], bool)
    assert isinstance(evidence["downloaded_model_families"], list)
    if evidence["redacted_hf_cache_location"] is not None:
        assert "(redirected, path redacted)" in evidence["redacted_hf_cache_location"]
        assert evidence["redacted_hf_cache_location"].count("\\") <= 1
