"""Stage 7B.1: graph build tests -- frozen-input identity, extraction
validation, revision-scoped assertions, and build-accuracy evaluation.
Deterministic (fake extractor, fake embeddings, in-memory stores); no
network."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ingestion_bench.cross_document_benchmark.benchmark_runner import build_evidence_alignment
from ingestion_bench.graph_retrieval_benchmark import config
from ingestion_bench.graph_retrieval_benchmark.builder import (
    FrozenInputMismatchError,
    build_graph,
    load_fixtures_and_verify,
    verify_frozen_input_identity,
)
from ingestion_bench.graph_retrieval_benchmark.benchmark_runner import load_contract
from ingestion_bench.graph_retrieval_benchmark.evaluator import evaluate_graph_build
from ingestion_bench.graph_retrieval_benchmark.extractor import ChunkExtraction, ExtractedRelationship, FakeRelationshipExtractor
from ingestion_bench.graph_retrieval_benchmark.model import ExtractionRun
from ingestion_bench.retrieval_baseline.embeddings import FakeEmbeddingProvider

REPO_ROOT = Path(__file__).resolve().parent.parent
GRAPH_ROOT = REPO_ROOT / "src" / "ingestion_bench" / "graph_retrieval_benchmark"


@pytest.fixture(scope="module")
def contract():
    return load_contract(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH)


@pytest.fixture(scope="module")
def built(contract):
    fixtures, verification = load_fixtures_and_verify(contract)
    projection = build_graph(fixtures, FakeRelationshipExtractor(), FakeEmbeddingProvider())
    return fixtures, verification, projection


# --- frozen input identity ---------------------------------------------------


def test_frozen_input_identity_matches_stage7b0(built):
    _fixtures, verification, _projection = built
    assert verification.index_hash_matches is True
    assert verification.total_chunk_count == 11
    assert verification.recomputed_index_hash == verification.committed_index_hash


def test_frozen_input_verification_fails_on_tampered_chunk(contract):
    """If a re-loaded input differs from the committed Stage 7B.0
    evidence, verification must fail BEFORE any graph is built."""
    fixtures, _verification = load_fixtures_and_verify(contract)
    # Tamper one chunk's content hash in a shallow copy of the fixtures.
    import copy

    tampered = copy.deepcopy(fixtures)
    some_symbol = next(iter(tampered))
    chunk = tampered[some_symbol].chunks[0]
    tampered[some_symbol].chunks[0] = chunk.model_copy(update={"content_sha256": "0" * 64})
    with pytest.raises(FrozenInputMismatchError):
        verify_frozen_input_identity(tampered, contract)


# --- extraction validation ---------------------------------------------------


def test_every_edge_supporting_text_is_exact_substring_of_its_chunk(built):
    fixtures, _verification, projection = built
    text_by_chunk = {c.chunk_id: c.retrieval_text for fx in fixtures.values() for c in fx.chunks}
    for edge in projection.edge_assertions:
        assert edge.supporting_text in text_by_chunk[edge.supporting_chunk_id]
        assert edge.subject_node_id and edge.object_node_id


def test_every_edge_links_to_an_existing_chunk(built):
    fixtures, _verification, projection = built
    valid = {c.chunk_id for fx in fixtures.values() for c in fx.chunks}
    valid_hashes = {c.chunk_id: c.content_sha256 for fx in fixtures.values() for c in fx.chunks}
    for edge in projection.edge_assertions:
        assert edge.supporting_chunk_id in valid
        assert edge.supporting_content_sha256 == valid_hashes[edge.supporting_chunk_id]


def test_unsupported_extraction_is_rejected_not_silently_accepted(contract):
    """A relationship whose supporting_text is not a substring, or whose
    subject/object is not present in the supporting_text, must be
    REJECTED by the builder -- never silently turned into an edge."""

    class _BadExtractor:
        extractor_identity = "bad-stub"

        def extract(self, chunks):
            out = []
            for c in chunks:
                out.append((c.chunk_id, ChunkExtraction(
                    entities=[],
                    relationships=[
                        ExtractedRelationship(subject="X", predicate="p", object="Y", supporting_text="THIS TEXT IS NOT IN THE CHUNK"),
                        ExtractedRelationship(subject="Ghost", predicate="p", object="Phantom", supporting_text=c.retrieval_text[:20]),
                    ],
                )))
            run = ExtractionRun(extraction_run_id="extrun_bad", extractor_identity=self.extractor_identity, chunk_count=len(chunks))
            return out, run

    fixtures, _verification = load_fixtures_and_verify(contract)
    projection = build_graph(fixtures, _BadExtractor(), FakeEmbeddingProvider())
    assert projection.edge_assertions == []
    assert projection.rejected_relationship_count == 2 * len(projection.chunk_evidence)
    assert all("THIS TEXT IS NOT IN THE CHUNK" not in r for r in [e.supporting_text for e in projection.edge_assertions])


def test_revision_scoped_assertions_remain_separate(built):
    """The SAME relationship extracted from a current chunk vs a
    historical chunk must be two DISTINCT edge assertions (different
    document_revision_id / supporting chunk) -- never merged into one
    timeless edge. O-31 -> C-88 (current, obl_rev2) and O-31 -> C-88a
    (historical, obl_rev1) are distinct."""
    _fixtures, _verification, projection = built
    by_subject_predicate = {}
    for e in projection.edge_assertions:
        by_subject_predicate.setdefault((e.subject_node_id, e.predicate), set()).add((e.object_node_id, e.document_revision_id, e.supporting_chunk_id))
    # The O-31 is_satisfied_by edges: two distinct assertions (C-88, C-88a) on different revisions/chunks.
    satisfied = [v for (subj, pred), v in by_subject_predicate.items() if pred == "is_satisfied_by"]
    o31 = next(v for v in satisfied if len(v) >= 1)
    revisions = {rev for (_obj, rev, _chunk) in o31}
    # At least the current + historical satisfied-by assertions exist and are revision-distinct.
    assert len(o31) >= 2
    assert len(revisions) >= 2
    # No two assertions with different objects share the same edge identity/revision+chunk.
    chunks = {chunk for (_obj, _rev, chunk) in o31}
    assert len(chunks) == len(o31)


# --- build-accuracy evaluation ----------------------------------------------


def test_build_evaluation_fake_extractor_is_complete_and_clean(built, contract):
    fixtures, _verification, projection = built
    evidence = build_evidence_alignment(contract, fixtures)
    valid_chunk_ids = {c.chunk_id for fx in fixtures.values() for c in fx.chunks}
    ev = evaluate_graph_build(projection, contract, evidence, valid_chunk_ids)
    assert ev.expected_fact_edge_recall == 1.0
    assert ev.missing_expected_fact_ids == []
    assert ev.extracted_edge_precision == 1.0
    assert ev.unsupported_extracted_edge_count == 0
    assert ev.provenance_completeness == 1.0
    assert ev.edges_with_invalid_or_missing_supporting_chunk == 0
    assert ev.entity_normalization_collision_count == 0  # C-88 and C-88a never merge


def test_no_dangerous_identifier_collision_c88_vs_c88a(built):
    """C-88 and C-88a must be DIFFERENT nodes -- the normalization must
    never merge two distinct enterprise identifiers."""
    _fixtures, _verification, projection = built
    from ingestion_bench.graph_retrieval_benchmark.model import identifiers_in
    for node in projection.nodes.values():
        ids = set()
        for name in [node.canonical_name, *node.aliases]:
            ids |= identifiers_in(name)
        assert len(ids) <= 1, f"node {node.node_id} merged identifiers {ids}"


# --- holdout: construction never reads evaluation truth ---------------------


def test_builder_extractor_and_retriever_never_read_evaluation_truth():
    """Graph CONSTRUCTION and RETRIEVAL code must never read
    required_fact_ids / forbidden_fact_ids / expected_relationship_chain.
    Only the evaluator may. Checked at the AST level so an explanatory
    docstring naming these fields does not trip the test."""
    forbidden = {"required_fact_ids", "forbidden_fact_ids", "expected_relationship_chain"}
    for module in ("builder.py", "extractor.py", "retriever.py", "model.py", "store.py", "postgres_store.py"):
        tree = ast.parse((GRAPH_ROOT / module).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                assert node.slice.value not in forbidden, f"{module} reads evaluation truth key {node.slice.value!r}"
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden, f"{module} reads evaluation truth attribute {node.attr!r}"


def test_no_question_id_or_expected_path_in_graph_projection(built):
    """No question id, expected path, or answer text may appear anywhere
    in the built projection -- the graph is projection-neutral."""
    _fixtures, _verification, projection = built
    import json

    blob = json.dumps([json.loads(e.model_dump_json()) for e in projection.edge_assertions])
    blob += json.dumps([json.loads(n.model_dump_json()) for n in projection.nodes.values()])
    for token in ("question", "required_fact", "forbidden_fact", "expected_relationship", "Q01", "Q06"):
        assert token not in blob


def test_no_forbidden_dependency_in_graph_package():
    forbidden = ("wiki", "adk", "answer_baseline", "neo4j", "vision", "router", "decomposition", "workflow")
    for path in GRAPH_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                segs = node.module.lower().split(".")
                for name in forbidden:
                    assert name not in segs, f"{path} imports {node.module!r} (forbidden {name!r})"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    segs = alias.name.lower().split(".")
                    for name in forbidden:
                        assert name not in segs, f"{path} imports {alias.name!r} (forbidden {name!r})"
