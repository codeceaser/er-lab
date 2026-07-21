"""Compare vector-only retrieval against graph-enriched retrieval across a
small evaluation suite of questions, all aimed at the same piece of transitive
evidence: BCP Procedure P-100 (found in DOC_003), reachable from CRA-176046
only via CRA-176046 -> O-22 -> C-77 -> P-100.

Prints a report to the console and also writes the same report as Markdown to
reports/compare_retrieval_report.md (overwritten on every run).

Run: python src/compare_retrieval.py
"""

from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from graph_enriched_retriever import format_path, retrieve as graph_retrieve
from vector_retriever import retrieve as vector_retrieve

console = Console()

REPORT_PATH = Path(__file__).resolve().parent.parent / "reports" / "compare_retrieval_report.md"

# The seed corpus only has 4 chunks total, so the module-wide VECTOR_TOP_K (5)
# would always return every chunk regardless of query, making a vector-only
# "miss" structurally impossible. Use a tighter top_k here so vector-only
# retrieval actually has to rank and can plausibly miss the target chunk.
EVAL_VECTOR_TOP_K = 2

QUESTIONS = [
    {
        "id": "Q1",
        "text": "What is the BCP impact of CRA-176046 going down?",
    },
    {
        "id": "Q2",
        "text": (
            "If application 176046 is unavailable, what downstream resilience "
            "requirement should be reviewed?"
        ),
    },
    {
        "id": "Q3",
        "text": (
            "If CRA-176046 fails, which recovery procedure becomes relevant "
            "through its regulatory/control dependency chain?"
        ),
    },
    {
        "id": "Q4",
        "text": "For an outage of application 176046, trace the related obligation, control, and procedure.",
    },
]

# The transitive target this whole suite is probing for: BCP Procedure P-100,
# defined in the BCP Policy document (DOC_003), reachable from CRA-176046 only
# through a 4-hop chain (CRA-176046 -> O-22 -> C-77 -> P-100).
TARGET_ENTITY_IDS = {"PROC_P100", "DOC_BCP_POLICY"}
TARGET_DOCUMENT_ID = "DOC_003"
TARGET_MARKER = "P-100"

# Markdown lines accumulated for the current run; reset at the start of main().
_md_lines: list[str] = []


def md(line: str = "") -> None:
    _md_lines.append(line)


def md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def vector_found_target(vector_chunks: list[dict]) -> bool:
    return any(
        chunk["document_id"] == TARGET_DOCUMENT_ID or TARGET_MARKER in chunk["chunk_text"]
        for chunk in vector_chunks
    )


def graph_found_target(graph_result: dict) -> bool:
    if TARGET_ENTITY_IDS & graph_result["seed_entity_ids"]:
        return True
    for path in graph_result["discovered_paths"]:
        for step in path:
            if step["to_entity_id"] in TARGET_ENTITY_IDS:
                return True
    for edge_id in graph_result["discovered_edge_ids"]:
        for evidence in graph_result["evidence_by_edge"].get(edge_id, []):
            if evidence["document_id"] == TARGET_DOCUMENT_ID:
                return True
    return False


def graph_lineage_found_target(graph_result: dict) -> bool:
    """True only if the target was reached by walking an edge during query-time
    expansion (as opposed to being a direct graph_artifacts seed match)."""
    for path in graph_result["discovered_paths"]:
        for step in path:
            if step["to_entity_id"] in TARGET_ENTITY_IDS:
                return True
    return False


def evaluate(vector_hit: bool, graph_hit: bool) -> tuple[str, str]:
    """Return (PASS/FAIL, reason). PASS means graph-enriched found the target
    transitive evidence while vector-only missed it -- the gap this POC exists
    to demonstrate."""
    if graph_hit and not vector_hit:
        return "PASS", "graph-enriched found it, vector-only missed it"
    if graph_hit and vector_hit:
        return "FAIL", "vector-only also found it (no gap demonstrated)"
    if not graph_hit:
        return "FAIL", "graph-enriched missed it"
    return "FAIL", "neither retriever found it"


def print_vector_only_section(vector_chunks: list[dict]) -> None:
    table = Table(title="1. Vector-only retrieved chunks")
    table.add_column("Score", justify="right")
    table.add_column("Document")
    table.add_column("Chunk text")
    for chunk in vector_chunks:
        table.add_row(f"{chunk['score']:.4f}", chunk["title"], chunk["chunk_text"])
    console.print(table)

    md("### 1. Vector-only retrieved chunks")
    md()
    md("| Score | Document | Chunk text |")
    md("|---|---|---|")
    for chunk in vector_chunks:
        md(f"| {chunk['score']:.4f} | {md_escape(chunk['title'])} | {md_escape(chunk['chunk_text'])} |")
    md()


