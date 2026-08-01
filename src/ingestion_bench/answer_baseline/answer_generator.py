"""Stage 7A.2: answer generation.

Exactly ONE real answer model is configured (OpenAI, `config.ANSWER_MODEL`)
-- never a provider/plugin framework supporting swappable backends. A
separate, deterministic FAKE generator exists ONLY for the unit-test
suite, so tests never need network access or an API key.

Both generators funnel through `_resolve_answer_result`, which is the
ONLY place a `ClaimCitation`/`AnswerResult` is actually constructed --
it resolves `cited_chunk_provenance` by copying fields verbatim from the
already-known Stage 7A.1 `RetrievalResult` for each cited chunk_id that
WAS actually retrieved, and simply leaves provenance unresolved (never
fabricated) for a chunk_id the model cited that was never retrieved.
This is what makes "no answer claim can introduce a new source
reference" true by construction, while still preserving genuinely
invalid citations as data for validation.py to detect and count.
"""

from __future__ import annotations

import json
import time
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from ingestion_bench.answer_baseline import config
from ingestion_bench.answer_baseline.model import AnswerResult, CitedChunkProvenance, ClaimCitation
from ingestion_bench.answer_baseline.prompt import ANSWER_JSON_SCHEMA, SYSTEM_PROMPT, build_user_prompt
from ingestion_bench.retrieval_baseline.retrieval import RetrievalResult


class AnswerGenerator(Protocol):
    model_identity: str

    def generate(self, question_id: str, question: str, retrieved: list[RetrievalResult]) -> AnswerResult: ...


def _resolve_answer_result(
    *,
    question_id: str,
    question: str,
    retrieved: list[RetrievalResult],
    model_identity: str,
    evidence_sufficient: bool,
    answer_text: str,
    raw_claims: list[tuple[str, list[str]]],
    input_tokens: int | None,
    output_tokens: int | None,
    latency_seconds: float,
) -> AnswerResult:
    by_chunk_id = {r.chunk_id: r for r in retrieved}

    claim_citations: list[ClaimCitation] = []
    for claim_text, cited_chunk_ids in raw_claims:
        provenance = [
            CitedChunkProvenance(
                chunk_id=r.chunk_id,
                fixture=r.fixture,
                doc_id=r.doc_id,
                source_format=r.source_format,
                unit_indices=r.unit_indices,
                source_element_ids=r.source_element_ids,
                heading_source_element_ids=r.heading_source_element_ids,
                annotation_ids=r.annotation_ids,
                source_refs=r.source_refs,
            )
            for cid in cited_chunk_ids
            if (r := by_chunk_id.get(cid)) is not None
        ]
        claim_citations.append(
            ClaimCitation(claim_text=claim_text, cited_chunk_ids=list(cited_chunk_ids), cited_chunk_provenance=provenance)
        )

    cited_chunks = sorted({cid for claim in claim_citations for cid in claim.cited_chunk_ids})

    return AnswerResult(
        question_id=question_id,
        question=question,
        answer_text=answer_text,
        evidence_sufficient=evidence_sufficient,
        cited_chunks=cited_chunks,
        claim_citations=claim_citations,
        retrieved_chunk_ids=[r.chunk_id for r in retrieved],
        model_identity=model_identity,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=config.estimate_cost_usd(model_identity, input_tokens, output_tokens),
        answer_latency_seconds=latency_seconds,
    )


class FakeAnswerClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_text: str
    cited_chunk_ids: list[str] = Field(default_factory=list)


class FakeAnswerResponse(BaseModel):
    """A canned, fully-deterministic response a test wires up for a
    specific question_id -- including deliberately invalid content (a
    cited_chunk_id never present in `retrieved`, an evidence_sufficient
    claim that is inconsistent with an incomplete retrieval, etc.) so
    tests can prove validation.py actually detects such cases, without
    any network dependency or real model variance."""

    model_config = ConfigDict(extra="forbid")

    evidence_sufficient: bool
    answer_text: str
    claims: list[FakeAnswerClaim] = Field(default_factory=list)


class FakeAnswerGenerator:
    """Deterministic, no-network answer generator for the unit-test
    suite. Returns the canned `FakeAnswerResponse` registered for a
    question_id; if none was registered, returns a trivial default
    (one claim per retrieved chunk, citing exactly that chunk) so tests
    that don't care about answer content still get a valid, resolvable
    result."""

    model_identity = "fake-answer-generator-v1"

    def __init__(self, responses: dict[str, FakeAnswerResponse] | None = None) -> None:
        self._responses = responses or {}

    def generate(self, question_id: str, question: str, retrieved: list[RetrievalResult]) -> AnswerResult:
        start = time.perf_counter()
        response = self._responses.get(question_id)
        if response is None:
            response = FakeAnswerResponse(
                evidence_sufficient=True,
                answer_text="Fake deterministic answer.",
                claims=[FakeAnswerClaim(claim_text=f"Fake claim citing {r.chunk_id}.", cited_chunk_ids=[r.chunk_id]) for r in retrieved],
            )
        latency = time.perf_counter() - start
        return _resolve_answer_result(
            question_id=question_id,
            question=question,
            retrieved=retrieved,
            model_identity=self.model_identity,
            evidence_sufficient=response.evidence_sufficient,
            answer_text=response.answer_text,
            raw_claims=[(c.claim_text, c.cited_chunk_ids) for c in response.claims],
            input_tokens=None,
            output_tokens=None,
            latency_seconds=latency,
        )


class OpenAIAnswerGenerator:
    """The one REAL, configured answer model. The OpenAI client is
    loaded LAZILY (only on first `generate()` call), so merely
    constructing this class never requires network access or a valid
    API key -- only actually using it does. Uses OpenAI's structured
    JSON-schema output mode (`ANSWER_JSON_SCHEMA`) so the model's output
    always parses as exactly {evidence_sufficient, claims, answer_text}
    -- never free-form text that needs fuzzy re-parsing."""

    def __init__(self, model_identity: str | None = None) -> None:
        self.model_identity = model_identity or config.ANSWER_MODEL
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()
        return self._client

    def generate(self, question_id: str, question: str, retrieved: list[RetrievalResult]) -> AnswerResult:
        client = self._ensure_client()
        start = time.perf_counter()
        response = client.chat.completions.create(
            model=self.model_identity,
            temperature=config.ANSWER_TEMPERATURE,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(question, retrieved)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "answer", "schema": ANSWER_JSON_SCHEMA, "strict": True},
            },
        )
        latency = time.perf_counter() - start

        payload = json.loads(response.choices[0].message.content)
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage is not None else None
        output_tokens = usage.completion_tokens if usage is not None else None
        raw_claims = [(claim["claim_text"], claim["cited_chunk_ids"]) for claim in payload["claims"]]

        return _resolve_answer_result(
            question_id=question_id,
            question=question,
            retrieved=retrieved,
            model_identity=self.model_identity,
            evidence_sufficient=payload["evidence_sufficient"],
            answer_text=payload["answer_text"],
            raw_claims=raw_claims,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_seconds=latency,
        )
