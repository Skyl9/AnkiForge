import logging
import os
import sqlite3
import peewee
from peewee_migrate import Router
from ankiforge.database.models import db

# On définit le dossier des migrations relativement à ce fichier
MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")


def run_migrations() -> None:
    """
    Évalue la version de la base de données et exécute les migrations nécessaires
    en utilisant peewee-migrate.
    """
    # 1. Assurer la présence du répertoire de migration (sécurité)
    if not os.path.exists(MIGRATIONS_DIR):
        os.makedirs(MIGRATIONS_DIR, exist_ok=True)

    router = Router(db, migrate_dir=MIGRATIONS_DIR)

    # 2. Gestion de la transition depuis l'ancien système manuel
    # Si la table 'agents' ou 'personas' existe, c'est que l'utilisateur a au moins la v1
    is_legacy = db.table_exists("agents") or db.table_exists("personas")
    done_migrations = router.done

    if is_legacy:
        # Falsifier la migration initiale si elle n'est pas encore tracée
        if "001_initial" not in done_migrations:
            router.model.create(name="001_initial")
            logging.info("Legacy DB detected: faking migration 001_initial.")

        # Si la colonne prompt_pricing existe, l'utilisateur a déjà la structure de la v2
        if "002_llm_pricing" not in done_migrations:
            if db.table_exists("llm_configs"):
                columns = [col.name for col in db.get_columns("llm_configs")]
                if "prompt_pricing" in columns:
                    router.model.create(name="002_llm_pricing")
                    logging.info("Legacy DB detected: faking migration 002_llm_pricing.")

        # Si la colonne last_synced_at existe sur notemodel, l'utilisateur a déjà la structure de la v3
        if "003_orientation_features" not in done_migrations:
            if db.table_exists("notemodel"):
                columns = [col.name for col in db.get_columns("notemodel")]
                if "last_synced_at" in columns:
                    router.model.create(name="003_orientation_features")
                    logging.info("Legacy DB detected: faking migration 003_orientation_features.")

        # Si la table ai_cache existe déjà, l'utilisateur a déjà la structure de la v4
        if "004_ai_cache" not in done_migrations:
            if db.table_exists("ai_cache"):
                router.model.create(name="004_ai_cache")
                logging.info("Legacy DB detected: faking migration 004_ai_cache.")

        # Si la table personas existe, l'utilisateur a déjà la structure de la v5
        if "005_persona_engine" not in done_migrations:
            if db.table_exists("personas"):
                router.model.create(name="005_persona_engine")
                logging.info("Legacy DB detected: faking migration 005_persona_engine.")

        # Vérification et ajout dynamique de la colonne llm_config_id sur personas si absente
        if db.table_exists("personas"):
            cols = [col.name for col in db.get_columns("personas")]
            if "llm_config" not in cols and "llm_config_id" not in cols:
                try:
                    db.execute_sql("ALTER TABLE personas ADD COLUMN llm_config_id INTEGER REFERENCES llm_configs(id) ON DELETE SET NULL;")
                    logging.info("Column llm_config_id successfully added to personas table.")
                except Exception as e:
                    logging.warning(f"Notice on personas.llm_config_id: {e}")

        # Si la colonne chroma_collection_name existe sur documentmodel, l'utilisateur a la v6
        if "006_chroma_db" not in done_migrations:
            if db.table_exists("documentmodel"):
                columns = [col.name for col in db.get_columns("documentmodel")]
                if "chroma_collection_name" in columns:
                    router.model.create(name="006_chroma_db")
                    logging.info("Legacy DB detected: faking migration 006_chroma_db.")

        # Si la table linter_rules existe, l'utilisateur a la v7
        if "007_card_linter" not in done_migrations:
            if db.table_exists("linter_rules"):
                router.model.create(name="007_card_linter")
                logging.info("Legacy DB detected: faking migration 007_card_linter.")

        # Si la table document_chunks existe, l'utilisateur a la v8
        if "008_document_coverage" not in done_migrations:
            if db.table_exists("document_chunks"):
                router.model.create(name="008_document_coverage")
                logging.info("Legacy DB detected: faking migration 008_document_coverage.")

        # Si la colonne stability existe sur cardmodel, l'utilisateur a la v9
        if "009_srs_and_task_metrics" not in done_migrations:
            if db.table_exists("cardmodel"):
                columns = [col.name for col in db.get_columns("cardmodel")]
                if "stability" in columns:
                    router.model.create(name="009_srs_and_task_metrics")
                    logging.info("Legacy DB detected: faking migration 009_srs_and_task_metrics.")

        # Si la colonne original_media_id existe sur documentmodel, l'utilisateur a la v10
        if "010_document_original_media" not in done_migrations:
            if db.table_exists("documentmodel"):
                columns = [col.name for col in db.get_columns("documentmodel")]
                if "original_media" in columns or "original_media_id" in columns:
                    router.model.create(name="010_document_original_media")
                    logging.info("Legacy DB detected: faking migration 010_document_original_media.")

        # Si la table facet_profiles existe, l'utilisateur a la v11
        if "011_add_facet_profile" not in done_migrations:
            if db.table_exists("facet_profiles"):
                router.model.create(name="011_add_facet_profile")
                logging.info("Legacy DB detected: faking migration 011_add_facet_profile.")

        # Nettoyage et synchronisation de la table note_chunk_links
        if db.table_exists("note_chunk_links"):
            try:
                db.execute_sql("CREATE UNIQUE INDEX IF NOT EXISTS note_chunk_links_note_chunk ON note_chunk_links (note_id, chunk_id);")
            except Exception as e:
                logging.debug(f"Notice on note_chunk_links index: {e}")

    logging.info("Lancement des migrations via peewee-migrate...")
    try:
        # Exécute toutes les migrations en attente
        router.run()
        logging.info("Migrations terminées avec succès.")
    except (peewee.DatabaseError, sqlite3.Error) as e:
        logging.error(f"Erreur lors de l'exécution des migrations : {e}")
        # On ne bloque pas forcément l'appli si c'est une erreur mineure,
        # mais on logge l'alerte critique.
        raise
