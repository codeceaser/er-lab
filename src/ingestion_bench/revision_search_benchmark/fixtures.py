"""Stage 7R.2: loads the five POLICY-RETENTION-001 source documents
through the FROZEN Stage 5A adapter (DoclingStandardAdapter) and the
FROZEN Stage 4/4.1 chunker (chunk_document) -- read-only reuse only,
never a reimplementation, never a modification of either.

Authority facts (draft/effective/superseded/...) are NEVER attached to
CanonicalChunk here or anywhere else -- those labels come exclusively
from Stage 7R.1's registry/resolver at query time (see retriever.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ingestion_bench.adapters.docling_standard import DoclingStandardAdapter
from ingestion_bench.chunking import ChunkingConfig, DocumentRevisionContext, chunk_document, compute_document_revision_id
from ingestion_bench.chunking.model import CanonicalChunk
from ingestion_bench.revision_search_benchmark import config


@dataclass(frozen=True)
class RevisionFixture:
    symbol: str
    logical_document_id: str
    document_revision_id: str
    source_document_sha256: str
    version_label: str | None
    revision_number: int
    source_relative_path: str
    chunks: list[CanonicalChunk]


class FixtureConversionError(RuntimeError):
    """Raised when the frozen Docling adapter fails to convert a source
    fixture -- never silently skipped."""


def load_revision_fixture(
    *,
    symbol: str,
    source_relative_path: str,
    version_label: str | None,
    revision_number: int,
    adapter: DoclingStandardAdapter,
) -> RevisionFixture:
    source_path = config.FIXTURES_ROOT / source_relative_path
    result = adapter.convert(source_path, source_root=config.FIXTURES_ROOT)
    if result.conversion_status == "failed" or result.canonical_document is None:
        raise FixtureConversionError(f"conversion failed for symbol={symbol!r} ({source_relative_path}): {result.errors}")

    document = result.canonical_document
    document_revision_id = compute_document_revision_id(
        logical_document_id=config.LOGICAL_DOCUMENT_ID,
        source_document_sha256=document.source_sha256,
        version_label=version_label,
        revision_number=revision_number,
    )
    revision_context = DocumentRevisionContext(
        logical_document_id=config.LOGICAL_DOCUMENT_ID,
        document_revision_id=document_revision_id,
        source_document_sha256=document.source_sha256,
        version_label=version_label,
        revision_number=revision_number,
    )
    chunks = chunk_document(document, ChunkingConfig(), revision_context=revision_context)
    return RevisionFixture(
        symbol=symbol,
        logical_document_id=config.LOGICAL_DOCUMENT_ID,
        document_revision_id=document_revision_id,
        source_document_sha256=document.source_sha256,
        version_label=version_label,
        revision_number=revision_number,
        source_relative_path=source_relative_path,
        chunks=chunks,
    )


def load_all_revision_fixtures(fixture_inventory: list[dict]) -> dict[str, RevisionFixture]:
    """fixture_inventory: the contract's own "fixtures" list (declarative
    -- symbol/source_relative_path/version_label/revision_number). ONE
    DoclingStandardAdapter instance is built and reused across all five
    conversions (its underlying models are loaded once, never per file)."""
    adapter = DoclingStandardAdapter()
    fixtures: dict[str, RevisionFixture] = {}
    for entry in fixture_inventory:
        fixtures[entry["symbol"]] = load_revision_fixture(
            symbol=entry["symbol"],
            source_relative_path=entry["source_relative_path"],
            version_label=entry.get("version_label"),
            revision_number=entry["revision_number"],
            adapter=adapter,
        )
    return fixtures
