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
from .model import CanonicalChunk, ChunkingConfig, ChunkSourceRef, canonical_sha256, compute_chunking_config_hash

__all__ = [
    "CHUNKER_VERSION",
    "chunk_document",
    "split_oversized_text",
    "CanonicalChunk",
    "ChunkingConfig",
    "ChunkSourceRef",
    "canonical_sha256",
    "compute_chunking_config_hash",
]
