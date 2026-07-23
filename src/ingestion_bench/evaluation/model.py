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
    against the SAME expected facts and supporting chunks (D-040).

    Stage 6A.1 item 2: the catalog is COMPLETE -- one entry exists for
    EVERY expected manifest fact, not only matched ones. `match_status`
    distinguishes `"matched"` / `"partial"` / `"missing"` / `"not_applicable"`;
    a `"missing"` entry has empty evidence-id lists but is still present,
    so a future retrieval evaluation can distinguish "this was never
    ingested" (present here as `"missing"`) from "this was ingested but
    retrieval failed to surface it" (would be a retrieval-layer concern,
    not an ingestion one).

    Stage 6A.1 item 3: `expected_retrieval_difficulty` is deliberately
    UNCLASSIFIED (always `None`) in Stage 6A -- assigning a difficulty tag
    from ingestion-side signals alone (e.g. "appears more than once ->
    multi_hop") was premature inference not grounded in an actual
    retrieval question. Stage 6B assigns real difficulty to concrete
    benchmark questions built on top of this catalog."""

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
    # Stage 6A.1 item 3: nullable, always None until Stage 6B assigns real
    # difficulty to concrete benchmark questions -- never inferred here.
    expected_retrieval_difficulty: RetrievalDifficulty | None = None

    @model_validator(mode="after")
    def _validate_missing_has_no_evidence(self) -> "EvidenceAlignment":
        if self.match_status in ("missing", "not_applicable"):
            if self.matched_canonical_element_ids or self.matched_annotation_ids or self.matched_chunk_ids:
                raise ValueError(
                    f"match_status={self.match_status!r} must carry empty evidence-id lists "
                    f"(fact_id={self.fact_id!r})"
                )
        return self

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
    guess whether a metric is fuzzy/semantic (it never is).

    Metric-direction contract (Stage 6A.1 item 6): every MetricResult in
    this evaluator is HIGHER-IS-BETTER -- numerator counts the GOOD
    outcome (a match, a coverage hit, an absence of an unsupported claim),
    never the bad one. A metric that would naturally read as "count of
    problems" (e.g. duplicate text, missing z-order) is always phrased as
    its positive complement (e.g. `no_unexpected_text_duplication`,
    `overlap_z_order_recorded`) so `score * 100` can always be read as "%
    good" across the whole scorecard without checking each metric's
    polarity individually."""

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
    reinterpreted (Stage 6A section 14).

    Stage 6A.1 item 11: full input traceability. `canonical_document_hash`
    is `stable_canonical_hash()` (a semantic/content hash, unchanged from
    Stage 6A); the four `*_file_sha256` fields are raw-BYTES hashes of the
    actual Stage 5A artifact files this evaluation run read, so the exact
    input bytes are independently verifiable even for files (conversion
    report, raw Docling debug export) that have no canonical-model hash of
    their own. `determinism` is populated (never silently left `None`)
    whenever Stage 5A's own results.json supplied a determinism entry for
    this fixture (currently the three parity fixtures only)."""

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
    canonical_document_file_sha256: str
    canonical_chunks_file_sha256: str | None = None
    conversion_report_file_sha256: str
    raw_docling_debug_file_sha256: str | None = None
    artifact_completeness: dict[str, bool] = Field(default_factory=dict)


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
    # Stage 6A.1 item 2: the catalog is complete (every expected fact gets
    # an entry), so a status breakdown is meaningful evidence of that
    # completeness -- matched/partial/missing/not_applicable counts.
    evidence_alignment_count_by_status: dict[str, int] = Field(default_factory=dict)
    total_fixtures: int = Field(ge=0)


class EvaluationRun(BaseModel):
    """Stage 6A.1 item 11: `input_bundle_hash` is a deterministic SHA-256
    over every input this run actually read -- `manifest_sha256`,
    `stage5a_results_sha256`, and every fixture's own four
    `OperationalEvidence.*_file_sha256` values -- and `run_id` is itself
    derived from `input_bundle_hash` (never independent of it), so
    `run_id` genuinely identifies "this exact input bundle scored by this
    exact evaluator version," not just "a run happened.\""""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    input_bundle_hash: str
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
