"""Tests for ingestion_bench.evaluation.matcher (Stage 6A section 6/7):
exact whole-text matching and identifier occurrence counting, including
unique-vs-occurrence-level scoring distinctions."""

from __future__ import annotations

from ingestion_bench.evaluation.matcher import TextElement, find_exact_text_matches, find_identifier_matches, total_identifier_occurrences


def _elements() -> list[TextElement]:
    return [
        TextElement("e1", "Application APP-224510 supports the Payment Settlement business service.", "paragraph", 0),
        TextElement("e2", "APP-224510 is in scope for Regulatory Obligation O-31.", "paragraph", 0),
        TextElement("e3", "Regulatory Obligation O-31 is satisfied by Control C-88.", "paragraph", 0),
        TextElement("e4", "Legacy Control C-88a was retired and replaced by Control C-88.", "paragraph", 0),
        TextElement("e5", "Enterprise Resilience Overview", "heading", 0),
    ]


def test_find_exact_text_matches_whole_value_only_not_substring():
    """A fact whose text is a substring of a longer block must NOT match
    -- whole-value equality only."""
    elements = _elements()
    matches = find_exact_text_matches("APP-224510", elements)
    assert matches == []


def test_find_exact_text_matches_exact_whole_text():
    elements = _elements()
    matches = find_exact_text_matches("Application APP-224510 supports the Payment Settlement business service.", elements)
    assert [m.element_id for m in matches] == ["e1"]


def test_find_exact_text_matches_case_insensitive_by_default():
    elements = _elements()
    matches = find_exact_text_matches("enterprise resilience overview", elements)
    assert [m.element_id for m in matches] == ["e5"]


def test_find_identifier_matches_returns_element_and_occurrence_count():
    elements = _elements()
    matches = find_identifier_matches("APP-224510", elements)
    assert {(e.element_id, count) for e, count in matches} == {("e1", 1), ("e2", 1)}


def test_find_identifier_matches_excludes_boundary_unsafe_hits():
    """C-88 must never be credited for occurring inside C-88a (e4 has
    BOTH a C-88a occurrence and a real standalone C-88 occurrence)."""
    elements = _elements()
    matches = find_identifier_matches("C-88", elements)
    matched_ids = {e.element_id: count for e, count in matches}
    assert matched_ids == {"e3": 1, "e4": 1}  # e4's C-88a occurrence never counted


def test_total_identifier_occurrences_sums_across_elements():
    elements = _elements()
    assert total_identifier_occurrences("O-31", elements) == 2  # e2 and e3, one each


def test_unique_vs_occurrence_level_scoring_are_distinct_by_construction():
    """Unique recall asks 'was this identifier found at all' (one bit per
    identifier); occurrence recall asks 'how many of its expected
    occurrences were found' -- the matcher exposes both independently, so
    a caller can never collapse one into the other."""
    elements = _elements()
    unique_found = bool(find_identifier_matches("APP-224510", elements))
    occurrence_count = total_identifier_occurrences("APP-224510", elements)
    assert unique_found is True
    assert occurrence_count == 2  # two distinct occurrences, not collapsed into the single unique-recall bit
