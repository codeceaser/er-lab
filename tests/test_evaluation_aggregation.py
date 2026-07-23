"""Tests for ingestion_bench.evaluation.aggregation (Stage 6A sections 17
and 18): deterministic aggregate output, one-execution report generation,
no-applicable-denominator behaviour surfacing correctly in the rendered
Markdown, and miss-classification/evidence-alignment counting."""

from __future__ import annotations

from ingestion_bench.evaluation.aggregation import (
    aggregate_metrics_by_format,
    build_aggregate,
    build_evaluation_run,
    build_evidence_alignment_catalog,
    build_miss_ledger,
    render_scorecard_markdown,
)
from ingestion_bench.evaluation.model import (
    EvidenceAlignment,
    FixtureEvaluationResult,
    MetricResult,
    MissRecord,
    OperationalEvidence,
)


def _operational(status: str = "success", **overrides) -> OperationalEvidence:
    kwargs = dict(
        conversion_status=status, elapsed_ms=1.0, unit_count=1, heading_count=0, paragraph_count=1,
        list_item_count=0, table_count=0, table_cell_count=0, picture_count=0, caption_count=0,
        provenance_count=1, canonical_chunk_count=1, textual_chunk_count=1, asset_only_chunk_count=0,
        canonical_document_hash="a" * 64, canonical_document_file_sha256="b" * 64,
        canonical_chunks_file_sha256="c" * 64, conversion_report_file_sha256="d" * 64,
        raw_docling_debug_file_sha256="e" * 64, artifact_completeness={"canonical_document": True},
    )
    kwargs.update(overrides)
    return OperationalEvidence(**kwargs)


def _metric(numerator: int, denominator: int) -> MetricResult:
    score = None if denominator == 0 else numerator / denominator
    return MetricResult(metric_name="text_fact_recall", matching_rule="TEXT_NORMALIZED_V1", numerator=numerator, denominator=denominator, score=score)


def _pdf_result() -> FixtureEvaluationResult:
    return FixtureEvaluationResult(
        fixture="parity/PARITY_001.pdf", doc_id="PARITY_001", source_format="pdf", operational=_operational(),
        metrics={"text_fact_recall": _metric(4, 5)},
        miss_records=[
            MissRecord(
                fixture="parity/PARITY_001.pdf", fact_id="P_999", metric="text_fact_recall", result="miss",
                failure_class="parser_content_loss", explanation="e", confidence="certain",
            )
        ],
        evidence_alignments=[
            EvidenceAlignment(
                fact_id="P_001", fixture="parity/PARITY_001.pdf", fact_type="paragraph", match_status="matched",
                derivation="source_derived", expected_retrieval_difficulty="direct",
            )
        ],
    )


def _docx_result() -> FixtureEvaluationResult:
    return FixtureEvaluationResult(
        fixture="parity/PARITY_001.docx", doc_id="PARITY_001", source_format="docx", operational=_operational("partial"),
        metrics={"text_fact_recall": _metric(0, 0)},  # zero applicable expectations for this format
    )


def test_aggregate_metrics_by_format_sums_numerator_and_denominator():
    by_format = aggregate_metrics_by_format([_pdf_result()])
    assert by_format["pdf"]["text_fact_recall"].numerator == 4
    assert by_format["pdf"]["text_fact_recall"].denominator == 5
    assert by_format["overall"]["text_fact_recall"].numerator == 4


def test_aggregate_metrics_by_format_never_forces_score_when_all_denominators_zero():
    by_format = aggregate_metrics_by_format([_docx_result()])
    assert by_format["docx"]["text_fact_recall"].denominator == 0
    assert by_format["docx"]["text_fact_recall"].score is None


def test_aggregate_metrics_by_format_mixed_denominators_still_sums_correctly():
    by_format = aggregate_metrics_by_format([_pdf_result(), _docx_result()])
    # pdf contributes 4/5; docx contributes 0/0 -- overall must be 4/5, not distorted by the zero-denominator fixture.
    assert by_format["overall"]["text_fact_recall"].numerator == 4
    assert by_format["overall"]["text_fact_recall"].denominator == 5


def test_build_aggregate_counts_misses_by_classification():
    aggregate = build_aggregate([_pdf_result()])
    assert aggregate.miss_count_by_classification == {"parser_content_loss": 1}
    assert aggregate.evidence_alignment_count == 1
    assert aggregate.total_fixtures == 1


def test_build_evaluation_run_is_deterministic():
    manifest = {"manifest_version": "1.2.1"}
    run_a = build_evaluation_run([_pdf_result()], manifest, "1" * 64, "2" * 64)
    run_b = build_evaluation_run([_pdf_result()], manifest, "1" * 64, "2" * 64)
    assert run_a.run_id == run_b.run_id


def test_build_evaluation_run_id_changes_with_different_input_file_hash():
    """Stage 6A.1 item 11: run_id is derived from input_bundle_hash, which
    is itself a pure function of every input FILE's own bytes hash (not
    the semantic canonical_document_hash) -- changing the file hash must
    change both input_bundle_hash and run_id."""
    manifest = {"manifest_version": "1.2.1"}
    result_a = _pdf_result()
    result_b = result_a.model_copy(update={"operational": _operational(canonical_document_file_sha256="f" * 64)})
    run_a = build_evaluation_run([result_a], manifest, "1" * 64, "2" * 64)
    run_b = build_evaluation_run([result_b], manifest, "1" * 64, "2" * 64)
    assert run_a.run_id != run_b.run_id
    assert run_a.input_bundle_hash != run_b.input_bundle_hash


