"""Stage 7B.1: graph persistence contract + in-memory reference store.

The store holds nodes, revision-scoped edge assertions, and extraction
runs. It records auditable build metrics (counts, a deterministic graph
payload hash, a storage estimate). The in-memory store is used by the
default tests; the measured run uses the Postgres store
(postgres_store.py). Postgres is sufficient -- there is NO Neo4j and NO
generic graph framework.
"""

from __future__ import annotations

import hashlib
import json
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from ingestion_bench.graph_retrieval_benchmark.model import ExtractionRun, GraphEdgeAssertion, GraphNode


class GraphBuildManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_count: int
    edge_assertion_count: int
    evidence_count: int  # distinct supporting chunk_ids referenced by edges
    graph_payload_sha256: str
    storage_estimate_bytes: int
    build_latency_seconds: float
    extractor_identity: str
    extraction_input_tokens: int | None
    extraction_output_tokens: int | None
    extraction_estimated_cost_usd: float | None
    extraction_failure_count: int


def compute_graph_payload_hash(nodes: list[GraphNode], edges: list[GraphEdgeAssertion]) -> str:
    """Deterministic SHA-256 over the sorted node ids + the sorted
    (edge_assertion_id, subject, predicate, object, supporting_chunk_id,
    supporting_content_sha256) identity of every edge -- changes whenever
    the graph's structure or its evidence backing changes."""
    payload = {
        "nodes": sorted(n.node_id for n in nodes),
        "edges": sorted(
            [e.edge_assertion_id, e.subject_node_id, e.predicate.casefold().strip(), e.object_node_id,
             e.supporting_chunk_id, e.supporting_content_sha256]
            for e in edges
        ),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class GraphStore(Protocol):
    def save(self, nodes: list[GraphNode], edges: list[GraphEdgeAssertion], extraction_run: ExtractionRun) -> None: ...
    def all_nodes(self) -> list[GraphNode]: ...
    def all_edge_assertions(self) -> list[GraphEdgeAssertion]: ...
    def edge_assertions_for_revisions(self, eligible_revision_ids: list[str]) -> list[GraphEdgeAssertion]:
        """ONLY the edge assertions whose supporting revision is in the
        eligible set -- the authority-scoped subgraph. An empty eligible
        set yields no edges (never "return the whole graph")."""
        ...
    def node(self, node_id: str) -> GraphNode | None: ...


class InMemoryGraphStore:
    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdgeAssertion] = {}
        self._runs: dict[str, ExtractionRun] = {}

    def save(self, nodes: list[GraphNode], edges: list[GraphEdgeAssertion], extraction_run: ExtractionRun) -> None:
        for n in nodes:
            self._nodes[n.node_id] = n
        for e in edges:
            self._edges[e.edge_assertion_id] = e
        self._runs[extraction_run.extraction_run_id] = extraction_run

    def all_nodes(self) -> list[GraphNode]:
        return list(self._nodes.values())

    def all_edge_assertions(self) -> list[GraphEdgeAssertion]:
        return list(self._edges.values())

    def edge_assertions_for_revisions(self, eligible_revision_ids: list[str]) -> list[GraphEdgeAssertion]:
        if not eligible_revision_ids:
            return []
        eligible = set(eligible_revision_ids)
        return [e for e in self._edges.values() if e.document_revision_id in eligible]

    def node(self, node_id: str) -> GraphNode | None:
        return self._nodes.get(node_id)


def build_manifest(
    nodes: list[GraphNode], edges: list[GraphEdgeAssertion], extraction_run: ExtractionRun, build_latency_seconds: float
) -> GraphBuildManifest:
    node_json = sum(len(n.model_dump_json()) for n in nodes)
    edge_json = sum(len(e.model_dump_json()) for e in edges)
    return GraphBuildManifest(
        node_count=len(nodes),
        edge_assertion_count=len(edges),
        evidence_count=len({e.supporting_chunk_id for e in edges}),
        graph_payload_sha256=compute_graph_payload_hash(nodes, edges),
        storage_estimate_bytes=node_json + edge_json,
        build_latency_seconds=build_latency_seconds,
        extractor_identity=extraction_run.extractor_identity,
        extraction_input_tokens=extraction_run.input_tokens,
        extraction_output_tokens=extraction_run.output_tokens,
        extraction_estimated_cost_usd=extraction_run.estimated_cost_usd,
        extraction_failure_count=extraction_run.extraction_failure_count,
    )
