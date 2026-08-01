"""Stage 7A.2: prompt construction.

Built ENTIRELY from a single question's already-known Stage 7A.1
top-K retrieval context -- never re-runs retrieval, never adds outside
evidence. The model's own output schema is deliberately minimal
(`evidence_sufficient` + `claims: [{claim_text, cited_chunk_ids}]`);
every other field an `AnswerResult` needs is resolved later by
deterministic Python code (answer_generator.py/validation.py), never
trusted from the model's own output.
"""

from __future__ import annotations

from ingestion_bench.retrieval_baseline.retrieval import RetrievalResult

SYSTEM_PROMPT = """You are an auditable evidence-grounded question-answering system for an \
enterprise document corpus. You will be given a question and a fixed list of retrieved \
evidence chunks. Follow these rules exactly:

1. Use ONLY the retrieved evidence chunks below. Never use outside knowledge, and never \
invent facts not present in the retrieved text.
2. Some retrieved chunks may contain RETIRED, SUPERSEDED, HISTORICAL, LEGACY, DECOMMISSIONED, \
or DRAFT information (this may be stated explicitly in the chunk text, e.g. a label like \
"superseded", "retired", "do not use", "decommissioned", or a similar signal). You must \
distinguish CURRENT facts from such retired/superseded/historical/draft facts, and must \
never present retired/superseded/historical/draft evidence as if it were a current fact, \
even if it is topically similar to or shares an identifier substring with the current fact.
3. Some retrieved chunks may be distractors that are topically related but do not actually \
answer the question, or that describe a DIFFERENT entity than the one asked about. Never \
present such forbidden/distractor evidence as if it were the current, correct answer.
4. If the retrieved evidence does not contain a required fact needed to fully answer the \
question, you MUST explicitly state that the evidence is insufficient for that part of the \
answer (in the answer text) and set evidence_sufficient to false. Do not manufacture a \
missing table value, visual/chart fact, or relationship that is not actually present in the \
retrieved text.
5. Cite every substantive claim in your answer. A substantive claim is any factual statement \
that could be individually verified against the evidence (as opposed to filler/transition \
text). For each substantive claim, produce one claims[] entry with the exact claim text and \
the chunk_id(s) of the retrieved chunk(s) that actually support it.
6. You may cite ONLY chunk_id values that appear in the retrieved evidence list below. Never \
invent a chunk_id, and never cite a chunk that does not actually support the claim text it is \
attached to.
7. Set evidence_sufficient to true only if the retrieved evidence, taken together, fully and \
currently answers the question with no required fact missing.

Respond using only the structured fields you are given -- do not add any other information."""


def _format_chunk_block(result: RetrievalResult) -> str:
    heading = " > ".join(result.heading_path) if result.heading_path else "(no heading path)"
    return (
        f"[chunk_id: {result.chunk_id}] (rank {result.rank}, fixture: {result.fixture}, "
        f"doc_id: {result.doc_id}, heading path: {heading})\n{result.retrieval_text}"
    )


def build_user_prompt(question: str, retrieved: list[RetrievalResult]) -> str:
    chunk_blocks = "\n\n".join(_format_chunk_block(r) for r in retrieved)
    retrieved_ids = ", ".join(r.chunk_id for r in retrieved)
    return f"""Question: {question}

Retrieved evidence chunks (you may cite ONLY these chunk_id values: {retrieved_ids}):

{chunk_blocks}

Answer the question using only the rules in the system prompt."""


# The model's own output schema -- deliberately minimal. `claims` supplies
# only free-text claim content and the chunk ids the model itself asserts
# support it; `cited_chunk_provenance`/`retrieved_chunk_ids`/token usage/
# cost/latency/model_identity on the final AnswerResult are ALL resolved
# by this project's own code afterward, never taken from this schema.
ANSWER_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "evidence_sufficient": {"type": "boolean"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_text": {"type": "string"},
                    "cited_chunk_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["claim_text", "cited_chunk_ids"],
                "additionalProperties": False,
            },
        },
        "answer_text": {"type": "string"},
    },
    "required": ["evidence_sufficient", "claims", "answer_text"],
    "additionalProperties": False,
}
