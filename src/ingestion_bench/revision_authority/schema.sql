-- Stage 7R.1: revision-authority registry schema.
--
-- Two tables, owned exclusively by this package -- never
-- document_chunks/documents/kg_* (the separate, frozen ER GraphRAG POC)
-- or ingestion_bench_stage7a_* (Stage 7A.1's own vector table). No
-- migration framework: this file is applied idempotently
-- (CREATE TABLE IF NOT EXISTS) by postgres_repository.py on first use.
--
-- edib_document_revision_registry holds ONE row per revision: its
-- immutable identity columns (copied verbatim from
-- ingestion_bench.chunking.DocumentRevisionContext -- never
-- recomputed here) plus its CURRENT mutable authority state. Identity
-- columns are written once (register_revision); authority columns are
-- updated in place by record_authority_decision/activate_revision/
-- withdraw_revision -- history of those changes lives in the
-- append-only event table below, never by keeping old rows around here.
CREATE TABLE IF NOT EXISTS edib_document_revision_registry (
    document_revision_id      TEXT PRIMARY KEY,

    -- Immutable revision identity (Stage 4.1 DocumentRevisionContext).
    logical_document_id       TEXT NOT NULL,
    source_document_sha256    TEXT NOT NULL,
    version_label             TEXT,
    revision_number           INTEGER,

    -- Mutable authority metadata (Stage 7R.1 -- never on CanonicalChunk).
    publication_status         TEXT,
    approved_at                TIMESTAMPTZ,
    effective_from             DATE,
    effective_to               DATE,
    supersedes_revision_id     TEXT,
    superseded_by_revision_id  TEXT,
    authority_source           TEXT,
    authority_reference        TEXT,
    authority_recorded_at      TIMESTAMPTZ,
    authority_recorded_by      TEXT,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS edib_document_revision_registry_logical_document_id_idx
    ON edib_document_revision_registry (logical_document_id);

-- Append-only audit log. Normal application operations (service.py)
-- only ever INSERT here -- there is no UPDATE/DELETE statement against
-- this table anywhere in this package's own code.
CREATE TABLE IF NOT EXISTS edib_authority_decision_event (
    event_id             BIGSERIAL PRIMARY KEY,
    event_type           TEXT NOT NULL,
    logical_document_id  TEXT NOT NULL,
    revision_id          TEXT NOT NULL,
    related_revision_id  TEXT,
    recorded_at          TIMESTAMPTZ NOT NULL,
    authority_source     TEXT NOT NULL,
    authority_reference  TEXT NOT NULL,
    recorded_by          TEXT NOT NULL,
    detail               TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS edib_authority_decision_event_logical_document_id_idx
    ON edib_authority_decision_event (logical_document_id);
