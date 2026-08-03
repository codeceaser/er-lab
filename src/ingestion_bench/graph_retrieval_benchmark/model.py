"""Stage 7B.1: the small, bounded graph representation and the
extractor's strict structured I/O.

A relationship assertion is REVISION-SCOPED: the SAME relationship
extracted from a current chunk versus a historical chunk is two distinct
`GraphEdgeAssertion`s (different document_revision_id / supporting
chunk), never merged into one timeless edge. The model deliberately
stores NONE of is_current / is_latest / is_effective / superseded /
question ids / expected paths / answer text -- currency is decided at
query time by the frozen Stage 7R resolver, exactly as for Vector.
"""

from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel, ConfigDict, Field


# --- node identity normalization -------------------------------------------

_IDENTIFIER_RE = re.compile(r"\b([A-Za-z]{1,6}-\d+[A-Za-z]?)\b")
_ARTICLES = ("the ", "a ", "an ")
# Generic enterprise entity-type nouns. A real LLM extractor
# inconsistently keeps or drops these leading type words ("Control C-88"
# in one chunk, bare "C-88" in another), which would otherwise create two
# separate nodes for the same entity and break a multi-hop chain. This is
# a domain-general entity-resolution rule (a leading type noun followed by
# more text), applied UNIFORMLY to every node and NEVER referencing any
# expected fact/chain -- it does not merge distinct identifiers (C-88 vs
# C-88a stay separate).
_TYPE_WORD_PREFIXES = ("application ", "control ", "procedure ", "obligation ")
_TRAILING = (" business service",)


def normalize_entity_name(name: str) -> str:
    """Conservative, identifier-preserving normalization used to compute a
    node_id and to connect the same entity mentioned with slightly
    different surface forms (e.g. "the Payment Settlement business
    service" vs "Payment Settlement", or "Control C-88" vs "C-88"). Never
    collapses distinct identifiers: "C-88" and "C-88a" always normalize
    differently."""
    text = " ".join(name.strip().split()).casefold()
    for article in _ARTICLES:
        if text.startswith(article):
            text = text[len(article):]
    for prefix in _TYPE_WORD_PREFIXES:
        if text.startswith(prefix) and len(text) > len(prefix):
            text = text[len(prefix):]
            break
    for trailing in _TRAILING:
        if text.endswith(trailing):
            text = text[: -len(trailing)]
    return text.strip()


def identifiers_in(name: str) -> set[str]:
    """The enterprise identifiers (APP-224510, O-31, C-88, C-88a, P-205,
    ...) present in a surface form, uppercased -- used to detect dangerous
    normalization collisions (two DIFFERENT identifiers sharing a node)."""
    return {m.group(1).upper() for m in _IDENTIFIER_RE.finditer(name)}


def compute_node_id(normalized_name: str) -> str:
    return "node_" + hashlib.sha256(normalized_name.encode("utf-8")).hexdigest()[:24]


# --- extractor strict structured output ------------------------------------


class ExtractedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    entity_type: str
    aliases: list[str] = Field(default_factory=list)


class ExtractedRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    predicate: str
    object: str
    # MUST be an exact substring of the chunk's retrieval_text -- enforced
    # by the builder, which rejects any relationship failing this check.
    supporting_text: str


class ChunkExtraction(BaseModel):
    """The extractor's whole output for one chunk."""

    model_config = ConfigDict(extra="forbid")

    entities: list[ExtractedEntity] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)


class ExtractionRun(BaseModel):
    """Provenance for one extraction pass over the corpus. For the real
    OpenAI run every field is populated; the fake extractor leaves
    model-request fields None (no network)."""

    model_config = ConfigDict(extra="forbid")

    extraction_run_id: str
    extractor_identity: str
    model: str | None = None
    prompt_version: str | None = None
    prompt_sha256: str | None = None
    temperature: float | None = None
    request_hash: str | None = None
    raw_response_hash: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_seconds: float = 0.0
    estimated_cost_usd: float | None = None
    chunk_count: int = 0
    extraction_failure_count: int = 0
    extraction_failures: list[str] = Field(default_factory=list)


# --- graph projection ------------------------------------------------------


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    entity_type: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)


class GraphEdgeAssertion(BaseModel):
    """One revision-scoped relationship assertion, backed by exactly one
    existing Stage 7B.0 chunk. NO currency/latest/effective/superseded
    flag, NO question id, NO expected path, NO answer text."""

    model_config = ConfigDict(extra="forbid")

    edge_assertion_id: str
    subject_node_id: str
    predicate: str
    object_node_id: str

    logical_document_id: str
    document_revision_id: str
    supporting_chunk_id: str
    supporting_content_sha256: str
    supporting_text: str

    # Complete source provenance copied verbatim from the supporting
    # CanonicalChunk (never re-derived).
    source_relative_path: str
    source_document_sha256: str
    version_label: str | None = None
    revision_number: int | None = None
    unit_indices: list[int] = Field(default_factory=list)
    heading_path: list[str] = Field(default_factory=list)
    source_element_ids: list[str] = Field(default_factory=list)
    source_refs: list[dict] = Field(default_factory=list)

    extraction_run_id: str


def compute_edge_assertion_id(
    subject_node_id: str, predicate: str, object_node_id: str, supporting_chunk_id: str
) -> str:
    payload = "|".join([subject_node_id, predicate.casefold().strip(), object_node_id, supporting_chunk_id])
    return "edge_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
