"""Hashing tests for the canonical document model (Stage 2)."""

import inspect
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from ingestion_bench.benchmark_binding import BenchmarkBinding
from ingestion_bench.canonical import (
    CanonicalDocument,
    CanonicalParagraph,
    CanonicalUnit,
    compute_manifest_sha256,
    stable_canonical_hash,
    stable_element_id,
)

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "reference_manifest.json"


def _minimal_document(paragraph_text: str = "Hello world.") -> CanonicalDocument:
    return CanonicalDocument(
        doc_id="DOC1", source_format="pdf", source_filename="doc1.pdf",
        source_relative_path="parity/doc1.pdf", source_sha256="a" * 64,
        units=[CanonicalUnit(unit_index=0, unit_type="page", width=612, height=792, coordinate_unit="pt", coordinate_origin="top-left")],
        paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text=paragraph_text)],
    )


def test_stable_hash_is_sha256_hex():
    digest = stable_canonical_hash(_minimal_document())
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_stable_hash_deterministic_across_fresh_instances():
    digest_a = stable_canonical_hash(_minimal_document())
    digest_b = stable_canonical_hash(_minimal_document())
    assert digest_a == digest_b


def test_stable_hash_changes_with_content():
    digest_a = stable_canonical_hash(_minimal_document("Hello world."))
    digest_b = stable_canonical_hash(_minimal_document("Goodbye world."))
    assert digest_a != digest_b


def test_compute_manifest_sha256_deterministic():
    manifest = {"a": 1, "b": [1, 2, 3], "c": {"nested": True}}
    assert compute_manifest_sha256(manifest) == compute_manifest_sha256(dict(manifest))


def test_compute_manifest_sha256_ignores_existing_hash_field():
    without_hash = {"a": 1, "b": 2}
    with_hash = {"a": 1, "b": 2, "manifest_sha256": "should_be_ignored"}
    assert compute_manifest_sha256(without_hash) == compute_manifest_sha256(with_hash)


def test_compute_manifest_sha256_differs_for_different_content():
    digest_a = compute_manifest_sha256({"a": 1})
    digest_b = compute_manifest_sha256({"a": 2})
    assert digest_a != digest_b


def test_compute_manifest_sha256_key_order_independent():
    digest_a = compute_manifest_sha256({"a": 1, "b": 2})
    digest_b = compute_manifest_sha256({"b": 2, "a": 1})
    assert digest_a == digest_b


def test_frozen_manifest_hash_is_computable_and_deterministic():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    digest_a = compute_manifest_sha256(manifest)
    digest_b = compute_manifest_sha256(manifest)
    assert digest_a == digest_b
    assert len(digest_a) == 64


def test_frozen_manifest_has_no_self_embedded_hash():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert "manifest_sha256" not in manifest


def test_canonical_hash_independent_of_benchmark_binding():
    """The same CanonicalDocument content must hash identically regardless of
    which manifest version/run it is later bound to for evaluation -- proves
    the hash depends only on extracted content, never on benchmark metadata."""
    doc = _minimal_document()
    digest = stable_canonical_hash(doc)

    binding_a = BenchmarkBinding(
        doc_id=doc.doc_id, canonical_document_hash=digest, run_id="run-a",
        manifest_version="1.2.1", manifest_sha256="b" * 64,
    )
    binding_b = BenchmarkBinding(
        doc_id=doc.doc_id, canonical_document_hash=digest, run_id="run-b",
        manifest_version="9.9.9-different", manifest_sha256="9" * 64,
    )

    # Re-hashing the same document content is unaffected by either binding.
    assert stable_canonical_hash(doc) == digest
    assert binding_a.canonical_document_hash == binding_b.canonical_document_hash == digest


def test_benchmark_binding_rejects_non_hex_manifest_sha256():
    with pytest.raises(ValidationError):
        BenchmarkBinding(
            doc_id="DOC1", canonical_document_hash="a" * 64, run_id="run-a",
            manifest_version="1.2.1", manifest_sha256="z" * 64,
        )


