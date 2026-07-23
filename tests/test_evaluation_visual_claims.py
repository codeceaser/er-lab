"""Stage 6A.2 item 2: unsupported visual claims must be matched
INDIVIDUALLY against actual VisualFactAnnotation output -- the presence
of any VisualFactAnnotation must never be used as blanket evidence that
every unsupported claim was asserted. Uses hand-built CanonicalDocument
objects, no real Docling artifacts needed."""

from __future__ import annotations

from ingestion_bench.canonical import CanonicalDocument, CanonicalPicture, CanonicalUnit
from ingestion_bench.canonical.annotations import VisualFactAnnotation
from ingestion_bench.evaluation.evaluator import _score_visual_facts_and_unsupported_claims


def _unit() -> CanonicalUnit:
    return CanonicalUnit(unit_index=0, unit_type="page", width=612, height=792, coordinate_unit="pt", coordinate_origin="top-left")


def _picture() -> CanonicalPicture:
    return CanonicalPicture(picture_id="PIC_001", unit_index=0, order_index=0, artifact_ref="assets/PIC_001.png", content_sha256="b" * 64)


def _doc(annotations: list) -> CanonicalDocument:
    return CanonicalDocument(
        doc_id="DOC1", source_format="pdf", source_filename="doc1.pdf",
        source_relative_path="stress/doc1.pdf", source_sha256="a" * 64,
        units=[_unit()], pictures=[_picture()], annotations=annotations,
    )


def _supported_fact(**overrides) -> VisualFactAnnotation:
    defaults = dict(
        annotation_id="VF_ANN_1", target_ref="PIC_001", unit_index=0,
        derivation="model_derived", extraction_method="test_vision_enricher",
        fact_type="numeric", subject="Q4 pass rate", relation="equals", object=None, value=95, unit="%",
        raw_text="Q4: 95%",
    )
    defaults.update(overrides)
    return VisualFactAnnotation(**defaults)


UNSUPPORTED_CLAIM = {
    "fact_id": "CU_001", "fact_type": "numeric", "subject": "Q2 pass rate", "relation": "greater_than",
    "object": None, "value": 95, "unit": "%", "claim": "Pass rate exceeded 95% in Q2.",
}


def test_a_correct_supported_visual_fact_does_not_fail_an_unrelated_unsupported_claim():
    """One real, CORRECT visual fact is present (Q4 pass rate = 95%); the
    unsupported claim (Q2 pass rate > 95%) was never asserted. The mere
    presence of the Q4 annotation must not cause the Q2 unsupported claim
    to be scored as a failure -- unsupported_visual_claim_absence must
    remain 100%."""
    document = _doc([_supported_fact()])
    visual_facts = [{"fact_id": "CF_004", "raw_text": "Q4: 95%"}]

    metrics, miss_records, alignments = _score_visual_facts_and_unsupported_claims(
        "stress/STRESS_CHART_001.pdf", visual_facts, [UNSUPPORTED_CLAIM], document,
    )

    absence_metric = metrics["unsupported_visual_claim_absence"]
    assert absence_metric.numerator == 1
    assert absence_metric.denominator == 1
    assert absence_metric.score == 1.0
    assert not any(m.fact_id == "CU_001" for m in miss_records)

    cu_alignment = next(a for a in alignments if a.fact_id == "CU_001")
    assert cu_alignment.match_status == "not_applicable"


def test_the_unsupported_claim_itself_present_fails_only_that_claim():
    """The unsupported claim IS structurally asserted (Q2 pass rate > 95%
    actually present as a VisualFactAnnotation) alongside an unrelated,
    correct Q4 fact. Only CU_001 must fail -- the correct Q4 fact must not
    be implicated."""
    supported = _supported_fact()
    incorrectly_asserted = _supported_fact(
        annotation_id="VF_ANN_2", subject="Q2 pass rate", relation="greater_than", object=None, value=95, unit="%",
        raw_text="Q2 exceeded 95%",
    )
    document = _doc([supported, incorrectly_asserted])

    metrics, miss_records, alignments = _score_visual_facts_and_unsupported_claims(
        "stress/STRESS_CHART_001.pdf", [], [UNSUPPORTED_CLAIM], document,
    )

    absence_metric = metrics["unsupported_visual_claim_absence"]
    assert absence_metric.numerator == 0
    assert absence_metric.denominator == 1

    miss = next(m for m in miss_records if m.fact_id == "CU_001")
    assert miss.metric == "unsupported_visual_claim_absence"
    assert miss.failure_class == "unexpected_content"
    assert miss.supporting_canonical_element_ids == ["VF_ANN_2"]
    assert "VF_ANN_1" not in miss.supporting_canonical_element_ids

    cu_alignment = next(a for a in alignments if a.fact_id == "CU_001")
    assert cu_alignment.match_status == "missing"
    assert cu_alignment.matched_canonical_element_ids == []
    assert cu_alignment.matched_annotation_ids == []


def test_two_different_unsupported_claims_only_the_asserted_one_fails():
    """Two distinct unsupported claims; only one is structurally
    asserted. The other must remain not_applicable/passed."""
    asserted_claim = dict(UNSUPPORTED_CLAIM)
    other_claim = {
        "fact_id": "CU_002", "fact_type": "comparative", "subject": "Q1 pass rate", "relation": "greater_than",
        "object": "Q4 pass rate", "value": None, "unit": None, "claim": "Q1 exceeded Q4.",
    }
    incorrectly_asserted = _supported_fact(
        annotation_id="VF_ANN_2", subject="Q2 pass rate", relation="greater_than", object=None, value=95, unit="%",
        raw_text="Q2 exceeded 95%",
    )
    document = _doc([incorrectly_asserted])

    metrics, miss_records, alignments = _score_visual_facts_and_unsupported_claims(
        "stress/STRESS_CHART_001.pdf", [], [asserted_claim, other_claim], document,
    )

    absence_metric = metrics["unsupported_visual_claim_absence"]
    assert absence_metric.numerator == 1
    assert absence_metric.denominator == 2

    miss_fact_ids = {m.fact_id for m in miss_records}
    assert miss_fact_ids == {"CU_001"}

    other_alignment = next(a for a in alignments if a.fact_id == "CU_002")
    assert other_alignment.match_status == "not_applicable"
