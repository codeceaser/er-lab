"""Stage 7A.1: corpus profile tests.

Proves baseline_demo excludes the duplicate parity variants, the
format_comparison profiles are never combined, and the frozen
contracts/corpus_profiles_v1.json loads and validates against real
Stage 5A fixtures.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ingestion_bench.retrieval_baseline.config import ARTIFACTS_STAGE5A_ROOT, CORPUS_PROFILES_PATH
from ingestion_bench.retrieval_baseline.corpus import (
    CorpusProfile,
    CorpusProfileSet,
    load_corpus_chunks,
    load_corpus_profile_set,
)


def test_frozen_corpus_profiles_load_and_validate():
    profile_set = load_corpus_profile_set(CORPUS_PROFILES_PATH)
    assert set(profile_set.profiles.keys()) == {"baseline_demo", "parity_pdf", "parity_docx", "parity_pptx"}


def test_baseline_demo_excludes_duplicate_parity_variants():
    profile_set = load_corpus_profile_set(CORPUS_PROFILES_PATH)
    fixtures = set(profile_set.profiles["baseline_demo"].fixtures)
    assert "parity/PARITY_001.pdf" in fixtures
    assert "parity/PARITY_001.docx" not in fixtures
    assert "parity/PARITY_001.pptx" not in fixtures


def test_baseline_demo_includes_every_unique_stress_fixture():
    profile_set = load_corpus_profile_set(CORPUS_PROFILES_PATH)
    fixtures = set(profile_set.profiles["baseline_demo"].fixtures)
    stress_fixtures = {f for f in fixtures if f.startswith("stress/")}
    assert stress_fixtures == {
        "stress/STRESS_DOCX_001.docx",
        "stress/STRESS_PDF_001.pdf",
        "stress/STRESS_PPTX_001.pptx",
        "stress/STRESS_PPTX_002.pptx",
        "stress/STRESS_CHART_001.pdf",
        "stress/STRESS_SCANNED_001.pdf",
    }


def test_format_comparison_group_never_combined():
    profile_set = load_corpus_profile_set(CORPUS_PROFILES_PATH)
    for name in profile_set.format_comparison_group:
        assert len(profile_set.profiles[name].fixtures) == 1, name


def test_format_comparison_profiles_are_the_three_distinct_parity_formats():
    profile_set = load_corpus_profile_set(CORPUS_PROFILES_PATH)
    fixtures = {profile_set.profiles[name].fixtures[0] for name in profile_set.format_comparison_group}
    assert fixtures == {"parity/PARITY_001.pdf", "parity/PARITY_001.docx", "parity/PARITY_001.pptx"}


def test_model_rejects_baseline_demo_including_a_duplicate_parity_variant():
    with pytest.raises(ValidationError, match="duplicate parity variants"):
        CorpusProfileSet(
            corpus_profiles_version="1.0.0",
            profiles={
                "baseline_demo": CorpusProfile(
                    name="baseline_demo",
                    description="x",
                    fixtures=["parity/PARITY_001.pdf", "parity/PARITY_001.docx"],
                )
            },
            format_comparison_group=[],
        )


def test_model_rejects_a_format_comparison_profile_with_more_than_one_fixture():
    with pytest.raises(ValidationError, match="never combined"):
        CorpusProfileSet(
            corpus_profiles_version="1.0.0",
            profiles={
                "baseline_demo": CorpusProfile(name="baseline_demo", description="x", fixtures=["parity/PARITY_001.pdf"]),
                "bad_combo": CorpusProfile(
                    name="bad_combo", description="x", fixtures=["parity/PARITY_001.pdf", "parity/PARITY_001.docx"]
                ),
            },
            format_comparison_group=["bad_combo"],
        )


def test_model_rejects_unknown_fixture_key():
    with pytest.raises(ValidationError, match="unknown fixture"):
        CorpusProfile(name="bad", description="x", fixtures=["parity/NOT_A_REAL_FIXTURE.pdf"])


def test_model_rejects_duplicate_fixtures_within_one_profile():
    with pytest.raises(ValidationError, match="duplicate fixtures"):
        CorpusProfile(name="bad", description="x", fixtures=["parity/PARITY_001.pdf", "parity/PARITY_001.pdf"])


# --- real Stage 5A artifact loading ------------------------------------------


def _skip_if_no_artifacts():
    if not (ARTIFACTS_STAGE5A_ROOT / "PARITY_001_pdf" / "canonical_chunks.jsonl").exists():
        pytest.skip("artifacts/stage5a/ not present -- run scripts/run_docling_standard.py first")


def test_load_corpus_chunks_tags_every_chunk_with_fixture_identity():
    _skip_if_no_artifacts()
    profile_set = load_corpus_profile_set(CORPUS_PROFILES_PATH)
    profile = profile_set.profiles["parity_pdf"]
    tagged = load_corpus_chunks(profile, ARTIFACTS_STAGE5A_ROOT)
    assert tagged
    for tc in tagged:
        assert tc.fixture == "parity/PARITY_001.pdf"
        assert tc.doc_id == "PARITY_001"
        assert tc.source_format == "pdf"


def test_load_corpus_chunks_baseline_demo_spans_all_seven_fixtures():
    _skip_if_no_artifacts()
    profile_set = load_corpus_profile_set(CORPUS_PROFILES_PATH)
    profile = profile_set.profiles["baseline_demo"]
    tagged = load_corpus_chunks(profile, ARTIFACTS_STAGE5A_ROOT)
    fixtures_seen = {tc.fixture for tc in tagged}
    assert fixtures_seen == set(profile.fixtures)
