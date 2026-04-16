import logging
import os
import sqlite3
import peewee
from peewee_migrate import Router
from ankiforge.database.models import db, SchemaVersionModel

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

    # 2. Gestion de la transition depuis l'ancien système manuel (SchemaVersionModel)
    db.create_tables([SchemaVersionModel], safe=True)
    version_record, _ = SchemaVersionModel.get_or_create(id=1, defaults={"version": 1})

    # Si l'utilisateur est déjà en v2 via l'ancien système, on peut marquer
    # la migration 001_initial comme déjà faite si on veut éviter des logs de création
    # Mais peewee-migrate utilise 'CREATE TABLE IF NOT EXISTS' par défaut avec migrator.create_table
    # donc c'est sans danger de laisser rouler.

    logging.info("Lancement des migrations via peewee-migrate...")
    try:
        # Exécute toutes les migrations en attente
        router.run()

        # On met à jour l'ancienne table de version pour indiquer que peewee-migrate a pris le relais
        if version_record.version < 100:
            version_record.version = 100  # Marqueur arbitraire pour "Migré vers peewee-migrate"
            version_record.save()

        logging.info("Migrations terminées avec succès.")

    except (peewee.DatabaseError, sqlite3.Error) as e:
        logging.error(f"Erreur lors de l'exécution des migrations : {e}")
        # On ne bloque pas forcément l'appli si c'est une erreur mineure,
        # mais on logge l'alerte critique.
        raise