# --- evaluation_content_hash (Stage 6A.2 item 4) ----------------------------


def test_evaluation_content_hash_stable_for_identical_inputs_and_results():
    manifest = {"manifest_version": "1.2.1"}
    run_a = build_evaluation_run([_pdf_result()], manifest, "1" * 64, "2" * 64)
    run_b = build_evaluation_run([_pdf_result()], manifest, "1" * 64, "2" * 64)
    assert run_a.evaluation_content_hash == run_b.evaluation_content_hash


def test_evaluation_content_hash_unaffected_by_generated_at():
    """generated_at is mutable runtime/report metadata -- two runs that
    differ ONLY in when they happened must share the same
    evaluation_content_hash."""
    manifest = {"manifest_version": "1.2.1"}
    run = build_evaluation_run([_pdf_result()], manifest, "1" * 64, "2" * 64)
    mutated = run.model_copy(update={"generated_at": "2099-01-01T00:00:00+00:00"})
    assert mutated.generated_at != run.generated_at
    assert mutated.evaluation_content_hash == run.evaluation_content_hash


def test_evaluation_content_hash_changes_with_a_metric_change():
    manifest = {"manifest_version": "1.2.1"}
    result_a = _pdf_result()
    result_b = result_a.model_copy(update={"metrics": {"text_fact_recall": _metric(3, 5)}})
    run_a = build_evaluation_run([result_a], manifest, "1" * 64, "2" * 64)
    run_b = build_evaluation_run([result_b], manifest, "1" * 64, "2" * 64)
    assert run_a.evaluation_content_hash != run_b.evaluation_content_hash


def test_evaluation_content_hash_changes_with_an_evidence_alignment_change():
    manifest = {"manifest_version": "1.2.1"}
    result_a = _pdf_result()
    result_b = result_a.model_copy(update={
        "evidence_alignments": [
            EvidenceAlignment(
                fact_id="P_001", fixture="parity/PARITY_001.pdf", fact_type="paragraph",
                match_status="missing", derivation="not_applicable",
            ),
        ],
    })
    run_a = build_evaluation_run([result_a], manifest, "1" * 64, "2" * 64)
    run_b = build_evaluation_run([result_b], manifest, "1" * 64, "2" * 64)
    assert run_a.evaluation_content_hash != run_b.evaluation_content_hash


def test_evaluation_content_hash_changes_with_an_input_artifact_hash_change():
    manifest = {"manifest_version": "1.2.1"}
    result_a = _pdf_result()
    result_b = result_a.model_copy(update={"operational": _operational(canonical_document_file_sha256="f" * 64)})
    run_a = build_evaluation_run([result_a], manifest, "1" * 64, "2" * 64)
    run_b = build_evaluation_run([result_b], manifest, "1" * 64, "2" * 64)
    assert run_a.evaluation_content_hash != run_b.evaluation_content_hash


def test_evaluation_content_hash_changes_with_evaluator_version():
    from ingestion_bench.evaluation.aggregation import _compute_evaluation_content_hash

    aggregate = build_aggregate([_pdf_result()])
    hash_a = _compute_evaluation_content_hash("bundle" * 8, "1.1.0", "1.2.1", "1" * 64, "2" * 64, [_pdf_result()], aggregate)
    hash_b = _compute_evaluation_content_hash("bundle" * 8, "1.2.0", "1.2.1", "1" * 64, "2" * 64, [_pdf_result()], aggregate)
    assert hash_a != hash_b


def test_miss_ledger_contains_every_scored_miss():
    manifest = {"manifest_version": "1.2.1"}
    run = build_evaluation_run([_pdf_result()], manifest, "1" * 64, "2" * 64)
    ledger = build_miss_ledger(run)
    assert ledger["total_misses"] == 1
    assert ledger["entries"][0]["fact_id"] == "P_999"


def test_evidence_alignment_catalog_contains_every_matched_fact():
    manifest = {"manifest_version": "1.2.1"}
    run = build_evaluation_run([_pdf_result()], manifest, "1" * 64, "2" * 64)
    catalog = build_evidence_alignment_catalog(run)
    assert [e["fact_id"] for e in catalog] == ["P_001"]


def test_scorecard_markdown_renders_na_for_zero_denominator_never_zero_percent():
    manifest = {"manifest_version": "1.2.1"}
    run = build_evaluation_run([_docx_result()], manifest, "1" * 64, "2" * 64)
    markdown = render_scorecard_markdown(run)
    assert "n/a" in markdown
    assert "0.0%" not in markdown


def test_scorecard_and_json_come_from_the_same_run_object():
    """The Markdown table's numbers must be traceable to exactly the same
    EvaluationRun the JSON would serialize -- proven here by checking the
    rendered numerator/denominator match the run's own aggregate."""
    manifest = {"manifest_version": "1.2.1"}
    run = build_evaluation_run([_pdf_result()], manifest, "1" * 64, "2" * 64)
    markdown = render_scorecard_markdown(run)
    metric = run.aggregate.metrics_by_format["overall"]["text_fact_recall"]
    assert f"({metric.numerator}/{metric.denominator})" in markdown


def test_scorecard_markdown_lists_every_fixture():
    manifest = {"manifest_version": "1.2.1"}
    run = build_evaluation_run([_pdf_result(), _docx_result()], manifest, "1" * 64, "2" * 64)
    markdown = render_scorecard_markdown(run)
    assert "parity/PARITY_001.pdf" in markdown
    assert "parity/PARITY_001.docx" in markdown
