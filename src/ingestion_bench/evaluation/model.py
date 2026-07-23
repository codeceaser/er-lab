"""Strict Pydantic models for the Stage 6A deterministic ingestion-fidelity
evaluator.

Depends only on stdlib -- never on Docling, OpenAI, embeddings, or any
retrieval/graph/wiki concept. This module describes the SHAPE of an
evaluation result; ingestion_bench.evaluation.evaluator is what actually
compares reference_manifest.json against Stage 5A CanonicalDocument/
CanonicalChunk output to populate these models.
"""

from __future__ import annotations

import math
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Controlled miss-classification vocabulary (Stage 6A section 15) -- never
# freeform strings, so every miss ledger entry is machine-groupable.
FailureClass = Literal[
    "parser_content_loss",
    "parser_classification_loss",
    "parser_structure_loss",
    "parser_relationship_loss",
    "parser_provenance_loss",
    "mapper_loss",
    "chunk_projection_loss",
    "unexpected_content",
    "distractor_false_positive",
    "expected_not_applicable_to_lane",
    "evaluation_contract_insufficient",
    "unresolved",
]

ConfidenceLevel = Literal["certain", "supported", "unresolved"]
MatchStatus = Literal["matched", "partial", "missing", "not_applicable"]
DerivationClass = Literal["source_derived", "model_derived", "not_applicable"]
RetrievalDifficulty = Literal["direct", "relational", "multi_hop", "consolidation", "distractor_sensitive"]
MissResult = Literal["miss", "partial", "unexpected"]


def _validate_portable_fixture_ref(value: str, field_name: str = "fixture") -> str:
    """Same portability rule used throughout this project (canonical/
    model.py, adapters/base.py) -- reimplemented locally rather than
    importing a private helper, since this package's only dependency on
    canonical/chunking is their public model types (see evaluator.py)."""
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    if "\\" in value:
        raise ValueError(f"{field_name} must use normalized POSIX-style separators ('/'), not backslashes: {value!r}")
    if PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute():
        raise ValueError(f"{field_name} must be a relative, portable reference, not an absolute path: {value!r}")
    if ".." in PurePosixPath(value).parts:
        raise ValueError(f"{field_name} must not contain '..' path traversal components: {value!r}")
    return value


class FactExpectation(BaseModel):
    """One expected fact read directly from reference_manifest.json (never
    invented) -- see evaluator.py for the exact manifest field each
    fact_type is derived from."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str
    fixture: str
    fact_type: str
    expected_value: dict = Field(default_factory=dict)
    expected_location: dict = Field(default_factory=dict)
    is_distractor: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def _validate_fixture_portable(self) -> "FactExpectation":
        _validate_portable_fixture_ref(self.fixture)
        return self


class FactObservation(BaseModel):
    """What was actually found in Stage 5A output for one FactExpectation."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str
    fixture: str
    matched: bool
    matched_element_ids: list[str] = Field(default_factory=list)
    matched_annotation_ids: list[str] = Field(default_factory=list)
    matched_chunk_ids: list[str] = Field(default_factory=list)
    observed_value: dict | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _validate_fixture_portable(self) -> "FactObservation":
        _validate_portable_fixture_ref(self.fixture)
        return self


