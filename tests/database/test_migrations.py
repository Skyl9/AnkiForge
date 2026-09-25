import importlib
import os

import pytest
from peewee_migrate import Router

from ankiforge.database.migration import run_migrations
from ankiforge.database.models import PersonaModel, db

pytestmark = pytest.mark.integration


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
    assert "022_consultant_sessions" in router.done, "La migration 022 devrait être marquée comme terminée."
    assert "024_document_multimedia_and_albums" in router.done, "La migration 024 devrait être marquée comme terminée."
    assert "025_document_chunk_pages_and_headings" in router.done, "La migration 025 devrait être marquée comme terminée."
    assert "028_llm_max_tokens" in router.done, "La migration 028 devrait être marquée comme terminée."
    assert "029_llm_capabilities" in router.done, "La migration 029 devrait être marquée comme terminée."
    assert "030_fts5_and_perf_indexes" in router.done, "La migration 030 devrait être marquée comme terminée."
    assert "031_seed_dedicated_mcp_agents" in router.done, "La migration 031 devrait être marquée comme terminée."
    assert "033_chunk_strategy_version" in router.done, "La migration 033 devrait être marquée comme terminée."
    assert "036_embedding_cache_and_missing_indexes" in router.done, "La migration 036 devrait être marquée comme terminée."
    assert db.table_exists("settings"), "La table settings devrait exister."
    assert db.table_exists("consultant_sessions"), "La table consultant_sessions devrait exister."
    assert db.table_exists("consultant_messages"), "La table consultant_messages devrait exister."
    assert db.table_exists("embedding_cache"), "La table embedding_cache devrait exister."

    llm_cols = [c.name for c in db.get_columns("llm_configs")]
    assert "max_tokens" in llm_cols, "La colonne max_tokens est manquante sur llm_configs."
    assert "sort_order" in llm_cols, "La colonne sort_order est manquante sur llm_configs."

    chunk_cols = [c.name for c in db.get_columns("document_chunks")]
    assert "page_number" in chunk_cols, "La colonne page_number est manquante sur document_chunks."
    assert "heading_path" in chunk_cols, "La colonne heading_path est manquante sur document_chunks."

    doc_cols = [c.name for c in db.get_columns("documentmodel")]
    assert "chunk_strategy_version" in doc_cols, "La colonne chunk_strategy_version est manquante sur documentmodel."

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
    assert "022_consultant_sessions" in router.done
    assert "024_document_multimedia_and_albums" in router.done
    assert "025_document_chunk_pages_and_headings" in router.done
    assert "028_llm_max_tokens" in router.done
    assert "029_llm_capabilities" in router.done
    assert "030_fts5_and_perf_indexes" in router.done
    assert "031_seed_dedicated_mcp_agents" in router.done
    assert "033_chunk_strategy_version" in router.done
    assert "036_embedding_cache_and_missing_indexes" in router.done


def test_dedicated_agent_migration_repairs_empty_existing_prompts(mock_db):
    """La migration 031 doit réparer les agents créés avec un prompt vide."""
    migration_031 = importlib.import_module("ankiforge.database.migrations.031_seed_dedicated_mcp_agents")

    PersonaModel.create(name="Auditeur Wozniak", system_prompt="")
    PersonaModel.create(name="Architecte Modèles & CSS", system_prompt="Prompt personnalisé conservé")

    migration_031.migrate(None, db)

    repaired = PersonaModel.get(PersonaModel.name == "Auditeur Wozniak")
    assert repaired.system_prompt
    assert len(repaired.system_prompt) > 50
    assert "Wozniak" in repaired.system_prompt
    preserved = PersonaModel.get(PersonaModel.name == "Architecte Modèles & CSS")
    assert preserved.system_prompt == "Prompt personnalisé conservé"


def test_seed_initial_data_repairs_empty_existing_persona_prompts(mock_db):
    """Le seed doit réparer les personas préexistants dont le prompt est vide."""
    from ankiforge.database.seeds.initial_seed import seed_initial_data

    PersonaModel.create(name="Consultant Généraliste", system_prompt="")
    PersonaModel.create(name="Archiviste Pédagogue", system_prompt="")
    PersonaModel.create(name="Juge Fact-Checker", system_prompt="Prompt personnalisé conservé")

    seed_initial_data()

    for name in ("Consultant Généraliste", "Archiviste Pédagogue"):
        persona = PersonaModel.get(PersonaModel.name == name)
        assert persona.system_prompt
        assert len(persona.system_prompt) > 50
    assert PersonaModel.get(PersonaModel.name == "Juge Fact-Checker").system_prompt == "Prompt personnalisé conservé"
