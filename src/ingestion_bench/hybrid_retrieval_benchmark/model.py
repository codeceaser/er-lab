"""Stage 7B.2: the bounded hybrid data records.

Deliberately small: seed origins, edge-embedding records, bounded simple
paths, and fused chunks. No production/orchestration types, no plugin
registry.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ingestion_bench.revision_authority.resolver import RevisionAuthorityLabel


class SeedOrigin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_source: str  # "explicit_alias" | "vector_chunk" | "semantic_edge"
    matched_ref: str  # the alias, vector chunk_id, or edge_assertion_id that produced this seed
    source_rank: int
    semantic_score: float | None = None
    supporting_revision_ids: list[str] = Field(default_factory=list)


class HybridSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    canonical_name: str
    entity_type: str
    origins: list[SeedOrigin]  # deduped by node_id, ALL origins preserved


class EdgeEmbeddingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_assertion_id: str
    subject_node_id: str
    subject_canonical_name: str
    object_node_id: str
    object_canonical_name: str
    predicate: str

    logical_document_id: str
    document_revision_id: str
    supporting_chunk_id: str
    supporting_content_sha256: str
    supporting_text: str
    source_relative_path: str
    source_document_sha256: str
    unit_indices: list[int] = Field(default_factory=list)
    heading_path: list[str] = Field(default_factory=list)
    source_element_ids: list[str] = Field(default_factory=list)
    source_refs: list[dict] = Field(default_factory=list)

    representation: str  # "subject predicate object. supporting_text"
    embedding: list[float]


class PathCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path_id: str
    node_ids: list[str]  # no repeated node
    edge_assertion_ids: list[str]
    representation: str  # "subject predicate object\n..." derived ONLY from existing edges
    hop_length: int
    semantic_score: float
    supporting_chunk_ids: list[str]


class FusedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    final_rank: int
    rrf_score: float

    vector_rank: int | None = None
    vector_score: float | None = None
    graph_rank: int | None = None
    graph_score: float | None = None
    vector_rrf_contribution: float = 0.0
    graph_rrf_contribution: float = 0.0

    contributed_by: str  # "vector_only" | "graph_only" | "both"
    seed_sources: list[str] = Field(default_factory=list)
    supporting_path_ids: list[str] = Field(default_factory=list)
    supporting_edge_assertion_ids: list[str] = Field(default_factory=list)

    # complete source provenance (from the frozen chunk record)
    logical_document_id: str
    document_revision_id: str
    version_label: str | None = None
    revision_number: int | None = None
    source_relative_path: str
    source_document_sha256: str
    content_sha256: str
    retrieval_text: str
    chunk_type: str
    unit_indices: list[int] = Field(default_factory=list)
    heading_path: list[str] = Field(default_factory=list)
    source_element_ids: list[str] = Field(default_factory=list)
    source_refs: list[dict] = Field(default_factory=list)
    authority_label: RevisionAuthorityLabel | None = None


class RankedChunk(BaseModel):
    """A minimal (chunk_id, rank, score) entry -- the common input to
    fusion, produced by both the Vector side and each Graph side."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    rank: int
    score: float
