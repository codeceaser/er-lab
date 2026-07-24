"""Stage 6B: strict Pydantic models for the minimal retrieval benchmark
contract.

This module describes the SHAPE of a frozen benchmark question set only.
`resolver.py` is what actually maps a question's `required_fact_ids` to
`matched_chunk_ids` from a supplied Stage 6A `EvidenceAlignment` catalog
-- never hardcoded here, and never one lane's chunk ids treated as
authoritative gold.

No embeddings, no pgvector, no retrieval execution, no LLM, no network
call exists anywhere in this module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Reuses the exact difficulty vocabulary Stage 6A's EvidenceAlignment
# already reserved a field for (RetrievalDifficulty, D-046) -- Stage 6B
# is the first stage allowed to actually assign these labels, to real
# questions, rather than infer them from ingestion-side signals.
QuestionDifficulty = Literal["direct", "distractor_sensitive", "relational", "multi_hop", "consolidation"]

# The frozen Stage 6B distribution: 4 + 3 + 2 + 2 + 1 = 12 questions.
REQUIRED_DIFFICULTY_COUNTS: dict[str, int] = {
    "direct": 4,
    "distractor_sensitive": 3,
    "relational": 2,
    "multi_hop": 2,
    "consolidation": 1,
}
REQUIRED_QUESTION_COUNT = sum(REQUIRED_DIFFICULTY_COUNTS.values())


class BenchmarkQuestion(BaseModel):
    """One frozen benchmark question.

    `required_fact_ids`/`forbidden_fact_ids` reference STABLE fact ids
    from the Stage 6A gold evidence-alignment catalog -- either a
    manifest fact_id directly (e.g. "P_001", "CAP_001") or the
    evaluator's own derived compound id for sub-fact granularity (e.g.
    "T_001_r1c1" for one table cell, "ID_001_occ_0" for one identifier
    occurrence) -- never a chunk id, and never a lane-specific value.
    Which chunks actually satisfy a fact, in which ingestion lane, is
    resolved later by `resolver.py`, never hardcoded on the question
    itself.
    """

    model_config = ConfigDict(extra="forbid")

    question_id: str
    question: str
    difficulty: QuestionDifficulty
    required_fact_ids: list[str] = Field(min_length=1)
    forbidden_fact_ids: list[str] = Field(default_factory=list)
    citation_required: bool
    answer_rubric: str

    @model_validator(mode="after")
    def _validate_no_required_forbidden_overlap(self) -> "BenchmarkQuestion":
        overlap = set(self.required_fact_ids) & set(self.forbidden_fact_ids)
        if overlap:
            raise ValueError(
                f"{self.question_id}: required_fact_ids and forbidden_fact_ids overlap: {sorted(overlap)}"
            )
        return self

    @model_validator(mode="after")
    def _validate_no_duplicate_fact_ids(self) -> "BenchmarkQuestion":
        if len(self.required_fact_ids) != len(set(self.required_fact_ids)):
            raise ValueError(f"{self.question_id}: required_fact_ids contains duplicates")
        if len(self.forbidden_fact_ids) != len(set(self.forbidden_fact_ids)):
            raise ValueError(f"{self.question_id}: forbidden_fact_ids contains duplicates")
        return self


class RetrievalBenchmarkContract(BaseModel):
    """The complete, frozen Stage 6B benchmark: exactly 12 questions with
    a fixed distribution across difficulty categories. A closed,
    versioned data contract -- never a plug-in framework, generic rule
    engine, or configurable grading system."""

    model_config = ConfigDict(extra="forbid")

    contract_version: str
    questions: list[BenchmarkQuestion]

    @model_validator(mode="after")
    def _validate_question_count(self) -> "RetrievalBenchmarkContract":
        if len(self.questions) != REQUIRED_QUESTION_COUNT:
            raise ValueError(
                f"RetrievalBenchmarkContract must contain exactly {REQUIRED_QUESTION_COUNT} questions, "
                f"got {len(self.questions)}"
            )
        return self

    @model_validator(mode="after")
    def _validate_unique_question_ids(self) -> "RetrievalBenchmarkContract":
        seen: set[str] = set()
        for question in self.questions:
            if question.question_id in seen:
                raise ValueError(f"duplicate question_id: {question.question_id!r}")
            seen.add(question.question_id)
        return self

    @model_validator(mode="after")
    def _validate_difficulty_distribution(self) -> "RetrievalBenchmarkContract":
        counts: dict[str, int] = {}
        for question in self.questions:
            counts[question.difficulty] = counts.get(question.difficulty, 0) + 1
        for difficulty, expected in REQUIRED_DIFFICULTY_COUNTS.items():
            actual = counts.get(difficulty, 0)
            if actual != expected:
                raise ValueError(f"expected {expected} {difficulty!r} question(s), got {actual}")
        return self


def load_contract(path: str | Path) -> RetrievalBenchmarkContract:
    """Reads and validates the frozen contract JSON file -- the only
    place this package reads from disk."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return RetrievalBenchmarkContract.model_validate(data)
