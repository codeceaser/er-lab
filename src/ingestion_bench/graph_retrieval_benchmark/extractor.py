"""Stage 7B.1: the narrow relationship extractor.

ONE narrow interface + exactly two implementations (a deterministic Fake
for tests, an OpenAI one for the measured run) -- never a generic plugin
framework. The extractor's input is STRICTLY the chunk's own
retrieval_text + identity + provenance (see `ChunkExtractionInput`); it
never receives the Stage 7B.0 fact contract, required/forbidden facts,
expected chain, or any benchmark question or answer.

Output is strict structured (`ChunkExtraction`): entities (name,
entity_type, aliases) and relationships (subject, predicate, object,
supporting_text). The extractor extracts ONLY explicitly stated
relationships -- never an inferred one -- preserves enterprise
identifiers exactly, and every relationship's supporting_text must be an
exact substring of retrieval_text (the builder rejects any that is not).
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from ingestion_bench.graph_retrieval_benchmark import config
from ingestion_bench.graph_retrieval_benchmark.model import (
    ChunkExtraction,
    ExtractedEntity,
    ExtractedRelationship,
    ExtractionRun,
)


@dataclass(frozen=True)
class ChunkExtractionInput:
    """The ONLY information an extractor may see about a chunk -- no fact
    contract, no questions, no answers."""

    chunk_id: str
    content_sha256: str
    retrieval_text: str
    logical_document_id: str
    document_revision_id: str
    source_relative_path: str
    source_document_sha256: str
    version_label: str | None
    revision_number: int | None
    unit_indices: list[int] = field(default_factory=list)
    heading_path: list[str] = field(default_factory=list)
    source_element_ids: list[str] = field(default_factory=list)
    source_refs: list[dict] = field(default_factory=list)


class RelationshipExtractor(Protocol):
    extractor_identity: str

    def extract(self, chunks: list[ChunkExtractionInput]) -> tuple[list[tuple[str, ChunkExtraction]], ExtractionRun]:
        """Returns (per-chunk extractions, one aggregated ExtractionRun)."""
        ...


# --- deterministic rule-based fake extractor (no network) ------------------

# Each pattern parses ONE explicitly-stated enterprise relationship shape.
# Groups: (subject_surface, subject_type, object_surface, object_type,
# predicate). The matched span (m.group(0)) is the supporting_text and is
# by construction an exact substring of retrieval_text.
_PATTERNS: list[tuple[re.Pattern, str, str, str]] = [
    (re.compile(r"Application (APP-\d+) supports the (.+?) business service\."), "application", "business_service", "supports"),
    (re.compile(r"The (.+?) business service is governed by (Obligation O-\d+)\."), "business_service", "obligation", "is_governed_by"),
    (re.compile(r"(Obligation O-\d+) is satisfied by (Control C-\d+[a-z]?)\."), "obligation", "control", "is_satisfied_by"),
    (re.compile(r"(Control C-\d+[a-z]?) is implemented through (Procedure P-\d+)\."), "control", "procedure", "is_implemented_through"),
    (re.compile(r"(Procedure P-\d+) is (a retired operating procedure|the current operating procedure(?: for reconciliation)?)\."), "procedure", "status", "has_status"),
]


def _fake_extract_one(text: str) -> ChunkExtraction:
    entities: dict[str, ExtractedEntity] = {}
    relationships: list[ExtractedRelationship] = []

    def add_entity(name: str, entity_type: str, aliases: list[str]) -> None:
        if name not in entities:
            entities[name] = ExtractedEntity(name=name, entity_type=entity_type, aliases=sorted(set(aliases) - {name}))

    for pattern, subj_type, obj_type, predicate in _PATTERNS:
        for m in pattern.finditer(text):
            subject_surface, object_surface = m.group(1), m.group(2)
            if subj_type == "business_service":
                add_entity(subject_surface, "business_service", [f"the {subject_surface} business service", f"{subject_surface} business service"])
            else:
                add_entity(subject_surface, subj_type, [])
            if obj_type == "business_service":
                add_entity(object_surface, "business_service", [f"the {object_surface} business service", f"{object_surface} business service"])
            else:
                add_entity(object_surface, obj_type, [])
            relationships.append(ExtractedRelationship(subject=subject_surface, predicate=predicate, object=object_surface, supporting_text=m.group(0)))

    return ChunkExtraction(entities=list(entities.values()), relationships=relationships)


class FakeRelationshipExtractor:
    """Deterministic, no-network extractor: a plain rule-based parser of
    the chunk's own retrieval_text. Reads ONLY chunk text (never the fact
    contract or questions), exactly like FakeEmbeddingProvider /
    FakeAnswerGenerator elsewhere in this repository."""

    extractor_identity = "fake-relationship-extractor-v1"

    def extract(self, chunks: list[ChunkExtractionInput]) -> tuple[list[tuple[str, ChunkExtraction]], ExtractionRun]:
        start = time.perf_counter()
        out: list[tuple[str, ChunkExtraction]] = [(c.chunk_id, _fake_extract_one(c.retrieval_text)) for c in chunks]
        run = ExtractionRun(
            extraction_run_id="extrun_fake_" + hashlib.sha256("".join(c.chunk_id for c in chunks).encode()).hexdigest()[:16],
            extractor_identity=self.extractor_identity,
            latency_seconds=time.perf_counter() - start,
            chunk_count=len(chunks),
        )
        return out, run


# --- OpenAI extractor (measured run) ---------------------------------------

EXTRACTION_PROMPT_VERSION = "stage7b1-extract-v1"

SYSTEM_PROMPT = (
    "You are a precise enterprise-document relationship extractor. Given the text of ONE document chunk, "
    "extract the named entities and the relationships EXPLICITLY stated in that text. "
    "Rules you must obey exactly:\n"
    "1. Extract ONLY relationships explicitly stated in the text. Never infer, assume, or complete a relationship.\n"
    "2. Preserve every enterprise identifier exactly as written (for example APP-224510, O-31, C-88, C-88a, P-205).\n"
    "3. For every relationship, `supporting_text` MUST be an exact, verbatim, contiguous substring of the provided "
    "chunk text -- copy it character for character. If you cannot copy an exact substring, do not emit the relationship.\n"
    "4. entity_type should be one of: application, business_service, obligation, control, procedure, status, or other.\n"
    "5. Do not invent entities or relationships that are not present in the text."
)

EXTRACTION_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "entity_type": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "entity_type", "aliases"],
            },
        },
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "subject": {"type": "string"},
                    "predicate": {"type": "string"},
                    "object": {"type": "string"},
                    "supporting_text": {"type": "string"},
                },
                "required": ["subject", "predicate", "object", "supporting_text"],
            },
        },
    },
    "required": ["entities", "relationships"],
}


def _prompt_sha256() -> str:
    return hashlib.sha256((SYSTEM_PROMPT + "\x00" + str(EXTRACTION_JSON_SCHEMA)).encode("utf-8")).hexdigest()


def _build_user_prompt(retrieval_text: str) -> str:
    return f"Chunk text:\n\"\"\"\n{retrieval_text}\n\"\"\"\n\nExtract entities and explicitly-stated relationships as JSON."


class OpenAIRelationshipExtractor:
    """The one REAL, configured extraction model. The OpenAI client is
    loaded LAZILY (only on first extract() call), so merely constructing
    this class never requires network access or an API key. Uses OpenAI's
    structured JSON-schema output so the response always parses as exactly
    {entities, relationships}. Records full request/response provenance,
    tokens, latency, and estimated cost; a per-chunk failure is recorded
    (never silently dropped) and that chunk simply contributes no edges."""

    def __init__(self, model_identity: str | None = None) -> None:
        self.model_identity = model_identity or config.EXTRACTION_MODEL
        self.extractor_identity = f"openai:{self.model_identity}"
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()
        return self._client

    def _extract_one(self, chunk: ChunkExtractionInput) -> tuple[ChunkExtraction, int | None, int | None, str, str]:
        client = self._ensure_client()
        user_prompt = _build_user_prompt(chunk.retrieval_text)
        request_hash = hashlib.sha256((self.model_identity + "\x00" + SYSTEM_PROMPT + "\x00" + user_prompt).encode("utf-8")).hexdigest()
        response = client.chat.completions.create(
            model=self.model_identity,
            temperature=config.EXTRACTION_TEMPERATURE,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
            response_format={"type": "json_schema", "json_schema": {"name": "extraction", "schema": EXTRACTION_JSON_SCHEMA, "strict": True}},
        )
        raw = response.choices[0].message.content
        raw_response_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage is not None else None
        output_tokens = usage.completion_tokens if usage is not None else None
        extraction = ChunkExtraction.model_validate_json(raw)
        return extraction, input_tokens, output_tokens, request_hash, raw_response_hash

    def extract(self, chunks: list[ChunkExtractionInput]) -> tuple[list[tuple[str, ChunkExtraction]], ExtractionRun]:
        start = time.perf_counter()
        out: list[tuple[str, ChunkExtraction]] = []
        total_in = 0
        total_out = 0
        request_hashes: list[str] = []
        response_hashes: list[str] = []
        failures: list[str] = []
        for chunk in chunks:
            try:
                extraction, in_tok, out_tok, req_hash, resp_hash = self._extract_one(chunk)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{chunk.chunk_id}: {type(exc).__name__}: {exc}")
                out.append((chunk.chunk_id, ChunkExtraction()))
                continue
            out.append((chunk.chunk_id, extraction))
            total_in += in_tok or 0
            total_out += out_tok or 0
            request_hashes.append(req_hash)
            response_hashes.append(resp_hash)
        latency = time.perf_counter() - start
        run = ExtractionRun(
            extraction_run_id="extrun_openai_" + uuid.uuid4().hex[:16],
            extractor_identity=self.extractor_identity,
            model=self.model_identity,
            prompt_version=EXTRACTION_PROMPT_VERSION,
            prompt_sha256=_prompt_sha256(),
            temperature=config.EXTRACTION_TEMPERATURE,
            request_hash=hashlib.sha256("".join(request_hashes).encode("utf-8")).hexdigest() if request_hashes else None,
            raw_response_hash=hashlib.sha256("".join(response_hashes).encode("utf-8")).hexdigest() if response_hashes else None,
            input_tokens=total_in,
            output_tokens=total_out,
            latency_seconds=latency,
            estimated_cost_usd=config.estimate_cost_usd(self.model_identity, total_in, total_out),
            chunk_count=len(chunks),
            extraction_failure_count=len(failures),
            extraction_failures=failures,
        )
        return out, run
