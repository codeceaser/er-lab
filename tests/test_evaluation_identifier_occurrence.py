"""Stage 6A.1 item 1: identifier occurrence-aware scoring regression
tests. Occurrence recall must never be computed by counting all
appearances globally and capping at the expected total -- every manifest
occurrence is matched one-to-one against the specific element its
source_fact resolves to. No real Docling artifacts needed -- exercises
evaluator._score_identifiers directly against hand-built data."""

from __future__ import annotations

from ingestion_bench.evaluation.evaluator import _score_identifiers
from ingestion_bench.evaluation.matcher import TextElement


def test_missing_occurrence_is_not_satisfied_by_an_extra_occurrence_in_a_distractor_paragraph():
    """Exact scenario required by Stage 6A.1 item 1:
    - one required occurrence is missing (occ_1, tied to source_fact P_2,
      whose resolved paragraph does not actually contain the identifier)
    - an extra occurrence of the SAME identifier exists in a distractor
      paragraph that is not tied to any expected occurrence
    - occurrence recall must remain a miss for occ_1 -- the distractor's
      extra occurrence must never be pulled in to silently satisfy it."""
    identifier = "C-99"
    target_facts = [{
        "fact_id": "ID_X", "normalized_value": identifier,
        "occurrences": [
            {"raw_text": identifier, "source_fact": "P_1"},
            {"raw_text": identifier, "source_fact": "P_2"},
        ],
    }]
    p1 = TextElement("p1_id", f"Application text mentioning {identifier} here.", "paragraph", 0)
    p2 = TextElement("p2_id", "Text with no identifier at all in this specific paragraph.", "paragraph", 0)
    distractor = TextElement("d1_id", f"Unrelated distractor paragraph also happens to mention {identifier}.", "paragraph", 0)
    elements = [p1, p2, distractor]
    # P_2 resolves to a real element (p2) -- it just doesn't contain the
    # identifier. The distractor is NOT registered as resolving any
    # occurrence's source_fact, simulating a real extra/unrelated mention.
    matched_element_by_fact_id = {"P_1": p1, "P_2": p2}

    metrics, miss_records, unexpected, alignments = _score_identifiers(
        "parity/PARITY_001.pdf", target_facts, [], elements, {}, matched_element_by_fact_id, [], None,
    )

    occurrence_metric = metrics["identifier_occurrence_recall"]
    assert occurrence_metric.numerator == 1
    assert occurrence_metric.denominator == 2
    assert occurrence_metric.score == 0.5

    miss_fact_ids = {m.fact_id for m in miss_records if m.metric == "identifier_occurrence_recall"}
    assert "ID_X_occ_1" in miss_fact_ids
    assert "ID_X_occ_0" not in miss_fact_ids

    occ_1_alignment = next(a for a in alignments if a.fact_id == "ID_X_occ_1")
    assert occ_1_alignment.match_status == "missing"
    assert occ_1_alignment.matched_canonical_element_ids == []

    # The extra distractor occurrence must be recorded separately, never
    # silently consumed to fill the missing expectation.
    assert any(u.element_id == "d1_id" for u in unexpected)


def test_occurrence_recall_never_globally_counts_and_caps():
    """If the SAME element happens to contain the identifier twice but
    only ONE occurrence is expected there, occurrence recall must not
    credit a second, unrelated expected occurrence elsewhere using the
    same element's extra appearance -- one observed occurrence never
    satisfies two expected occurrences."""
    identifier = "P-1"
    target_facts = [{
        "fact_id": "ID_Y", "normalized_value": identifier,
        "occurrences": [
            {"raw_text": identifier, "source_fact": "P_1"},
            {"raw_text": identifier, "source_fact": "P_2"},
        ],
    }]
    # P_1 contains the identifier TWICE; P_2 contains it ZERO times.
    p1 = TextElement("p1_id", f"{identifier} appears here and also {identifier} again.", "paragraph", 0)
    p2 = TextElement("p2_id", "No mention here.", "paragraph", 0)
    elements = [p1, p2]
    matched_element_by_fact_id = {"P_1": p1, "P_2": p2}

    metrics, miss_records, unexpected, alignments = _score_identifiers(
        "parity/PARITY_001.pdf", target_facts, [], elements, {}, matched_element_by_fact_id, [], None,
    )

    occurrence_metric = metrics["identifier_occurrence_recall"]
    # occ_0 (source_fact=P_1) matches; occ_1 (source_fact=P_2) does NOT --
    # P_1's second appearance of the identifier must not be borrowed to
    # satisfy occ_1, since occ_1 resolves to P_2, not P_1.
    assert occurrence_metric.numerator == 1
    assert occurrence_metric.denominator == 2

    # P_1's second (unconsumed) occurrence is recorded as an extra, not silently used.
    assert any(u.element_id == "p1_id" for u in unexpected)


def test_unique_recall_is_true_when_at_least_one_occurrence_matches():
    identifier = "Z-1"
    target_facts = [{
        "fact_id": "ID_Z", "normalized_value": identifier,
        "occurrences": [
            {"raw_text": identifier, "source_fact": "P_1"},
            {"raw_text": identifier, "source_fact": "P_2"},
        ],
    }]
    p1 = TextElement("p1_id", f"{identifier} appears here.", "paragraph", 0)
    p2 = TextElement("p2_id", "No mention here.", "paragraph", 0)
    matched_element_by_fact_id = {"P_1": p1, "P_2": p2}

    metrics, _, _, _ = _score_identifiers(
        "parity/PARITY_001.pdf", target_facts, [], [p1, p2], {}, matched_element_by_fact_id, [], None,
    )
    assert metrics["identifier_unique_recall"].numerator == 1
    assert metrics["identifier_unique_recall"].denominator == 1
