"""Stage 7C.1: the bounded, source-grounded W1 facet compiler.

ONE compilation = ONE `(page_key, document_revision_id)` facet. Each call sees
ONLY the chunks of that revision that carry that page identity (Revision 6
SS3.1), so three properties are STRUCTURAL rather than merely validated:
claims are single-revision, no current/historical blending is possible, and
the compilation unit is the embedding unit.

The model's structured output is EXACTLY three fields -- `aliases`, `claims`,
`summary_sentences` (SS3.2, SS3.7). Everything else on a facet record is
deterministic: identity and metadata from Stage 7C.0, membership from SS2.2,
links derived from accepted claims (SS3.7), and `validation_status` assigned by
the deterministic validator (SS4.1) -- never by the model.

Compiler-model parity is FROZEN: the initial measured W1 compiler must use the
same model as the frozen Stage 7B.1 Real Graph extractor (`gpt-4o-mini` at
`temperature = 0`). The rationale is methodological parity for SS9.4's
attribution, not cost -- a stronger W1 model would confound representation with
extraction capability. If the environment resolves the compiler model to
anything else, the run fails before the first call.

Follows Stage 7A.2 `answer_baseline/`'s SHAPE (lazy client, strict json_schema
output, usage capture, prompt version + hash, cost estimate that returns None
rather than a fabricated number) without importing its code path.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Protocol

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from ingestion_bench.wiki_projection.model import Facet, PageIdentity, WikiSection

load_dotenv()

# --- frozen model parity (Revision 6 SS3.8) ---------------------------------
# The VALUE recorded in the frozen graph config, named here rather than
# imported: importing `graph_retrieval_benchmark` would be a Graph runtime
# dependency, which SS1.3/SS9.1 forbid.
STAGE7B1_EXTRACTION_MODEL = "gpt-4o-mini"
COMPILER_MODEL = os.environ.get("INGESTION_BENCH_WIKI_COMPILER_MODEL", STAGE7B1_EXTRACTION_MODEL)
COMPILER_TEMPERATURE = 0

_PRICING_USD_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}


def estimate_cost_usd(model_identity: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
    """Estimated USD cost where available. A model absent from the table, or a
    call with no usage report, yields None -- never a fabricated number."""
    if model_identity not in _PRICING_USD_PER_MILLION_TOKENS:
        return None
    if input_tokens is None or output_tokens is None:
        return None
    input_rate, output_rate = _PRICING_USD_PER_MILLION_TOKENS[model_identity]
    return (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate


class CompilerModelParityError(RuntimeError):
    """Raised BEFORE the first call when the configured compiler model is not
    the frozen Stage 7B.1 extraction model (Revision 6 SS3.8)."""


class UnresolvedBudgetError(RuntimeError):
    """Raised BEFORE the first call when a required budget value declared in
    Revision 6 has no value (SS3.9's whole-run dollar ceiling, Q6)."""


def verify_model_parity(model_identity: str) -> None:
    if model_identity != STAGE7B1_EXTRACTION_MODEL:
        raise CompilerModelParityError(
            f"compiler model {model_identity!r} != frozen Stage 7B.1 extraction model "
            f"{STAGE7B1_EXTRACTION_MODEL!r}; SS9.4's attribution is only interpretable if extraction "
            "capability is held constant, so the run fails before the first call (Revision 6 SS3.8)"
        )


# --- hard ceilings (Revision 6 SS3.9) ---------------------------------------

F_MAX_INPUT_CHUNKS_PER_FACET = 12
MAX_INPUT_TOKENS_PER_FACET = 8_000
MAX_CLAIMS_PER_FACET = 20  # accepted + uncertain
MAX_ALIASES_PER_FACET = 8
MAX_SUMMARY_SENTENCES_PER_FACET = 5
MAX_OUTPUT_TOKENS_PER_FACET = 4_000
PAY_MAX_PAYLOAD_CHARACTERS = 4_000

# The whole-run dollar ceiling is DELIBERATELY absent. Revision 6 SS3.9 records
# it as "declared before the run (Q6)" and Q6 states "only the per-run dollar
# cap remains open". It is a required Gate Q-9 input and it is not this code's
# to choose -- see `resolve_run_dollar_ceiling`.
RUN_DOLLAR_CEILING_ENV_VAR = "INGESTION_BENCH_STAGE7C1_DOLLAR_CAP"


def resolve_run_dollar_ceiling() -> float:
    """The whole-run dollar ceiling, or a hard STOP.

    Revision 6 leaves this value literally unresolved. Choosing one here would
    be inventing a frozen contract value, and Gate Q-9 ("within declared dollar
    cap") cannot be evaluated against an invented cap.
    """
    raw = os.environ.get(RUN_DOLLAR_CEILING_ENV_VAR)
    if raw is None or not raw.strip():
        raise UnresolvedBudgetError(
            "Revision 6 SS3.9's whole-run dollar ceiling is UNRESOLVED (open question Q6: "
            "'only the per-run dollar cap remains open'). It is a required Gate Q-9 input and must be "
            f"set by the owner, not chosen here. Set {RUN_DOLLAR_CEILING_ENV_VAR} to the approved cap "
            "in USD, or supply it explicitly to the runner."
        )
    return float(raw)


# --- prompt contract ---------------------------------------------------------

PROMPT_VERSION = "stage7c1-facet-compiler-v1"

SYSTEM_PROMPT = """You are a bounded, source-grounded compiler for ONE page facet of an \
enterprise evidence wiki. You are given a page identity and the COMPLETE source text of the \
chunks from ONE document revision in which that identity occurs. Follow these rules exactly.

1. Use ONLY the supplied source text. Never use outside knowledge. Never infer a fact that the \
supplied text does not state.
2. You may output ONLY three things: aliases, claims, and summary sentences. You must NOT \
invent or output page identities, page titles, page types, link targets, relationship labels \
for links, membership, authority state, or any currency/effectiveness field.
3. Every claim and every alias MUST cite the chunk id(s) it comes from, and MUST supply \
supporting_quotes that are EXACT, VERBATIM, CHARACTER-FOR-CHARACTER substrings of that \
chunk's source text. Do not paraphrase inside a supporting quote. Do not fix typos, casing, \
or punctuation inside a quote.
4. Every claim must DIRECTLY INVOLVE this facet's page identity: the identity must be the \
claim's subject or its object (or a genuine alias of it that you also report). A claim about \
two other entities that merely co-occur in the text does not belong on this page.
5. One claim = ONE atomic assertion, expressed as subject / predicate / object. The predicate \
must be the relationship as the source states it. Do not merge two assertions into one claim.
6. Do NOT assert that anything is current, latest, effective, in force, active, or that it \
supersedes something, UNLESS those words appear inside the exact source span you quote. This \
corpus's authority and currency are decided elsewhere; you must never encode them.
7. Identifiers that differ by even one character are DIFFERENT entities (for example C-88 and \
C-88a are NOT the same control). Never merge them, and never treat one as an alias of the other.
8. An alias is a surface form that genuinely NAMES THIS PAGE'S ENTITY in the supplied text. \
Mark status "supported" only when the alias string appears verbatim in a cited chunk; \
otherwise mark it "uncertain". A related, broader, narrower or adjacent entity is NOT an alias.
9. Every summary sentence must faithfully represent ONLY the claims it references, and must \
reference at least one of your own claims by claim_id. Do not overstate, do not invert a \
direction, do not merge claims into an unsupported composite, and do not drop a qualification.
10. If the supplied text supports nothing, return empty lists. Returning nothing is correct \
and expected when the source says nothing about this identity beyond its occurrence. Never \
pad output to seem useful."""

FACET_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["aliases", "claims", "summary_sentences"],
    "properties": {
        "aliases": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["alias", "supporting_chunk_ids", "supporting_quotes", "status"],
                "properties": {
                    "alias": {"type": "string"},
                    "supporting_chunk_ids": {"type": "array", "items": {"type": "string"}},
                    "supporting_quotes": {"type": "array", "items": {"type": "string"}},
                    "status": {"type": "string", "enum": ["supported", "uncertain"]},
                },
            },
        },
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "claim_id", "subject", "predicate", "object", "claim_text",
                    "supporting_chunk_ids", "supporting_quotes",
                ],
                "properties": {
                    "claim_id": {"type": "string"},
                    "subject": {"type": "string"},
                    "predicate": {"type": "string"},
                    "object": {"type": "string"},
                    "claim_text": {"type": "string"},
                    "supporting_chunk_ids": {"type": "array", "items": {"type": "string"}},
                    "supporting_quotes": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "summary_sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["sentence_id", "text", "supported_claim_ids"],
                "properties": {
                    "sentence_id": {"type": "string"},
                    "text": {"type": "string"},
                    "supported_claim_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}


def prompt_sha256() -> str:
    """Exact content hash of the prompt contract -- system prompt + schema."""
    blob = json.dumps(
        {"version": PROMPT_VERSION, "system_prompt": SYSTEM_PROMPT, "schema": FACET_JSON_SCHEMA},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class FacetCompilationInput(BaseModel):
    """Everything ONE compilation may see. Deliberately carries no other
    revision, no other page, no other facet's output, no benchmark truth, no
    authority state and no Graph output (Revision 6 SS3.1)."""

    model_config = ConfigDict(extra="forbid")

    page_key: str
    page_type: str
    display_title: str
    document_revision_id: str
    logical_document_id: str
    input_chunk_ids: list[str]
    chunk_texts: dict[str, str]
    chunk_heading_paths: dict[str, list[str]]


def build_facet_input(facet: Facet, page: PageIdentity, sections_by_chunk: dict[str, WikiSection]) -> FacetCompilationInput:
    return FacetCompilationInput(
        page_key=page.page_key,
        page_type=page.page_type,
        display_title=page.display_title,
        document_revision_id=facet.document_revision_id,
        logical_document_id=facet.logical_document_id,
        input_chunk_ids=list(facet.chunk_ids),
        chunk_texts={cid: sections_by_chunk[cid].source_text for cid in facet.chunk_ids},
        chunk_heading_paths={cid: list(sections_by_chunk[cid].heading_path) for cid in facet.chunk_ids},
    )


def build_user_prompt(facet_input: FacetCompilationInput) -> str:
    lines = [
        f"PAGE IDENTITY: {facet_input.display_title}",
        f"PAGE KEY: {facet_input.page_key}",
        f"PAGE TYPE: {facet_input.page_type}",
        "",
        "You are compiling ONE facet: what this ONE document revision says around this identity.",
        "You can see no other revision and no other page.",
        "",
        "SOURCE CHUNKS (verbatim; quote from these exactly):",
        "",
    ]
    for chunk_id in facet_input.input_chunk_ids:
        heading = " > ".join(facet_input.chunk_heading_paths.get(chunk_id, []))
        lines.append(f"--- chunk_id: {chunk_id}")
        if heading:
            lines.append(f"    heading: {heading}")
        lines.append(f"    source_text: {facet_input.chunk_texts[chunk_id]}")
        lines.append("")
    lines.append(
        "Return aliases, claims and summary_sentences for THIS page identity only, citing only "
        "the chunk ids listed above."
    )
    return "\n".join(lines)


# --- raw model output (pre-validation) ---------------------------------------


class RawAlias(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str
    supporting_chunk_ids: list[str] = Field(default_factory=list)
    supporting_quotes: list[str] = Field(default_factory=list)
    status: str = "uncertain"


class RawClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    subject: str
    predicate: str
    object: str
    claim_text: str
    supporting_chunk_ids: list[str] = Field(default_factory=list)
    supporting_quotes: list[str] = Field(default_factory=list)


class RawSummarySentence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence_id: str
    text: str
    supported_claim_ids: list[str] = Field(default_factory=list)


class FacetCompilationOutput(BaseModel):
    """One compilation's complete result, with full provenance. `generation_failed`
    records a call that did not produce parseable output -- never silently
    dropped, because SS4.2 forbids discarding anything silently."""

    model_config = ConfigDict(extra="forbid")

    page_key: str
    document_revision_id: str
    run_id: int

    aliases: list[RawAlias] = Field(default_factory=list)
    claims: list[RawClaim] = Field(default_factory=list)
    summary_sentences: list[RawSummarySentence] = Field(default_factory=list)

    model_identity: str
    temperature: float
    prompt_version: str
    prompt_sha256: str
    input_chunk_ids: list[str]
    raw_response_json: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    latency_seconds: float = 0.0
    generation_failed: bool = False
    generation_error: str | None = None


class FacetCompiler(Protocol):
    model_identity: str

    def compile_facet(self, facet_input: FacetCompilationInput, run_id: int) -> FacetCompilationOutput: ...


def _preflight(facet_input: FacetCompilationInput) -> None:
    """The one ceiling checkable BEFORE the call. Token ceilings are evaluated
    against the API's own usage report afterwards (SS3.9 breach = fail the
    facet, never truncate-and-continue)."""
    if len(facet_input.input_chunk_ids) > F_MAX_INPUT_CHUNKS_PER_FACET:
        raise CeilingBreach(
            f"facet {facet_input.page_key}/{facet_input.document_revision_id}: "
            f"{len(facet_input.input_chunk_ids)} input chunks exceeds F_max={F_MAX_INPUT_CHUNKS_PER_FACET}"
        )


class CeilingBreach(RuntimeError):
    """A Revision 6 SS3.9 ceiling was exceeded. Fails the facet; never batched,
    truncated, summarized hierarchically, or worked around."""


class OpenAIFacetCompiler:
    """The one REAL, configured compiler. The client is loaded LAZILY, so
    constructing this class never requires network access or an API key --
    only actually compiling does. Uses strict json_schema output mode so the
    result always parses as exactly {aliases, claims, summary_sentences}."""

    def __init__(self, model_identity: str | None = None) -> None:
        self.model_identity = model_identity or COMPILER_MODEL
        verify_model_parity(self.model_identity)
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()
        return self._client

    def compile_facet(self, facet_input: FacetCompilationInput, run_id: int) -> FacetCompilationOutput:
        _preflight(facet_input)
        client = self._ensure_client()
        start = time.perf_counter()

        base = dict(
            page_key=facet_input.page_key, document_revision_id=facet_input.document_revision_id,
            run_id=run_id, model_identity=self.model_identity, temperature=float(COMPILER_TEMPERATURE),
            prompt_version=PROMPT_VERSION, prompt_sha256=prompt_sha256(),
            input_chunk_ids=list(facet_input.input_chunk_ids),
        )

        try:
            response = client.chat.completions.create(
                model=self.model_identity,
                temperature=COMPILER_TEMPERATURE,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(facet_input)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "wiki_facet", "schema": FACET_JSON_SCHEMA, "strict": True},
                },
            )
            latency = time.perf_counter() - start
            content = response.choices[0].message.content
            payload = json.loads(content)
            usage = response.usage
            input_tokens = usage.prompt_tokens if usage is not None else None
            output_tokens = usage.completion_tokens if usage is not None else None
            return FacetCompilationOutput(
                **base,
                aliases=[RawAlias(**a) for a in payload["aliases"]],
                claims=[RawClaim(**c) for c in payload["claims"]],
                summary_sentences=[RawSummarySentence(**s) for s in payload["summary_sentences"]],
                raw_response_json=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=estimate_cost_usd(self.model_identity, input_tokens, output_tokens),
                latency_seconds=latency,
            )
        except Exception as exc:  # noqa: BLE001 -- recorded, never silently dropped (SS4.2)
            return FacetCompilationOutput(
                **base, latency_seconds=time.perf_counter() - start,
                generation_failed=True, generation_error=f"{type(exc).__name__}: {exc}",
            )


class ScriptedFacetCompiler:
    """A deterministic test double that replays a caller-supplied output per
    `(page_key, document_revision_id)`. Used ONLY by the test suite, to
    exercise validation paths (bad citations, out-of-scope claims, forbidden
    status terms, ceiling breaches) that a well-behaved compiler would not
    produce. Never used to produce reported results."""

    model_identity = "scripted-deterministic-v1"

    def __init__(self, scripted: dict[tuple[str, str], dict] | None = None) -> None:
        self._scripted = scripted or {}

    def compile_facet(self, facet_input: FacetCompilationInput, run_id: int) -> FacetCompilationOutput:
        _preflight(facet_input)
        payload = self._scripted.get((facet_input.page_key, facet_input.document_revision_id), {})
        return FacetCompilationOutput(
            page_key=facet_input.page_key, document_revision_id=facet_input.document_revision_id,
            run_id=run_id,
            aliases=[RawAlias(**a) for a in payload.get("aliases", [])],
            claims=[RawClaim(**c) for c in payload.get("claims", [])],
            summary_sentences=[RawSummarySentence(**s) for s in payload.get("summary_sentences", [])],
            model_identity=self.model_identity, temperature=0.0,
            prompt_version=PROMPT_VERSION, prompt_sha256=prompt_sha256(),
            input_chunk_ids=list(facet_input.input_chunk_ids),
            raw_response_json=json.dumps(payload, sort_keys=True),
            input_tokens=payload.get("_input_tokens"),
            output_tokens=payload.get("_output_tokens"),
            latency_seconds=0.0,
        )


class FakeFacetCompiler:
    """A deterministic, NON-LLM stand-in that produces plausibly-shaped output
    from the source text by fixed rules, so the whole 7C.1 pipeline (schema,
    validation, link derivation, adjudication packet, previews, repeatability)
    can be exercised end-to-end with ZERO model calls.

    It is a TEST DOUBLE, not a compiler: it makes no semantic judgement and its
    output must never be reported as a W1 result.
    """

    model_identity = "fake-deterministic-facet-compiler-v1"

    def compile_facet(self, facet_input: FacetCompilationInput, run_id: int) -> FacetCompilationOutput:
        import re

        _preflight(facet_input)
        aliases: list[RawAlias] = []
        claims: list[RawClaim] = []
        summaries: list[RawSummarySentence] = []

        title = facet_input.display_title
        for chunk_id in facet_input.input_chunk_ids:
            text = facet_input.chunk_texts[chunk_id]
            if title and title in text:
                aliases.append(
                    RawAlias(alias=title, supporting_chunk_ids=[chunk_id], supporting_quotes=[title], status="supported")
                )
            # A deliberately simple, deterministic relation pattern -- enough to
            # produce well-formed claims for pipeline testing, nothing more.
            for sentence in re.split(r"(?<=\.)\s+", text):
                match = re.match(
                    r"^(?:The\s+|Application\s+|Control\s+|Obligation\s+|Procedure\s+)?"
                    r"(?P<subject>[A-Z][\w&/-]*(?:\s+[A-Z][\w&/-]*)*|[A-Za-z]{1,6}-\d+[A-Za-z]?)\s+"
                    r"(?P<predicate>supports|is governed by|is satisfied by|is implemented through)\s+"
                    r"(?P<object>.+?)\.$",
                    sentence.strip(),
                )
                if not match:
                    continue
                subject = match.group("subject").strip()
                obj = match.group("object").strip()
                if title not in (subject, obj) and title not in sentence:
                    continue
                quote = sentence.strip().rstrip(".")
                if quote not in text:
                    continue
                claim_id = f"clm_{run_id}_{len(claims) + 1}"
                claims.append(
                    RawClaim(
                        claim_id=claim_id, subject=subject, predicate=match.group("predicate"), object=obj,
                        claim_text=sentence.strip(), supporting_chunk_ids=[chunk_id], supporting_quotes=[quote],
                    )
                )
                summaries.append(
                    RawSummarySentence(
                        sentence_id=f"s_{run_id}_{len(summaries) + 1}",
                        text=sentence.strip(), supported_claim_ids=[claim_id],
                    )
                )

        return FacetCompilationOutput(
            page_key=facet_input.page_key, document_revision_id=facet_input.document_revision_id,
            run_id=run_id, aliases=aliases, claims=claims, summary_sentences=summaries,
            model_identity=self.model_identity, temperature=0.0,
            prompt_version=PROMPT_VERSION, prompt_sha256=prompt_sha256(),
            input_chunk_ids=list(facet_input.input_chunk_ids),
            raw_response_json=None, input_tokens=None, output_tokens=None,
            estimated_cost_usd=None, latency_seconds=0.0,
        )