def test_benchmark_binding_rejects_non_hex_canonical_document_hash():
    with pytest.raises(ValidationError):
        BenchmarkBinding(
            doc_id="DOC1", canonical_document_hash="not-a-hash", run_id="run-a",
            manifest_version="1.2.1", manifest_sha256="a" * 64,
        )


def test_benchmark_binding_rejects_wrong_length_hash():
    with pytest.raises(ValidationError):
        BenchmarkBinding(
            doc_id="DOC1", canonical_document_hash="a" * 63, run_id="run-a",
            manifest_version="1.2.1", manifest_sha256="a" * 64,
        )


def test_benchmark_binding_rejects_uppercase_hash():
    with pytest.raises(ValidationError):
        BenchmarkBinding(
            doc_id="DOC1", canonical_document_hash="A" * 64, run_id="run-a",
            manifest_version="1.2.1", manifest_sha256="a" * 64,
        )


def test_canonical_document_rejects_non_hex_source_sha256():
    with pytest.raises(ValidationError):
        CanonicalDocument(
            doc_id="DOC1", source_format="pdf", source_filename="doc1.pdf",
            source_relative_path="parity/doc1.pdf", source_sha256="not-a-hash",
            units=[CanonicalUnit(unit_index=0, unit_type="page", width=1, height=1, coordinate_unit="pt", coordinate_origin="top-left")],
        )


def test_canonical_picture_rejects_non_hex_content_sha256():
    from ingestion_bench.canonical import CanonicalPicture

    with pytest.raises(ValidationError):
        CanonicalPicture(picture_id="pic1", unit_index=0, content_sha256="not-a-hash", artifact_ref="parity/pic1.png")


# --- stable_element_id -------------------------------------------------


def test_stable_element_id_deterministic():
    id_a = stable_element_id("DOC1", "paragraph", unit_index=0, order_index=1)
    id_b = stable_element_id("DOC1", "paragraph", unit_index=0, order_index=1)
    assert id_a == id_b


def test_stable_element_id_changes_with_identity_components():
    base = stable_element_id("DOC1", "paragraph", unit_index=0, order_index=1)
    different_unit = stable_element_id("DOC1", "paragraph", unit_index=1, order_index=1)
    different_order = stable_element_id("DOC1", "paragraph", unit_index=0, order_index=2)
    different_type = stable_element_id("DOC1", "heading", unit_index=0, order_index=1)
    different_doc = stable_element_id("DOC2", "paragraph", unit_index=0, order_index=1)
    different_discriminator = stable_element_id("DOC1", "paragraph", unit_index=0, order_index=1, discriminator="x")

    ids = {base, different_unit, different_order, different_type, different_doc, different_discriminator}
    assert len(ids) == 6, "every identity-component change must change the id"


def test_stable_element_id_extra_dict_insertion_order_independent():
    id_a = stable_element_id("DOC1", "annotation", unit_index=0, extra={"a": 1, "b": 2})
    id_b = stable_element_id("DOC1", "annotation", unit_index=0, extra={"b": 2, "a": 1})
    assert id_a == id_b


def test_stable_element_id_is_sha256_hex():
    digest = stable_element_id("DOC1", "picture", unit_index=0)
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_hashing_module_does_not_use_uuid4_or_builtin_hash():
    """stable_element_id must never call uuid4() (random) or Python's
    built-in hash() (unstable across processes). The module's own docstrings
    mention "uuid4" by name to document *why* it's avoided, so this checks
    for actual usage -- an `import uuid` statement, or a bare hash(...) call
    -- not just the word's presence anywhere in the file."""
    import ingestion_bench.canonical.hashing as hashing_module

    source = inspect.getsource(hashing_module)
    assert re.search(r"^\s*(import uuid|from uuid)", source, re.MULTILINE) is None, (
        "must not import uuid (would allow calling uuid4())"
    )
    assert re.search(r"(?<!\w)hash\(", source) is None, "must not call Python's builtin hash()"
