"""Pydantic models for the canonical chunking layer.

Depends only on ingestion_bench.canonical (CanonicalDocument's own types,
e.g. BoundingBox, and its validate_sha256_hex helper) -- never on Docling,
OpenAI, or any DOCX/PDF/PPTX library.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ingestion_bench.canonical import BoundingBox
from ingestion_bench.canonical.model import validate_sha256_hex


def _canonical_json_bytes(data: dict[str, Any]) -> bytes:
    """Same canonical-serialization principle as
    ingestion_bench.canonical.hashing: sorted keys, compact separators,
    UTF-8 -- reimplemented locally (rather than importing that module's
    private helper) so the chunking package's only dependency on canonical/
    is its public model/annotation types plus stable_element_id."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_sha256(data: dict[str, Any]) -> str:
    """SHA-256 hex digest of a dict's canonical JSON serialization. Used for
    CanonicalChunk.content_sha256, ChunkingConfig hashing, and
    document_revision_id -- never uuid4() or Python's built-in hash()."""
    return hashlib.sha256(_canonical_json_bytes(data)).hexdigest()


def text_sha256(text: str) -> str:
    """SHA-256 hex digest of raw text, used for
    CanonicalChunk.embedding_input_sha256. Deliberately NOT routed through
    canonical_sha256's dict-oriented JSON wrapping -- the input here is
    already a single normalized string, not a structured payload."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


ChunkSourceElementType = Literal["heading", "paragraph", "list_item", "table", "picture", "caption"]


def _validate_char_span(start_char: int | None, end_char: int | None, where: str) -> None:
    if (start_char is None) != (end_char is None):
        raise ValueError(f"{where}: start_char and end_char must either both be None or both be populated")
    if start_char is not None and end_char is not None:
        if not (0 <= start_char <= end_char):
            raise ValueError(f"{where}: start_char ({start_char}) must satisfy 0 <= start_char <= end_char ({end_char})")


class TextFragment(BaseModel):
    """One deterministic, lossless fragment of a split oversized element
    (Stage 4.2 chunking rule): text is always the exact verbatim slice
    original_text[start_char:end_char] -- never a whitespace-normalized
    reconstruction -- so concatenating every fragment's text in
    fragment_index order always reproduces the original text exactly."""

    model_config = ConfigDict(extra="forbid")

    text: str
    fragment_index: int = Field(ge=0)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_span(self) -> TextFragment:
        if self.start_char > self.end_char:
            raise ValueError(f"start_char ({self.start_char}) must be <= end_char ({self.end_char})")
        return self


class ChunkSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    element_id: str
    unit_index: int = Field(ge=0)
    order_index: int | None = Field(default=None, ge=0)
    bbox: BoundingBox | None = None
    element_type: ChunkSourceElementType

    # Populated only when this ref points at one fragment of a split
    # oversized element (Stage 4.2) -- otherwise all three stay None. This
    # is what lets two fragments with byte-identical text (e.g. a paragraph
    # that repeats the same sentence) remain distinguishable, auditable,
    # and non-colliding in content_sha256/duplicate-occurrence detection.
    fragment_index: int | None = Field(default=None, ge=0)
    start_char: int | None = None
    end_char: int | None = None

    @model_validator(mode="after")
    def _validate_char_span(self) -> ChunkSourceRef:
        _validate_char_span(self.start_char, self.end_char, "ChunkSourceRef")
        return self


class ChunkAssetRef(BaseModel):
    """A picture's stored-artifact identity, retained on its chunk even when
    the picture carries no caption, OCR, or model-derived annotation text
    (chunking rule 4, Stage 4.1) -- so an asset-only picture is never
    silently dropped from the chunked corpus."""

    model_config = ConfigDict(extra="forbid")

    picture_id: str
    artifact_ref: str
    content_sha256: str
    unit_index: int = Field(ge=0)
    bbox: BoundingBox | None = None

    @field_validator("content_sha256")
    @classmethod
    def _content_sha256_is_valid(cls, v: str) -> str:
        return validate_sha256_hex(v, "content_sha256")


def _normalize_version_label(version_label: str | None) -> str | None:
    """Canonical normalization (strip, lower-case) shared between
    compute_document_revision_id's hash input and
    DocumentRevisionContext.version_label's OWN stored value (Stage 4.2) --
    so "Draft" and "draft" don't just hash identically, they are STORED
    identically, and every serialized field derived from them (chunk
    lineage metadata included) is byte-identical too."""
    if version_label is None:
        return None
    return version_label.strip().lower()


def compute_document_revision_id(
    logical_document_id: str,
    source_document_sha256: str,
    version_label: str | None = None,
    revision_number: int | None = None,
) -> str:
    """Deterministic document_revision_id: SHA-256 over stable identity
    components only -- never a random UUID. logical_document_id is never a
    filename (the caller derives it from a stable, non-filename document
    identity); version_label is normalized before hashing so equivalent
    labels never disagree on revision identity."""
    payload = {
        "logical_document_id": logical_document_id,
        "source_document_sha256": source_document_sha256,
        "version_label": _normalize_version_label(version_label),
        "revision_number": revision_number,
    }
    return canonical_sha256(payload)


class DocumentRevisionContext(BaseModel):
    """Identity of one revision of one logical document, supplied explicitly
    by the caller of chunk_document(). A future document-revision registry
    (not implemented in this stage) is expected to be the authoritative
    source of these values for Stage 5 adapters.

    Deliberately excludes mutable retrieval/index state -- is_latest,
    is_current, publication_status, superseded_by_revision_id, ingestion
    timestamps. None of that participates in a stable chunk's identity or
    content hash (see CanonicalChunk); it belongs to that future registry /
    a ChunkIndexRecord, managed later.

    Intended default retrieval policy (to be enforced by that future
    registry, not by this chunking layer, which only carries the lineage
    fields needed to support it later):
      - retrieve the currently effective authoritative revision;
      - do not merely boost the most recently uploaded revision;
      - drafts and future-effective revisions must not supersede the
        current active revision;
      - historical revisions are included only for explicit historical or
        comparison queries.
    """

    model_config = ConfigDict(extra="forbid")

    logical_document_id: str
    document_revision_id: str
    source_document_sha256: str
    version_label: str | None = None
    revision_number: int | None = Field(default=None, ge=0)

    @field_validator("source_document_sha256")
    @classmethod
    def _source_document_sha256_is_valid(cls, v: str) -> str:
        return validate_sha256_hex(v, "source_document_sha256")

    @field_validator("document_revision_id")
    @classmethod
    def _document_revision_id_is_valid_sha256(cls, v: str) -> str:
        return validate_sha256_hex(v, "document_revision_id")

    @field_validator("logical_document_id")
    @classmethod
    def _logical_document_id_is_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("logical_document_id must not be empty (or all-whitespace)")
        return v

    @field_validator("version_label")
    @classmethod
    def _version_label_is_normalized_and_nonempty(cls, v: str | None) -> str | None:
        """Stores the CANONICALLY NORMALIZED value, not the caller's raw
        string -- see _normalize_version_label. A caller who supplies a
        version_label must supply real content; pass None (not "") to mean
        'no version label'."""
        if v is None:
            return None
        normalized = _normalize_version_label(v)
        if not normalized:
            raise ValueError(
                "version_label, when supplied, must be nonempty after stripping whitespace -- "
                "use None to mean 'no version label'"
            )
        return normalized

    @model_validator(mode="after")
    def _validate_document_revision_id_is_deterministic(self) -> DocumentRevisionContext:
        """document_revision_id is never freely chosen -- it must always
        equal compute_document_revision_id() over this context's own stable
        fields, so two contexts with identical identity components always
        agree and one with a mismatched id is rejected at construction."""
        expected = compute_document_revision_id(
            logical_document_id=self.logical_document_id,
            source_document_sha256=self.source_document_sha256,
            version_label=self.version_label,
            revision_number=self.revision_number,
        )
        if self.document_revision_id != expected:
            raise ValueError(
                "document_revision_id must equal compute_document_revision_id(logical_document_id, "
                f"source_document_sha256, version_label, revision_number); got {self.document_revision_id!r}, "
                f"expected {expected!r}"
            )
        return self


class CanonicalChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    doc_id: str

    # Document-revision lineage (Stage 4.1) -- copied verbatim from the
    # DocumentRevisionContext supplied to chunk_document(). Stable identity
    # only; see DocumentRevisionContext's docstring for what is deliberately
    # excluded and why.
    logical_document_id: str
    document_revision_id: str
    source_document_sha256: str
    version_label: str | None = None
    revision_number: int | None = None

    chunk_index: int = Field(ge=0)
    chunk_type: Literal["text", "table", "picture", "mixed"]
    unit_indices: list[int]
    heading_path: list[str] = Field(default_factory=list)

    # Active heading context at the point this chunk was emitted, outermost
    # to innermost (Stage 4.1 chunking rule: heading context must be
    # auditable, not just a flattened heading_path string).
    heading_source_element_ids: list[str] = Field(default_factory=list)
    heading_source_refs: list[ChunkSourceRef] = Field(default_factory=list)

    source_element_ids: list[str]
    annotation_ids: list[str] = Field(default_factory=list)
    source_refs: list[ChunkSourceRef]

    # Retained picture-artifact identities for this chunk, populated even
    # when the picture has no textual annotation (Stage 4.1 chunking rule).
    asset_refs: list[ChunkAssetRef] = Field(default_factory=list)

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

    # Integrity hash of the full auditable chunk content, including
    # provenance (source_refs, heading_source_refs, asset_refs) -- changing
    # bbox/source order/asset identity changes this even when rendered text
    # is unchanged.
    content_sha256: str

    # SHA-256 of retrieval_text -- the exact normalized text passed to the
    # embedding model. None when retrieval_text is empty (e.g. an asset-only
    # picture chunk with no caption/OCR/model-derived text): there is no
    # meaningful embedding input, and every such chunk must NOT collapse
    # onto the SHA-256 of "" as if they were interchangeable duplicates.
    # Used for embedding reuse/deduplication when present; deliberately
    # independent of document_revision_id and of provenance, so identical
    # retrieval_text across chunks/revisions can share one embedding even
    # when content_sha256 differs.
    embedding_input_sha256: str | None = None

    chunker_version: str
    chunking_config_hash: str

    @field_validator("chunk_id")
    @classmethod
    def _chunk_id_is_valid_sha256(cls, v: str) -> str:
        return validate_sha256_hex(v, "chunk_id")

    @field_validator("document_revision_id")
    @classmethod
    def _document_revision_id_is_valid_sha256(cls, v: str) -> str:
        return validate_sha256_hex(v, "document_revision_id")

    @field_validator("content_sha256")
    @classmethod
    def _content_sha256_is_valid(cls, v: str) -> str:
        return validate_sha256_hex(v, "content_sha256")

    @field_validator("chunking_config_hash")
    @classmethod
    def _chunking_config_hash_is_valid(cls, v: str) -> str:
        return validate_sha256_hex(v, "chunking_config_hash")

    @field_validator("source_document_sha256")
    @classmethod
    def _source_document_sha256_is_valid(cls, v: str) -> str:
        return validate_sha256_hex(v, "source_document_sha256")

    @field_validator("embedding_input_sha256")
    @classmethod
    def _embedding_input_sha256_is_valid(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return validate_sha256_hex(v, "embedding_input_sha256")

    @model_validator(mode="after")
    def _validate_unit_indices(self) -> CanonicalChunk:
        if not self.unit_indices:
            raise ValueError("unit_indices must not be empty")
        for value in self.unit_indices:
            if value < 0:
                raise ValueError(f"unit_indices must be nonnegative: {value!r}")
        if list(self.unit_indices) != sorted(self.unit_indices):
            raise ValueError(f"unit_indices must be sorted ascending: {self.unit_indices!r}")
        if len(set(self.unit_indices)) != len(self.unit_indices):
            raise ValueError(f"unit_indices must not contain duplicates: {self.unit_indices!r}")
        return self

    @model_validator(mode="after")
    def _validate_unique_id_lists(self) -> CanonicalChunk:
        def check_unique(values: list[str], name: str) -> None:
            seen: set[str] = set()
            for value in values:
                if value in seen:
                    raise ValueError(f"duplicate {name}: {value!r}")
                seen.add(value)

        check_unique(self.source_element_ids, "source_element_ids entry")
        check_unique(self.annotation_ids, "annotation_ids entry")
        return self

    @model_validator(mode="after")
    def _validate_contains_model_derived_consistency(self) -> CanonicalChunk:
        expected = self.model_derived_text is not None
        if self.contains_model_derived != expected:
            raise ValueError(
                f"contains_model_derived={self.contains_model_derived!r} is inconsistent with "
                f"model_derived_text is not None ({expected!r})"
            )
        return self


class ChunkingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Limits SOURCE-TEXT packing while elements (paragraphs/list items/
    # non-standalone tables & pictures) are accumulated into a buffer --
    # NOT the final retrieval_text, which may exceed max_chars once the
    # heading-path prefix and/or the labeled model-derived section are
    # appended on top of a source_text that was itself packed up to this
    # limit. This has been the packing target since Stage 4; documented
    # explicitly here per the Stage 4.1 hardening review.
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
