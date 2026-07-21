"""Explicit link between extracted content and the manifest it is evaluated
against.

Deliberately NOT part of canonical/: the architectural rule is that
CanonicalDocument says what was extracted, reference_manifest.json says what
should have been extracted, and the evaluator compares the two. Neither side
should know about the other. BenchmarkBinding is the third, separate thing
that carries the link between them, so an evaluator can look up "which
manifest version should this canonical document be scored against" without
CanonicalDocument (or ExtractionRun) ever needing a manifest_version/
manifest_sha256 field of its own -- which would also leak into
stable_canonical_hash(), making it depend on benchmark metadata rather than
purely on extracted content.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator

from .canonical.model import validate_sha256_hex


class BenchmarkBinding(BaseModel):
    doc_id: str
    # Pins the exact extracted content (not just doc_id, which could in
    # principle be reprocessed into different content across runs).
    canonical_document_hash: str
    # Which ExtractionRun produced that canonical_document_hash.
    run_id: str
    manifest_version: str
    manifest_sha256: str

    @field_validator("canonical_document_hash")
    @classmethod
    def _canonical_document_hash_is_valid(cls, v: str) -> str:
        return validate_sha256_hex(v, "canonical_document_hash")

    @field_validator("manifest_sha256")
    @classmethod
    def _manifest_sha256_is_valid(cls, v: str) -> str:
        return validate_sha256_hex(v, "manifest_sha256")
