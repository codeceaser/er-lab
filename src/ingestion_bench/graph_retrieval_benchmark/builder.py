"""Stage 7B.1: frozen-input verification and graph construction.

`verify_frozen_input_identity` re-loads the Stage 7B.0 fixtures through
the frozen adapter+chunker and proves they are byte-for-byte the SAME
inputs Stage 7B.0 measured (source SHA-256, document_revision_ids,
chunk_ids, chunk content hashes via the committed index_hash, and corpus
logical-document ids) -- raising BEFORE any graph is built if anything
differs. It never rechunks differently.

`build_graph` runs a relationship extractor over the frozen chunks and
projects strictly-validated, revision-scoped edge assertions. Graph
construction NEVER reads evaluation truth (the fact contract, required/
forbidden facts, expected chain, or questions). Every accepted edge:
  - has a `supporting_text` that is an exact substring of the chunk's
    retrieval_text (else rejected);
  - has a subject and object that the extractor actually named as
    entities of that chunk / that appear in the supporting_text (else
    rejected -- a bare, source-unsupported endpoint is never accepted);
  - references exactly one existing Stage 7B.0 chunk.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from ingestion_bench.cross_document_benchmark.fixtures import RevisionFixture, load_all_revision_fixtures
from ingestion_bench.graph_retrieval_benchmark import config
from ingestion_bench.graph_retrieval_benchmark.extractor import ChunkExtractionInput, RelationshipExtractor
from ingestion_bench.graph_retrieval_benchmark.model import (
    ExtractionRun,
    GraphEdgeAssertion,
    GraphNode,
    compute_edge_assertion_id,
    compute_node_id,
    normalize_entity_name,
)
from ingestion_bench.retrieval_baseline.embeddings import EmbeddingProvider
from ingestion_bench.revision_search_benchmark.store import RevisionVectorRecord, compute_index_hash


class FrozenInputMismatchError(RuntimeError):
    """Raised when a re-loaded Stage 7B.0 input differs from the committed
    Stage 7B.0 evidence -- graph construction must never proceed on
    different inputs."""


class FrozenInputVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus_logical_document_ids: list[str]
    revision_symbols: list[str]
    total_chunk_count: int
    recomputed_index_hash: str
    committed_index_hash: str
    index_hash_matches: bool


def _load_committed_vector_results() -> dict:
    import json

    return json.loads(config.STAGE7B0_VECTOR_RESULTS_PATH.read_text(encoding="utf-8"))


def verify_frozen_input_identity(fixtures: dict[str, RevisionFixture], contract: dict) -> FrozenInputVerification:
    committed = _load_committed_vector_results()
    committed_by_symbol = {f["symbol"]: f for f in committed["fixture_inventory"]}

    for symbol, fixture in fixtures.items():
        exp = committed_by_symbol.get(symbol)
        if exp is None:
            raise FrozenInputMismatchError(f"symbol {symbol!r} not present in committed Stage 7B.0 fixture inventory")
        if fixture.source_document_sha256 != exp["source_document_sha256"]:
            raise FrozenInputMismatchError(
                f"{symbol}: source_document_sha256 {fixture.source_document_sha256!r} != committed {exp['source_document_sha256']!r}"
            )
        if fixture.document_revision_id != exp["document_revision_id"]:
            raise FrozenInputMismatchError(
                f"{symbol}: document_revision_id {fixture.document_revision_id!r} != committed {exp['document_revision_id']!r}"
            )
        actual_chunk_ids = [c.chunk_id for c in fixture.chunks]
        if actual_chunk_ids != exp["chunk_ids"]:
            raise FrozenInputMismatchError(f"{symbol}: chunk_ids {actual_chunk_ids} != committed {exp['chunk_ids']}")

    # index_hash over (chunk_id, content_sha256) for ALL chunks proves
    # both chunk identity AND content hashes match the committed inputs.
    all_chunks = [(c.chunk_id, c.content_sha256) for fx in fixtures.values() for c in fx.chunks]
    recomputed_index_hash = compute_index_hash(all_chunks)
    committed_index_hash = committed["index_build"]["index_hash"]
    if recomputed_index_hash != committed_index_hash:
        raise FrozenInputMismatchError(
            f"recomputed index_hash {recomputed_index_hash!r} != committed Stage 7B.0 index_hash {committed_index_hash!r} "
            "-- chunk identity or content hashes differ from the frozen inputs"
        )

    corpus_docs = sorted({fx.logical_document_id for fx in fixtures.values()})
    expected_corpus_docs = sorted(set(contract["logical_documents"].keys()))
    if corpus_docs != expected_corpus_docs:
        raise FrozenInputMismatchError(f"corpus logical documents {corpus_docs} != contract {expected_corpus_docs}")

    return FrozenInputVerification(
        corpus_logical_document_ids=corpus_docs,
        revision_symbols=sorted(fixtures),
        total_chunk_count=len(all_chunks),
        recomputed_index_hash=recomputed_index_hash,
        committed_index_hash=committed_index_hash,
        index_hash_matches=True,
    )


# --- graph projection result -----------------------------------------------


@dataclass
class GraphProjection:
    nodes: dict[str, GraphNode]
    edge_assertions: list[GraphEdgeAssertion]
    # chunk_id -> provenance-rich record (with embedding) for the retriever
    # to hydrate evidence and rank by supporting-chunk similarity.
    chunk_evidence: dict[str, RevisionVectorRecord]
    extraction_run: ExtractionRun
    rejected_relationship_count: int = 0
    rejected_relationships: list[str] = field(default_factory=list)
    duplicate_assertion_count: int = 0


def _chunk_inputs(fixtures: dict[str, RevisionFixture]) -> list[ChunkExtractionInput]:
    inputs: list[ChunkExtractionInput] = []
    for fixture in fixtures.values():
        for chunk in fixture.chunks:
            inputs.append(ChunkExtractionInput(
                chunk_id=chunk.chunk_id, content_sha256=chunk.content_sha256, retrieval_text=chunk.retrieval_text,
                logical_document_id=chunk.logical_document_id, document_revision_id=chunk.document_revision_id,
                source_relative_path=fixture.source_relative_path, source_document_sha256=chunk.source_document_sha256,
                version_label=chunk.version_label, revision_number=chunk.revision_number,
                unit_indices=list(chunk.unit_indices), heading_path=list(chunk.heading_path),
                source_element_ids=list(chunk.source_element_ids),
                source_refs=[ref.model_dump(mode="json") for ref in chunk.source_refs],
            ))
    return inputs


def _record_from_input(chunk: ChunkExtractionInput, embedding: list[float], embedding_model: str) -> RevisionVectorRecord:
    return RevisionVectorRecord(
        embedding_model=embedding_model, logical_document_id=chunk.logical_document_id,
        document_revision_id=chunk.document_revision_id, version_label=chunk.version_label,
        revision_number=chunk.revision_number, source_document_sha256=chunk.source_document_sha256,
        source_relative_path=chunk.source_relative_path, chunk_id=chunk.chunk_id, content_sha256=chunk.content_sha256,
        retrieval_text=chunk.retrieval_text, chunk_type="text", unit_indices=chunk.unit_indices,
        heading_path=chunk.heading_path, source_element_ids=chunk.source_element_ids, source_refs=chunk.source_refs,
        embedding=embedding,
    )


def build_graph(
    fixtures: dict[str, RevisionFixture],
    extractor: RelationshipExtractor,
    embedding_provider: EmbeddingProvider,
) -> GraphProjection:
    chunk_inputs = _chunk_inputs(fixtures)
    input_by_chunk = {c.chunk_id: c for c in chunk_inputs}

    # Embed every chunk once (same embedding model as Vector) for the
    # retriever's supporting-chunk similarity ranking.
    embed_result = embedding_provider.embed([c.retrieval_text for c in chunk_inputs])
    chunk_evidence = {
        c.chunk_id: _record_from_input(c, vec, embedding_provider.model_identity)
        for c, vec in zip(chunk_inputs, embed_result.vectors)
    }

    extractions, extraction_run = extractor.extract(chunk_inputs)

    nodes: dict[str, GraphNode] = {}
    edge_assertions: list[GraphEdgeAssertion] = []
    seen_edges: set[str] = set()
    rejected: list[str] = []
    duplicate_count = 0

    def upsert_node(name: str, entity_type: str, aliases: list[str]) -> str:
        normalized = normalize_entity_name(name)
        node_id = compute_node_id(normalized)
        if node_id not in nodes:
            nodes[node_id] = GraphNode(node_id=node_id, entity_type=entity_type, canonical_name=name, aliases=sorted({name, *aliases}))
        else:
            merged = sorted({nodes[node_id].canonical_name, *nodes[node_id].aliases, name, *aliases})
            nodes[node_id] = nodes[node_id].model_copy(update={"aliases": [a for a in merged if a != nodes[node_id].canonical_name]})
        return node_id

    for chunk_id, extraction in extractions:
        chunk = input_by_chunk[chunk_id]
        entity_types = {e.name: e.entity_type for e in extraction.entities}
        entity_aliases: dict[str, list[str]] = {e.name: list(e.aliases) for e in extraction.entities}

        for rel in extraction.relationships:
            # Reject: supporting_text must be an exact substring of the chunk text.
            if rel.supporting_text not in chunk.retrieval_text:
                rejected.append(f"{chunk_id}: supporting_text not a substring of retrieval_text: {rel.supporting_text!r}")
                continue
            # Reject: subject and object must each be supported by the source
            # assertion (present in the supporting_text). A bare, source-
            # unsupported endpoint is never accepted.
            if rel.subject not in rel.supporting_text or rel.object not in rel.supporting_text:
                rejected.append(f"{chunk_id}: subject/object not supported by supporting_text: {rel.subject!r}/{rel.object!r}")
                continue

            subject_node_id = upsert_node(rel.subject, entity_types.get(rel.subject, "other"), entity_aliases.get(rel.subject, []))
            object_node_id = upsert_node(rel.object, entity_types.get(rel.object, "other"), entity_aliases.get(rel.object, []))
            edge_assertion_id = compute_edge_assertion_id(subject_node_id, rel.predicate, object_node_id, chunk_id)
            if edge_assertion_id in seen_edges:
                duplicate_count += 1  # exact duplicate assertion from the same chunk -- keep one
                continue
            seen_edges.add(edge_assertion_id)
            edge_assertions.append(GraphEdgeAssertion(
                edge_assertion_id=edge_assertion_id, subject_node_id=subject_node_id, predicate=rel.predicate,
                object_node_id=object_node_id, logical_document_id=chunk.logical_document_id,
                document_revision_id=chunk.document_revision_id, supporting_chunk_id=chunk_id,
                supporting_content_sha256=chunk.content_sha256, supporting_text=rel.supporting_text,
                source_relative_path=chunk.source_relative_path, source_document_sha256=chunk.source_document_sha256,
                version_label=chunk.version_label, revision_number=chunk.revision_number,
                unit_indices=chunk.unit_indices, heading_path=chunk.heading_path,
                source_element_ids=chunk.source_element_ids, source_refs=chunk.source_refs,
                extraction_run_id=extraction_run.extraction_run_id,
            ))

    return GraphProjection(
        nodes=nodes, edge_assertions=edge_assertions, chunk_evidence=chunk_evidence,
        extraction_run=extraction_run, rejected_relationship_count=len(rejected), rejected_relationships=rejected,
        duplicate_assertion_count=duplicate_count,
    )


def load_fixtures_and_verify(contract: dict) -> tuple[dict[str, RevisionFixture], FrozenInputVerification]:
    fixtures = load_all_revision_fixtures(contract["fixtures"])
    verification = verify_frozen_input_identity(fixtures, contract)
    return fixtures, verification
