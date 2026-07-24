"""Stage 6A.2 item 2: unsupported visual claims must be matched
INDIVIDUALLY against actual VisualFactAnnotation output -- the presence
of any VisualFactAnnotation must never be used as blanket evidence that
every unsupported claim was asserted. Uses hand-built CanonicalDocument
objects, no real Docling artifacts needed."""

from __future__ import annotations

from pathlib import Path

from ingestion_bench.canonical import CanonicalDocument, CanonicalPicture, CanonicalUnit
from ingestion_bench.canonical.annotations import VisualFactAnnotation
from ingestion_bench.evaluation.evaluator import (
    _score_visual_facts_and_unsupported_claims,
    build_fact_catalog,
    load_manifest,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_ROOT = REPO_ROOT / "fixtures"


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


# --- real-manifest integration (Stage 6A.2a item 3) -------------------------


def test_real_manifest_cu_001_carries_full_structured_fields_through_the_catalog():
    """Loads the FROZEN reference_manifest.json through build_fact_catalog()
    -- the same path the real evaluator uses -- and proves CU_001's
    structured fields (fact_type/subject/relation/object/value/unit/claim/
    is_supported/reason) survive intact. This must FAIL against a
    _stress_chart_facts() implementation truncated to fact_id/claim only."""
    manifest = load_manifest(FIXTURES_ROOT)
    catalog = build_fact_catalog(manifest, "stress_chart", "STRESS_CHART_001")

    cu_001 = next(f for f in catalog["unsupported_claim"] if f["fact_id"] == "CU_001")

    assert cu_001["fact_type"] == "numeric"
    assert cu_001["subject"] == "Q2 pass rate"
    assert cu_001["relation"] == "greater_than"
    assert cu_001["object"] is None
    assert cu_001["value"] == 95
    assert cu_001["unit"] == "%"
    assert cu_001["claim"] == "Pass rate exceeded 95% in Q2."
    assert cu_001["is_supported"] is False
    assert cu_001["reason"]


def test_real_manifest_catalog_scored_against_an_unrelated_visual_fact_stays_100_percent():
    """The exact catalog result from build_fact_catalog() -- not a
    hand-built replacement -- passed to
    _score_visual_facts_and_unsupported_claims() alongside an unrelated,
    valid VisualFactAnnotation (matching CF_004, Q4 pass rate). CU_001
    (Q2 pass rate > 95%) was never asserted -- absence must stay 100%."""
    manifest = load_manifest(FIXTURES_ROOT)
    catalog = build_fact_catalog(manifest, "stress_chart", "STRESS_CHART_001")
    cf_004 = next(f for f in catalog["visual_fact"] if f["fact_id"] == "CF_004")

    unrelated_fact = VisualFactAnnotation(
        annotation_id="VF_ANN_CF_004", target_ref="PIC_001", unit_index=0,
        derivation="model_derived", extraction_method="test_vision_enricher",
        fact_type=cf_004["fact_type"], subject=cf_004["subject"], relation=cf_004["relation"],
        object=cf_004["object"], value=cf_004["value"], unit=cf_004["unit"], raw_text=cf_004["raw_text"],
    )
    document = _doc([unrelated_fact])

    metrics, miss_records, alignments = _score_visual_facts_and_unsupported_claims(
        "stress/STRESS_CHART_001.pdf", catalog["visual_fact"], catalog["unsupported_claim"], document,
    )

    absence_metric = metrics["unsupported_visual_claim_absence"]
    assert absence_metric.score == 1.0
    assert not any(m.fact_id == "CU_001" for m in miss_records)
    cu_alignment = next(a for a in alignments if a.fact_id == "CU_001")
    assert cu_alignment.match_status == "not_applicable"
    assert cu_alignment.expected_value["subject"] == "Q2 pass rate"


def test_real_manifest_catalog_scored_against_cu_001_itself_flags_only_cu_001():
    """The exact catalog result from build_fact_catalog() passed to
    _score_visual_facts_and_unsupported_claims() alongside a
    VisualFactAnnotation that structurally matches CU_001 itself (Q2 pass
    rate > 95%) -- CU_001 alone must be detected as an unsupported
    asserted claim; must FAIL (silently score 100%) against a
    _stress_chart_facts() implementation truncated to fact_id/claim only,
    since a truncated CU_001 dict has fact_type=None/subject=None/etc. and
    can never structurally match any real VisualFactAnnotation."""
    manifest = load_manifest(FIXTURES_ROOT)
    catalog = build_fact_catalog(manifest, "stress_chart", "STRESS_CHART_001")
    cu_001 = next(f for f in catalog["unsupported_claim"] if f["fact_id"] == "CU_001")

    asserting_fact = VisualFactAnnotation(
        annotation_id="VF_ANN_CU_001", target_ref="PIC_001", unit_index=0,
        derivation="model_derived", extraction_method="test_vision_enricher",
        fact_type=cu_001["fact_type"], subject=cu_001["subject"], relation=cu_001["relation"],
        object=cu_001["object"], value=cu_001["value"], unit=cu_001["unit"], raw_text=cu_001["claim"],
    )
    document = _doc([asserting_fact])

    metrics, miss_records, alignments = _score_visual_facts_and_unsupported_claims(
        "stress/STRESS_CHART_001.pdf", catalog["visual_fact"], catalog["unsupported_claim"], document,
    )

    absence_metric = metrics["unsupported_visual_claim_absence"]
    assert absence_metric.numerator == 0
    assert absence_metric.score == 0.0

    miss_fact_ids = {m.fact_id for m in miss_records if m.metric == "unsupported_visual_claim_absence"}
    assert miss_fact_ids == {"CU_001"}

    cu_alignment = next(a for a in alignments if a.fact_id == "CU_001")
    assert cu_alignment.match_status == "missing"
