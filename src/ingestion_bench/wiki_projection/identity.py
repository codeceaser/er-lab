"""Stage 7C.0: deterministic identity, anchor extraction and sentence
splitting. NO model call, NO benchmark truth, NO authority state, NO Graph
import.

Three deterministic anchor lanes, all reading only `source_text` and
`heading_path`:

  Lane 1  identifier anchors   -> page identities, kind `governed_identifier`
  Lane 2  repeated-phrase      -> page identities, kind `business_topic`
  Lane 3  heading-title        -> NOT page identities; structural browsing
                                  only (Revision 6 SS7.1 makes `heading_title`
                                  non-traversable, so it never creates a hub)

`identifiers_in` is the ~4-line regex LIFTED from the frozen
graph_retrieval_benchmark into this neutral module (Revision 6 Q9). The
frozen package is NOT imported -- lifting, not importing, is the contract.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

# --- Lane 1: identifier regex, lifted verbatim (Q9) --------------------------
# Identical pattern to graph_retrieval_benchmark/model.py:23. Uppercasing the
# match is what keeps C-88 and C-88a DISTINCT ("C-88" vs "C-88A").
_IDENTIFIER_RE = re.compile(r"\b([A-Za-z]{1,6}-\d+[A-Za-z]?)\b")


def identifiers_in(text: str) -> set[str]:
    """The enterprise identifiers present in a surface form, uppercased:
    `C-88` -> "C-88", `C-88a` -> "C-88A". Protects the C-88 / C-88a
    boundary."""
    return {m.group(1).upper() for m in _IDENTIFIER_RE.finditer(text)}


@dataclass(frozen=True)
class Occurrence:
    """One deterministic surface occurrence inside one text field."""

    surface: str
    normalized: str
    start_char: int
    end_char: int


def identifier_occurrences(text: str) -> list[Occurrence]:
    """Every identifier occurrence with its exact half-open char span, in
    ascending span order."""
    out = [
        Occurrence(surface=m.group(1), normalized=m.group(1).upper(), start_char=m.start(1), end_char=m.end(1))
        for m in _IDENTIFIER_RE.finditer(text)
    ]
    return sorted(out, key=lambda o: (o.start_char, o.end_char))


# --- Lane 2: conservative repeated-phrase anchors ----------------------------

# A candidate token is a capitalised word (or an identifier token, which must
# not FRAGMENT an otherwise valid run).
_PHRASE_TOKEN_RE = re.compile(r"^[A-Z][A-Za-z0-9&/-]*$")

# The fixed CLOSED stop-list. Frozen at 7C.0; never extended per corpus, per
# question or per run.
#
# Reading of the Revision 6 SS2.1 rule, recorded because the rule admits two
# readings and only one reproduces the plan's own SS0.1 corpus property:
# a stop-listed token BREAKS a run rather than poisoning it. Under the other
# reading ("reject the whole candidate if any token is stop-listed"), the
# sentence "The Payment Settlement business service is governed by ..." would
# yield the single run [The, Payment, Settlement] and be rejected outright,
# destroying the `Payment Settlement` anchor that SS0.1 states IS this corpus's
# only cross-document phrase anchor and that SS1.5.2's chain depends on. Under
# the implemented reading the run is [Payment, Settlement] and no candidate
# ever contains a stop word -- so the rule's literal requirement also holds.
_STOP_LIST: frozenset[str] = frozenset(
    {
        "a", "an", "and", "any", "are", "as", "at", "be", "but", "by", "for", "from", "how", "if", "in",
        "into", "is", "it", "its", "no", "not", "of", "on", "or", "over", "per", "so", "such", "than",
        "that", "the", "their", "then", "there", "these", "they", "this", "those", "through", "to",
        "under", "until", "up", "was", "were", "what", "when", "where", "which", "while", "who", "with",
    }
)

PHRASE_MIN_TOKENS = 2
PHRASE_MAX_TOKENS = 4
PHRASE_MIN_CHARS = 3
PHRASE_MAX_CHARS = 60
PHRASE_MIN_DISTINCT_CHUNKS = 2
PHRASE_MIN_DISTINCT_LOGICAL_DOCUMENTS = 2

_WORD_RE = re.compile(r"\S+")


def normalize_phrase(text: str) -> str:
    """Lane 2 key: casefold + single-space collapse."""
    return " ".join(text.split()).casefold()


def _is_stop(token: str) -> bool:
    return token.strip(".,;:()[]{}\"'").casefold() in _STOP_LIST


def _qualifies(token: str) -> bool:
    stripped = token.strip(".,;:()[]{}\"'")
    if not stripped or _is_stop(stripped):
        return False
    return bool(_PHRASE_TOKEN_RE.match(stripped)) or bool(_IDENTIFIER_RE.fullmatch(stripped))


def phrase_candidates(text: str) -> list[Occurrence]:
    """Maximal runs of 2-4 consecutive qualifying tokens, with the exact
    half-open char span of the run in `text`.

    A run is maximal over QUALIFYING tokens; a non-qualifying or stop-listed
    token ends the current run. A maximal run outside [2, 4] tokens yields no
    candidate at all (it is neither truncated nor split -- truncation would be
    a tunable choice, and this rule must be untunable).
    """
    tokens = [(m.group(0), m.start(), m.end()) for m in _WORD_RE.finditer(text)]
    out: list[Occurrence] = []
    run: list[tuple[str, int, int]] = []

    def ends_sentence(token: str) -> bool:
        """A phrase never spans a sentence boundary: a token carrying
        sentence-final punctuation closes the run after being included."""
        return token.rstrip("\"')]}").endswith((".", "!", "?"))

    def flush() -> None:
        if PHRASE_MIN_TOKENS <= len(run) <= PHRASE_MAX_TOKENS:
            # Trim trailing punctuation from the run's last token so the span
            # covers the phrase, never the sentence's full stop.
            start = run[0][1]
            last_raw = run[-1][0]
            trimmed_len = len(last_raw.rstrip(".,;:()[]{}\"'"))
            end = run[-1][1] + trimmed_len
            surface = text[start:end]
            if PHRASE_MIN_CHARS <= len(surface) <= PHRASE_MAX_CHARS:
                out.append(
                    Occurrence(surface=surface, normalized=normalize_phrase(surface), start_char=start, end_char=end)
                )
        run.clear()

    for token, start, end in tokens:
        if _qualifies(token):
            run.append((token, start, end))
            if ends_sentence(token):
                flush()
        else:
            flush()
    flush()
    return sorted(out, key=lambda o: (o.start_char, o.end_char))


def phrase_candidate_is_identifier_colliding(normalized_phrase: str) -> bool:
    """A candidate carrying an identifier token collides with that
    identifier's OWN page identity -- identifiers win, so the phrase
    candidate is dropped (Revision 6 SS2.1, "identifiers win").

    This is what keeps `Obligation O-31` from becoming a second, competing
    hub alongside `IDENT:O-31`, and it is why SS0.1 records `Payment
    Settlement` as this corpus's ONLY surviving cross-document phrase anchor.
    """
    return bool(identifiers_in(normalized_phrase))


# --- page identity -----------------------------------------------------------

ANCHOR_KIND_IDENTIFIER = "identifier"
ANCHOR_KIND_PHRASE = "phrase"
ANCHOR_KIND_HEADING_TITLE = "heading_title"

PAGE_TYPE_BY_ANCHOR_KIND = {
    ANCHOR_KIND_IDENTIFIER: "governed_identifier",
    ANCHOR_KIND_PHRASE: "business_topic",
}

_PAGE_KEY_PREFIX_BY_ANCHOR_KIND = {
    ANCHOR_KIND_IDENTIFIER: "IDENT",
    ANCHOR_KIND_PHRASE: "PHRASE",
}


def page_key(anchor_kind: str, normalized_value: str) -> str:
    """`page_key = "{kind}:{normalized_identity}"` -- e.g. `IDENT:O-31`,
    `PHRASE:payment settlement` (Revision 6 SS3.2). Only Lane 1 and Lane 2
    anchors have page identities; a `heading_title` anchor never does."""
    prefix = _PAGE_KEY_PREFIX_BY_ANCHOR_KIND.get(anchor_kind)
    if prefix is None:
        raise ValueError(f"anchor_kind {anchor_kind!r} does not carry a page identity (Revision 6 SS3.2)")
    return f"{prefix}:{normalized_value}"


def page_type_for(anchor_kind: str) -> str:
    """Fully deterministic: the anchor's own kind (Revision 6 SS3.2)."""
    page_type = PAGE_TYPE_BY_ANCHOR_KIND.get(anchor_kind)
    if page_type is None:
        raise ValueError(f"anchor_kind {anchor_kind!r} has no page_type (Revision 6 SS3.2)")
    return page_type


