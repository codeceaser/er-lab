"""Tests for ingestion_bench.evaluation.normalization (Stage 6A section 4):
deterministic text normalization and boundary-safe identifier matching.
No fuzzy/semantic matching -- every test proves an EXACT rule."""

from __future__ import annotations

from ingestion_bench.evaluation.normalization import (
    collapse_whitespace,
    find_identifier_occurrences,
    identifier_present,
    normalize_linebreaks,
    normalize_text_for_comparison,
    texts_match,
)


def test_collapse_whitespace_collapses_runs_and_strips_lines():
    assert collapse_whitespace("  Hello    world  \n  Second   line  ") == "Hello world\nSecond line"


def test_normalize_linebreaks_converts_crlf_and_cr_to_lf():
    assert normalize_linebreaks("a\r\nb\rc") == "a\nb\nc"


def test_normalize_text_for_comparison_case_folds_by_default():
    assert normalize_text_for_comparison("Application APP-224510") == normalize_text_for_comparison("application app-224510")


def test_normalize_text_for_comparison_case_sensitive_when_requested():
    assert normalize_text_for_comparison("Hello", fold_case=False) != normalize_text_for_comparison("hello", fold_case=False)


def test_normalize_text_for_comparison_preserves_punctuation():
    normalized = normalize_text_for_comparison("Control C-88 mandates Recovery Procedure P-205.")
    assert "c-88" in normalized
    assert "." in normalized


def test_texts_match_exact_after_normalization():
    assert texts_match("Hello   World", "hello world")


def test_texts_match_false_for_different_text():
    assert not texts_match("Hello World", "Hello Word")


def test_texts_match_whitespace_and_linebreak_insensitive():
    assert texts_match("Line one\r\nLine two", "Line one\nLine two")


# --- identifier boundary safety -------------------------------------------


def test_identifier_present_exact_match():
    assert identifier_present("Regulatory Obligation O-31 is satisfied by Control C-88.", "C-88")


def test_identifier_boundary_c88_never_matches_inside_c88a():
    """The primary token-boundary stress case declared in the manifest
    (ID_D002's false_merge_risk note)."""
    text = "Legacy Control C-88a was retired and replaced by Control C-88."
    assert not identifier_present("Legacy Control C-88a was retired", "C-88")
    occurrences = find_identifier_occurrences(text, "C-88")
    # Only the second, standalone "C-88" (not the "C-88a" occurrence) must match.
    assert len(occurrences) == 1
    start, end = occurrences[0]
    assert text[start:end] == "C-88"


def test_identifier_boundary_c88a_never_matches_for_a_search_of_c88a_variant():
    text = "Control C-88 mandates Recovery Procedure P-205."
    assert not identifier_present(text, "C-88a")


def test_identifier_boundary_app224510_never_matches_app224499():
    text = "APP-224499 was the predecessor system for payment settlement."
    assert not identifier_present(text, "APP-224510")


def test_identifier_present_is_case_sensitive():
    assert identifier_present("Application APP-224510 supports", "APP-224510")
    assert not identifier_present("application app-224510 supports", "APP-224510")


def test_find_identifier_occurrences_counts_multiple_occurrences_in_one_text():
    text = "APP-224510 is in scope. Later, APP-224510 is referenced again."
    occurrences = find_identifier_occurrences(text, "APP-224510")
    assert len(occurrences) == 2


def test_find_identifier_occurrences_respects_start_and_end_boundaries():
    text = "P-205"
    occurrences = find_identifier_occurrences(text, "P-205")
    assert occurrences == [(0, 5)]


def test_identifier_boundary_no_match_when_directly_adjacent_to_alnum():
    assert not identifier_present("XP-205Y", "P-205")
    assert identifier_present("(P-205)", "P-205")
