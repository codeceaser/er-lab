"""Stage 7A.2: strict Pydantic models for the auditable vector-RAG
answer baseline.

The answer model (LLM) ever supplies only `claim_text` and
`cited_chunk_ids` (a list of strings) -- every other field on
`ClaimCitation`/`AnswerResult` (provenance, token usage, cost, latency,
`retrieved_chunk_ids`, the `cited_chunks` union) is computed/resolved by
this project's OWN code from the Stage 7A.1 retrieval context, never
trusted from the model's own output. This is what makes "no answer claim
can introduce a new source reference" true by construction, and what
lets `validation.py` mechanically detect a genuinely invalid citation
(the model citing a chunk_id that was never retrieved) as DATA, rather
than the model layer silently rejecting or crashing on it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CitedChunkProvenance(BaseModel):
    """One cited chunk's provenance, resolved from the Stage 7A.1
    retrieval context this answer was generated from -- copied verbatim,
    never invented. Only ever attached for a chunk_id that WAS actually
    retrieved; a citation to an unretrieved chunk_id has no corresponding
    entry here (see `validation.py` for how that is detected and
    counted, never silently dropped)."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    fixture: str
    doc_id: str
    source_format: str
    unit_indices: list[int] = Field(default_factory=list)
    source_element_ids: list[str] = Field(default_factory=list)
    heading_source_element_ids: list[str] = Field(default_factory=list)
    annotation_ids: list[str] = Field(default_factory=list)
    source_refs: list[dict] = Field(default_factory=list)


class ClaimCitation(BaseModel):
    """One substantive claim from the generated answer, with the exact
    chunk id(s) the answer model cited as supporting evidence."""

    model_config = ConfigDict(extra="forbid")

    claim_text: str
    cited_chunk_ids: list[str] = Field(default_factory=list)
    cited_chunk_provenance: list[CitedChunkProvenance] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_provenance_ids_are_a_subset_of_cited_ids(self) -> "ClaimCitation":
        """Provenance may be a PROPER SUBSET of cited_chunk_ids (a
        citation to a chunk that was never retrieved legitimately has no
        provenance to attach -- that is an invalid citation, detected by
        validation.py, not a construction-time error here) but must
        never contain an id that was not even cited."""
        provenance_ids = {p.chunk_id for p in self.cited_chunk_provenance}
        cited_ids = set(self.cited_chunk_ids)
        extra = provenance_ids - cited_ids
        if extra:
            raise ValueError(f"cited_chunk_provenance contains ids never in cited_chunk_ids: {sorted(extra)}")
        return self


class AnswerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    question: str
    answer_text: str
    evidence_sufficient: bool
    cited_chunks: list[str] = Field(default_factory=list)
    claim_citations: list[ClaimCitation] = Field(default_factory=list)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    model_identity: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    answer_latency_seconds: float = Field(ge=0)

    @model_validator(mode="after")
    def _validate_cited_chunks_is_the_union_of_claim_citations(self) -> "AnswerResult":
        """cited_chunks is always COMPUTED from claim_citations by this
        project's own code (never independently supplied) -- this
        equality is an internal-consistency guard, not a business-rule
        check on the answer model's behavior."""
        expected = sorted({cid for claim in self.claim_citations for cid in claim.cited_chunk_ids})
        if sorted(self.cited_chunks) != expected:
            raise ValueError(f"cited_chunks {sorted(self.cited_chunks)} must equal the union of claim citations {expected}")
        return self
