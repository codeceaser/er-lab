-- Stage 7R.1/7R.1a: revision-authority registry schema.
--
-- Three tables, owned exclusively by this package -- never
-- document_chunks/documents/kg_* (the separate, frozen ER GraphRAG POC)
-- or ingestion_bench_stage7a_* (Stage 7A.1's own vector table). No
-- migration framework: this file is applied idempotently
-- (CREATE TABLE IF NOT EXISTS) by postgres_repository.py on first use.
--
-- edib_document_revision_registry holds ONE row per revision: its
-- immutable identity columns (copied verbatim from
-- ingestion_bench.chunking.DocumentRevisionContext -- never
-- recomputed here) plus its CURRENT mutable GOVERNANCE status only.
-- Stage 7R.1a: this table no longer carries effective_from/
-- effective_to/supersession columns at all -- those moved to
-- edib_revision_authority_period below, the SOLE authoritative source
-- for effective-date resolution (never two competing copies of an
-- effective interval).
CREATE TABLE IF NOT EXISTS edib_document_revision_registry (
    document_revision_id      TEXT PRIMARY KEY,

    -- Immutable revision identity (Stage 4.1 DocumentRevisionContext).
    logical_document_id       TEXT NOT NULL,
    source_document_sha256    TEXT NOT NULL,
    version_label             TEXT,
    revision_number           INTEGER,

    -- Mutable GOVERNANCE metadata only (Stage 7R.1a) -- never on CanonicalChunk.
    publication_status          TEXT,
    approved_at                 TIMESTAMPTZ,
    authority_source            TEXT,
    authority_reference         TEXT,
    authority_recorded_at       TIMESTAMPTZ,
    authority_recorded_by       TEXT,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS edib_document_revision_registry_logical_document_id_idx
    ON edib_document_revision_registry (logical_document_id);

-- Stage 7R.1a: the SOLE authoritative source for effective-date
-- resolution. A revision may have MULTIPLE, non-overlapping rows here
-- over time (a historical period later closed by supersession/
-- withdrawal/rollback/correction; a later period from a reinstatement).
CREATE TABLE IF NOT EXISTS edib_revision_authority_period (
    authority_period_id    BIGSERIAL PRIMARY KEY,
    logical_document_id    TEXT NOT NULL,
    document_revision_id   TEXT NOT NULL,

    effective_from          DATE NOT NULL,
    effective_to            DATE,

    predecessor_revision_id TEXT,
    opening_event_id        BIGINT NOT NULL,
    closing_event_id        BIGINT,
    closure_reason          TEXT,

    authority_source        TEXT NOT NULL,
    authority_reference     TEXT NOT NULL,
    recorded_at             TIMESTAMPTZ NOT NULL,
    recorded_by              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS edib_revision_authority_period_logical_document_id_idx
    ON edib_revision_authority_period (logical_document_id);
CREATE INDEX IF NOT EXISTS edib_revision_authority_period_document_revision_id_idx
    ON edib_revision_authority_period (document_revision_id);

-- Append-only audit log. Normal application operations (service.py)
-- only ever INSERT here -- there is no UPDATE/DELETE statement against
-- this table anywhere in this package's own code.
-- decision_effective_date is WHEN the authority change takes effect;
-- recorded_at is WHEN the decision was recorded -- deliberately
-- separate columns, never reconstructed by parsing detail's free text.
CREATE TABLE IF NOT EXISTS edib_authority_decision_event (
    event_id                  BIGSERIAL PRIMARY KEY,
    event_type                TEXT NOT NULL,
    logical_document_id       TEXT NOT NULL,
    revision_id                TEXT NOT NULL,
    related_revision_id        TEXT,
    decision_effective_date    DATE,
    closure_reason             TEXT,
    recorded_at                TIMESTAMPTZ NOT NULL,
    authority_source           TEXT NOT NULL,
    authority_reference        TEXT NOT NULL,
    recorded_by                TEXT NOT NULL,
    detail                     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS edib_authority_decision_event_logical_document_id_idx
    ON edib_authority_decision_event (logical_document_id);
