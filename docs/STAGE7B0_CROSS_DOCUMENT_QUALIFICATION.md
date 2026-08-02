# Stage 7B.0 — Cross-Document Relationship Holdout: Artifact Qualification

This document qualifies the Stage 7B.0 benchmark: it explains *why the
corpus is built the way it is*, *what the Vector baseline is expected to
do*, and *what the benchmark does and does not prove*. It is the
companion to `contracts/cross_document_relationship_benchmark_v1.json`
and the measured scorecard `reports/stage7b0_cross_document_vector_scorecard.md`.

Stage 7B.0 **does not implement Graph RAG**. It creates and qualifies a
benchmark that can *later* determine, fairly, whether an evidence-backed
graph projection adds measurable retrieval value beyond Vector RAG.

## The corpus and why each document exists

The current relationship chain is deliberately distributed **one hop per
logical document**:

| Logical document | Current fact it contributes | Hop |
|---|---|---|
| `APP-PORTFOLIO` | APP-224510 supports Payment Settlement | 1 |
| `SERVICE-CATALOGUE` | Payment Settlement is governed by Obligation O-31 | 2 |
| `OBLIGATION-REGISTER` | Obligation O-31 is satisfied by Control C-88 | 3 |
| `CONTROL-LIBRARY` | Control C-88 is implemented through Procedure P-205 | 4 |
| `PROCEDURE-CATALOGUE` | Procedure P-205 is the current operating procedure | 5 |

No document names more than one hop, so the full chain
`APP-224510 → Payment Settlement → O-31 → C-88 → P-205` exists **only as a
join across five documents**, never inside one chunk.

## Which fact each document contributes and whether it is genuinely distributed

Each real-chain source file contains a **single relationship sentence**
under a heading, so the frozen Stage 4/4.1 chunker produces exactly **one
single-fact chunk per revision** (verified — see the
`test_no_single_chunk_contains_a_preassembled_multi_hop_answer` and
`test_multi_hop_facts_are_distributed_across_documents_and_chunks`
tests). The evidence alignment (`artifacts/stage7b0/evidence_alignment.json`)
records the resolved supporting `chunk_id` for every fact. Because the
required facts of every multi-hop question map to **distinct chunks in
distinct documents**, the distribution is genuine, not cosmetic.

## Which distractor each document/revision introduces

| Distractor | Where | Kind | What it tests |
|---|---|---|---|
| `APP-224499` (retired application) | `APP-PORTFOLIO` rev1 | authority (historical) | current queries must exclude it |
| `Control C-88a` (superseded control) | `OBLIGATION-REGISTER` rev1, `CONTROL-LIBRARY` rev1 | authority (historical) | current queries must exclude it; historical queries must recover it |
| `Procedure P-204` (historical procedure) | `CONTROL-LIBRARY` rev1, `PROCEDURE-CATALOGUE` rev1 | authority (historical) | current excludes / historical recovers |
| `Control C-91` (draft/proposed control) | `CONTROL-LIBRARY` rev3 (registered, never activated) | authority (draft) | current excludes; draft intent surfaces it |
| Payment Reconciliation chain (`APP-330012`, `O-32`, `C-77`, `P-301`) | `ADJACENT-DOMAIN` | **lexical** (authority-eligible) | vector must rank the *right* chain above a lexically similar unrelated one |

The first four distractors are removed by the **Stage 7R authority
resolver** (they are historical or draft). The adjacent-domain chain is
deliberately **authority-current** — it cannot be filtered by authority
at all, so it is a pure test of whether *vector ranking* keeps the
correct chain ahead of a lexically similar wrong one.

## Why the corpus does not structurally favour Graph

- Every fact is a **plain source sentence** naturally present in a
  document. There are **no graph nodes, edges, paths, adjacency lists,
  expected answers, or benchmark labels** in any `CanonicalDocument` or
  `CanonicalChunk` — a structural test and an AST test enforce this.
- The relationship chain, required/forbidden facts, and expected answers
  live **only in the contract as evaluation truth**; the retriever is
  handed only query text, intent, `as_of_date`, requested revisions, and
  a top-K budget (enforced by
  `test_retriever_and_store_never_read_evaluation_truth`).
- Both sides of any future comparison consume the **same** canonical
  chunks, the **same** authority resolver, the **same** questions and
  budgets. The fairness contract (item 6, embedded in the benchmark JSON)
  additionally forbids any precomputed per-question path and requires
  every future node/edge to cite supporting `chunk_id`s that already
  exist in this chunk set. A graph therefore cannot "win" by smuggling in
  precomputed answers — it can only win by traversing the *same* evidence
  more completely.

## What direct and relationship questions Vector is expected to handle

- **Direct / one-hop / distractor / current-authority / historical-direct /
  draft** lookups (a single required fact): Vector is expected to handle
  these well — the answer sentence is lexically close to the query.
- **Distributed multi-hop** lookups (2–5 required facts across 2–5
  documents): Vector is expected to retrieve the **endpoints** it can
  lexically match but to **miss intermediate hops** the query never
  names, especially when a fixed evidence budget forces a lexically
  similar adjacent-domain chunk ahead of a required intermediate hop.
  This is the gap a graph projection would target.

## What this benchmark proves

- The corpus genuinely distributes every multi-hop relationship across
  separate documents, with no pre-assembled answer in any chunk.
- Authority filtering (current vs. historical vs. draft) occurs **before**
  vector ranking, for every question, with **zero** authority leakage.
- It measures, per question, exactly how much of each distributed chain a
  Vector baseline recovers within a fixed budget — coverage@K,
  all-required@K, MRR, nDCG, evidence-document diversity, and a
  solved/partial/failed classification — with complete provenance on
  every hit.
- It freezes a fair, reproducible comparison harness a future graph
  projection must be measured against under identical conditions.

## What this benchmark does not prove

- It does **not** prove a graph projection is better — no graph is built
  in Stage 7B.0.
- It is a **small, controlled** corpus. Under a current-intent query only
  six chunks are authority-eligible, so the vector recall ceiling is easy
  to reach and absolute scores overstate what Vector would achieve on a
  large corpus. The value is the **methodology** and the **honest
  per-question breakdown**, not the headline numbers.
- A single embedding model (`sentence-transformers/all-MiniLM-L6-v2`) and
  a single document format (DOCX) are used; this benchmark isolates
  distributed-relationship retrieval, not format parity (Stage 6B/7A.1)
  or embedding-model choice.
