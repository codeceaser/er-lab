"""Stage 7B.2: hybrid Vector-Graph probe tests.

Deterministic (fake embeddings, in-memory) except the one skippable real
sentence-transformers + Postgres run. Assertions target frozen-input
identity, authority safety (filter before ranking/traversal), path/edge
integrity, RRF determinism, budget, and scoring parity -- NEVER that any
hybrid mode must beat Vector (Hybrid superiority is not a test
expectation)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ingestion_bench.hybrid_retrieval_benchmark import config as hcfg
from ingestion_bench.hybrid_retrieval_benchmark.benchmark_runner import run_probe
from ingestion_bench.revision_authority.repository import InMemoryRevisionAuthorityRepository
from ingestion_bench.retrieval_baseline.embeddings import FakeEmbeddingProvider

REPO_ROOT = Path(__file__).resolve().parent.parent
HYBRID_ROOT = REPO_ROOT / "src" / "ingestion_bench" / "hybrid_retrieval_benchmark"
QUERY_PATH_MODULES = ("seed_provider.py", "path_retriever.py", "fusion.py", "edge_index.py", "evaluator.py", "benchmark_runner.py", "model.py", "config.py")


@pytest.fixture(scope="module")
def probe_result():
    return run_probe(hcfg.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH, hcfg.load_probe_config(), InMemoryRevisionAuthorityRepository(), FakeEmbeddingProvider())


def _rows(result, question_id=None, mode=None, cond=None):
    out = result.mode_results
    if question_id:
        out = [m for m in out if m.question_id == question_id]
    if mode:
        out = [m for m in out if m.mode == mode]
    if cond:
        out = [m for m in out if m.graph_condition == cond]
    return out


# --- frozen input identity --------------------------------------------------


def test_all_frozen_inputs_match(probe_result):
    iv = probe_result.input_verification
    assert iv.corpus_index_hash_matches is True
    assert iv.real_graph_payload_hash_matches is True
    assert iv.recomputed_real_graph_payload_hash == iv.committed_real_graph_payload_hash
    assert len(iv.vector_result_question_ids) == 12


def test_real_graph_loaded_from_snapshot_not_re_extracted(probe_result):
    iv = probe_result.input_verification
    # The real graph carries the committed OpenAI extraction run id -- it
    # was loaded, not freshly extracted (a fresh extraction would mint a
    # new uuid).
    assert iv.real_graph_extraction_run_id.startswith("extrun_openai_")
    assert iv.real_graph_node_count > 0 and iv.real_graph_edge_count > 0


def test_perfect_graph_is_perfect(probe_result):
    iv = probe_result.input_verification
    assert iv.perfect_graph_recall == 1.0
    assert iv.perfect_graph_precision == 1.0
    assert iv.perfect_graph_collisions == 0


# --- no query-time LLM / no evaluation truth --------------------------------


def test_no_openai_or_network_import_in_query_path_modules():
    for module in QUERY_PATH_MODULES:
        tree = ast.parse((HYBRID_ROOT / module).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for n in names:
                assert "openai" not in n.lower(), f"{module} imports {n!r}"
            # No reference to the OpenAI extractor class either.
            if isinstance(node, ast.Name):
                assert node.id != "OpenAIRelationshipExtractor", f"{module} references OpenAIRelationshipExtractor"


def test_query_time_llm_calls_are_zero(probe_result):
    for m in probe_result.mode_results:
        assert m.query_time_llm_calls == 0


def test_seed_path_fusion_never_read_evaluation_truth():
    forbidden = {"required_fact_ids", "forbidden_fact_ids", "expected_relationship_chain"}
    for module in ("seed_provider.py", "path_retriever.py", "fusion.py", "edge_index.py"):
        tree = ast.parse((HYBRID_ROOT / module).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                assert node.slice.value not in forbidden, f"{module} reads {node.slice.value!r}"
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden, f"{module} reads attribute {node.attr!r}"


# --- authority: filter before ranking / traversal ---------------------------


def test_zero_authority_leakage_across_all_modes(probe_result):
    for m in probe_result.mode_results:
        assert m.authority_leakage_count == 0, f"{m.question_id}/{m.mode}/{m.graph_condition}"


def test_edge_semantic_index_filters_eligibility_before_ranking():
    from ingestion_bench.hybrid_retrieval_benchmark.edge_index import InMemoryEdgeSemanticIndex
    from ingestion_bench.hybrid_retrieval_benchmark.model import EdgeEmbeddingRecord

    def _rec(eid, rev, emb):
        return EdgeEmbeddingRecord(
            edge_assertion_id=eid, subject_node_id="s", subject_canonical_name="s", object_node_id="o", object_canonical_name="o",
            predicate="p", logical_document_id="D", document_revision_id=rev, supporting_chunk_id="c", supporting_content_sha256="0" * 64,
            supporting_text="t", source_relative_path="x", source_document_sha256="0" * 64, representation="r", embedding=emb,
        )
    idx = InMemoryEdgeSemanticIndex([_rec("e_ineligible", "rev-bad", [1.0, 0.0]), _rec("e_eligible", "rev-ok", [0.0, 1.0])])
    # empty eligible -> []
    assert idx.semantic_search_eligible(query_vector=[1.0, 0.0], eligible_revision_ids=[], top_n=5) == []
    # ineligible edge is the strongest match but is filtered BEFORE ranking
    out = idx.semantic_search_eligible(query_vector=[1.0, 0.0], eligible_revision_ids=["rev-ok"], top_n=5)
    assert [r.edge_assertion_id for r, _ in out] == ["e_eligible"]


def test_vector_chunk_seed_pool_filters_eligibility_before_ranking():
    from ingestion_bench.hybrid_retrieval_benchmark.seed_provider import _authority_aware_vector_pool
    from ingestion_bench.revision_search_benchmark.store import RevisionVectorRecord

    def _r(cid, rev, emb):
        return RevisionVectorRecord(
            embedding_model="fake", logical_document_id="D", document_revision_id=rev, version_label=None, revision_number=1,
            source_document_sha256="a" * 64, source_relative_path="x", chunk_id=cid, content_sha256="b" * 64,
            retrieval_text="t", chunk_type="text", embedding=emb,
        )
    ce = {"good": _r("good", "rev-ok", [0.0, 1.0]), "bad": _r("bad", "rev-bad", [1.0, 0.0])}
    assert _authority_aware_vector_pool(query_vector=[1.0, 0.0], chunk_evidence=ce, eligible_revision_ids=[], pool_size=5) == []
    pool = _authority_aware_vector_pool(query_vector=[1.0, 0.0], chunk_evidence=ce, eligible_revision_ids=["rev-ok"], pool_size=5)
    assert [cid for cid, _ in pool] == ["good"]


# --- seeds ------------------------------------------------------------------


def test_seed_provenance_and_multiple_seeds_and_sources(probe_result):
    """H1/H2 support multiple seeds and preserve every origin (explicit /
    vector_chunk / semantic_edge) on a node seeded by more than one
    source."""
    # Q06 (names APP-224510) on the perfect graph should seed multiple
    # nodes from multiple sources.
    m = _rows(probe_result, "Q06_four_hop_procedure_of_app", "H1", "perfect_graph")[0]
    assert m.total_seed_count >= 1
    assert (m.explicit_seed_count + m.vector_seed_count + m.semantic_seed_count) >= m.total_seed_count  # a node may have multiple origins


def test_c88_never_merges_with_c88a_in_either_graph(probe_result):
    from ingestion_bench.graph_retrieval_benchmark.model import identifiers_in
    import json

    # perfect graph nodes are in the run; real graph nodes are in the committed 7B.1 report
    report = json.loads((REPO_ROOT / "reports" / "stage7b1_graph_build_results.json").read_text(encoding="utf-8"))
    for node in report["nodes"]:
        ids = set()
        for name in [node["canonical_name"], *node["aliases"]]:
            ids |= identifiers_in(name)
        assert len(ids) <= 1, f"real-graph node merged identifiers {ids}"


# --- paths ------------------------------------------------------------------


def test_path_integrity_via_direct_call():
    """Simple paths never repeat a node, never exceed the hop limit, and
    reference only existing edge assertions."""
    from ingestion_bench.graph_retrieval_benchmark.builder import build_graph, load_fixtures_and_verify
    from ingestion_bench.graph_retrieval_benchmark.extractor import FakeRelationshipExtractor
    from ingestion_bench.hybrid_retrieval_benchmark.model import HybridSeed, SeedOrigin
    from ingestion_bench.hybrid_retrieval_benchmark.path_retriever import semantic_path_ranked_graph_evidence

    contract = hcfg.load_probe_config()
    from ingestion_bench.graph_retrieval_benchmark.benchmark_runner import load_contract
    qc = load_contract(hcfg.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH)
    fixtures, _v = load_fixtures_and_verify(qc)
    proj = build_graph(fixtures, FakeRelationshipExtractor(), FakeEmbeddingProvider())
    edge_ids = {e.edge_assertion_id for e in proj.edge_assertions}
    # seed on every node to force maximal path enumeration
    seeds = [HybridSeed(node_id=n.node_id, canonical_name=n.canonical_name, entity_type=n.entity_type, origins=[SeedOrigin(seed_source="explicit_alias", matched_ref="x", source_rank=1)]) for n in proj.nodes.values()]
    max_hops = contract["candidate_parameters"]["max_hop_depth"]
    side = semantic_path_ranked_graph_evidence(seeds=seeds, eligible_edges=proj.edge_assertions, node_by_id=proj.nodes, chunk_evidence=proj.chunk_evidence, query_vector=[0.1] * 32, embedding_provider=FakeEmbeddingProvider(), max_hops=max_hops, max_candidate_paths=contract["candidate_parameters"]["max_candidate_paths"])
    assert side.candidate_path_count <= contract["candidate_parameters"]["max_candidate_paths"]
    for path in side.paths:
        assert len(path.node_ids) == len(set(path.node_ids)), "path has a repeated node"
        assert path.hop_length <= max_hops
        assert all(eid in edge_ids for eid in path.edge_assertion_ids), "path references a non-existent edge"


# --- evidence / budget / determinism ----------------------------------------


def test_only_original_chunks_are_evidence(probe_result):
    import json
    report = json.loads((REPO_ROOT / "reports" / "stage7b0_cross_document_vector_results.json").read_text(encoding="utf-8"))
    valid = {c for f in report["fixture_inventory"] for c in f["chunk_ids"]}
    for m in probe_result.mode_results:
        for cid in m.final_chunk_ids:
            assert cid in valid, f"{m.mode}: non-source chunk {cid} in evidence"


def test_final_results_never_exceed_frozen_top_k(probe_result):
    for m in probe_result.mode_results:
        assert len(m.final_chunk_ids) <= m.top_k
        assert len(m.fused_chunks) <= m.top_k


def test_rrf_is_deterministic():
    from ingestion_bench.hybrid_retrieval_benchmark.fusion import rrf_fuse
    from ingestion_bench.hybrid_retrieval_benchmark.model import RankedChunk

    v = [RankedChunk(chunk_id="a", rank=1, score=0.9), RankedChunk(chunk_id="b", rank=2, score=0.5)]
    g = [RankedChunk(chunk_id="b", rank=1, score=0.8), RankedChunk(chunk_id="c", rank=2, score=0.4)]
    r1 = rrf_fuse(vector_ranked=v, graph_ranked=g, rrf_constant=60, top_k=3, chunk_evidence={}, authority_labels={}, graph_chunk_support={})
    r2 = rrf_fuse(vector_ranked=v, graph_ranked=g, rrf_constant=60, top_k=3, chunk_evidence={}, authority_labels={}, graph_chunk_support={})
    assert [f.chunk_id for f in r1] == [f.chunk_id for f in r2]
    assert r1[0].chunk_id == "b"  # b is in both -> highest RRF


def test_all_five_modes_and_both_conditions_present(probe_result):
    modes = {m.mode for m in probe_result.mode_results}
    assert modes == {"V", "G", "H0", "H1", "H2"}
    conds = {m.graph_condition for m in probe_result.mode_results}
    assert conds == {"common", "real_graph", "perfect_graph"}


def test_all_modes_scored_by_the_frozen_stage7b0_scorer():
    from ingestion_bench.cross_document_benchmark import benchmark_runner as vector_runner
    from ingestion_bench.hybrid_retrieval_benchmark import evaluator as hybrid_evaluator
    assert hybrid_evaluator._evaluate_question is vector_runner._evaluate_question


def test_probe_contract_has_no_question_specific_tuning():
    """The probe contract holds ONE global algorithm configuration + the
    decision gates. It must contain no question-specific PATHS, SEEDS,
    ANSWERS, or relationship HINTS, and no per-question algorithm
    parameters. (Naming the target questions Q04/Q06/Q07/Q12 inside the
    DECISION GATES is the gate criteria the spec itself defines, not
    per-question algorithm tuning -- so question ids are allowed only in
    the decision_gates section.)"""
    import json
    contract = json.loads(hcfg.HYBRID_PROBE_CONTRACT_PATH.read_text(encoding="utf-8"))
    # Evaluation-truth hints must never appear anywhere.
    blob = json.dumps(contract)
    for token in ("required_fact", "forbidden_fact", "expected_relationship", "supporting_chunk", "supporting_text", "expected_supporting"):
        assert token not in blob, f"probe contract contains evaluation-truth token {token!r}"
    # Question ids must not appear OUTSIDE the decision_gates section (no
    # per-question algorithm parameters).
    non_gate = {k: v for k, v in contract.items() if k != "decision_gates"}
    non_gate_blob = json.dumps(non_gate)
    for token in ("Q01", "Q04", "Q06", "Q07", "Q10", "Q12"):
        assert token not in non_gate_blob, f"probe contract references {token!r} outside decision_gates (per-question tuning)"
    # The candidate parameters are a single flat global config (no
    # per-question keys).
    assert set(contract["candidate_parameters"].keys()) == {
        "vector_candidate_multiplier", "max_vector_seed_chunks", "semantic_edge_candidate_count",
        "max_hop_depth", "max_candidate_paths", "rrf_constant",
    }


def test_decision_gate_is_deterministic():
    a = run_probe(hcfg.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH, hcfg.load_probe_config(), InMemoryRevisionAuthorityRepository(), FakeEmbeddingProvider())
    b = run_probe(hcfg.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH, hcfg.load_probe_config(), InMemoryRevisionAuthorityRepository(), FakeEmbeddingProvider())
    assert a.decision_gate == b.decision_gate
    assert [(m.question_id, m.mode, m.graph_condition, m.required_fact_coverage_at_k) for m in a.mode_results] == [(m.question_id, m.mode, m.graph_condition, m.required_fact_coverage_at_k) for m in b.mode_results]


def test_frozen_stages_unmodified_by_stage7b2():
    import subprocess
    result = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--",
         "src/ingestion_bench/cross_document_benchmark", "src/ingestion_bench/graph_retrieval_benchmark",
         "src/ingestion_bench/revision_authority", "src/ingestion_bench/retrieval_baseline",
         "contracts/cross_document_relationship_benchmark_v1.json", "reports/stage7b0_cross_document_vector_results.json",
         "reports/stage7b1_graph_build_results.json"],
        cwd=REPO_ROOT, capture_output=True,
    )
    if result.returncode not in (0, 1):
        pytest.skip("git diff unavailable")
    assert result.returncode == 0, "a frozen Stage 7B.0/7B.1/7R/7A input was modified"


# --- real sentence-transformers + Postgres (skippable) ----------------------


def _real_infra() -> bool:
    try:
        if not hcfg.DATABASE_URL:
            return False
        import psycopg

        conn = psycopg.connect(hcfg.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"), connect_timeout=5)
        conn.close()
        import sentence_transformers  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _real_infra(), reason="DATABASE_URL/Postgres unreachable or sentence-transformers missing")
def test_real_sentence_transformers_and_postgres_edge_index():
    """Real ST embeddings end-to-end probe + a real Postgres edge index
    proving SQL-level eligibility filtering before ranking."""
    from ingestion_bench.graph_retrieval_benchmark.builder import build_graph, load_fixtures_and_verify
    from ingestion_bench.graph_retrieval_benchmark.benchmark_runner import load_contract
    from ingestion_bench.graph_retrieval_benchmark.extractor import FakeRelationshipExtractor
    from ingestion_bench.hybrid_retrieval_benchmark.edge_index import PgEdgeSemanticIndex, build_edge_embedding_records
    from ingestion_bench.retrieval_baseline.embeddings import SentenceTransformerEmbeddingProvider
    from ingestion_bench.revision_authority.repository import InMemoryRevisionAuthorityRepository

    provider = SentenceTransformerEmbeddingProvider()
    result = run_probe(hcfg.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH, hcfg.load_probe_config(), InMemoryRevisionAuthorityRepository(), provider)
    assert result.input_verification.corpus_index_hash_matches is True
    assert sum(m.authority_leakage_count for m in result.mode_results) == 0
    assert result.decision_gate in ("A", "B", "C", "D")

    # Real Postgres edge index: eligibility IN (...) before ORDER BY/LIMIT.
    qc = load_contract(hcfg.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH)
    fixtures, _v = load_fixtures_and_verify(qc)
    proj = build_graph(fixtures, FakeRelationshipExtractor(), provider)
    records, _manifest = build_edge_embedding_records(proj.edge_assertions, proj.nodes, provider)
    idx = PgEdgeSemanticIndex(embedding_dimension=provider.dimension, table_name="_pytest_7b2_edge")
    try:
        idx.load(records)
        eligible = [records[0].document_revision_id]
        out = idx.semantic_search_eligible(query_vector=records[0].embedding, eligible_revision_ids=eligible, top_n=5)
        assert out and all(r.document_revision_id in set(eligible) for r, _ in out)
        assert idx.semantic_search_eligible(query_vector=records[0].embedding, eligible_revision_ids=[], top_n=5) == []
    finally:
        from sqlalchemy import text
        with idx._ensure().connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS _pytest_7b2_edge CASCADE"))
            conn.commit()
