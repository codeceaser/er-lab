"""Stage 7C.0: the isolated Postgres implementation of the projection store.

Mirrors Stage 7B.2a's `vector_candidate_store.py` pattern: this stage's OWN
tables only (`edib_stage7c_anchor`, `edib_stage7c_anchor_posting`), and
authority filtering expressed as `document_revision_id IN (:ids)` in the SAME
statement that selects -- never "select everything, then drop ineligible rows".

Stage 7C.0 creates ONLY the two projection tables. `facet`,
`facet_embedding` and `compilation_audit` belong to Stage 7C.1 and are not
created, referenced or migrated here.

No pgvector column exists in this module: the deterministic projection stores
no embedding of any kind.
"""

from __future__ import annotations

import json

from ingestion_bench.wiki_projection import config
from ingestion_bench.wiki_projection.model import AnchorPosting, WikiAnchor


class PgWikiProjectionStore:
    def __init__(self, *, database_url: str | None = None, anchor_table: str | None = None,
                 posting_table: str | None = None) -> None:
        self._database_url = database_url or config.DATABASE_URL
        self._anchor_table = anchor_table or config.ANCHOR_TABLE_NAME
        self._posting_table = posting_table or config.ANCHOR_POSTING_TABLE_NAME
        self._engine = None

    def _ensure_ready(self):
        if self._engine is not None:
            return self._engine
        from sqlalchemy import create_engine, text

        engine = create_engine(self._database_url)
        with engine.connect() as conn:
            conn.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._anchor_table} (
                        anchor_id TEXT PRIMARY KEY,
                        anchor_kind TEXT NOT NULL,
                        normalized_value TEXT NOT NULL,
                        display_text TEXT NOT NULL,
                        extraction_method TEXT NOT NULL,
                        is_ambiguous BOOLEAN NOT NULL,
                        display_variants JSONB NOT NULL,
                        has_disjoint_identifier_context BOOLEAN NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._posting_table} (
                        posting_hash TEXT PRIMARY KEY,
                        anchor_id TEXT NOT NULL,
                        chunk_id TEXT NOT NULL,
                        document_revision_id TEXT NOT NULL,
                        logical_document_id TEXT NOT NULL,
                        field TEXT NOT NULL,
                        start_char INTEGER NOT NULL,
                        end_char INTEGER NOT NULL,
                        surface_text TEXT NOT NULL,
                        source_ref JSONB NOT NULL
                    )
                    """
                )
            )
            # Indexed on the two columns every membership and authority query
            # uses (Revision 6 SS10.3).
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {self._posting_table}_anchor_idx ON {self._posting_table} (anchor_id)"))
            conn.execute(
                text(f"CREATE INDEX IF NOT EXISTS {self._posting_table}_revision_idx ON {self._posting_table} (document_revision_id)")
            )
            conn.commit()
        self._engine = engine
        return engine

    def upsert_anchors(self, anchors: list[WikiAnchor]) -> int:
        from sqlalchemy import text

        engine = self._ensure_ready()
        with engine.connect() as conn:
            for anchor in anchors:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {self._anchor_table}
                            (anchor_id, anchor_kind, normalized_value, display_text, extraction_method,
                             is_ambiguous, display_variants, has_disjoint_identifier_context)
                        VALUES (:anchor_id, :anchor_kind, :normalized_value, :display_text, :extraction_method,
                                :is_ambiguous, CAST(:display_variants AS JSONB), :has_disjoint)
                        ON CONFLICT (anchor_id) DO UPDATE SET
                            display_text = EXCLUDED.display_text,
                            is_ambiguous = EXCLUDED.is_ambiguous,
                            display_variants = EXCLUDED.display_variants,
                            has_disjoint_identifier_context = EXCLUDED.has_disjoint_identifier_context
                        """
                    ),
                    {
                        "anchor_id": anchor.anchor_id, "anchor_kind": anchor.anchor_kind,
                        "normalized_value": anchor.normalized_value, "display_text": anchor.display_text,
                        "extraction_method": anchor.extraction_method, "is_ambiguous": anchor.is_ambiguous,
                        "display_variants": json.dumps(anchor.display_variants),
                        "has_disjoint": anchor.has_disjoint_identifier_context,
                    },
                )
            conn.commit()
        return len(anchors)

    def upsert_postings(self, postings: list[AnchorPosting]) -> int:
        from sqlalchemy import text

        engine = self._ensure_ready()
        with engine.connect() as conn:
            for posting in postings:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {self._posting_table}
                            (posting_hash, anchor_id, chunk_id, document_revision_id, logical_document_id,
                             field, start_char, end_char, surface_text, source_ref)
                        VALUES (:posting_hash, :anchor_id, :chunk_id, :document_revision_id, :logical_document_id,
                                :field, :start_char, :end_char, :surface_text, CAST(:source_ref AS JSONB))
                        ON CONFLICT (posting_hash) DO NOTHING
                        """
                    ),
                    {
                        "posting_hash": posting.posting_hash, "anchor_id": posting.anchor_id,
                        "chunk_id": posting.chunk_id, "document_revision_id": posting.document_revision_id,
                        "logical_document_id": posting.logical_document_id, "field": posting.field,
                        "start_char": posting.start_char, "end_char": posting.end_char,
                        "surface_text": posting.surface_text, "source_ref": json.dumps(posting.source_ref),
                    },
                )
            conn.commit()
        return len(postings)

    def all_anchors(self) -> list[WikiAnchor]:
        from sqlalchemy import text

        engine = self._ensure_ready()
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT * FROM {self._anchor_table} ORDER BY anchor_id")).mappings().all()
        return [
            WikiAnchor(
                anchor_id=r["anchor_id"], anchor_kind=r["anchor_kind"], normalized_value=r["normalized_value"],
                display_text=r["display_text"], extraction_method=r["extraction_method"],
                is_ambiguous=r["is_ambiguous"], display_variants=list(r["display_variants"]),
                has_disjoint_identifier_context=r["has_disjoint_identifier_context"],
            )
            for r in rows
        ]

    def postings_for_revisions(self, eligible_revision_ids: list[str]) -> list[AnchorPosting]:
        """Authority restriction is in the SAME statement as the selection --
        never applied afterwards. Empty eligible set -> []."""
        from sqlalchemy import text

        if not eligible_revision_ids:
            return []
        engine = self._ensure_ready()
        with engine.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        f"""
                        SELECT * FROM {self._posting_table}
                        WHERE document_revision_id = ANY(:eligible)
                        ORDER BY document_revision_id, chunk_id, start_char, end_char, anchor_id
                        """
                    ),
                    {"eligible": list(eligible_revision_ids)},
                )
                .mappings()
                .all()
            )
        return [
            AnchorPosting(
                posting_hash=r["posting_hash"], anchor_id=r["anchor_id"], chunk_id=r["chunk_id"],
                document_revision_id=r["document_revision_id"], logical_document_id=r["logical_document_id"],
                field=r["field"], start_char=r["start_char"], end_char=r["end_char"],
                surface_text=r["surface_text"], source_ref=dict(r["source_ref"]),
            )
            for r in rows
        ]

    def anchor_count(self) -> int:
        from sqlalchemy import text

        engine = self._ensure_ready()
        with engine.connect() as conn:
            return int(conn.execute(text(f"SELECT COUNT(*) FROM {self._anchor_table}")).scalar() or 0)

    def posting_count(self) -> int:
        from sqlalchemy import text

        engine = self._ensure_ready()
        with engine.connect() as conn:
            return int(conn.execute(text(f"SELECT COUNT(*) FROM {self._posting_table}")).scalar() or 0)
