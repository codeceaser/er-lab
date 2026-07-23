"""Generic, reusable matching primitives over canonical text elements.
evaluator.py builds TextElement lists from a CanonicalDocument and calls
these; nothing here knows about reference_manifest.json or Docling.

Every function documents its exact matching rule -- see normalization.py
for the underlying normalization rules themselves. No fuzzy or semantic
matching exists here.
"""

from __future__ import annotations

from dataclasses import dataclass

from .normalization import find_identifier_occurrences, normalize_text_for_comparison


@dataclass(frozen=True)
class TextElement:
    """One text-bearing canonical element, flattened out of whichever
    CanonicalDocument list it came from (heading/paragraph/list_item/
    caption) or an OcrAnnotation, for uniform matching."""

    element_id: str
    text: str
    element_type: str
    unit_index: int


def find_exact_text_matches(expected_text: str, candidates: list[TextElement], *, fold_case: bool = True) -> list[TextElement]:
    """Exact, normalized WHOLE-TEXT match (TEXT_NORMALIZED_V1) -- every
    canonical text element in this benchmark corresponds to exactly one
    source paragraph/heading/list-item/caption, so whole-value equality is
    the correct rule; a substring match would over-credit a fact whose
    text merely appears inside a longer, unrelated block."""
    target = normalize_text_for_comparison(expected_text, fold_case=fold_case)
    return [c for c in candidates if normalize_text_for_comparison(c.text, fold_case=fold_case) == target]


def find_identifier_matches(identifier: str, candidates: list[TextElement]) -> list[tuple[TextElement, int]]:
    """(element, occurrence_count) for every candidate containing at least
    one boundary-safe occurrence of `identifier` (IDENTIFIER_BOUNDARY_V1)."""
    out: list[tuple[TextElement, int]] = []
    for candidate in candidates:
        count = len(find_identifier_occurrences(candidate.text, identifier))
        if count:
            out.append((candidate, count))
    return out


def total_identifier_occurrences(identifier: str, candidates: list[TextElement]) -> int:
    return sum(count for _, count in find_identifier_matches(identifier, candidates))