DISPLAY_TITLE_RULE = (
    "first_source_occurrence_surface_form: the exact surface text of this anchor's "
    "first posting in ascending (document_revision_id, chunk_id, start_char, end_char) "
    "order, copied verbatim from source_text/heading_path; never re-worded, never "
    "type-prefixed, never generated"
)


def compute_anchor_id(anchor_kind: str, normalized_value: str) -> str:
    """`anchor_id = sha256(anchor_kind | normalized_value)` (Revision 6 SS2.1)."""
    return hashlib.sha256(f"{anchor_kind}|{normalized_value}".encode("utf-8")).hexdigest()


def compute_section_id(document_revision_id: str, chunk_id: str) -> str:
    """`section_id = sha256(document_revision_id | chunk_id)` (Revision 6 SS2.1)."""
    return hashlib.sha256(f"{document_revision_id}|{chunk_id}".encode("utf-8")).hexdigest()


def compute_posting_hash(
    *, anchor_id: str, chunk_id: str, document_revision_id: str, field: str, start_char: int, end_char: int
) -> str:
    """Deterministic posting identity/provenance hash. Never random, never
    run-scoped."""
    blob = f"{anchor_id}|{chunk_id}|{document_revision_id}|{field}|{start_char}|{end_char}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --- frozen deterministic sentence splitter ----------------------------------
