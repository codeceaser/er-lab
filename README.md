# ER GraphRAG POC

A small, local proof-of-concept comparing **vector-only retrieval** against
**graph-enriched retrieval** over a tiny Enterprise Resilience corpus, to
test whether graph expansion can surface transitive evidence that plain
vector search misses.

## Stack

- PostgreSQL + [pgvector](https://github.com/pgvector/pgvector)
- `sentence-transformers/all-MiniLM-L6-v2` embeddings (384-dim)
- Python: `psycopg`, `sqlalchemy`, `pgvector`, `python-dotenv`, `rich`

No Neo4j, no LangChain, no LlamaIndex, no LLM extraction, no web UI. Graph
relationships and evidence are hand-seeded, not LLM-extracted.

## Setup

1. Start Postgres + pgvector via Docker Compose (uses the official
   [`pgvector/pgvector:pg16`](https://github.com/pgvector/pgvector) image, so
   the extension is available out of the box — no manual extension install):

   ```
   docker compose up -d
   ```

   This starts a container on host port **5434** (mapped to the container's
   5432), with user `er_admin` / password `er_admin_pw` / database
   `er_graphrag_poc`, matching `.env.example` below. Port 5434 (not the more
   common 5433/5432) is used to avoid clashing with any Postgres you may
   already have running locally — change the host-side port in
   `docker-compose.yml` if 5434 is also taken on your machine, and update
   `.env` to match.

2. Copy `.env.example` to `.env` and adjust `DATABASE_URL` if you changed the
   port above:

   ```
   DATABASE_URL=postgresql+psycopg://er_admin:er_admin_pw@localhost:5434/er_graphrag_poc
   ```

3. Create a virtualenv and install dependencies:

   ```
   pip install -r requirements.txt
   ```

## Running the POC

Run each step from the project root, in order:

```
python src/create_schema.py          # (re)creates all tables + vector extension
python src/seed_documents.py         # inserts documents + document_chunks (embedded)
python src/seed_graph.py             # inserts kg_entities, kg_edges, kg_evidence
python src/build_graph_artifacts.py  # builds graph_artifacts from entities + edges (embedded)
python src/compare_retrieval.py      # runs the side-by-side comparison report
```

`compare_retrieval.py` prints the report to the console and also writes it as
Markdown to `reports/compare_retrieval_report.md` (overwritten each run).

Individual retrievers can also be run standalone:

```
python src/vector_retriever.py "What is the BCP impact of CRA-176046 going down?"
python src/graph_enriched_retriever.py "What is the BCP impact of CRA-176046 going down?"
```

## How the comparison works

- **Vector-only retrieval** (`vector_retriever.py`) embeds the query and
  searches `document_chunks` only, by cosine similarity.
- **Graph-enriched retrieval** (`graph_enriched_retriever.py`):
  1. Embeds the query and searches `graph_artifacts` (entity artifacts and
     single-edge artifacts only) for seed entities/edges.
  2. Expands the graph outward from those seeds, up to 4 hops, by walking
     `kg_edges` at query time (breadth-first, either direction). This is
     where multi-hop lineage is *discovered* — nothing in `graph_artifacts`
     ever encodes a multi-hop path directly.
  3. Attaches `kg_evidence` to every edge discovered along the way.
  4. Independently runs the same unfiltered vector search over
     `document_chunks` as the baseline (graph results never filter or bias
     the document search).

`compare_retrieval.py` runs both retrievers against the fixed question
*"What is the BCP impact of CRA-176046 going down?"* and prints a report
showing whether **BCP Procedure P-100** — reachable only via the transitive
chain `CRA-176046 -> O-22 -> C-77 -> P-100` — was found by each approach.

## Fairness constraints enforced in this POC

- `graph_artifacts` contains only two artifact types: `entity` and
  `single_edge`. No path summaries, no community summaries, and nothing that
  directly answers the evaluation question.
- Every `kg_edge` has at least one `kg_evidence` row pointing at the
  `document_chunk` that supports it.
- Multi-hop lineage is computed at query time via graph traversal, never
  precomputed or stored.
- Vector-only retrieval searches `document_chunks` exclusively.
- Graph-enriched retrieval searches `document_chunks` and `graph_artifacts`
  independently; graph expansion never filters the vector search.

## Project layout

```
docker-compose.yml            # Postgres + pgvector (pgvector/pgvector:pg16), port 5434
src/
  config.py                    # env config, model name, retrieval defaults
  db.py                        # SQLAlchemy engine, connections, embedding helpers
  create_schema.py             # DDL for all tables
  seed_documents.py            # sample documents + embedded chunks
  seed_graph.py                # kg_entities, kg_edges, kg_evidence
  build_graph_artifacts.py     # entity + single-edge artifacts (embedded)
  vector_retriever.py          # baseline vector-only retrieval
  graph_enriched_retriever.py  # graph artifact search + query-time expansion
  compare_retrieval.py         # side-by-side comparison report
```
