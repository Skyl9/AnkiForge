import os

import pytest
from peewee_migrate import Router

from ankiforge.database.migration import run_migrations
from ankiforge.database.models import db

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "src", "ankiforge", "database", "migrations")


@pytest.mark.integration
def test_run_migrations_idempotency(mock_db):
    """
    Vérifie que run_migrations ne plante pas, crée la table migratehistory,
    falsifie les migrations sur une base legacy, et est idempotent.
    """
    # mock_db crée déjà les tables métier, donc on simule un environnement legacy.
    # On supprime migratehistory si elle existe pour simuler un vieil utilisateur
    if db.table_exists("migratehistory"):
        db.execute_sql("DROP TABLE migratehistory")

    # 1. Première exécution (Legacy DB)
    run_migrations()

    # Vérifications de l'état
    assert db.table_exists("migratehistory"), "La table migratehistory de peewee-migrate est manquante."

    router = Router(db, migrate_dir=MIGRATIONS_DIR)
    assert "001_initial" in router.done, "La migration 001_initial devrait être marquée comme terminée."

    columns = [col.name for col in db.get_columns("llm_configs")]
    assert "prompt_pricing" in columns, "La colonne prompt_pricing est manquante."

    # S'il l'avait faked (parce qu'elle était legacy), elle devrait être dans router.done.
    assert "002_llm_pricing" in router.done, "La migration 002 devrait être marquée comme terminée."
    assert "003_orientation_features" in router.done, "La migration 003 devrait être marquée comme terminée."
    assert "004_ai_cache" in router.done, "La migration 004 devrait être marquée comme terminée."
    assert "005_persona_engine" in router.done, "La migration 005 devrait être marquée comme terminée."
    assert "018_app_settings" in router.done, "La migration 018 devrait être marquée comme terminée."
    assert "020_notetype_description" in router.done, "La migration 020 devrait être marquée comme terminée."
    assert "021_performance_indexes" in router.done, "La migration 021 devrait être marquée comme terminée."
    assert db.table_exists("settings"), "La table settings devrait exister."

    # 2. Deuxième exécution (Idempotence)
    run_migrations()

    router = Router(db, migrate_dir=MIGRATIONS_DIR)
    assert "001_initial" in router.done
    assert "003_orientation_features" in router.done
    assert "004_ai_cache" in router.done
    assert "005_persona_engine" in router.done
    assert "018_app_settings" in router.done
    assert "020_notetype_description" in router.done
    assert "021_performance_indexes" in router.done
