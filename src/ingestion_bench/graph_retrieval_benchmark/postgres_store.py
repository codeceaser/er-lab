"""Stage 7B.1: the ONE real, persisted graph store -- Postgres, using its
OWN isolated tables (edib_stage7b1_graph_node / _graph_edge_assertion /
_graph_extraction_run). NO Neo4j; Postgres is sufficient for a corpus
this size. Never any other stage's tables.

`edge_assertions_for_revisions` applies the authority-eligibility filter
in SQL (`document_revision_id IN (...)`), so the traversal that consumes
its output only ever sees the eligible subgraph.
"""

from __future__ import annotations

import json

from sqlalchemy import Engine, bindparam, create_engine, text

from ingestion_bench.graph_retrieval_benchmark.config import (
    DATABASE_URL,
    GRAPH_EDGE_TABLE,
    GRAPH_EXTRACTION_RUN_TABLE,
    GRAPH_NODE_TABLE,
)
from ingestion_bench.graph_retrieval_benchmark.model import ExtractionRun, GraphEdgeAssertion, GraphNode


class GraphStoreUnavailable(RuntimeError):
    """Raised when DATABASE_URL is not configured or the database is not
    reachable. Callers catch this to skip gracefully."""


class PgGraphStore:
    def __init__(self, database_url: str | None = None, node_table: str | None = None, edge_table: str | None = None, run_table: str | None = None) -> None:
        self._database_url = database_url or DATABASE_URL
        if not self._database_url:
            raise GraphStoreUnavailable("DATABASE_URL is not set -- copy .env.example to .env and set it, or pass database_url= explicitly")
        self._node_table = node_table or GRAPH_NODE_TABLE
        self._edge_table = edge_table or GRAPH_EDGE_TABLE
        self._run_table = run_table or GRAPH_EXTRACTION_RUN_TABLE
        self._engine: Engine | None = None
        self._schema_ready = False

    def _ensure_ready(self) -> Engine:
        if self._engine is None:
            try:
                engine = create_engine(self._database_url, future=True)
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            except Exception as exc:  # noqa: BLE001
                raise GraphStoreUnavailable(f"could not connect to the configured database: {type(exc).__name__}: {exc}") from exc
            self._engine = engine
        if not self._schema_ready:
            self._create_schema_if_needed()
            self._schema_ready = True
        return self._engine

    def _create_schema_if_needed(self) -> None:
        assert self._engine is not None
        with self._engine.connect() as conn:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {self._node_table} (
                    node_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    canonical_name TEXT NOT NULL,
                    aliases TEXT NOT NULL
                )
            """))
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {self._edge_table} (
                    edge_assertion_id TEXT PRIMARY KEY,
                    subject_node_id TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_node_id TEXT NOT NULL,
                    logical_document_id TEXT NOT NULL,
                    document_revision_id TEXT NOT NULL,
                    supporting_chunk_id TEXT NOT NULL,
                    supporting_content_sha256 TEXT NOT NULL,
                    supporting_text TEXT NOT NULL,
                    source_relative_path TEXT NOT NULL,
                    source_document_sha256 TEXT NOT NULL,
                    version_label TEXT,
                    revision_number INTEGER,
                    unit_indices TEXT NOT NULL,
                    heading_path TEXT NOT NULL,
                    source_element_ids TEXT NOT NULL,
                    source_refs TEXT NOT NULL,
                    extraction_run_id TEXT NOT NULL
                )
            """))
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {self._edge_table}_document_revision_idx ON {self._edge_table} (document_revision_id)"))
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {self._run_table} (
                    extraction_run_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
            """))
            conn.commit()

    def save(self, nodes: list[GraphNode], edges: list[GraphEdgeAssertion], extraction_run: ExtractionRun) -> None:
        engine = self._ensure_ready()
        with engine.connect() as conn:
            for n in nodes:
                conn.execute(
                    text(f"INSERT INTO {self._node_table} (node_id, entity_type, canonical_name, aliases) "
                         "VALUES (:id, :t, :n, :a) ON CONFLICT (node_id) DO UPDATE SET "
                         "entity_type=EXCLUDED.entity_type, canonical_name=EXCLUDED.canonical_name, aliases=EXCLUDED.aliases"),
                    {"id": n.node_id, "t": n.entity_type, "n": n.canonical_name, "a": json.dumps(n.aliases)},
                )
            for e in edges:
                conn.execute(
                    text(f"""
                        INSERT INTO {self._edge_table} (
                            edge_assertion_id, subject_node_id, predicate, object_node_id, logical_document_id,
                            document_revision_id, supporting_chunk_id, supporting_content_sha256, supporting_text,
                            source_relative_path, source_document_sha256, version_label, revision_number,
                            unit_indices, heading_path, source_element_ids, source_refs, extraction_run_id
                        ) VALUES (
                            :eid, :subj, :pred, :obj, :ldid, :drid, :cid, :csha, :stext,
                            :srp, :ssha, :vl, :rn, :ui, :hp, :sei, :sr, :erid
                        ) ON CONFLICT (edge_assertion_id) DO NOTHING
                    """),
                    {
                        "eid": e.edge_assertion_id, "subj": e.subject_node_id, "pred": e.predicate, "obj": e.object_node_id,
                        "ldid": e.logical_document_id, "drid": e.document_revision_id, "cid": e.supporting_chunk_id,
                        "csha": e.supporting_content_sha256, "stext": e.supporting_text, "srp": e.source_relative_path,
                        "ssha": e.source_document_sha256, "vl": e.version_label, "rn": e.revision_number,
                        "ui": json.dumps(e.unit_indices), "hp": json.dumps(e.heading_path),
                        "sei": json.dumps(e.source_element_ids), "sr": json.dumps(e.source_refs), "erid": e.extraction_run_id,
                    },
                )
            conn.execute(
                text(f"INSERT INTO {self._run_table} (extraction_run_id, payload) VALUES (:id, :p) "
                     "ON CONFLICT (extraction_run_id) DO UPDATE SET payload=EXCLUDED.payload"),
                {"id": extraction_run.extraction_run_id, "p": extraction_run.model_dump_json()},
            )
            conn.commit()

    def _node_from_row(self, row) -> GraphNode:
        return GraphNode(node_id=row["node_id"], entity_type=row["entity_type"], canonical_name=row["canonical_name"], aliases=json.loads(row["aliases"]))

    def _edge_from_row(self, row) -> GraphEdgeAssertion:
        return GraphEdgeAssertion(
            edge_assertion_id=row["edge_assertion_id"], subject_node_id=row["subject_node_id"], predicate=row["predicate"],
            object_node_id=row["object_node_id"], logical_document_id=row["logical_document_id"],
            document_revision_id=row["document_revision_id"], supporting_chunk_id=row["supporting_chunk_id"],
            supporting_content_sha256=row["supporting_content_sha256"], supporting_text=row["supporting_text"],
            source_relative_path=row["source_relative_path"], source_document_sha256=row["source_document_sha256"],
            version_label=row["version_label"], revision_number=row["revision_number"],
            unit_indices=json.loads(row["unit_indices"]), heading_path=json.loads(row["heading_path"]),
            source_element_ids=json.loads(row["source_element_ids"]), source_refs=json.loads(row["source_refs"]),
            extraction_run_id=row["extraction_run_id"],
        )

    def all_nodes(self) -> list[GraphNode]:
        engine = self._ensure_ready()
        with engine.connect() as conn:
            return [self._node_from_row(r) for r in conn.execute(text(f"SELECT * FROM {self._node_table}")).mappings()]

    def all_edge_assertions(self) -> list[GraphEdgeAssertion]:
        engine = self._ensure_ready()
        with engine.connect() as conn:
            return [self._edge_from_row(r) for r in conn.execute(text(f"SELECT * FROM {self._edge_table}")).mappings()]

    def edge_assertions_for_revisions(self, eligible_revision_ids: list[str]) -> list[GraphEdgeAssertion]:
        if not eligible_revision_ids:
            return []
        engine = self._ensure_ready()
        stmt = text(f"SELECT * FROM {self._edge_table} WHERE document_revision_id IN :ids").bindparams(bindparam("ids", expanding=True))
        with engine.connect() as conn:
            return [self._edge_from_row(r) for r in conn.execute(stmt, {"ids": list(eligible_revision_ids)}).mappings()]

    def node(self, node_id: str) -> GraphNode | None:
        engine = self._ensure_ready()
        with engine.connect() as conn:
            row = conn.execute(text(f"SELECT * FROM {self._node_table} WHERE node_id = :id"), {"id": node_id}).mappings().first()
        return self._node_from_row(row) if row else None
