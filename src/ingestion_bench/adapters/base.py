"""Parser-neutral adapter contract.

Depends only on ingestion_bench.canonical -- never on Docling, OpenAI, or
any parser-specific library. Every concrete adapter (Docling standard
local today; OpenAI vendor-native, OpenAI-enriched Docling, etc. later)
must return an AdapterConversionResult shaped exactly like this, so
nothing downstream (the chunker, a future evaluator) needs to know which
adapter produced it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from ingestion_bench.canonical import CanonicalDocument, ExtractionRun

# "success"   -- a fully validated CanonicalDocument was produced, no items skipped for cause.
# "partial"   -- a fully validated CanonicalDocument was produced, but one or more source
#                items were skipped or degraded (see diagnostics) -- never reported as success.
# "failed"    -- no CanonicalDocument could be produced; canonical_document is None and
#                extraction_run is None. errors explains why.
ConversionStatus = Literal["success", "partial", "failed"]


class AdapterDiagnostic(BaseModel):
    """One structured, deterministic record of a skipped, unsupported,
    degraded, or ambiguous mapping decision made while converting one
    source document. Every such decision gets one of these -- nothing is
    ever silently dropped."""

    model_config = ConfigDict(extra="forbid")

    category: str
    severity: Literal["info", "warning", "error"]
    message: str
    docling_self_ref: str | None = None
    unit_index: int | None = None


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
    elapsed_ms: float
    docling_version: str
    docling_core_version: str
    input_format: str
    source_relative_path: str
    source_sha256: str
    raw_docling_debug_artifact: str | None = None


class DocumentParserAdapter(Protocol):
    """Every parser adapter implements exactly this. source_root is used
    only to compute a portable, POSIX-style source_relative_path -- never
    to derive logical_document_id (that stays a benchmark-runner concern,
    supplied explicitly when building a DocumentRevisionContext for the
    chunker -- see scripts/run_docling_standard.py)."""

    def convert(self, source_path: Path, *, source_root: Path) -> AdapterConversionResult: ...
