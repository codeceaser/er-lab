"""Strict Pydantic validation tests for ingestion_bench.evaluation.model
(Stage 6A section 3). No Docling, no real artifacts -- pure model tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ingestion_bench.evaluation.model import (
    EvaluationRun,
    EvidenceAlignment,
    FixtureEvaluationResult,
    MetricResult,
    MissRecord,
    OperationalEvidence,
)


def _operational(**overrides) -> OperationalEvidence:
    kwargs = dict(
        conversion_status="success", elapsed_ms=10.0, unit_count=1, heading_count=0, paragraph_count=1,
        list_item_count=0, table_count=0, table_cell_count=0, picture_count=0, caption_count=0,
        provenance_count=1, canonical_chunk_count=1, textual_chunk_count=1, asset_only_chunk_count=0,
        canonical_document_hash="a" * 64, canonical_document_file_sha256="b" * 64,
        canonical_chunks_file_sha256="c" * 64, conversion_report_file_sha256="d" * 64,
        raw_docling_debug_file_sha256="e" * 64, artifact_completeness={"canonical_document": True},
    )
    kwargs.update(overrides)
    return OperationalEvidence(**kwargs)


# --- MetricResult --------------------------------------------------------


def test_metric_result_accepts_consistent_score():
    m = MetricResult(metric_name="x", matching_rule="r", numerator=2, denominator=4, score=0.5)
    assert m.score == 0.5


def test_metric_result_rejects_score_when_denominator_zero():
    with pytest.raises(ValidationError):
        MetricResult(metric_name="x", matching_rule="r", numerator=0, denominator=0, score=0.0)


def test_metric_result_score_none_when_denominator_zero_is_valid():
    m = MetricResult(metric_name="x", matching_rule="r", numerator=0, denominator=0, score=None, excluded_not_applicable=3)
    assert m.score is None
    assert m.excluded_not_applicable == 3


def test_metric_result_requires_score_when_denominator_positive():
    with pytest.raises(ValidationError):
        MetricResult(metric_name="x", matching_rule="r", numerator=1, denominator=2, score=None)


def test_metric_result_rejects_numerator_greater_than_denominator():
    with pytest.raises(ValidationError):
        MetricResult(metric_name="x", matching_rule="r", numerator=5, denominator=2, score=2.5)


def test_metric_result_rejects_incorrect_score():
    with pytest.raises(ValidationError):
        MetricResult(metric_name="x", matching_rule="r", numerator=1, denominator=2, score=0.9)


def test_metric_result_rejects_nan_score():
    with pytest.raises(ValidationError):
        MetricResult(metric_name="x", matching_rule="r", numerator=1, denominator=2, score=float("nan"))


def test_metric_result_rejects_infinite_score():
    with pytest.raises(ValidationError):
        MetricResult(metric_name="x", matching_rule="r", numerator=1, denominator=2, score=float("inf"))


def test_metric_result_rejects_negative_numerator():
    with pytest.raises(ValidationError):
        MetricResult(metric_name="x", matching_rule="r", numerator=-1, denominator=2, score=0.0)


def test_metric_result_forbids_extra_fields():
    with pytest.raises(ValidationError):
        MetricResult(metric_name="x", matching_rule="r", numerator=1, denominator=1, score=1.0, unexpected_field=True)


# --- MissRecord ------------------------------------------------------------


def test_miss_record_requires_portable_fixture():
    with pytest.raises(ValidationError):
        MissRecord(
            fixture="C:\\abs\\path.pdf", fact_id="F1", metric="m", result="miss",
            failure_class="parser_content_loss", explanation="e", confidence="certain",
        )


def test_miss_record_mapper_loss_requires_raw_docling_reference():
    with pytest.raises(ValidationError):
        MissRecord(
            fixture="parity/PARITY_001.pdf", fact_id="F1", metric="m", result="miss",
            failure_class="mapper_loss", explanation="e", confidence="certain",
            raw_docling_references=[],
        )


def test_miss_record_mapper_loss_accepted_with_raw_docling_reference():
    record = MissRecord(
        fixture="parity/PARITY_001.pdf", fact_id="F1", metric="m", result="miss",
        failure_class="mapper_loss", explanation="e", confidence="certain",
        raw_docling_references=["#/texts/3"],
    )
    assert record.failure_class == "mapper_loss"


def test_miss_record_rejects_unknown_failure_class():
    with pytest.raises(ValidationError):
        MissRecord(
            fixture="parity/PARITY_001.pdf", fact_id="F1", metric="m", result="miss",
            failure_class="totally_made_up", explanation="e", confidence="certain",
        )


# --- EvidenceAlignment / FixtureEvaluationResult ----------------------------


def _alignment(fact_id: str) -> EvidenceAlignment:
    return EvidenceAlignment(
        fact_id=fact_id, fixture="parity/PARITY_001.pdf", fact_type="paragraph", match_status="matched",
        derivation="source_derived", expected_retrieval_difficulty="direct",
    )


def test_fixture_evaluation_result_rejects_duplicate_evidence_alignment_fact_ids():
    with pytest.raises(ValidationError):
        FixtureEvaluationResult(
            fixture="parity/PARITY_001.pdf", doc_id="PARITY_001", source_format="pdf",
            operational=_operational(), evidence_alignments=[_alignment("F1"), _alignment("F1")],
        )


def test_fixture_evaluation_result_accepts_unique_evidence_alignment_fact_ids():
    result = FixtureEvaluationResult(
        fixture="parity/PARITY_001.pdf", doc_id="PARITY_001", source_format="pdf",
        operational=_operational(), evidence_alignments=[_alignment("F1"), _alignment("F2")],
    )
    assert len(result.evidence_alignments) == 2


def test_fixture_evaluation_result_forbids_extra_fields():
    with pytest.raises(ValidationError):
        FixtureEvaluationResult(
            fixture="parity/PARITY_001.pdf", doc_id="PARITY_001", source_format="pdf",
            operational=_operational(), unexpected="nope",
        )


# --- EvaluationRun -----------------------------------------------------------


def _fixture_result(fixture: str) -> FixtureEvaluationResult:
    return FixtureEvaluationResult(fixture=fixture, doc_id="X", source_format="pdf", operational=_operational())


def test_evaluation_run_rejects_duplicate_fixtures():
    from ingestion_bench.evaluation.model import AggregateEvaluationResult

    with pytest.raises(ValidationError):
        EvaluationRun(
            run_id="r" * 64, input_bundle_hash="i" * 64, evaluation_content_hash="c" * 64,
            generated_at="2026-01-01T00:00:00+00:00", manifest_version="1.2.1", manifest_sha256="a" * 64,
            stage5a_results_sha256="b" * 64, evaluator_version="1.0.0",
            fixture_results=[_fixture_result("parity/PARITY_001.pdf"), _fixture_result("parity/PARITY_001.pdf")],
            aggregate=AggregateEvaluationResult(evidence_alignment_count=0, total_fixtures=2),
        )


# --- hash field validation (Stage 6A.2 item 5) ------------------------------


def _valid_run_kwargs(**overrides) -> dict:
    from ingestion_bench.evaluation.model import AggregateEvaluationResult

    kwargs = dict(
        run_id="a" * 64, input_bundle_hash="b" * 64, evaluation_content_hash="c" * 64,
        generated_at="2026-01-01T00:00:00+00:00", manifest_version="1.2.1", manifest_sha256="d" * 64,
        stage5a_results_sha256="e" * 64, evaluator_version="1.0.0",
        fixture_results=[_fixture_result("parity/PARITY_001.pdf")],
        aggregate=AggregateEvaluationResult(evidence_alignment_count=0, total_fixtures=1),
    )
    kwargs.update(overrides)
    return kwargs


@pytest.mark.parametrize("field", ["run_id", "input_bundle_hash", "evaluation_content_hash", "manifest_sha256", "stage5a_results_sha256"])
def test_evaluation_run_rejects_malformed_hash_fields(field):
    for bad_value in ["not-a-hash", "A" * 64, "a" * 63, "a" * 65, "g" * 64, ""]:
        with pytest.raises(ValidationError):
            EvaluationRun(**_valid_run_kwargs(**{field: bad_value}))


def test_evaluation_run_accepts_well_formed_hash_fields():
    run = EvaluationRun(**_valid_run_kwargs())
    assert run.run_id == "a" * 64


@pytest.mark.parametrize("field", ["canonical_document_hash", "canonical_document_file_sha256", "conversion_report_file_sha256"])
def test_operational_evidence_rejects_malformed_required_hash_fields(field):
    for bad_value in ["not-a-hash", "A" * 64, "a" * 63, "g" * 64]:
        with pytest.raises(ValidationError):
            _operational(**{field: bad_value})


@pytest.mark.parametrize("field", ["canonical_chunks_file_sha256", "raw_docling_debug_file_sha256"])
def test_operational_evidence_rejects_malformed_optional_hash_fields_when_present(field):
    with pytest.raises(ValidationError):
        _operational(**{field: "not-a-hash"})


def test_operational_evidence_accepts_none_for_optional_hash_fields():
    op = _operational(canonical_chunks_file_sha256=None, raw_docling_debug_file_sha256=None)
    assert op.canonical_chunks_file_sha256 is None
    assert op.raw_docling_debug_file_sha256 is None
