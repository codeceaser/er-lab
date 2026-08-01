"""Stage 7A.2: prompt construction tests."""

from __future__ import annotations

from ingestion_bench.answer_baseline.prompt import ANSWER_JSON_SCHEMA, SYSTEM_PROMPT, build_user_prompt
from ingestion_bench.retrieval_baseline.retrieval import RetrievalResult


def _result(chunk_id: str, text: str, heading_path: list[str] | None = None) -> RetrievalResult:
    return RetrievalResult(
        rank=1, score=0.9, chunk_id=chunk_id, content_sha256="a" * 64, retrieval_text=text,
        fixture="x/y", doc_id="D", source_format="pdf", unit_indices=[0], source_element_ids=[],
        heading_source_element_ids=[], annotation_ids=[], source_refs=[], heading_path=heading_path or [],
    )


def test_system_prompt_instructs_current_vs_retired_distinction():
    lowered = SYSTEM_PROMPT.lower()
    for term in ("retired", "superseded", "historical", "draft"):
        assert term in lowered


def test_system_prompt_forbids_manufacturing_missing_facts_and_requires_insufficiency_statement():
    lowered = SYSTEM_PROMPT.lower()
    assert "insufficient" in lowered
    assert "invent" in lowered or "manufacture" in lowered


def test_system_prompt_restricts_citations_to_supplied_chunk_ids():
    lowered = SYSTEM_PROMPT.lower()
    assert "chunk_id" in lowered


def test_user_prompt_includes_only_the_supplied_retrieved_chunks_and_their_text():
    """The retired/draft evidence in a chunk's own retrieval_text is
    present in the prompt verbatim (never filtered out) -- the model
    must see it to be able to correctly disregard it per the system
    prompt's own instructions."""
    retrieved = [
        _result("c1", "Current control C-88 is active."),
        _result("c2", "SB_002 (Superseded annotation, draft, do not use): RTO was 8 hours."),
    ]
    prompt = build_user_prompt("What is the current RTO?", retrieved)
    assert "c1" in prompt and "c2" in prompt
    assert "Current control C-88 is active." in prompt
    assert "Superseded annotation, draft, do not use" in prompt
    assert "c1, c2" in prompt or ("c1" in prompt and "c2" in prompt)


def test_user_prompt_never_includes_a_chunk_id_not_in_the_supplied_list():
    retrieved = [_result("c1", "text one")]
    prompt = build_user_prompt("q", retrieved)
    assert "c2" not in prompt


def test_answer_json_schema_is_minimal_and_strict():
    props = ANSWER_JSON_SCHEMA["properties"]
    assert set(props.keys()) == {"evidence_sufficient", "claims", "answer_text"}
    assert ANSWER_JSON_SCHEMA["additionalProperties"] is False
    claim_props = props["claims"]["items"]["properties"]
    assert set(claim_props.keys()) == {"claim_text", "cited_chunk_ids"}
    assert props["claims"]["items"]["additionalProperties"] is False
