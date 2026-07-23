"""Miss-classification helpers (Stage 6A sections 5 and 15).

Raw Docling debug JSON is read ONLY here, and ONLY to distinguish two
failure classes once an expectation is already known to be absent from
CanonicalDocument:

  parser_content_loss -- the expected fact never reached Docling's own
    output at all (absent from the raw debug export too).
  mapper_loss          -- the expected fact IS present in Docling's raw
    output, but the Stage 5A mapper did not carry it into
    CanonicalDocument.

Raw Docling output is never used as the scored representation -- scoring
is always against CanonicalDocument/CanonicalChunk; this module is
consulted only for attribution once a miss is already established.
mapper_loss is never returned without the raw text/identifier that
justifies it.
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


def unresolved_classification(reason: str) -> tuple[str, str, list[str]]:
    """Used when no raw debug artifact was available at all to attribute
    a miss between parser and mapper -- never guesses."""
    return "unresolved", "unresolved", []
