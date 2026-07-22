"""Parser-neutral adapter contract.

Depends only on ingestion_bench.canonical -- never on Docling, OpenAI, or
any parser-specific library. Every concrete adapter (Docling standard
local today; OpenAI vendor-native, OpenAI-enriched Docling, etc. later)
must return an AdapterConversionResult shaped exactly like this, so
nothing downstream (the chunker, a future evaluator) needs to know which
adapter produced it.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ingestion_bench.canonical import CanonicalDocument, ExtractionRun
from ingestion_bench.canonical.model import validate_sha256_hex

# "success"   -- a fully validated CanonicalDocument was produced, no items skipped for cause.
# "partial"   -- a fully validated CanonicalDocument was produced, but Docling itself reported
#                PARTIAL_SUCCESS, or at least one diagnostic has affects_fidelity=True (see
#                AdapterDiagnostic) -- never derived from diagnostic severity alone (Stage 5A.1).
# "failed"    -- no CanonicalDocument could be produced; canonical_document is None and
#                extraction_run is None. errors explains why.
ConversionStatus = Literal["success", "partial", "failed"]


def _validate_portable_relative_path(value: str, field_name: str) -> str:
    """Same portability rule as ingestion_bench.canonical.model's private
    helper of the same shape -- reimplemented locally rather than reaching
    into that module's underscore-prefixed (non-public) function, since
    ingestion_bench.canonical is a frozen contract this package must not
    modify or depend on beyond its explicitly public surface."""
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    if "\\" in value:
        raise ValueError(f"{field_name} must use normalized POSIX-style separators ('/'), not backslashes: {value!r}")
    if PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute():
        raise ValueError(f"{field_name} must be a relative, portable reference, not an absolute path: {value!r}")
    if ".." in PurePosixPath(value).parts:
        raise ValueError(f"{field_name} must not contain '..' path traversal components: {value!r}")
    return value


class AdapterDiagnostic(BaseModel):
    """One structured, deterministic record of a skipped, unsupported,
    degraded, or ambiguous mapping decision made while converting one
    source document. Every such decision gets one of these -- nothing is
    ever silently dropped.

    severity and affects_fidelity are deliberately independent axes
    (Stage 5A.1): severity describes operational seriousness (would an
    operator want to be alerted?); affects_fidelity describes whether
    source content, structure, provenance, or relationships were actually
    lost or degraded in the resulting CanonicalDocument. An "info"-severity
    diagnostic can still affect fidelity (e.g. DOCX pagination collapsing
    to one unit is unsurprising and not alarming, but it IS a real loss of
    page-boundary information) -- conversion_status is derived from
    affects_fidelity, never from severity alone. See
    docs/POC_DECISION_LOG.md D-037."""

    model_config = ConfigDict(extra="forbid")

    category: str
    severity: Literal["info", "warning", "error"]
    message: str
    docling_self_ref: str | None = None
    unit_index: int | None = None
    affects_fidelity: bool = False


class AdapterConversionResult(BaseModel):
    """Strict result of converting exactly one source document through one
    parser adapter.

    Fields that must be inspectable even when conversion FAILS (no
    CanonicalDocument was ever produced) live directly on this model:
    elapsed_ms, docling_version, docling_core_version, input_format,
    source_relative_path, source_sha256, diagnostics, errors,
    raw_docling_debug_artifact. Concepts that are only meaningful once a
    CanonicalDocument actually exists -- run_id, timing duplicated in
    richer form, warnings, raw_artifact_refs, canonical_document_hash,
    model_artifacts, remote_inference_calls -- reuse ExtractionRun
    (ingestion_bench.canonical.extraction_run) rather than duplicating
    those concepts here; extraction_run is None exactly when
    conversion_status == "failed".
    """

    model_config = ConfigDict(extra="forbid")

    canonical_document: CanonicalDocument | None
    extraction_run: ExtractionRun | None
    conversion_status: ConversionStatus
    diagnostics: list[AdapterDiagnostic] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    elapsed_ms: float = Field(ge=0)
    docling_version: str
    docling_core_version: str
    input_format: str
    source_relative_path: str
    source_sha256: str
    raw_docling_debug_artifact: str | None = None

    @field_validator("source_sha256")
    @classmethod
    def _source_sha256_is_valid(cls, v: str) -> str:
        return validate_sha256_hex(v, "source_sha256")

    @field_validator("source_relative_path")
    @classmethod
    def _source_relative_path_is_portable(cls, v: str) -> str:
        return _validate_portable_relative_path(v, "source_relative_path")

    @model_validator(mode="after")
    def _validate_status_matches_document_presence(self) -> AdapterConversionResult:
        if self.conversion_status == "failed":
            if self.canonical_document is not None or self.extraction_run is not None:
                raise ValueError(
                    "conversion_status='failed' requires canonical_document and extraction_run "
                    "to both be None"
                )
        else:
            if self.canonical_document is None or self.extraction_run is None:
                raise ValueError(
                    f"conversion_status={self.conversion_status!r} requires both canonical_document "
                    "and extraction_run to be present"
                )
        return self


class DocumentParserAdapter(Protocol):
    """Every parser adapter implements exactly this. source_root is used
    only to compute a portable, POSIX-style source_relative_path -- never
    to derive logical_document_id (that stays a benchmark-runner concern,
    supplied explicitly when building a DocumentRevisionContext for the
    chunker -- see scripts/run_docling_standard.py)."""

    def convert(self, source_path: Path, *, source_root: Path) -> AdapterConversionResult: ...