def print_artifact_matches_section(artifact_matches: list[dict]) -> None:
    table = Table(title="3. Graph artifact matches (seeds)")
    table.add_column("Score", justify="right")
    table.add_column("Type")
    table.add_column("Artifact text")
    for row in artifact_matches:
        table.add_row(f"{row['score']:.4f}", row["artifact_type"], row["artifact_text"])
    console.print(table)

    md("### 3. Graph artifact matches (seeds)")
    md()
    md("| Score | Type | Artifact text |")
    md("|---|---|---|")
    for row in artifact_matches:
        md(f"| {row['score']:.4f} | {row['artifact_type']} | {md_escape(row['artifact_text'])} |")
    md()


def print_lineage_paths_section(graph_result: dict) -> None:
    console.print("[bold]4. Discovered graph lineage paths (via query-time expansion)[/bold]")
    md("### 4. Discovered graph lineage paths (via query-time expansion)")
    md()
    if not graph_result["discovered_paths"]:
        console.print("  (none discovered)")
        md("(none discovered)")
        md()
        return
    for path in graph_result["discovered_paths"]:
        formatted = format_path(path, graph_result["entity_names"])
        console.print(f"  - {formatted}")
        md(f"- {formatted}")
    md()


def fmt_hit(hit: bool) -> str:
    return "[bold green]YES[/bold green]" if hit else "[bold red]NO[/bold red]"


def run_question(question: dict) -> dict:
    console.print(Panel(f"{question['id']}: {question['text']}", style="bold cyan"))
    md(f"## {question['id']}: {question['text']}")
    md()

    vector_chunks = vector_retrieve(question["text"], top_k=EVAL_VECTOR_TOP_K)
    graph_result = graph_retrieve(question["text"], vector_top_k=EVAL_VECTOR_TOP_K)

    print_vector_only_section(vector_chunks)

    vector_hit = vector_found_target(vector_chunks)
    console.print(f"\n2. Did vector-only find PROC_P100 / DOC_003?  {fmt_hit(vector_hit)}\n")
    md(f"**2. Did vector-only find PROC_P100 / DOC_003?** {'YES' if vector_hit else 'NO'}")
    md()

    print_artifact_matches_section(graph_result["artifact_matches"])
    console.print()
    print_lineage_paths_section(graph_result)

    graph_hit = graph_found_target(graph_result)
    lineage_hit = graph_lineage_found_target(graph_result)
    console.print(f"\n5. Did graph-enriched find PROC_P100 / DOC_003?  {fmt_hit(graph_hit)}")
    md(f"**5. Did graph-enriched find PROC_P100 / DOC_003?** {'YES' if graph_hit else 'NO'}")
    md()

    result, reason = evaluate(vector_hit, graph_hit)
    result_style = "bold green" if result == "PASS" else "bold red"
    console.print(f"6. Result: [{result_style}]{result}[/{result_style}] ({reason})\n")
    md(f"**6. Result:** {result} ({reason})")
    md()

    return {
        "id": question["id"],
        "text": question["text"],
        "vector_hit": vector_hit,
        "graph_hit": graph_hit,
        "lineage_hit": lineage_hit,
        "result": result,
    }


def print_summary_table(rows: list[dict]) -> None:
    table = Table(title="Evaluation summary")
    table.add_column("Question")
    table.add_column("Vector found P-100")
    table.add_column("Graph found P-100")
    table.add_column("Graph lineage found")
    table.add_column("Result")
    for row in rows:
        result_style = "bold green" if row["result"] == "PASS" else "bold red"
        table.add_row(
            row["id"],
            fmt_hit(row["vector_hit"]),
            fmt_hit(row["graph_hit"]),
            fmt_hit(row["lineage_hit"]),
            f"[{result_style}]{row['result']}[/{result_style}]",
        )
    console.print(table)

    md("## Evaluation summary")
    md()
    md("| Question | Vector found P-100 | Graph found P-100 | Graph lineage found | Result |")
    md("|---|---|---|---|---|")
    for row in rows:
        md(
            f"| {row['id']} | {'YES' if row['vector_hit'] else 'NO'} "
            f"| {'YES' if row['graph_hit'] else 'NO'} | {'YES' if row['lineage_hit'] else 'NO'} "
            f"| {row['result']} |"
        )
    md()


def write_report() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(_md_lines), encoding="utf-8")
    console.print(f"\n[dim]Markdown report written to {REPORT_PATH}[/dim]")


def main() -> None:
    _md_lines.clear()
    md("# Retrieval Comparison Report")
    md()
    md(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md()

    rows = [run_question(question) for question in QUESTIONS]
    print_summary_table(rows)
    write_report()


if __name__ == "__main__":
    main()
