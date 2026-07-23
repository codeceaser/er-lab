"""Deterministic, documented text/identifier normalization rules for
Stage 6A evaluation (section 4). No fuzzy or semantic matching exists
anywhere in this module or is ever used by default -- every comparison
function here is exact, given its documented normalization rule.

Each *_RULE constant is the exact string stored on
MetricResult.matching_rule for every metric that uses it, so a reader
never has to guess which comparison a metric actually performed.
"""

from __future__ import annotations

import re
import unicodedata

_HORIZONTAL_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
_LINEBREAK_RE = re.compile(r"\r\n|\r")


def normalize_unicode(text: str, form: str = "NFC") -> str:
    return unicodedata.normalize(form, text)


def normalize_linebreaks(text: str) -> str:
    """CRLF/CR -> LF only -- never removes intentional line breaks."""
    return _LINEBREAK_RE.sub("\n", text)


def collapse_whitespace(text: str) -> str:
    """Collapses runs of horizontal whitespace to one space, strips
    leading/trailing whitespace per line, then strips the whole result.
    Never collapses meaningful line breaks between lines."""
    text = _HORIZONTAL_WHITESPACE_RE.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


TEXT_NORMALIZED_CASE_FOLD_RULE = (
    "TEXT_NORMALIZED_V1(case_fold=True): unicode NFC -> CRLF/CR normalized to LF -> "
    "horizontal whitespace collapsed -> each line stripped -> casefold(). "
    "No punctuation stripping (punctuation is part of fact meaning in this benchmark)."
)
TEXT_NORMALIZED_CASE_SENSITIVE_RULE = (
    "TEXT_NORMALIZED_V1(case_fold=False): same as TEXT_NORMALIZED_V1(case_fold=True) "
    "without casefold() -- used only where the metric explicitly requires case sensitivity."
)


def normalize_text_for_comparison(text: str, *, fold_case: bool = True) -> str:
    """The one text-comparison rule used throughout Stage 6A's text/
    heading/caption/OCR metrics: exact WHOLE-VALUE equality after this
    normalization -- never a substring match, never fuzzy/semantic."""
    text = normalize_unicode(text)
    text = normalize_linebreaks(text)
    text = collapse_whitespace(text)
    if fold_case:
        text = text.casefold()
    return text


def texts_match(expected: str, observed: str, *, fold_case: bool = True) -> bool:
    return normalize_text_for_comparison(expected, fold_case=fold_case) == normalize_text_for_comparison(
        observed, fold_case=fold_case
    )


IDENTIFIER_MATCH_RULE = (
    "IDENTIFIER_BOUNDARY_V1: exact, case-SENSITIVE substring match where the character "
    "immediately before and after the identifier is not alphanumeric -- "
    "regex (?<![A-Za-z0-9])<identifier>(?![A-Za-z0-9]), applied to raw (unnormalized) text. "
    "Case-sensitive deliberately: identifiers in this manifest are always uppercase and "
    "case-folding risks merging distinct-looking tokens."
)

_identifier_pattern_cache: dict[str, re.Pattern[str]] = {}


def _identifier_pattern(identifier: str) -> re.Pattern[str]:
    if identifier not in _identifier_pattern_cache:
        _identifier_pattern_cache[identifier] = re.compile(
            r"(?<![A-Za-z0-9])" + re.escape(identifier) + r"(?![A-Za-z0-9])"
        )
    return _identifier_pattern_cache[identifier]


def find_identifier_occurrences(text: str, identifier: str) -> list[tuple[int, int]]:
    """Every boundary-safe (start, end) span where `identifier` occurs in
    `text`. `C-88` never matches inside `C-88a`, and `C-88a` never matches
    for a search of `C-88` (the token-boundary check in
    IDENTIFIER_MATCH_RULE cuts both ways)."""
    return [(m.start(), m.end()) for m in _identifier_pattern(identifier).finditer(text)]


def identifier_present(text: str, identifier: str) -> bool:
    return _identifier_pattern(identifier).search(text) is not None


OCR_PHRASE_MATCH_RULE = (
    "OCR_PHRASE_MATCH_V1 (Stage 6A.1): the normalized expected phrase must appear with "
    "word-boundary-safe containment (regex (?<!\\w)<phrase>(?!\\w) over TEXT_NORMALIZED_V1 text) "
    "either inside a SINGLE observed OCR line, or inside the space-joined concatenation of two or "
    "more ADJACENT observed OCR fragments for the same picture, ordered by ocr_sequence. A short "
    "observed fragment (e.g. 'P-205') is never credited as full recovery of a longer expected phrase "
    "(e.g. 'Activate Procedure P-205') -- containment is always checked expected-in-observed, never "
    "the reverse."
)

_phrase_pattern_cache: dict[str, re.Pattern[str]] = {}


def _phrase_boundary_pattern(normalized_phrase: str) -> re.Pattern[str]:
    if normalized_phrase not in _phrase_pattern_cache:
        _phrase_pattern_cache[normalized_phrase] = re.compile(r"(?<!\w)" + re.escape(normalized_phrase) + r"(?!\w)")
    return _phrase_pattern_cache[normalized_phrase]


def ocr_phrase_recovered(expected_text: str, ordered_ocr_lines: list[tuple[str, int | None]]) -> bool:
    """ordered_ocr_lines: (text, ocr_sequence) pairs already scoped to one
    picture -- ocr_sequence may be None (Docling supplied no sequence
    evidence), in which case that fragment sorts last and is still tried
    for single-line containment, just never used to seed a multi-fragment
    reconstruction ordering ambiguously."""
    target = normalize_text_for_comparison(expected_text)
    if not target:
        return False
    pattern = _phrase_boundary_pattern(target)

    normalized_lines = [normalize_text_for_comparison(text) for text, _ in ordered_ocr_lines]
    for line in normalized_lines:
        if pattern.search(line):
            return True

    ordered = sorted(
        zip(normalized_lines, (seq for _, seq in ordered_ocr_lines)),
        key=lambda pair: (pair[1] is None, pair[1] if pair[1] is not None else 0),
    )
    ordered_texts = [text for text, _ in ordered]
    max_len = len(target) + 64  # bound the reconstruction window -- never scan unboundedly
    for start in range(len(ordered_texts)):
        accumulated = ""
        for end in range(start, len(ordered_texts)):
            accumulated = f"{accumulated} {ordered_texts[end]}".strip() if accumulated else ordered_texts[end]
            if pattern.search(accumulated):
                return True
            if len(accumulated) > max_len:
                break
    return False
