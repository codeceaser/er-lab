"""Stage 7R.1b item 5: one-time, explicit reset for this package's own
THREE isolated Stage 7R tables -- and ONLY these three:

    edib_document_revision_registry
    edib_revision_authority_period
    edib_authority_decision_event

Intended for the case where PostgresRevisionAuthorityRepository refuses
to start with a Stage7RLegacySchemaError (populated legacy effective_from/
effective_to/supersedes_revision_id/superseded_by_revision_id data on
edib_document_revision_registry with no corresponding
edib_revision_authority_period row) and that legacy data is disposable
POC data, not something worth a one-time manual migration.

DROPs (CASCADE) then immediately recreates all three tables from the
CURRENT schema.sql, in dependency order (period/event first, registry
last, mirroring their foreign-key-free but logically-dependent order) --
never touches any other table in the database (document_chunks/
documents/kg_* from the separate ER GraphRAG POC, ingestion_bench_stage7a_*
from Stage 7A.1, or anything else). Requires an explicit --yes flag; runs
in dry-run mode (prints what it WOULD do) otherwise.

Usage (from the repository root, with the venv active):
    python scripts/reset_stage7r_tables.py           # dry run
    python scripts/reset_stage7r_tables.py --yes      # actually drop + recreate
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sqlalchemy import create_engine, text  # noqa: E402

from ingestion_bench.revision_authority import config  # noqa: E402

_TABLES = (config.AUTHORITY_PERIOD_TABLE, config.AUTHORITY_EVENT_TABLE, config.REVISION_REGISTRY_TABLE)


def main() -> None:
    confirmed = "--yes" in sys.argv[1:]

    if not config.DATABASE_URL:
        print("DATABASE_URL is not set -- nothing to reset.")
        sys.exit(1)

    print("This will DROP and recreate ONLY these three tables:")
    for table in _TABLES:
        print(f"  - {table}")
    print("No other table in the database is touched.")

    if not confirmed:
        print("\nDry run only -- pass --yes to actually execute.")
        return

    engine = create_engine(config.DATABASE_URL, future=True)
    with engine.connect() as conn:
        for table in _TABLES:
            conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        conn.commit()
    print("Dropped.")

    # PostgresRevisionAuthorityRepository._ensure_ready() recreates all
    # three tables (schema.sql, CREATE TABLE IF NOT EXISTS) and applies
    # the Stage 7R.1a event-column ALTERs the first time it is used --
    # forcing that path right here confirms the reset actually leaves a
    # working, current-shape schema behind, not just an empty database.
    from ingestion_bench.revision_authority.postgres_repository import PostgresRevisionAuthorityRepository

    repo = PostgresRevisionAuthorityRepository(database_url=config.DATABASE_URL)
    repo._ensure_ready()
    print("Recreated (current Stage 7R.1a/7R.1b schema).")


if __name__ == "__main__":
    main()
