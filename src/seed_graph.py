"""Seed the knowledge graph: kg_entities, kg_edges, and kg_evidence.

Every edge inserted here is backed by exactly one kg_evidence row pointing at
the document_chunk that supports it (fairness constraint #5).

Run: python src/seed_graph.py
"""

from rich.console import Console
from sqlalchemy import text

from db import get_connection

console = Console()

ENTITIES = [
    {
        "entity_id": "APP_CRA_176046",
        "entity_type": "Application",
        "canonical_name": "CRA-176046",
        "aliases": ["CRA", "application 176046"],
    },
    {
        "entity_id": "SERVICE_CRA",
        "entity_type": "BusinessService",
        "canonical_name": "Compliance Risk Assessment",
        "aliases": ["Compliance Risk Assessment service"],
    },
    {
        "entity_id": "OBL_O22",
        "entity_type": "RegulatoryObligation",
        "canonical_name": "Regulatory Obligation O-22",
        "aliases": ["O-22"],
    },
    {
        "entity_id": "CTRL_C77",
        "entity_type": "Control",
        "canonical_name": "Control C-77",
        "aliases": ["C-77"],
    },
    {
        "entity_id": "PROC_P100",
        "entity_type": "BCPProcedure",
        "canonical_name": "BCP Procedure P-100",
        "aliases": ["Procedure P-100"],
    },
    {
        "entity_id": "DOC_BCP_POLICY",
        "entity_type": "Document",
        "canonical_name": "BCP Policy 2026",
        "aliases": ["BCP Policy"],
    },
    {
        "entity_id": "ORG_COMPLIANCE_RISK_TEAM",
        "entity_type": "OrgUnit",
        "canonical_name": "Compliance Risk Team",
        "aliases": ["Compliance Risk Team"],
    },
    {
        "entity_id": "GEO_APAC",
        "entity_type": "Geography",
        "canonical_name": "APAC",
        "aliases": ["APAC"],
    },
    {
        "entity_id": "RTO_4_HOURS",
        "entity_type": "RecoveryMetric",
        "canonical_name": "RTO 4 hours",
        "aliases": ["4 hours"],
    },
]

# Each edge carries its single supporting evidence record inline.
EDGES = [
    {
        "edge_id": "EDGE_001",
        "source_entity_id": "APP_CRA_176046",
        "relationship_type": "SUPPORTS",
        "target_entity_id": "SERVICE_CRA",
        "document_id": "DOC_001",
        "chunk_id": "CHUNK_DOC_001_001",
        "evidence_text": "Application CRA-176046 supports the Compliance Risk Assessment service.",
    },
    {
        "edge_id": "EDGE_002",
        "source_entity_id": "APP_CRA_176046",
        "relationship_type": "IN_SCOPE_FOR",
        "target_entity_id": "OBL_O22",
        "document_id": "DOC_001",
        "chunk_id": "CHUNK_DOC_001_001",
        "evidence_text": "CRA-176046 is in scope for Regulatory Obligation O-22.",
    },
    {
        "edge_id": "EDGE_003",
        "source_entity_id": "OBL_O22",
        "relationship_type": "SATISFIED_BY",
        "target_entity_id": "CTRL_C77",
        "document_id": "DOC_002",
        "chunk_id": "CHUNK_DOC_002_001",
        "evidence_text": "Regulatory Obligation O-22 is satisfied by Control C-77.",
    },
    {
        "edge_id": "EDGE_004",
        "source_entity_id": "CTRL_C77",
        "relationship_type": "MANDATES",
        "target_entity_id": "PROC_P100",
        "document_id": "DOC_003",
        "chunk_id": "CHUNK_DOC_003_001",
        "evidence_text": "Control C-77 mandates BCP Procedure P-100 for critical compliance applications.",
    },
    {
        "edge_id": "EDGE_005",
        "source_entity_id": "PROC_P100",
        "relationship_type": "DEFINED_IN",
        "target_entity_id": "DOC_BCP_POLICY",
        "document_id": "DOC_003",
        "chunk_id": "CHUNK_DOC_003_001",
        "evidence_text": (
            "Procedure P-100 requires manual recovery steps and continuity validation "
            "before business restoration."
        ),
    },
    {
        "edge_id": "EDGE_006",
        "source_entity_id": "SERVICE_CRA",
        "relationship_type": "OWNED_BY",
        "target_entity_id": "ORG_COMPLIANCE_RISK_TEAM",
        "document_id": "DOC_004",
        "chunk_id": "CHUNK_DOC_004_001",
        "evidence_text": (
            "Compliance Risk Assessment is a critical business service owned by the "
            "Compliance Risk Team."
        ),
    },
    {
        "edge_id": "EDGE_007",
        "source_entity_id": "SERVICE_CRA",
        "relationship_type": "OPERATES_IN",
        "target_entity_id": "GEO_APAC",
        "document_id": "DOC_004",
        "chunk_id": "CHUNK_DOC_004_001",
        "evidence_text": "The service operates in APAC and has an RTO of 4 hours.",
    },
    {
        "edge_id": "EDGE_008",
        "source_entity_id": "SERVICE_CRA",
        "relationship_type": "HAS_RTO",
        "target_entity_id": "RTO_4_HOURS",
        "document_id": "DOC_004",
        "chunk_id": "CHUNK_DOC_004_001",
        "evidence_text": "The service operates in APAC and has an RTO of 4 hours.",
    },
]


def seed_graph() -> None:
    with get_connection() as conn:
        for entity in ENTITIES:
            conn.execute(
                text(
                    """
                    INSERT INTO kg_entities (entity_id, entity_type, canonical_name, aliases)
                    VALUES (:entity_id, :entity_type, :canonical_name, :aliases)
                    """
                ),
                entity,
            )
            console.print(f"  inserted entity {entity['entity_id']}")

        for i, edge in enumerate(EDGES, start=1):
            conn.execute(
                text(
                    """
                    INSERT INTO kg_edges
                        (edge_id, source_entity_id, relationship_type, target_entity_id)
                    VALUES
                        (:edge_id, :source_entity_id, :relationship_type, :target_entity_id)
                    """
                ),
                {
                    "edge_id": edge["edge_id"],
                    "source_entity_id": edge["source_entity_id"],
                    "relationship_type": edge["relationship_type"],
                    "target_entity_id": edge["target_entity_id"],
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO kg_evidence
                        (evidence_id, edge_id, document_id, chunk_id, evidence_text)
                    VALUES
                        (:evidence_id, :edge_id, :document_id, :chunk_id, :evidence_text)
                    """
                ),
                {
                    "evidence_id": f"EVID_{i:03d}",
                    "edge_id": edge["edge_id"],
                    "document_id": edge["document_id"],
                    "chunk_id": edge["chunk_id"],
                    "evidence_text": edge["evidence_text"],
                },
            )
            console.print(f"  inserted edge {edge['edge_id']} (+ evidence)")

        conn.commit()


if __name__ == "__main__":
    try:
        seed_graph()
        console.print("[bold green]Graph entities, edges, and evidence seeded successfully.[/bold green]")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[bold red]Seeding graph failed:[/bold red] {exc}")
        raise
