"""Stage 7B.2: the hybrid probe runner.

Verifies all frozen inputs, loads the real Stage 7B.1 graph snapshot and
builds the perfect FakeRelationshipExtractor graph, builds an edge
semantic index per graph condition, and for every frozen Stage 7B.0
question runs the five modes (V/G/H0/H1/H2) over both graph conditions --
scoring each with the frozen Stage 7B.0 scorer -- then applies the fixed
decision gates. No query-time LLM.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from ingestion_bench.cross_document_benchmark.benchmark_runner import FactEvidence, build_evidence_alignment
from ingestion_bench.graph_retrieval_benchmark.builder import build_graph, load_fixtures_and_verify
from ingestion_bench.graph_retrieval_benchmark.evaluator import evaluate_graph_build
from ingestion_bench.graph_retrieval_benchmark.extractor import FakeRelationshipExtractor
from ingestion_bench.graph_retrieval_benchmark.model import GraphEdgeAssertion, GraphNode
from ingestion_bench.graph_retrieval_benchmark.retriever import _resolve_corpus, graph_search
from ingestion_bench.graph_retrieval_benchmark.store import InMemoryGraphStore, build_manifest, compute_graph_payload_hash
from ingestion_bench.graph_retrieval_benchmark.builder import GraphProjection
from ingestion_bench.hybrid_retrieval_benchmark import config as hcfg
from ingestion_bench.hybrid_retrieval_benchmark.edge_index import build_edge_embedding_records, InMemoryEdgeSemanticIndex
from ingestion_bench.hybrid_retrieval_benchmark.evaluator import GateInputs, ResolutionBundle, TARGET_QUESTIONS, Q12, decide, score_mode
from ingestion_bench.hybrid_retrieval_benchmark.fusion import rrf_fuse
from ingestion_bench.hybrid_retrieval_benchmark.model import FusedChunk, RankedChunk
from ingestion_bench.hybrid_retrieval_benchmark.path_retriever import GraphSideResult, hop_ranked_graph_evidence, semantic_path_ranked_graph_evidence
from ingestion_bench.hybrid_retrieval_benchmark.seed_provider import SeedResult, collect_hybrid_seeds
from ingestion_bench.hybrid_retrieval_benchmark.vector_candidate_store import InMemoryVectorCandidateStore
from ingestion_bench.retrieval_baseline.embeddings import EmbeddingProvider
from ingestion_bench.revision_authority.contract_runner import _run_registry_setup
from ingestion_bench.revision_authority.repository import RevisionAuthorityRepository
from ingestion_bench.revision_authority.resolver import RevisionAuthorityLabel
from ingestion_bench.revision_authority.service import RevisionAuthorityService
from ingestion_bench.revision_search_benchmark.store import RevisionVectorRecord, compute_index_hash


# --- input verification -----------------------------------------------------


class InputVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus_index_hash_matches: bool
    committed_vector_index_hash: str
    vector_result_question_ids: list[str]
    real_graph_payload_hash_matches: bool
    committed_real_graph_payload_hash: str
    recomputed_real_graph_payload_hash: str
    perfect_graph_payload_hash: str
    perfect_graph_recall: float
    perfect_graph_precision: float
    perfect_graph_collisions: int
    real_graph_node_count: int
    real_graph_edge_count: int
    real_graph_extraction_run_id: str


class InputVerificationError(RuntimeError):
    pass


class FrozenGVerification(BaseModel):
    """Section 5 evidence: the real-graph G condition is the committed
    Stage 7B.1 per-question Graph result, LOADED directly. When the run's
    embedding model matches the committed Stage 7B.1 model, a fresh
    graph_search rerun is additionally required to reproduce the frozen
    ranking (chunk_id + rank) EXACTLY, with scores equal within a 1e-6
    tolerance (a live re-embedding is not bit-reproducible vs the committed
    float scores), before use."""

    model_config = ConfigDict(extra="forbid")

    committed_embedding_model: str
    run_embedding_model: str
    embedding_model_matches: bool
    g_loaded_directly_from_frozen_7b1: bool
    rerun_equality_asserted: bool  # only when embedding_model_matches
    rerun_equality_holds: bool     # True (or vacuously True when not asserted)
    per_question_frozen_g_chunk_counts: dict[str, int]
    mismatched_question_ids: list[str]


# --- per-mode result --------------------------------------------------------


class ModeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    question_type: str
    query_intent: str
    top_k: int
    mode: str
    graph_condition: str  # "common" (V) | "real_graph" | "perfect_graph"

    required_fact_coverage_at_k: float
    all_required_facts_retrieved_at_k: bool
    complete_chain_represented: bool
    mrr: float
    ndcg_at_k: float
    forbidden_fact_hit_ids: list[str]
    authority_leakage_count: int
    evidence_document_diversity: int
    outcome: str
    authority_correct: bool
    final_chunk_ids: list[str]

    # hybrid-specific (0/empty for V and G)
    explicit_seed_count: int = 0
    vector_seed_count: int = 0
    semantic_seed_count: int = 0
    total_seed_count: int = 0
    no_seed: bool = False
    eligible_semantic_edge_hits: int = 0
    candidate_path_count: int = 0
    vg_overlap_at_k: int = 0
    chunks_only_vector: int = 0
    chunks_only_graph: int = 0
    chunks_both: int = 0
    seed_source_contribution: dict[str, int] = {}
    query_time_embedding_calls: int = 0
    query_time_llm_calls: int = 0

    # --- section 1: seed-saturation diagnostics ---
    eligible_graph_node_count: int = 0
    supplemental_seed_candidate_count: int = 0
    selected_supplemental_seed_count: int = 0
    seed_saturation_ratio: float = 0.0
    seed_saturation_ok: bool = True

    # --- section 2: path-enumeration diagnostics (H2) ---
    paths_enumerated_before_ranking: int = 0
    paths_retained_after_ranking: int = 0
    path_count_by_hop_length: dict[int, int] = {}
    path_count_by_originating_seed: dict[str, int] = {}
    eligible_edge_path_coverage: float = 0.0

    # --- section 6: timing / call accounting (resolver never double-counted) ---
    query_embedding_latency_seconds: float = 0.0
    query_embedding_calls: int = 0
    authority_resolution_latency_seconds: float = 0.0
    vector_candidate_store_latency_seconds: float = 0.0
    semantic_edge_store_latency_seconds: float = 0.0
    graph_load_latency_seconds: float = 0.0
    traversal_latency_seconds: float = 0.0
    path_embedding_latency_seconds: float = 0.0
    path_embedding_calls: int = 0
    fusion_latency_seconds: float = 0.0

    total_latency_seconds: float

    fused_chunks: list[FusedChunk]


class ProbeRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    generated_at: str
    embedding_model: str
    candidate_parameters: dict[str, Any]

    input_verification: InputVerification
    frozen_g_verification: FrozenGVerification
    edge_index_manifests: dict[str, Any]

    mode_results: list[ModeResult]

    decision_gate: str
    decision: str
    decision_rationale: str
    real_gate_inputs: dict[str, Any]
    perfect_gate_inputs: dict[str, Any]


# --- helpers ----------------------------------------------------------------

_EMPTY_SEED_RESULT = SeedResult(
    seeds=[], eligible_graph_node_count=0, supplemental_seed_candidate_count=0, selected_supplemental_seed_count=0,
    explicit_seed_count=0, total_seed_count=0, seed_saturation_ratio=0.0, seed_saturation_ok=True, eligible_semantic_edge_hits=0,
    vector_candidate_store_latency_seconds=0.0, semantic_edge_store_latency_seconds=0.0,
)


def _load_real_graph() -> tuple[list[GraphNode], list[GraphEdgeAssertion], str, str]:
    report = json.loads(hcfg.STAGE7B1_GRAPH_BUILD_RESULTS_PATH.read_text(encoding="utf-8"))
    nodes = [GraphNode.model_validate(n) for n in report["nodes"]]
    edges = [GraphEdgeAssertion.model_validate(e) for e in report["edge_assertions"]]
    committed_hash = report["build_manifest"]["graph_payload_sha256"]
    extraction_run_id = report["extraction_run"]["extraction_run_id"]
    return nodes, edges, committed_hash, extraction_run_id


def _load_frozen_7b1_graph_results() -> tuple[dict[str, list[dict]], str]:
    """Section 5: the committed Stage 7B.1 per-question Graph result hits,
    keyed by question id, plus the model they were produced with."""
    report = json.loads(hcfg.STAGE7B1_GRAPH_RETRIEVAL_RESULTS_PATH.read_text(encoding="utf-8"))
    by_q = {row["question_id"]: row["graph_result"]["hits"] for row in report["graph_question_metrics"]}
    return by_q, report["embedding_model"]


def _ranked_from_hits(hits: list[dict]) -> list[RankedChunk]:
    return [RankedChunk(chunk_id=h["chunk_id"], rank=h["rank"], score=h["similarity_score"]) for h in sorted(hits, key=lambda h: h["rank"])]


def _frozen_graph_fused(hits: list[dict]) -> tuple[list[FusedChunk], list[RankedChunk]]:
    """Build the real-graph G evidence DIRECTLY from the frozen Stage 7B.1
    graph_result hits (loaded, never recomputed) -- section 5."""
    fused: list[FusedChunk] = []
    ranked: list[RankedChunk] = []
    for h in sorted(hits, key=lambda h: h["rank"]):
        label = RevisionAuthorityLabel.model_validate(h["authority_label"]) if h.get("authority_label") else None
        ranked.append(RankedChunk(chunk_id=h["chunk_id"], rank=h["rank"], score=h["similarity_score"]))
        fused.append(FusedChunk(
            chunk_id=h["chunk_id"], final_rank=h["rank"], rrf_score=h["similarity_score"], graph_rank=h["rank"],
            graph_score=h["similarity_score"], contributed_by="graph_only", seed_sources=["explicit_alias"],
            supporting_edge_assertion_ids=list(h.get("supporting_edge_assertion_ids", [])),
            logical_document_id=h["logical_document_id"], document_revision_id=h["document_revision_id"],
            version_label=h.get("version_label"), revision_number=h.get("revision_number"),
            source_relative_path=h["source_relative_path"], source_document_sha256=h["source_document_sha256"],
            content_sha256=h["content_sha256"], retrieval_text=h["retrieval_text"], chunk_type=h["chunk_type"],
            unit_indices=list(h.get("unit_indices", [])), heading_path=list(h.get("heading_path", [])),
            source_element_ids=list(h.get("source_element_ids", [])), source_refs=list(h.get("source_refs", [])),
            authority_label=label,
        ))
    return fused, ranked


def _vector_fused(vector_hits: list[dict]) -> list[FusedChunk]:
    fused: list[FusedChunk] = []
    for h in sorted(vector_hits, key=lambda h: h["rank"]):
        label = RevisionAuthorityLabel.model_validate(h["authority_label"]) if h.get("authority_label") else None
        fused.append(FusedChunk(
            chunk_id=h["chunk_id"], final_rank=h["rank"], rrf_score=h["similarity_score"], vector_rank=h["rank"],
            vector_score=h["similarity_score"], contributed_by="vector_only", logical_document_id=h["logical_document_id"],
            document_revision_id=h["document_revision_id"], version_label=h.get("version_label"), revision_number=h.get("revision_number"),
            source_relative_path=h["source_relative_path"], source_document_sha256=h["source_document_sha256"],
            content_sha256=h["content_sha256"], retrieval_text=h["retrieval_text"], chunk_type=h["chunk_type"],
            unit_indices=h["unit_indices"], heading_path=h["heading_path"], source_element_ids=h["source_element_ids"],
            source_refs=h["source_refs"], authority_label=label,
        ))
    return fused


def _graph_fused(graph_result, chunk_evidence: dict[str, RevisionVectorRecord]) -> tuple[list[FusedChunk], list[RankedChunk]]:
    fused: list[FusedChunk] = []
    ranked: list[RankedChunk] = []
    for h in graph_result.hits:
        ranked.append(RankedChunk(chunk_id=h.chunk_id, rank=h.rank, score=h.similarity_score))
        fused.append(FusedChunk(
            chunk_id=h.chunk_id, final_rank=h.rank, rrf_score=h.similarity_score, graph_rank=h.rank, graph_score=h.similarity_score,
            contributed_by="graph_only", seed_sources=["explicit_alias"], supporting_edge_assertion_ids=list(h.supporting_edge_assertion_ids),
            logical_document_id=h.logical_document_id, document_revision_id=h.document_revision_id, version_label=h.version_label,
            revision_number=h.revision_number, source_relative_path=h.source_relative_path, source_document_sha256=h.source_document_sha256,
            content_sha256=h.content_sha256, retrieval_text=h.retrieval_text, chunk_type=h.chunk_type, unit_indices=list(h.unit_indices),
            heading_path=list(h.heading_path), source_element_ids=list(h.source_element_ids), source_refs=list(h.source_refs),
            authority_label=h.authority_label,
        ))
    return fused, ranked


def _hybrid_metrics(seed_result, graph_side: GraphSideResult, fused: list[FusedChunk], vector_ranked: list[RankedChunk], graph_ranked: list[RankedChunk]) -> dict[str, Any]:
    seeds = seed_result.seeds
    explicit = sum(1 for s in seeds if any(o.seed_source == "explicit_alias" for o in s.origins))
    vector = sum(1 for s in seeds if any(o.seed_source == "vector_chunk" for o in s.origins))
    semantic = sum(1 for s in seeds if any(o.seed_source == "semantic_edge" for o in s.origins))
    v_ids = {r.chunk_id for r in vector_ranked}
    g_ids = {r.chunk_id for r in graph_ranked}
    contribution: dict[str, int] = {}
    for fc in fused:
        for src in fc.seed_sources:
            contribution[src] = contribution.get(src, 0) + 1
    return dict(
        explicit_seed_count=explicit, vector_seed_count=vector, semantic_seed_count=semantic, total_seed_count=len(seeds),
        no_seed=(len(seeds) == 0), candidate_path_count=graph_side.candidate_path_count,
        vg_overlap_at_k=len(v_ids & g_ids), chunks_only_vector=sum(1 for f in fused if f.contributed_by == "vector_only"),
        chunks_only_graph=sum(1 for f in fused if f.contributed_by == "graph_only"), chunks_both=sum(1 for f in fused if f.contributed_by == "both"),
        seed_source_contribution=contribution,
        # section 1 seed-saturation diagnostics
        eligible_graph_node_count=seed_result.eligible_graph_node_count,
        supplemental_seed_candidate_count=seed_result.supplemental_seed_candidate_count,
        selected_supplemental_seed_count=seed_result.selected_supplemental_seed_count,
        seed_saturation_ratio=seed_result.seed_saturation_ratio, seed_saturation_ok=seed_result.seed_saturation_ok,
        eligible_semantic_edge_hits=seed_result.eligible_semantic_edge_hits,
        # section 2 path diagnostics
        paths_enumerated_before_ranking=graph_side.paths_enumerated_before_ranking,
        paths_retained_after_ranking=graph_side.paths_retained_after_ranking,
        path_count_by_hop_length=dict(graph_side.path_count_by_hop_length),
        path_count_by_originating_seed=dict(graph_side.path_count_by_originating_seed),
        eligible_edge_path_coverage=graph_side.eligible_edge_path_coverage,
        # section 6 store latencies (from the seed collection)
        vector_candidate_store_latency_seconds=seed_result.vector_candidate_store_latency_seconds,
        semantic_edge_store_latency_seconds=seed_result.semantic_edge_store_latency_seconds,
    )


def run_probe(
    question_contract_path: Path, probe_config: dict, repository: RevisionAuthorityRepository, embedding_provider: EmbeddingProvider,
    persisted: bool = False,
) -> ProbeRunResult:
    """Run the hybrid probe. With ``persisted=True`` the MEASURED path uses
    isolated Postgres stores (graph, edge-semantic index, pgvector
    candidate store) -- eligibility filtered in SQL BEFORE ORDER BY/LIMIT.
    ``persisted=False`` uses the deterministic in-memory stores (tests)."""
    contract = json.loads(Path(question_contract_path).read_text(encoding="utf-8"))
    params = probe_config["candidate_parameters"]

    # --- 1. frozen input verification + graphs ---
    fixtures, verification = load_fixtures_and_verify(contract)
    committed_vector = json.loads(hcfg.STAGE7B0_VECTOR_RESULTS_PATH.read_text(encoding="utf-8"))
    vector_by_question = {q["question_id"]: q for q in committed_vector["question_results"]}

    perfect_proj = build_graph(fixtures, FakeRelationshipExtractor(), embedding_provider)
    chunk_evidence = perfect_proj.chunk_evidence
    evidence = build_evidence_alignment(contract, fixtures)
    valid_chunk_ids = {c.chunk_id for fx in fixtures.values() for c in fx.chunks}
    perfect_eval = evaluate_graph_build(perfect_proj, contract, evidence, valid_chunk_ids)
    perfect_payload = compute_graph_payload_hash(list(perfect_proj.nodes.values()), perfect_proj.edge_assertions)
    if not (perfect_eval.expected_fact_edge_recall == 1.0 and perfect_eval.extracted_edge_precision == 1.0 and perfect_eval.entity_normalization_collision_count == 0):
        raise InputVerificationError(f"perfect graph not perfect: recall {perfect_eval.expected_fact_edge_recall}, precision {perfect_eval.extracted_edge_precision}, collisions {perfect_eval.entity_normalization_collision_count}")

    real_nodes, real_edges, committed_real_hash, extraction_run_id = _load_real_graph()
    recomputed_real_hash = compute_graph_payload_hash(real_nodes, real_edges)
    if recomputed_real_hash != committed_real_hash:
        raise InputVerificationError(f"real graph payload hash {recomputed_real_hash} != committed {committed_real_hash}")
    real_proj = GraphProjection(nodes={n.node_id: n for n in real_nodes}, edge_assertions=real_edges, chunk_evidence=chunk_evidence, extraction_run=perfect_proj.extraction_run)

    input_verification = InputVerification(
        corpus_index_hash_matches=verification.index_hash_matches, committed_vector_index_hash=committed_vector["index_build"]["index_hash"],
        vector_result_question_ids=[q["question_id"] for q in committed_vector["question_results"]],
        real_graph_payload_hash_matches=True, committed_real_graph_payload_hash=committed_real_hash,
        recomputed_real_graph_payload_hash=recomputed_real_hash, perfect_graph_payload_hash=perfect_payload,
        perfect_graph_recall=perfect_eval.expected_fact_edge_recall, perfect_graph_precision=perfect_eval.extracted_edge_precision,
        perfect_graph_collisions=perfect_eval.entity_normalization_collision_count, real_graph_node_count=len(real_nodes),
        real_graph_edge_count=len(real_edges), real_graph_extraction_run_id=extraction_run_id,
    )

    # --- stores (in-memory for tests; isolated Postgres for the measured run) ---
    projections = {"real_graph": real_proj, "perfect_graph": perfect_proj}
    conditions: dict[str, tuple[GraphProjection, Any]] = {}
    edge_indexes: dict[str, Any] = {}
    graph_load_latency: dict[str, float] = {}
    edge_index_manifests: dict[str, Any] = {}
    embedding_dimension = len(next(iter(chunk_evidence.values())).embedding) if chunk_evidence else 0

    # Shared authority-aware Vector candidate store over the frozen chunk
    # embeddings (eligibility applied BEFORE ranking + LIMIT).
    if persisted:
        from ingestion_bench.hybrid_retrieval_benchmark.vector_candidate_store import PgVectorCandidateStore
        vector_candidate_store = PgVectorCandidateStore(embedding_dimension=embedding_dimension, table_name="edib_stage7b2_vector_candidate")
        vector_candidate_store.load(list(chunk_evidence.values()))
    else:
        vector_candidate_store = InMemoryVectorCandidateStore(list(chunk_evidence.values()))

    for name, proj in projections.items():
        gl_start = time.perf_counter()
        if persisted:
            from ingestion_bench.hybrid_retrieval_benchmark.graph_store_pg import PgGraphStore
            from ingestion_bench.hybrid_retrieval_benchmark.edge_index import PgEdgeSemanticIndex
            store = PgGraphStore(table_prefix=f"edib_stage7b2_graph_{name}")
            store.save(list(proj.nodes.values()), proj.edge_assertions, proj.extraction_run)
            records, manifest = build_edge_embedding_records(proj.edge_assertions, proj.nodes, embedding_provider)
            edge_index = PgEdgeSemanticIndex(embedding_dimension=embedding_dimension, table_name=f"edib_stage7b2_edge_{name}")
            edge_index.load(records)
        else:
            store = InMemoryGraphStore()
            store.save(list(proj.nodes.values()), proj.edge_assertions, proj.extraction_run)
            records, manifest = build_edge_embedding_records(proj.edge_assertions, proj.nodes, embedding_provider)
            edge_index = InMemoryEdgeSemanticIndex(records)
        graph_load_latency[name] = time.perf_counter() - gl_start
        conditions[name] = (proj, store)
        edge_indexes[name] = edge_index
        edge_index_manifests[name] = json.loads(manifest.model_dump_json())

    # --- section 5: the real-graph G is the frozen Stage 7B.1 result, loaded ---
    frozen_g_hits, committed_g_model = _load_frozen_7b1_graph_results()
    frozen_g_fused: dict[str, list[FusedChunk]] = {}
    frozen_g_ranked: dict[str, list[RankedChunk]] = {}
    for qid, hits in frozen_g_hits.items():
        fused_g, ranked_g = _frozen_graph_fused(hits)
        frozen_g_fused[qid] = fused_g
        frozen_g_ranked[qid] = ranked_g
    embedding_model_matches = embedding_provider.model_identity == committed_g_model
    frozen_g_mismatches: list[str] = []  # populated during the run when equality is asserted

    # --- 2. authority setup (once, corpus-level) ---
    service = RevisionAuthorityService(repository)
    revision_by_symbol = {s: {"source_document_sha256": fx.source_document_sha256, "version_label": fx.version_label, "revision_number": fx.revision_number} for s, fx in fixtures.items()}
    symbol_to_id: dict[str, str] = {}
    id_to_symbol: dict[str, str] = {}
    rc: list = []
    tc: list = []
    for document in contract["authority_setup"]["documents"]:
        _run_registry_setup(repository, service, document, revision_by_symbol, symbol_to_id, id_to_symbol, rc, tc)
    corpus_docs = sorted({fx.logical_document_id for fx in fixtures.values()})

    def _requested(question: dict) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for sym in question.get("requested_revision_symbols", []):
            out.setdefault(fixtures[sym].logical_document_id, []).append(symbol_to_id[sym])
        return out

    # --- 3. per-question, all modes, both conditions ---
    mode_results: list[ModeResult] = []
    for question in contract["questions"]:
        qid = question["question_id"]
        top_k = question["top_k"]
        as_of = date.fromisoformat(question["as_of_date"])
        requested = _requested(question)
        _qe_start = time.perf_counter()
        query_vector = embedding_provider.embed([question["query"]]).vectors[0]
        query_embedding_latency = time.perf_counter() - _qe_start

        resolutions, merged_labels, eligible_union, integrity_errors, snapshot_hash, resolver_latency = _resolve_corpus(
            service=service, corpus_logical_document_ids=corpus_docs, query_intent=question["query_intent"], as_of_date=as_of,
            requested_revision_ids_by_document=requested,
        )
        bundle = ResolutionBundle(resolutions=resolutions, eligible_union=sorted(set(eligible_union)), snapshot_hash=snapshot_hash,
                                  integrity_errors=integrity_errors, failed_closed=bool(integrity_errors),
                                  requested_by_document=requested, query_intent=question["query_intent"], as_of_date=as_of)

        v_hits = vector_by_question[qid]["result"]["hits"]
        v_fused = _vector_fused(v_hits)
        v_ranked = _ranked_from_hits(v_hits)

        def _record(mode: str, cond: str, fused: list[FusedChunk], latency: float, extra: dict) -> None:
            score = score_mode(question, fused, bundle, evidence, id_to_symbol, latency)
            mode_results.append(ModeResult(
                question_id=qid, question_type=question["question_type"], query_intent=question["query_intent"], top_k=top_k,
                mode=mode, graph_condition=cond,
                required_fact_coverage_at_k=score.required_fact_coverage_at_k, all_required_facts_retrieved_at_k=score.all_required_facts_retrieved_at_k,
                complete_chain_represented=score.complete_chain_represented, mrr=score.mrr, ndcg_at_k=score.ndcg_at_k,
                forbidden_fact_hit_ids=score.forbidden_fact_hit_ids, authority_leakage_count=score.authority_leakage_count,
                evidence_document_diversity=score.evidence_document_diversity, outcome=score.outcome, authority_correct=score.authority_correct,
                final_chunk_ids=score.hit_chunk_ids, total_latency_seconds=latency, fused_chunks=fused,
                **{k: extra[k] for k in extra},
            ))

        # V (common) -- report the FROZEN Stage 7B.0 Vector total latency
        # (resolver + real vector search), not a resolver-only recompute,
        # so the H2/Vector latency-gate ratio is honest. V is frozen: no
        # query-time embedding is done in this run.
        v_latency = vector_by_question[qid]["total_latency_seconds"]
        _record("V", "common", v_fused, v_latency, {"query_embedding_calls": 0, "query_time_embedding_calls": 0})

        for cond, (proj, store) in conditions.items():
            eligible_edges = store.edge_assertions_for_revisions(bundle.eligible_union)
            edge_index = edge_indexes[cond]
            gl = graph_load_latency[cond]

            # G -- real graph loads the FROZEN Stage 7B.1 result directly
            # (section 5); perfect graph is computed. When the run's model
            # matches the committed 7B.1 model, a rerun must reproduce the
            # frozen ranked (chunk_id, rank, score) tuples EXACTLY.
            if cond == "real_graph":
                g_fused, g_ranked = frozen_g_fused[qid], frozen_g_ranked[qid]
                g_qe_calls = 0
                g_traversal_latency = 0.0
                if embedding_model_matches:
                    _gr = time.perf_counter()
                    rerun = graph_search(
                        service=service, store=store, projection=proj, corpus_logical_document_ids=corpus_docs, query=question["query"],
                        query_intent=question["query_intent"], as_of_date=as_of, requested_revision_ids_by_document=requested,
                        query_vector=query_vector, top_k=top_k, max_hops=params["max_hop_depth"],
                    )
                    g_traversal_latency = time.perf_counter() - _gr
                    _rf, rerun_ranked = _graph_fused(rerun, chunk_evidence)
                    # The RANKING (chunk_id + rank) must match the frozen
                    # result exactly; scores are compared within a tight
                    # numeric tolerance because a live re-embedding is not
                    # bit-reproducible vs the committed float scores.
                    same_ranking = [(r.chunk_id, r.rank) for r in rerun_ranked] == [(r.chunk_id, r.rank) for r in g_ranked]
                    scores_close = len(rerun_ranked) == len(g_ranked) and all(
                        abs(a.score - b.score) <= 1e-6 for a, b in zip(rerun_ranked, g_ranked)
                    )
                    if not (same_ranking and scores_close):
                        frozen_g_mismatches.append(qid)
                    g_qe_calls = 1
            else:
                _gr = time.perf_counter()
                g_result = graph_search(
                    service=service, store=store, projection=proj, corpus_logical_document_ids=corpus_docs, query=question["query"],
                    query_intent=question["query_intent"], as_of_date=as_of, requested_revision_ids_by_document=requested,
                    query_vector=query_vector, top_k=top_k, max_hops=params["max_hop_depth"],
                )
                g_traversal_latency = time.perf_counter() - _gr
                g_fused, g_ranked = _graph_fused(g_result, chunk_evidence)
                g_qe_calls = 1
            _record("G", cond, g_fused, resolver_latency + query_embedding_latency * g_qe_calls + g_traversal_latency, {
                "query_embedding_latency_seconds": query_embedding_latency * g_qe_calls, "query_embedding_calls": g_qe_calls,
                "query_time_embedding_calls": g_qe_calls, "authority_resolution_latency_seconds": resolver_latency,
                "graph_load_latency_seconds": gl, "traversal_latency_seconds": g_traversal_latency,
            })

            # H0 -- RRF(V, simple-G)
            _f = time.perf_counter()
            h0 = rrf_fuse(vector_ranked=v_ranked, graph_ranked=g_ranked, rrf_constant=params["rrf_constant"], top_k=top_k,
                          chunk_evidence=chunk_evidence, authority_labels=merged_labels, graph_chunk_support={})
            h0_fusion_latency = time.perf_counter() - _f
            m0 = _hybrid_metrics(_EMPTY_SEED_RESULT, GraphSideResult([], [], [], {}, 0, 0, 0.0), h0, v_ranked, g_ranked)
            m0.update({"query_embedding_latency_seconds": query_embedding_latency, "query_embedding_calls": 1, "query_time_embedding_calls": 1,
                       "authority_resolution_latency_seconds": resolver_latency, "graph_load_latency_seconds": gl, "fusion_latency_seconds": h0_fusion_latency})
            _record("H0", cond, h0, resolver_latency + query_embedding_latency + h0_fusion_latency, m0)

            # expanded seeds for H1/H2 (RRF-capped supplemental seeds)
            seed_start = time.perf_counter()
            seed_result = collect_hybrid_seeds(
                query=question["query"], query_vector=query_vector, nodes=list(proj.nodes.values()), node_by_id=proj.nodes,
                eligible_revision_ids=bundle.eligible_union, eligible_edges=eligible_edges,
                vector_candidate_store=vector_candidate_store, edge_index=edge_index, top_k=top_k,
                vector_candidate_multiplier=params["vector_candidate_multiplier"], max_vector_seed_chunks=params["max_vector_seed_chunks"],
                semantic_edge_candidate_count=params["semantic_edge_candidate_count"], max_supplemental_seed_nodes=params["max_supplemental_seed_nodes"],
                supplemental_seed_saturation_threshold=params["supplemental_seed_saturation_threshold"], rrf_constant=params["rrf_constant"],
            )
            seed_latency = time.perf_counter() - seed_start
            seeds = seed_result.seeds

            # H1 -- RRF(V, hop-ranked expanded-seed graph)
            h1_side = hop_ranked_graph_evidence(seeds=seeds, eligible_edges=eligible_edges, chunk_evidence=chunk_evidence, query_vector=query_vector, max_hops=params["max_hop_depth"])
            h1_ranked = h1_side.ranked_chunks
            _f = time.perf_counter()
            h1 = rrf_fuse(vector_ranked=v_ranked, graph_ranked=h1_ranked, rrf_constant=params["rrf_constant"], top_k=top_k,
                          chunk_evidence=chunk_evidence, authority_labels=merged_labels, graph_chunk_support=h1_side.chunk_support)
            h1_fusion_latency = time.perf_counter() - _f
            m1 = _hybrid_metrics(seed_result, h1_side, h1, v_ranked, h1_ranked)
            m1.update({"query_embedding_latency_seconds": query_embedding_latency, "query_embedding_calls": 1, "path_embedding_calls": 0,
                       "query_time_embedding_calls": 1, "authority_resolution_latency_seconds": resolver_latency, "graph_load_latency_seconds": gl,
                       "traversal_latency_seconds": h1_side.latency_seconds, "fusion_latency_seconds": h1_fusion_latency})
            _record("H1", cond, h1, resolver_latency + query_embedding_latency + seed_latency + h1_side.latency_seconds + h1_fusion_latency, m1)

            # H2 -- RRF(V, semantic-path-ranked expanded-seed graph)
            h2_side = semantic_path_ranked_graph_evidence(
                seeds=seeds, eligible_edges=eligible_edges, node_by_id=proj.nodes, chunk_evidence=chunk_evidence, query_vector=query_vector,
                embedding_provider=embedding_provider, max_hops=params["max_hop_depth"], max_candidate_paths=params["max_candidate_paths"],
                path_enumeration_safety_ceiling=params["path_enumeration_safety_ceiling"],
            )
            h2_ranked = h2_side.ranked_chunks
            _f = time.perf_counter()
            h2 = rrf_fuse(vector_ranked=v_ranked, graph_ranked=h2_ranked, rrf_constant=params["rrf_constant"], top_k=top_k,
                          chunk_evidence=chunk_evidence, authority_labels=merged_labels, graph_chunk_support=h2_side.chunk_support)
            h2_fusion_latency = time.perf_counter() - _f
            m2 = _hybrid_metrics(seed_result, h2_side, h2, v_ranked, h2_ranked)
            m2.update({"query_embedding_latency_seconds": query_embedding_latency, "query_embedding_calls": 1,
                       "path_embedding_calls": h2_side.embedding_calls, "query_time_embedding_calls": 1 + h2_side.embedding_calls,
                       "authority_resolution_latency_seconds": resolver_latency, "graph_load_latency_seconds": gl,
                       "traversal_latency_seconds": h2_side.enumeration_latency_seconds,
                       "path_embedding_latency_seconds": h2_side.path_embedding_latency_seconds, "fusion_latency_seconds": h2_fusion_latency})
            _record("H2", cond, h2, resolver_latency + query_embedding_latency + seed_latency + h2_side.latency_seconds + h2_fusion_latency, m2)

    # --- 4. section 5 frozen-G verification ---
    frozen_g_verification = FrozenGVerification(
        committed_embedding_model=committed_g_model, run_embedding_model=embedding_provider.model_identity,
        embedding_model_matches=embedding_model_matches, g_loaded_directly_from_frozen_7b1=True,
        rerun_equality_asserted=embedding_model_matches, rerun_equality_holds=(len(frozen_g_mismatches) == 0),
        per_question_frozen_g_chunk_counts={qid: len(hits) for qid, hits in frozen_g_hits.items()},
        mismatched_question_ids=sorted(set(frozen_g_mismatches)),
    )
    if embedding_model_matches and frozen_g_mismatches:
        raise InputVerificationError(
            f"real-graph G rerun diverged from the frozen Stage 7B.1 result for: {sorted(set(frozen_g_mismatches))}"
        )

    # --- 5. decision gates ---
    real_gate, perfect_gate, real_improves_any, perfect_improves_any = _gate_inputs(mode_results, vector_by_question)
    gate_id, decision, rationale = decide(real_gate, perfect_gate, real_improves_any, perfect_improves_any)

    return ProbeRunResult(
        contract_version=probe_config["contract_version"], generated_at=datetime.now(timezone.utc).isoformat(),
        embedding_model=embedding_provider.model_identity, candidate_parameters=params, input_verification=input_verification,
        frozen_g_verification=frozen_g_verification, edge_index_manifests=edge_index_manifests, mode_results=mode_results,
        decision_gate=gate_id, decision=decision, decision_rationale=rationale, real_gate_inputs=json.loads(real_gate.model_dump_json()),
        perfect_gate_inputs=json.loads(perfect_gate.model_dump_json()),
    )


def _gate_inputs(mode_results: list[ModeResult], vector_by_question: dict) -> tuple[GateInputs, GateInputs, bool, bool]:
    by_key = {(m.question_id, m.mode, m.graph_condition): m for m in mode_results}
    question_ids = [q for q in {m.question_id for m in mode_results}]

    def _vector_cov(qid: str) -> float:
        return vector_by_question[qid]["required_fact_coverage_at_k"]

    def _vector_complete(qid: str) -> bool:
        return vector_by_question[qid]["complete_chain_represented"]

    def _build(cond: str) -> tuple[GateInputs, bool]:
        target_improvements = 0
        improves_any_target = False
        regressions: list[str] = []
        q12_regressed = False
        leakage = 0
        latencies_h2 = []
        latencies_v = []
        for qid in question_ids:
            h2 = by_key[(qid, "H2", cond)]
            v = by_key[(qid, "V", "common")]
            leakage += h2.authority_leakage_count
            latencies_h2.append(h2.total_latency_seconds)
            latencies_v.append(v.total_latency_seconds)
            if h2.required_fact_coverage_at_k < _vector_cov(qid) - 1e-9:
                regressions.append(qid)
            if qid in TARGET_QUESTIONS:
                if h2.complete_chain_represented and not _vector_complete(qid):
                    target_improvements += 1
                if h2.required_fact_coverage_at_k > _vector_cov(qid) + 1e-9:
                    improves_any_target = True
            if qid == Q12 and h2.required_fact_coverage_at_k < _vector_cov(qid) - 1e-9:
                q12_regressed = True
        mean_ratio = (sum(latencies_h2) / len(latencies_h2)) / (sum(latencies_v) / len(latencies_v)) if latencies_v and sum(latencies_v) > 0 else 1.0
        return GateInputs(
            target_complete_chain_improvements=target_improvements, regressions_vs_vector=sorted(regressions), q12_regressed=q12_regressed,
            total_authority_leakage=leakage, same_final_k=True, uses_query_time_llm=False, mean_latency_ratio_vs_vector=mean_ratio,
        ), improves_any_target

    real_gate, real_improves = _build("real_graph")
    perfect_gate, perfect_improves = _build("perfect_graph")
    return real_gate, perfect_gate, real_improves, perfect_improves
