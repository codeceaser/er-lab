"""Stage 7B.2a: the isolated, persisted Postgres graph store used by the
MEASURED run (section 4).

Persists the graph nodes and edge assertions in isolated tables and
returns the authority-scoped subgraph via a SQL
`document_revision_id IN (...)` predicate -- the eligibility restriction
is applied in the database BEFORE any edge is handed to traversal, never
by post-filtering a full-graph fetch. An empty eligible set yields no
edges (never "return the whole graph"). In-memory `InMemoryGraphStore`
remains the deterministic-test store; this one is for the measured run.
"""

from __future__ import annotations

from ingestion_bench.graph_retrieval_benchmark.model import GraphEdgeAssertion, GraphNode
from ingestion_bench.graph_retrieval_benchmark.store import ExtractionRun


class PgGraphStoreUnavailable(RuntimeError):
    """Raised when DATABASE_URL is not configured or unreachable."""


class PgGraphStore:
    def __init__(self, table_prefix: str, database_url: str | None = None) -> None:
        from ingestion_bench.hybrid_retrieval_benchmark.config import DATABASE_URL

        self._database_url = database_url or DATABASE_URL
        if not self._database_url:
            raise PgGraphStoreUnavailable("DATABASE_URL is not set -- pass database_url= explicitly")
        self._nodes_table = f"{table_prefix}_node"
        self._edges_table = f"{table_prefix}_edge"
        self._engine = None

    def _ensure(self):
        from sqlalchemy import create_engine, text

        if self._engine is None:
            try:
                engine = create_engine(self._database_url, future=True)
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            except Exception as exc:  # noqa: BLE001
                raise PgGraphStoreUnavailable(f"could not connect: {type(exc).__name__}: {exc}") from exc
            with engine.connect() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {self._nodes_table} CASCADE"))
                conn.execute(text(f"DROP TABLE IF EXISTS {self._edges_table} CASCADE"))
                conn.execute(text(f"CREATE TABLE {self._nodes_table} (node_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"))
                conn.execute(text(f"""
                    CREATE TABLE {self._edges_table} (
                        edge_assertion_id TEXT PRIMARY KEY,
                        document_revision_id TEXT NOT NULL,
                        payload TEXT NOT NULL
                    )
                """))
                conn.execute(text(f"CREATE INDEX {self._edges_table}_rev_idx ON {self._edges_table} (document_revision_id)"))
                conn.commit()
            self._engine = engine
        return self._engine

    def save(self, nodes: list[GraphNode], edges: list[GraphEdgeAssertion], extraction_run: ExtractionRun) -> None:
        from sqlalchemy import text

        engine = self._ensure()
        with engine.connect() as conn:
            for n in nodes:
                conn.execute(
                    text(f"INSERT INTO {self._nodes_table} (node_id, payload) VALUES (:i, :p) ON CONFLICT (node_id) DO NOTHING"),
                    {"i": n.node_id, "p": n.model_dump_json()},
                )
            for e in edges:
                conn.execute(
                    text(f"INSERT INTO {self._edges_table} (edge_assertion_id, document_revision_id, payload) "
                         "VALUES (:i, :rev, :p) ON CONFLICT (edge_assertion_id) DO NOTHING"),
                    {"i": e.edge_assertion_id, "rev": e.document_revision_id, "p": e.model_dump_json()},
                )
            conn.commit()

    def all_nodes(self) -> list[GraphNode]:
        from sqlalchemy import text

        engine = self._ensure()
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT payload FROM {self._nodes_table} ORDER BY node_id")).mappings()
            return [GraphNode.model_validate_json(row["payload"]) for row in rows]

    def all_edge_assertions(self) -> list[GraphEdgeAssertion]:
        from sqlalchemy import text

        engine = self._ensure()
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT payload FROM {self._edges_table} ORDER BY edge_assertion_id")).mappings()
            return [GraphEdgeAssertion.model_validate_json(row["payload"]) for row in rows]

    def edge_assertions_for_revisions(self, eligible_revision_ids: list[str]) -> list[GraphEdgeAssertion]:
        """The authority-scoped subgraph -- eligibility is a SQL
        `document_revision_id IN (...)` predicate applied in the database
        BEFORE any edge reaches traversal. Empty eligible set -> []."""
        if not eligible_revision_ids:
            return []
        from sqlalchemy import bindparam, text

        engine = self._ensure()
        stmt = text(
            f"SELECT payload FROM {self._edges_table} WHERE document_revision_id IN :ids ORDER BY edge_assertion_id"
        ).bindparams(bindparam("ids", expanding=True))
        with engine.connect() as conn:
            rows = conn.execute(stmt, {"ids": list(eligible_revision_ids)}).mappings()
            return [GraphEdgeAssertion.model_validate_json(row["payload"]) for row in rows]

    def node(self, node_id: str) -> GraphNode | None:
        from sqlalchemy import text

        engine = self._ensure()
        with engine.connect() as conn:
            row = conn.execute(text(f"SELECT payload FROM {self._nodes_table} WHERE node_id = :i"), {"i": node_id}).mappings().first()
            return GraphNode.model_validate_json(row["payload"]) if row else None
