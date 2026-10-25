"""Test de la migration 047 : création de staged_bundles et colonnes de bundles sur staged_patches."""

from pathlib import Path

import pytest
from peewee_migrate import Router

from ankiforge.database.migration import run_migrations
from ankiforge.database.models import StagedBundleModel, StagedPatchModel, db

pytestmark = pytest.mark.integration

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "ankiforge" / "database" / "migrations"


def _rewind_before_migration_047() -> None:
    """Ramène la base dans un état antérieur à la migration 047."""
    db.execute_sql("DROP TABLE IF EXISTS staged_bundles;")
    db.execute_sql("DROP TABLE IF EXISTS staged_patches;")
    db.execute_sql("""
        CREATE TABLE staged_patches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patch_id VARCHAR(255) NOT NULL,
            patch_type VARCHAR(255) NOT NULL,
            target_id INTEGER NOT NULL DEFAULT 0,
            original_version_id INTEGER,
            diff_payload TEXT NOT NULL,
            status VARCHAR(255) NOT NULL DEFAULT 'pending',
            created_at DATETIME NOT NULL,
            applied_at DATETIME
        );
    """)
    if db.table_exists("migratehistory"):
        db.execute_sql("DELETE FROM migratehistory WHERE name = '047_create_staged_bundles';")


def test_migration_047_creates_bundle_table_and_columns(mock_db):
    """Vérifie que la migration 047 crée staged_bundles et enrichit staged_patches."""
    # 1. Jouer les migrations jusqu'à 046
    run_migrations()

    # 2. Revenir juste avant 047
    _rewind_before_migration_047()

    assert not db.table_exists("staged_bundles")
    cols_before = [c.name for c in db.get_columns("staged_patches")]
    assert "bundle_id" not in cols_before
    assert "step_order" not in cols_before

    # 3. Exécuter la migration 047 via le router
    Router(db, migrate_dir=str(MIGRATIONS_DIR)).run()

    assert db.table_exists("staged_bundles")
    assert db.table_exists("staged_patches")

    bundle_cols = [c.name for c in db.get_columns("staged_bundles")]
    assert "bundle_id" in bundle_cols
    assert "title" in bundle_cols
    assert "status" in bundle_cols
    assert "total_steps" in bundle_cols
    assert "current_step" in bundle_cols

    patch_cols = [c.name for c in db.get_columns("staged_patches")]
    assert "bundle_id" in patch_cols
    assert "step_order" in patch_cols


def test_migration_047_is_idempotent(mock_db):
    """Vérifie que réexécuter la migration 047 ne génère pas d'erreur."""
    run_migrations()
    Router(db, migrate_dir=str(MIGRATIONS_DIR)).run()

    bundle = StagedBundleModel.create(
        bundle_id="bundle_test_idempotent",
        title="Test Idempotent",
        status="building",
    )
    patch = StagedPatchModel.create(
        patch_id="patch_test_idempotent",
        bundle=bundle,
        step_order=1,
        patch_type="note_create",
        diff_payload="{}",
        status="pending",
    )

    assert patch.bundle.bundle_id == "bundle_test_idempotent"
    assert patch.step_order == 1
