"""Stage 6A.1 item 10: table matching hardening tests -- best deterministic
candidate selection (never the first table exceeding a threshold) and
one-to-one cell matching (a duplicate observed value can never satisfy two
expected cells). Uses hand-built CanonicalDocument objects, no real
Docling artifacts needed."""

from __future__ import annotations

from ingestion_bench.canonical import CanonicalDocument, CanonicalTable, CanonicalTableCell, CanonicalUnit
from ingestion_bench.evaluation.evaluator import _score_tables


def _unit() -> CanonicalUnit:
    return CanonicalUnit(unit_index=0, unit_type="page", width=612, height=792, coordinate_unit="pt", coordinate_origin="top-left")


def _doc(tables: list[CanonicalTable]) -> CanonicalDocument:
    return CanonicalDocument(
        doc_id="DOC1", source_format="pdf", source_filename="doc1.pdf",
        source_relative_path="parity/doc1.pdf", source_sha256="a" * 64,
        units=[_unit()], tables=tables,
    )


def test_best_candidate_table_selected_not_first_exceeding_threshold():
    """A weaker-overlap table appearing FIRST in document order must not
    be selected over a later table with strictly higher overlap."""
    weak_table = CanonicalTable(
        table_id="t_weak", unit_index=0, order_index=0, n_rows=2, n_cols=2,
        cells=[
            CanonicalTableCell(row=0, col=0, text="Metric", is_header=True),
            CanonicalTableCell(row=0, col=1, text="Unrelated", is_header=True),
        ],
    )
    strong_table = CanonicalTable(
        table_id="t_strong", unit_index=0, order_index=1, n_rows=2, n_cols=2,
        cells=[
            CanonicalTableCell(row=0, col=0, text="Metric", is_header=True),
            CanonicalTableCell(row=0, col=1, text="Value", is_header=True),
            CanonicalTableCell(row=1, col=0, text="RTO", is_header=False),
            CanonicalTableCell(row=1, col=1, text="4 hours", is_header=False),
        ],
    )
    document = _doc([weak_table, strong_table])
    fact = {
        "fact_id": "T_001", "n_rows": 2, "n_cols": 2,
        "cells": [
            {"row": 0, "col": 0, "text": "Metric", "is_header": True},
            {"row": 0, "col": 1, "text": "Value", "is_header": True},
            {"row": 1, "col": 0, "text": "RTO", "is_header": False},
            {"row": 1, "col": 1, "text": "4 hours", "is_header": False},
        ],
        "expected_location": {},
    }

    metrics, miss_records, alignments = _score_tables("parity/PARITY_001.pdf", [fact], document, {})

    table_alignment = next(a for a in alignments if a.fact_id == "T_001")
    assert table_alignment.matched_canonical_element_ids == ["t_strong"]
    assert metrics["table_cell_text_recall"].numerator == 4  # all 4 expected cells found on the STRONG table


def test_duplicate_observed_cell_value_cannot_satisfy_two_expected_cells():
    """Two expected cells sharing the same text value must each be
    matched to a DIFFERENT observed cell -- one observed cell can never
    be consumed twice."""
    table = CanonicalTable(
        table_id="t1", unit_index=0, order_index=0, n_rows=2, n_cols=2,
        cells=[
            CanonicalTableCell(row=0, col=0, text="N/A", is_header=False),
            CanonicalTableCell(row=0, col=1, text="N/A", is_header=False),
        ],
    )
    document = _doc([table])
    fact = {
        "fact_id": "T_002", "n_rows": 2, "n_cols": 2,
        "cells": [
            {"row": 0, "col": 0, "text": "N/A", "is_header": False},
            {"row": 0, "col": 1, "text": "N/A", "is_header": False},
            {"row": 1, "col": 0, "text": "N/A", "is_header": False},  # a THIRD expected "N/A" -- only 2 observed exist
        ],
        "expected_location": {},
    }

    metrics, miss_records, alignments = _score_tables("parity/PARITY_001.pdf", [fact], document, {})

    # Exactly 2 of the 3 expected "N/A" cells can be satisfied (one
    # observed cell per expected cell, never reused) -- the third must be
    # a genuine miss, not silently matched by re-using an already-consumed
    # observed cell.
    assert metrics["table_cell_text_recall"].numerator == 2
    assert metrics["table_cell_text_recall"].denominator == 3

    cell_alignments = [a for a in alignments if a.fact_type == "table_cell"]
    assert len(cell_alignments) == 3  # one EvidenceAlignment PER expected cell (item 10)
    matched_ids = [a.matched_canonical_element_ids for a in cell_alignments if a.match_status in ("matched", "partial")]
    missing_count = sum(1 for a in cell_alignments if a.match_status == "missing")
    assert missing_count == 1
    assert len(matched_ids) == 2


def test_one_evidence_alignment_per_expected_cell():
    table = CanonicalTable(
        table_id="t1", unit_index=0, order_index=0, n_rows=1, n_cols=3,
        cells=[
            CanonicalTableCell(row=0, col=0, text="A", is_header=False),
            CanonicalTableCell(row=0, col=1, text="B", is_header=False),
            CanonicalTableCell(row=0, col=2, text="C", is_header=False),
        ],
    )
    document = _doc([table])
    fact = {
        "fact_id": "T_003", "n_rows": 1, "n_cols": 3,
        "cells": [
            {"row": 0, "col": 0, "text": "A", "is_header": False},
            {"row": 0, "col": 1, "text": "B", "is_header": False},
            {"row": 0, "col": 2, "text": "C", "is_header": False},
        ],
        "expected_location": {},
    }
    _metrics, _miss_records, alignments = _score_tables("parity/PARITY_001.pdf", [fact], document, {})
    cell_fact_ids = {a.fact_id for a in alignments if a.fact_type == "table_cell"}
    assert cell_fact_ids == {"T_003_r0c0", "T_003_r0c1", "T_003_r0c2"}


def test_no_candidate_table_records_missing_alignment_for_every_cell():
    document = _doc([])
    fact = {
        "fact_id": "T_004", "n_rows": 1, "n_cols": 1, "cells": [{"row": 0, "col": 0, "text": "Only", "is_header": False}],
        "expected_location": {},
    }
    metrics, miss_records, alignments = _score_tables("parity/PARITY_001.pdf", [fact], document, {})
    assert metrics["table_presence"].numerator == 0
    assert metrics["table_presence"].denominator == 1
    assert any(a.fact_id == "T_004_r0c0" and a.match_status == "missing" for a in alignments)
    assert any(a.fact_id == "T_004" and a.match_status == "missing" for a in alignments)
