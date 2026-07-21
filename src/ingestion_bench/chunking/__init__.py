"""Parser-agnostic canonical chunking layer.

    Source document
        -> parser adapter             [Stage 5]
        -> CanonicalDocument
        -> canonical chunker          [Stage 4, this package]
        -> CanonicalChunk[]
        -> embedding / KB builders    [later]

Depends only on ingestion_bench.canonical -- never on Docling, OpenAI, or
any DOCX/PDF/PPTX library -- and never inspects reference_manifest.json.
"""

from .chunker import CHUNKER_VERSION, chunk_document, split_oversized_text
from .model import (
    CanonicalChunk,
    ChunkAssetRef,
    ChunkingConfig,
    ChunkSourceRef,
    DocumentRevisionContext,
    canonical_sha256,
    compute_chunking_config_hash,
    compute_document_revision_id,
    text_sha256,
)

__all__ = [
    "CHUNKER_VERSION",
    "chunk_document",
    "split_oversized_text",
    "CanonicalChunk",
    "ChunkAssetRef",
    "ChunkingConfig",
    "ChunkSourceRef",
    "DocumentRevisionContext",
    "canonical_sha256",
    "compute_chunking_config_hash",
    "compute_document_revision_id",
    "text_sha256",
]