class EvidenceAlignment(BaseModel):
    """One entry of the Stage 6A gold fact-to-evidence-alignment catalog
    (section 16) -- reusable later to evaluate vector/graph/wiki retrieval
    against the SAME expected facts and supporting chunks (D-040)."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str
    fixture: str
    fact_type: str
    expected_value: dict = Field(default_factory=dict)
    expected_location: dict = Field(default_factory=dict)
    matched_canonical_element_ids: list[str] = Field(default_factory=list)
    matched_annotation_ids: list[str] = Field(default_factory=list)
    matched_chunk_ids: list[str] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)
    unit_indexes: list[int] = Field(default_factory=list)
    match_status: MatchStatus
    derivation: DerivationClass
    expected_retrieval_difficulty: RetrievalDifficulty

    @model_validator(mode="after")
    def _validate_fixture_portable(self) -> "EvidenceAlignment":
        _validate_portable_fixture_ref(self.fixture)
        return self


class MissRecord(BaseModel):
    """One row of the Stage 6A machine-readable miss ledger (section 15).
    A mapper_loss classification must never be assigned without supporting
    raw Docling evidence -- see classification.py::classify_text_absence,
    the only place failure_class="mapper_loss" is ever produced, and it is
    always paired with a non-empty raw_docling_references entry."""

    model_config = ConfigDict(extra="forbid")

    fixture: str
    fact_id: str
    metric: str
    expected_value: dict | None = None
    observed_value: dict | None = None
    result: MissResult
    failure_class: FailureClass
    explanation: str
    supporting_canonical_element_ids: list[str] = Field(default_factory=list)
    supporting_chunk_ids: list[str] = Field(default_factory=list)
    raw_docling_references: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel

    @model_validator(mode="after")
    def _validate_fixture_portable(self) -> "MissRecord":
        _validate_portable_fixture_ref(self.fixture)
        return self

    @model_validator(mode="after")
    def _validate_mapper_loss_has_raw_evidence(self) -> "MissRecord":
        if self.failure_class == "mapper_loss" and not self.raw_docling_references:
            raise ValueError(
                "failure_class='mapper_loss' must never be assigned without at least one "
                "raw_docling_references entry as supporting evidence"
            )
        return self


class UnexpectedObservation(BaseModel):
    """A canonical element with no corresponding manifest expectation --
    e.g. Docling's DOCX backend duplicating a table header cell's text as
    a standalone body paragraph (a real finding, not hypothetical -- see
    reports/stage6a_docling_baseline_scorecard.md)."""

    model_config = ConfigDict(extra="forbid")

    fixture: str
    element_id: str
    element_type: str
    text: str
    reason: str

    @model_validator(mode="after")
    def _validate_fixture_portable(self) -> "UnexpectedObservation":
        _validate_portable_fixture_ref(self.fixture)
        return self


class MetricResult(BaseModel):
    """One scored metric. score is None exactly when denominator == 0 --
    a metric with no applicable expectations is never silently reported as
    0%. matching_rule documents, in one line, the exact normalization/
    matching rule used (see normalization.py) so a reader never has to
    guess whether a metric is fuzzy/semantic (it never is)."""

    model_config = ConfigDict(extra="forbid")

    metric_name: str
    matching_rule: str
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    excluded_not_applicable: int = Field(ge=0, default=0)
    score: float | None = None
    supporting_matches: list[str] = Field(default_factory=list)
    supporting_misses: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_numerator_denominator(self) -> "MetricResult":
        if self.numerator > self.denominator:
            raise ValueError(f"numerator ({self.numerator}) must be <= denominator ({self.denominator})")
        return self

    @model_validator(mode="after")
    def _validate_score(self) -> "MetricResult":
        if self.denominator == 0:
            if self.score is not None:
                raise ValueError("score must be None when denominator == 0 (no applicable expectations)")
            return self
        if self.score is None:
            raise ValueError("score must be populated when denominator > 0")
        if not math.isfinite(self.score):
            raise ValueError(f"score must be finite, got {self.score!r}")
        expected = self.numerator / self.denominator
        if abs(self.score - expected) > 1e-9:
            raise ValueError(f"score ({self.score!r}) must equal numerator/denominator ({expected!r})")
        return self


class OperationalEvidence(BaseModel):
    """Copied and validated from Stage 5A evidence -- never recomputed or
    reinterpreted (Stage 6A section 14)."""

    model_config = ConfigDict(extra="forbid")

    conversion_status: Literal["success", "partial", "failed"]
    elapsed_ms: float = Field(ge=0)
    diagnostics_by_category: dict[str, int] = Field(default_factory=dict)
    diagnostics_by_severity: dict[str, int] = Field(default_factory=dict)
    diagnostics_by_affects_fidelity: dict[str, int] = Field(default_factory=dict)
    unit_count: int = Field(ge=0)
    heading_count: int = Field(ge=0)
    paragraph_count: int = Field(ge=0)
    list_item_count: int = Field(ge=0)
    table_count: int = Field(ge=0)
    table_cell_count: int = Field(ge=0)
    picture_count: int = Field(ge=0)
    caption_count: int = Field(ge=0)
    annotation_counts: dict = Field(default_factory=dict)
    provenance_count: int = Field(ge=0)
    canonical_chunk_count: int = Field(ge=0)
    textual_chunk_count: int = Field(ge=0)
    asset_only_chunk_count: int = Field(ge=0)
    canonical_document_hash: str
    determinism: dict | None = None


class FixtureEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture: str
    doc_id: str
    source_format: Literal["docx", "pdf", "pptx"]
    operational: OperationalEvidence
    metrics: dict[str, MetricResult] = Field(default_factory=dict)
    miss_records: list[MissRecord] = Field(default_factory=list)
    unexpected_observations: list[UnexpectedObservation] = Field(default_factory=list)
    evidence_alignments: list[EvidenceAlignment] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_fixture_portable(self) -> "FixtureEvaluationResult":
        _validate_portable_fixture_ref(self.fixture)
        return self

    @model_validator(mode="after")
    def _validate_evidence_alignment_fact_ids_unique(self) -> "FixtureEvaluationResult":
        seen: set[str] = set()
        for alignment in self.evidence_alignments:
            if alignment.fact_id in seen:
                raise ValueError(f"duplicate fact_id in evidence_alignments: {alignment.fact_id!r}")
            seen.add(alignment.fact_id)
        return self


class AggregateEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrics_by_format: dict[str, dict[str, MetricResult]] = Field(default_factory=dict)
    miss_count_by_classification: dict[str, int] = Field(default_factory=dict)
    evidence_alignment_count: int = Field(ge=0)
    total_fixtures: int = Field(ge=0)


class EvaluationRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    generated_at: str
    manifest_version: str
    manifest_sha256: str
    stage5a_results_sha256: str
    evaluator_version: str
    fixture_results: list[FixtureEvaluationResult]
    aggregate: AggregateEvaluationResult

    @model_validator(mode="after")
    def _validate_fixtures_unique(self) -> "EvaluationRun":
        seen: set[str] = set()
        for result in self.fixture_results:
            if result.fixture in seen:
                raise ValueError(f"duplicate fixture in fixture_results: {result.fixture!r}")
            seen.add(result.fixture)
        return self
