"""Pydantic models for the canonical chunking layer.

Depends only on ingestion_bench.canonical (CanonicalDocument's own types,
e.g. BoundingBox) -- never on Docling, OpenAI, or any DOCX/PDF/PPTX library.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ingestion_bench.canonical import BoundingBox


def _canonical_json_bytes(data: dict[str, Any]) -> bytes:
    """Same canonical-serialization principle as
    ingestion_bench.canonical.hashing: sorted keys, compact separators,
    UTF-8 -- reimplemented locally (rather than importing that module's
    private helper) so the chunking package's only dependency on canonical/
    is its public model/annotation types plus stable_element_id."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_sha256(data: dict[str, Any]) -> str:
    """SHA-256 hex digest of a dict's canonical JSON serialization. Used for
    both CanonicalChunk.content_sha256 and ChunkingConfig hashing -- never
    uuid4() or Python's built-in hash()."""
    return hashlib.sha256(_canonical_json_bytes(data)).hexdigest()


class ChunkSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    element_id: str
    unit_index: int
    order_index: int | None = None
    bbox: BoundingBox | None = None
    element_type: str


class CanonicalChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    doc_id: str
    chunk_index: int = Field(ge=0)
    chunk_type: Literal["text", "table", "picture", "mixed"]
    unit_indices: list[int]
    heading_path: list[str] = Field(default_factory=list)
    source_element_ids: list[str]
    annotation_ids: list[str] = Field(default_factory=list)
    source_refs: list[ChunkSourceRef]

    # Source-derived content: directly extracted text (paragraph/list/table
    # text, OCR, captions, ...). Never includes model-derived statements.
    source_text: str

    # Model-derived content (VisibleTextAnnotation, ImageDescriptionAnnotation,
    # VisualFactAnnotation, model_derived DiagramNode/EdgeAnnotation,
    # SemanticClaimAnnotation, UncertaintyAnnotation), rendered and labeled,
    # kept in its own field so it is never silently mixed into source_text.
    # Always populated when such annotations exist, REGARDLESS of
    # ChunkingConfig.include_model_derived_annotations -- that flag only
    # controls whether this content also appears in retrieval_text.
    model_derived_text: str | None = None

    # What a retriever should actually index/return: source_text, optionally
    # prefixed with heading context, optionally followed by a clearly
    # labeled model-derived section (per ChunkingConfig).
    retrieval_text: str

    contains_model_derived: bool

    content_sha256: str
    chunker_version: str
    chunking_config_hash: str


class ChunkingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_chars: int = Field(default=1200, gt=0)
    include_heading_context: bool = True
    include_model_derived_annotations: bool = True
    cross_unit_boundaries: bool = False
    table_as_standalone_chunk: bool = True
    picture_as_standalone_chunk: bool = True
    # "split": oversized single elements are deterministically split
    #   (sentence boundaries first, falling back to whitespace boundaries --
    #   see chunker.split_oversized_text's docstring for the exact algorithm).
    # "keep_oversized": never split; a single element larger than max_chars
    #   becomes one chunk that exceeds max_chars.
    oversized_element_policy: Literal["split", "keep_oversized"] = "split"


def compute_chunking_config_hash(config: ChunkingConfig) -> str:
    return canonical_sha256(config.model_dump(mode="json"))