#
# Frozen at 7C.0 because Stage 7C.1's SS6.2 component-5 identity-bearing source
# passage must consume an ALREADY-FROZEN projection contract. NO W1 payload is
# constructed here.

SENTENCE_SPLITTER_VERSION = "wiki_sentence_splitter_v1"
_SENTENCE_SPLIT_SPEC = (
    "split source_text on blank-line block boundaries, then within each block "
    "after a '.', '!' or '?' that is followed by whitespace or end-of-block; "
    "spans are half-open over the ORIGINAL text; leading/trailing whitespace is "
    "excluded from a sentence span but never removed from the underlying text"
)
_SENTENCE_END_RE = re.compile(r"[.!?](?=\s|$)")


def sentence_splitter_identity() -> dict[str, str]:
    """The frozen splitter's identity + hash, recorded in the projection
    contract and manifest."""
    blob = f"{SENTENCE_SPLITTER_VERSION}|{_SENTENCE_SPLIT_SPEC}|{_SENTENCE_END_RE.pattern}"
    return {
        "version": SENTENCE_SPLITTER_VERSION,
        "specification": _SENTENCE_SPLIT_SPEC,
        "pattern": _SENTENCE_END_RE.pattern,
        "sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
    }


def split_sentences(text: str) -> list[Occurrence]:
    """Deterministic sentence boundaries with exact half-open spans over
    `text`. Used by Stage 7C.1 (not by 7C.0) to build the SS6.2 component-5
    passage; frozen here so 7C.1 cannot redefine it."""
    out: list[Occurrence] = []
    cursor = 0
    for block in text.split("\n\n"):
        block_start = text.index(block, cursor) if block else cursor
        cursor = block_start + len(block)
        pos = 0
        for match in _SENTENCE_END_RE.finditer(block):
            piece = block[pos : match.end()]
            stripped = piece.strip()
            if stripped:
                start = block_start + pos + (len(piece) - len(piece.lstrip()))
                out.append(
                    Occurrence(
                        surface=stripped, normalized=" ".join(stripped.split()), start_char=start,
                        end_char=start + len(stripped),
                    )
                )
            pos = match.end()
        tail = block[pos:]
        if tail.strip():
            stripped = tail.strip()
            start = block_start + pos + (len(tail) - len(tail.lstrip()))
            out.append(
                Occurrence(
                    surface=stripped, normalized=" ".join(stripped.split()), start_char=start,
                    end_char=start + len(stripped),
                )
            )
    return out


def stop_list_snapshot() -> list[str]:
    """The frozen closed stop-list, sorted -- recorded in the contract so it
    is auditable and provably unchanged between runs."""
    return sorted(_STOP_LIST)
