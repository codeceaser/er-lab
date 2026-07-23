"""Miss-classification helpers (Stage 6A sections 5 and 15).

Raw Docling debug JSON is read ONLY here, and ONLY to attribute an
expectation already known to be unsatisfied by CanonicalDocument:

  parser_content_loss     -- the expected TEXT never reached Docling's
    own output at all (absent from the raw debug export too).
  mapper_loss              -- the expected TEXT is present in Docling's
    raw output, but the Stage 5A mapper did not carry it into
    CanonicalDocument.
  parser_relationship_loss -- the expected content IS present in
    CanonicalDocument (e.g. as a plain paragraph), but the specific
    RELATIONSHIP/STRUCTURE/CLASSIFICATION it should also carry (e.g.
    "this paragraph is a caption linked to picture X") is absent from
    Docling's own raw output too -- Docling itself never exposed it.
  mapper_loss (relationship variant) -- same missing relationship, but
    Docling's raw output DOES explicitly expose it (e.g. the raw
    picture object's own `captions` list references this exact text
    item) and the Stage 5A mapper still failed to preserve it.

Stage 6A.1 correction (item 4): a raw Docling `self_ref` proves TEXT
existence only -- it never by itself proves Docling exposed a semantic
type, hierarchy, caption linkage, or other relationship. `mapper_loss`
for a relationship/structure gap is only ever returned by
`classify_relationship_absence` when the specific relationship field
(e.g. `pictures[i].captions`) is inspected directly and found to
reference the element in question -- never inferred from mere text
presence.

Stage 6A.2 correction (item 1): the same discipline applies to identifier
OCCURRENCE misses. `classify_identifier_occurrence_absence` never
searches the whole-document raw text blob for the identifier -- an
identifier appearing anywhere else in the document (a different
paragraph, a different picture) must never prove `mapper_loss` for a
missing occurrence tied to a SPECIFIC expected context (a specific
paragraph/heading/caption, or a specific picture's own OCR children).
The caller (evaluator.py::_score_identifiers) resolves that specific
scoped context first; this function only ever inspects it.

Raw Docling output is never used as the scored representation -- scoring
is always against CanonicalDocument/CanonicalChunk; this module is
consulted only for attribution once a miss is already established.
mapper_loss is never returned without the raw evidence that justifies it.
"""

from __future__ import annotations

from typing import Any

from .normalization import identifier_present, normalize_text_for_comparison


def extract_raw_text_blob(raw_debug: dict[str, Any]) -> list[tuple[str, str]]:
    """(source_ref, text) for every text-bearing surface in a raw Docling
    export this project's mapper reads from: texts[].text and every
    tables[].data.table_cells[].text. Debug evidence only."""
    out: list[tuple[str, str]] = []
    for item in raw_debug.get("texts", []) or []:
        text = item.get("text")
        if text:
            out.append((item.get("self_ref", "#/texts/?"), text))
    for table_index, table in enumerate(raw_debug.get("tables", []) or []):
        table_ref = table.get("self_ref", f"#/tables/{table_index}")
        for cell in (table.get("data", {}) or {}).get("table_cells", []) or []:
            text = cell.get("text")
            if text:
                out.append((table_ref, text))
    return out


def classify_text_absence(
    expected_text: str, raw_text_blob: list[tuple[str, str]], *, fold_case: bool = True
) -> tuple[str, str, list[str]]:
    """Returns (failure_class, confidence, raw_docling_references) for an
    expected text fact already confirmed absent from CanonicalDocument.
    "certain" confidence -- the raw blob was actually available and
    searched exhaustively."""
    target = normalize_text_for_comparison(expected_text, fold_case=fold_case)
    matches = [ref for ref, text in raw_text_blob if normalize_text_for_comparison(text, fold_case=fold_case) == target]
    if matches:
        return "mapper_loss", "certain", matches
    return "parser_content_loss", "certain", []


def classify_identifier_absence(
    identifier: str, raw_text_blob: list[tuple[str, str]]
) -> tuple[str, str, list[str]]:
    matches = [ref for ref, text in raw_text_blob if identifier_present(text, identifier)]
    if matches:
        return "mapper_loss", "certain", matches
    return "parser_content_loss", "certain", []


def classify_identifier_occurrence_absence(
    identifier: str, scoped_raw_items: list[tuple[str, str]] | None,
) -> tuple[str, str, list[str]]:
    """Stage 6A.2 item 1: attributes a missing identifier OCCURRENCE using
    ONLY the raw Docling item(s) relevant to that occurrence's own
    expected context (a specific paragraph/heading/caption's raw
    counterpart, or a specific picture's own raw OCR children) -- never
    the whole-document raw text blob. `scoped_raw_items` is:
      None -- the expected context itself could not be resolved in raw
        Docling at all (e.g. the source paragraph/picture has no
        identifiable raw counterpart) -- returns ("unresolved",
        "unresolved", []), never guessed as mapper_loss.
      [] -- the context WAS resolved (a specific raw item, or a specific
        picture's children list) but contains no matching raw text at
        all -- returns ("parser_content_loss", "certain", []).
      non-empty -- searched for `identifier`; a match returns
        ("mapper_loss", "certain", [matching refs]) since raw Docling
        explicitly contains the identifier in the exact required context
        and the mapper failed to preserve it; no match still returns
        ("parser_content_loss", "certain", [])."""
    if scoped_raw_items is None:
        return "unresolved", "unresolved", []
    matches = [ref for ref, text in scoped_raw_items if identifier_present(text, identifier)]
    if matches:
        return "mapper_loss", "certain", matches
    return "parser_content_loss", "certain", []


def unresolved_classification(reason: str) -> tuple[str, str, list[str]]:
    """Used when no raw debug artifact was available at all to attribute
    a miss between parser and mapper -- never guesses."""
    return "unresolved", "unresolved", []


def classify_relationship_absence(
    raw_debug: dict[str, Any], *, parent_collection: str, parent_self_ref: str,
    relation_field: str, child_self_ref: str | None,
) -> tuple[str, str, list[str]]:
    """Stage 6A.1 item 4: attributes a missing RELATIONSHIP (not missing
    text) between `parent_self_ref` (e.g. a picture) and `child_self_ref`
    (e.g. its caption text item) by inspecting Docling's own raw
    `relation_field` list on the parent object directly -- never inferred
    from the child text's mere presence/self_ref elsewhere in the
    document. Returns:
      ("mapper_loss", "certain", [parent_self_ref]) -- Docling's raw
        relation_field explicitly references child_self_ref; the mapper
        dropped a relationship Docling itself exposed.
      ("parser_relationship_loss", "certain", []) -- the parent exists in
        raw Docling but relation_field does not reference child_self_ref
        (empty or referencing something else) -- Docling never exposed
        this relationship for the mapper to preserve.
      ("parser_relationship_loss", "unresolved", []) -- the parent object
        itself could not be found in raw Docling at all; the relationship
        question cannot be resolved, so this is recorded as an unresolved
        parser-side gap, never guessed as mapper_loss.
    """
    for item in raw_debug.get(parent_collection, []) or []:
        if item.get("self_ref") != parent_self_ref:
            continue
        refs = {ref.get("$ref") for ref in item.get(relation_field, []) or []}
        if child_self_ref is not None and child_self_ref in refs:
            return "mapper_loss", "certain", [parent_self_ref]
        return "parser_relationship_loss", "certain", []
    return "parser_relationship_loss", "unresolved", []
