"""Stage 7A.1: corpus-level gold-evidence resolution tests.

Proves the fixture + fact_id + chunk_id scoped identity (fact ids are
NOT globally unique across the PARITY_001 PDF/DOCX/PPTX variants), and
that missing-from-ingestion/not-applicable facts are correctly excluded
from the gold set entirely -- never silently miscounted as a retrieval
failure.
"""

from __future__ import annotations

import json

import pytest

from ingestion_bench.evaluation.model import EvidenceAlignment
from ingestion_bench.retrieval_baseline.config import ARTIFACTS_STAGE5A_ROOT, CORPUS_PROFILES_PATH, EVIDENCE_ALIGNMENT_PATH
from ingestion_bench.retrieval_baseline.corpus import load_corpus_profile_set
from ingestion_bench.retrieval_baseline.gold import gold_chunk_ids, resolve_corpus_gold_evidence


def _skip_if_no_artifacts():
    if not EVIDENCE_ALIGNMENT_PATH.exists():
        pytest.skip("artifacts/stage6a/evidence_alignment.json not present -- run scripts/run_stage6a_evaluation.py first")
    if not (ARTIFACTS_STAGE5A_ROOT / "PARITY_001_pdf" / "canonical_chunks.jsonl").exists():
        pytest.skip("artifacts/stage5a/ not present -- run scripts/run_docling_standard.py first")


def _real_catalog() -> list[EvidenceAlignment]:
    return [EvidenceAlignment.model_validate(e) for e in json.loads(EVIDENCE_ALIGNMENT_PATH.read_text(encoding="utf-8"))]


def test_fact_id_alone_is_not_globally_unique_across_parity_formats():
    """The SAME fact_id ("P_001") legitimately resolves to a DIFFERENT
    chunk_id in each parity format -- proving why the scoped fixture +
    fact_id + chunk_id identity is required, not optional."""
    _skip_if_no_artifacts()
    catalog = _real_catalog()
    chunk_ids_by_fixture = {
        a.fixture: a.matched_chunk_ids[0]
        for a in catalog
        if a.fact_id == "P_001" and a.fixture.startswith("parity/") and a.matched_chunk_ids
    }
    assert len(chunk_ids_by_fixture) == 3  # pdf, docx, pptx all declare P_001
    assert len(set(chunk_ids_by_fixture.values())) == 3  # all three chunk_ids are DIFFERENT


def test_scoped_resolution_returns_one_entry_per_fixture_that_declares_the_fact():
    _skip_if_no_artifacts()
    catalog = _real_catalog()
    fixtures = ["parity/PARITY_001.pdf", "parity/PARITY_001.docx", "parity/PARITY_001.pptx"]
    indexed = {a.matched_chunk_ids[0] for a in catalog if a.fact_id == "P_001" and a.fixture in fixtures}
    evidence = resolve_corpus_gold_evidence(["P_001"], fixtures, catalog, indexed)
    entries = evidence["P_001"]
    assert len(entries) == 3
    assert {e.fixture for e in entries} == set(fixtures)
    assert all(e.status == "available_with_chunks" for e in entries)


def test_a_fact_not_declared_for_a_fixture_is_silently_skipped_not_an_error():
    """Unlike Stage 6B's single-fixture resolver (which raises on an
    unknown fact_id), the corpus-level resolver must NOT raise when a
    fact simply doesn't apply to one of several fixtures in a
    multi-suite corpus -- e.g. a stress-only fact checked against a
    parity fixture."""
    _skip_if_no_artifacts()
    catalog = _real_catalog()
    evidence = resolve_corpus_gold_evidence(
        ["STRESS_SCANNED_001_OCR_TEXT"], ["parity/PARITY_001.pdf", "stress/STRESS_SCANNED_001.pdf"], catalog, set()
    )
    entries = evidence["STRESS_SCANNED_001_OCR_TEXT"]
    assert len(entries) == 1
    assert entries[0].fixture == "stress/STRESS_SCANNED_001.pdf"


def test_missing_from_ingestion_fact_is_excluded_never_a_fabricated_chunk_id():
    """ID_004_occ_2 (DOCX) is a REAL Stage 6A missing-from-ingestion
    finding (D-047) -- the corpus resolver must report it as such, with
    zero chunk_ids, never invent a chunk_id or silently drop the fact."""
    _skip_if_no_artifacts()
    catalog = _real_catalog()
    evidence = resolve_corpus_gold_evidence(["ID_004_occ_2"], ["parity/PARITY_001.docx"], catalog, set())
    entries = evidence["ID_004_occ_2"]
    assert len(entries) == 1
    assert entries[0].status == "missing_from_ingestion"
    assert entries[0].chunk_ids == []


def test_not_applicable_fact_is_excluded_from_gold_chunk_ids():
    """CF_001 (a chart visual fact) is structurally not_applicable to
    path A -- must contribute NOTHING to the gold set, and must not be
    confused with a genuine retrieval-availability gap."""
    _skip_if_no_artifacts()
    catalog = _real_catalog()
    evidence = resolve_corpus_gold_evidence(["CF_001"], ["stress/STRESS_CHART_001.pdf"], catalog, set())
    entries = evidence["CF_001"]
    assert entries[0].status == "not_applicable"
    assert gold_chunk_ids(entries) == set()


def test_chunk_id_not_present_in_this_corpus_index_becomes_ingested_without_chunks():
    """A fact genuinely matched at Stage 6A, but whose chunk id is not
    part of THIS corpus profile's actually-built index (e.g. the fixture
    was excluded from this profile, or a real chunk_projection_loss) must
    resolve to ingested_without_chunks -- never silently treated as
    available."""
    _skip_if_no_artifacts()
    catalog = _real_catalog()
    # Deliberately supply an EMPTY indexed_chunk_ids set -- simulates
    # "this corpus profile's index doesn't actually contain the matched
    # chunk," regardless of why.
    evidence = resolve_corpus_gold_evidence(["P_001"], ["parity/PARITY_001.pdf"], catalog, set())
    entries = evidence["P_001"]
    assert entries[0].status == "ingested_without_chunks"
    assert entries[0].chunk_ids == []


def test_gold_chunk_ids_unions_across_multiple_fixture_entries():
    _skip_if_no_artifacts()
    catalog = _real_catalog()
    fixtures = ["parity/PARITY_001.pdf", "parity/PARITY_001.docx"]
    indexed = {a.matched_chunk_ids[0] for a in catalog if a.fact_id == "P_001" and a.fixture in fixtures}
    evidence = resolve_corpus_gold_evidence(["P_001"], fixtures, catalog, indexed)
    union = gold_chunk_ids(evidence["P_001"])
    assert len(union) == 2  # pdf and docx chunk ids are different, both present
