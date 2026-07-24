"""Stage 6B: tests for the minimal, deterministic retrieval benchmark
contract (`contracts/retrieval_benchmark_v1.json`) and its resolver.

Proves: exactly 12 questions exist; every required/forbidden fact id is
real (exists in the actual Stage 6A gold evidence-alignment catalog);
question ids are unique; the difficulty distribution is exactly
4/3/2/2/1; required and forbidden facts never overlap; fact-to-chunk
resolution is deterministic; a fact missing from ingestion is never
confused with a retrieval miss (no retrieval layer exists yet); and this
package introduces no network/LLM/vector-database/Graph-RAG/wiki/ADK
dependency of any kind.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ingestion_bench.evaluation.model import EvidenceAlignment
from ingestion_bench.retrieval_benchmark.model import (
    REQUIRED_DIFFICULTY_COUNTS,
    REQUIRED_QUESTION_COUNT,
    BenchmarkQuestion,
    RetrievalBenchmarkContract,
    load_contract,
)
from ingestion_bench.retrieval_benchmark.resolver import (
    FactResolutionStatus,
    resolve_fact,
    resolve_question_facts,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "contracts" / "retrieval_benchmark_v1.json"
EVIDENCE_CATALOG_PATH = REPO_ROOT / "artifacts" / "stage6a" / "evidence_alignment.json"


def _load_real_catalog() -> list[EvidenceAlignment]:
    if not EVIDENCE_CATALOG_PATH.exists():
        pytest.skip("artifacts/stage6a/evidence_alignment.json not present -- run scripts/run_stage6a_evaluation.py first")
    raw = json.loads(EVIDENCE_CATALOG_PATH.read_text(encoding="utf-8"))
    return [EvidenceAlignment.model_validate(e) for e in raw]


def _catalog_for_fixture(catalog: list[EvidenceAlignment], fixture: str) -> list[EvidenceAlignment]:
    return [a for a in catalog if a.fixture == fixture]


# --- contract-shape assertions (also enforced by model validators; re-checked explicitly here) ---


def test_contract_has_exactly_twelve_questions():
    contract = load_contract(CONTRACT_PATH)
    assert REQUIRED_QUESTION_COUNT == 12
    assert len(contract.questions) == 12


def test_question_ids_are_unique():
    contract = load_contract(CONTRACT_PATH)
    ids = [q.question_id for q in contract.questions]
    assert len(ids) == len(set(ids))


def test_difficulty_distribution_matches_required_counts():
    contract = load_contract(CONTRACT_PATH)
    assert REQUIRED_DIFFICULTY_COUNTS == {
        "direct": 4,
        "distractor_sensitive": 3,
        "relational": 2,
        "multi_hop": 2,
        "consolidation": 1,
    }
    counts: dict[str, int] = {}
    for q in contract.questions:
        counts[q.difficulty] = counts.get(q.difficulty, 0) + 1
    assert counts == REQUIRED_DIFFICULTY_COUNTS


def test_required_and_forbidden_facts_never_overlap():
    contract = load_contract(CONTRACT_PATH)
    checked = 0
    for q in contract.questions:
        checked += 1
        assert not (set(q.required_fact_ids) & set(q.forbidden_fact_ids)), q.question_id
    assert checked == 12


def test_every_question_has_a_nonempty_rubric_and_at_least_one_required_fact():
    contract = load_contract(CONTRACT_PATH)
    for q in contract.questions:
        assert q.required_fact_ids, q.question_id
        assert q.answer_rubric.strip(), q.question_id
        assert isinstance(q.citation_required, bool)


def test_model_rejects_a_thirteenth_question():
    contract = load_contract(CONTRACT_PATH)
    extra = contract.questions[0].model_copy(update={"question_id": "Q_EXTRA_999"})
    with pytest.raises(ValidationError, match="exactly 12"):
        RetrievalBenchmarkContract(contract_version="1.0.0", questions=[*contract.questions, extra])


def test_model_rejects_duplicate_question_ids():
    contract = load_contract(CONTRACT_PATH)
    duplicated = contract.questions[0].model_copy(update={"question_id": contract.questions[1].question_id})
    questions = [duplicated, *contract.questions[1:]]
    with pytest.raises(ValidationError, match="duplicate question_id"):
        RetrievalBenchmarkContract(contract_version="1.0.0", questions=questions)


def test_model_rejects_wrong_difficulty_distribution():
    contract = load_contract(CONTRACT_PATH)
    # Retag one "direct" question as "relational" -- breaks the required 4/2 split.
    mutated = [q.model_copy(update={"difficulty": "relational"}) if q.question_id == "Q_DIRECT_001" else q for q in contract.questions]
    with pytest.raises(ValidationError):
        RetrievalBenchmarkContract(contract_version="1.0.0", questions=mutated)


def test_model_rejects_required_forbidden_overlap():
    with pytest.raises(ValidationError, match="overlap"):
        BenchmarkQuestion(
            question_id="Q_BAD", question="x", difficulty="direct",
            required_fact_ids=["P_001"], forbidden_fact_ids=["P_001"],
            citation_required=True, answer_rubric="r",
        )


# --- real-catalog integration: every referenced fact id must actually exist ---


def test_every_required_and_forbidden_fact_id_exists_in_the_real_stage6a_catalog():
    catalog = _load_real_catalog()
    real_fact_ids = {a.fact_id for a in catalog}
    contract = load_contract(CONTRACT_PATH)
    checked = 0
    for q in contract.questions:
        for fact_id in (*q.required_fact_ids, *q.forbidden_fact_ids):
            checked += 1
            assert fact_id in real_fact_ids, f"{q.question_id}: fact_id {fact_id!r} does not exist in the real Stage 6A catalog"
    assert checked > 0


# --- resolver: the four resolution states, proven against real data ---


def test_resolver_available_with_chunks_on_real_matched_fact():
    catalog = _load_real_catalog()
    pdf_catalog = _catalog_for_fixture(catalog, "parity/PARITY_001.pdf")
    resolved = resolve_question_facts(["P_001"], pdf_catalog)
    assert resolved["P_001"].status == "available_with_chunks"
    assert resolved["P_001"].matched_chunk_ids


def test_resolver_missing_from_ingestion_on_real_missing_fact():
    """ID_004_occ_2 (the identifier occurrence tied to VF_NODE_003, the
    picture's own OCR content) is a REAL, measured miss for DOCX -- see
    docs/POC_DECISION_LOG.md D-047."""
    catalog = _load_real_catalog()
    docx_catalog = _catalog_for_fixture(catalog, "parity/PARITY_001.docx")
    resolved = resolve_question_facts(["ID_004_occ_2"], docx_catalog)
    assert resolved["ID_004_occ_2"].status == "missing_from_ingestion"
    assert resolved["ID_004_occ_2"].matched_chunk_ids == []


def test_resolver_not_applicable_on_real_path_a_visual_fact():
    """CF_001 (a chart visual fact) is structurally not_applicable to
    path A, which has no VisionEnricher -- see D-041/D-048."""
    catalog = _load_real_catalog()
    chart_catalog = _catalog_for_fixture(catalog, "stress/STRESS_CHART_001.pdf")
    resolved = resolve_question_facts(["CF_001"], chart_catalog)
    assert resolved["CF_001"].status == "not_applicable"
    assert resolved["CF_001"].matched_chunk_ids == []


def test_resolver_ingested_without_chunks_on_a_hand_built_case():
    """No real fixture in the current baseline happens to have a
    matched/partial fact with zero matched_chunk_ids (chunk_availability
    is 100% across the board, per the frozen Stage 6A scorecard) -- this
    state is proven with a hand-built EvidenceAlignment, the same pattern
    used throughout this project's Stage 6A test suite for states that
    are real and must be handled correctly but do not currently occur in
    the measured baseline."""
    alignment = EvidenceAlignment(
        fact_id="P_999", fixture="parity/PARITY_001.pdf", fact_type="paragraph",
        match_status="matched", derivation="source_derived",
        matched_canonical_element_ids=["p999_id"], matched_chunk_ids=[],
    )
    resolved = resolve_question_facts(["P_999"], [alignment])
    assert resolved["P_999"].status == "ingested_without_chunks"
    assert resolved["P_999"].matched_chunk_ids == []


def test_resolve_fact_raises_on_unknown_fact_id():
    catalog = _load_real_catalog()
    pdf_catalog = _catalog_for_fixture(catalog, "parity/PARITY_001.pdf")
    with pytest.raises(KeyError):
        resolve_question_facts(["NOT_A_REAL_FACT_ID"], pdf_catalog)


def test_resolve_question_facts_raises_on_mixed_fixture_catalog():
    """The resolver requires a catalog already scoped to ONE ingestion
    lane -- mixing two fixtures (which legitimately share identical
    fact_ids, e.g. "P_001" in both PDF and DOCX) must fail loudly, never
    silently pick one arbitrarily."""
    catalog = _load_real_catalog()
    mixed = _catalog_for_fixture(catalog, "parity/PARITY_001.pdf") + _catalog_for_fixture(catalog, "parity/PARITY_001.docx")
    with pytest.raises(ValueError, match="duplicate fact_id"):
        resolve_question_facts(["P_001"], mixed)


def test_fact_to_chunk_resolution_is_deterministic_across_repeated_calls():
    catalog = _load_real_catalog()
    pdf_catalog = _catalog_for_fixture(catalog, "parity/PARITY_001.pdf")
    contract = load_contract(CONTRACT_PATH)
    q = next(q for q in contract.questions if q.question_id == "Q_CONSOLIDATION_001")
    fact_ids = [*q.required_fact_ids, *q.forbidden_fact_ids]

    results = [resolve_question_facts(fact_ids, pdf_catalog) for _ in range(5)]
    first = results[0]
    for other in results[1:]:
        assert other.keys() == first.keys()
        for fact_id in first:
            assert other[fact_id].status == first[fact_id].status
            assert other[fact_id].matched_chunk_ids == first[fact_id].matched_chunk_ids
    # dict insertion order must also match fact_ids order (never re-sorted
    # or reordered by the resolver itself).
    assert list(first.keys()) == fact_ids


def test_resolution_order_matches_input_order_not_catalog_order():
    catalog = _load_real_catalog()
    pdf_catalog = _catalog_for_fixture(catalog, "parity/PARITY_001.pdf")
    # Deliberately reversed relative to the catalog's own order.
    reversed_ids = ["T_001_r0c1", "T_001_r0c0", "P_005", "P_001"]
    resolved = resolve_question_facts(reversed_ids, pdf_catalog)
    assert list(resolved.keys()) == reversed_ids


# --- missing-ingestion facts must never be confused with retrieval misses ---


def test_missing_ingestion_facts_are_not_incorrectly_treated_as_retrieval_misses():
    """No retrieval layer exists yet (Stage 7A+) -- every resolver status
    describes INGESTION-side availability only. 'missing_from_ingestion'
    must be its own explicit, correctly-populated state, never silently
    dropped, never raising, and never expressed using retrieval
    vocabulary."""
    for status in FactResolutionStatus.__args__:
        assert "retriev" not in status.lower(), f"resolver vocabulary must never describe retrieval outcomes: {status!r}"

    catalog = _load_real_catalog()
    docx_catalog = _catalog_for_fixture(catalog, "parity/PARITY_001.docx")
    catalog_index = {a.fact_id: a for a in docx_catalog}
    resolution = resolve_fact("ID_004_occ_2", catalog_index)
    assert resolution.status == "missing_from_ingestion"
    # A genuinely missing-from-ingestion fact must be represented
    # explicitly (a real FactResolution object), not raise, not be
    # silently omitted, and must carry zero chunk ids (there is nothing
    # for any future retrieval layer to have found).
    assert resolution.matched_chunk_ids == []


def test_every_real_fact_id_across_every_fixture_resolves_to_one_known_state():
    """Sanity check that the four resolver states are mutually exclusive
    and exhaustive for every real fact_id across every real fixture in
    the current baseline -- every fact_id resolves to exactly one of the
    four known states, never an unrecognized fifth value."""
    catalog = _load_real_catalog()
    fixtures = sorted({a.fixture for a in catalog})
    checked = 0
    for fixture in fixtures:
        fixture_catalog = _catalog_for_fixture(catalog, fixture)
        fact_ids = [a.fact_id for a in fixture_catalog]
        resolved = resolve_question_facts(fact_ids, fixture_catalog)
        for fact_id in fact_ids:
            checked += 1
            assert resolved[fact_id].status in FactResolutionStatus.__args__
    assert checked > 0


# --- isolation: no forbidden dependency of any kind ---


def _source_has_import(path: Path, module_substring: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(module_substring in alias.name for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.module:
            if module_substring in node.module:
                return True
    return False


def test_retrieval_benchmark_package_has_no_forbidden_dependencies():
    """No network, LLM, vector-database, Graph RAG, wiki, ADK, embedding,
    or Docling dependency of any kind -- this stage defines a CONTRACT
    only."""
    src_root = REPO_ROOT / "src" / "ingestion_bench" / "retrieval_benchmark"
    forbidden = (
        "openai", "requests", "httpx", "urllib", "socket", "aiohttp",
        "psycopg", "pgvector", "sentence_transformers", "torch", "docling",
        "networkx", "neo4j", "graphrag", "wiki", "adk",
    )
    checked = 0
    for path in src_root.rglob("*.py"):
        checked += 1
        for module in forbidden:
            assert not _source_has_import(path, module), f"{path} imports forbidden module containing {module!r}"
    assert checked > 0


def test_retrieval_benchmark_package_only_depends_on_pydantic_and_evaluation_model():
    """The only cross-package dependency is the read-only Stage 6A
    EvidenceAlignment model -- never chunking, adapters, or canonical
    directly, and never a new manifest reader (D-042 reserves that to
    ingestion_bench.evaluation alone)."""
    src_root = REPO_ROOT / "src" / "ingestion_bench" / "retrieval_benchmark"
    for path in src_root.rglob("*.py"):
        assert not _source_has_import(path, "ingestion_bench.chunking"), path
        assert not _source_has_import(path, "ingestion_bench.adapters"), path
        assert not _source_has_import(path, "ingestion_bench.canonical"), path


def test_retrieval_benchmark_package_never_reads_reference_manifest_directly():
    """Stage 6A's evaluation package is the ONLY package allowed to read
    reference_manifest.json (D-042, enforced by
    tests/test_stage6a_integration.py). This package must build its
    contract from the frozen JSON file + the Stage 6A catalog only, never
    from a second, independent manifest reader."""
    src_root = REPO_ROOT / "src" / "ingestion_bench" / "retrieval_benchmark"
    for path in src_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "reference_manifest" not in source, path


def test_evaluation_package_was_not_modified_by_this_stage():
    """Stage 6B must not modify src/ingestion_bench/evaluation/ -- proven
    here by confirming that package still contains no reference to this
    stage's own contract file or package name (a weak but real guard
    against accidental cross-editing)."""
    src_root = REPO_ROOT / "src" / "ingestion_bench" / "evaluation"
    for path in src_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "retrieval_benchmark" not in source, path
        assert "retrieval_benchmark_v1" not in source, path
