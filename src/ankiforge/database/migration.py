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
