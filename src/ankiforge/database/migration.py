import logging

from peewee import CharField, DateTimeField, SQL, OperationalError
from peewee_migrate.cli import migrate
from playhouse.migrate import SqliteMigrator

from ankiforge.database.models import db, SchemaVersionModel


def run_migrations() -> None:
    """Évalue la version de la base de données et exécute les migrations nécessaires."""

    # 1. S'assurer que la table de version existe (cas des anciens utilisateurs)
    db.create_tables([SchemaVersionModel], safe=True)

    # 2. Récupérer la version actuelle
    version_record, _ = SchemaVersionModel.get_or_create(id=1, defaults={"version": 1})
    current_version = version_record.version

    migrator = SqliteMigrator(db)

    # --- MIGRATION V1 -> V2 ---
    # Objectif : Ajout de 'output_format' et 'created_at' dans la table 'agents'
    if current_version < 2:
        logging.info("Exécution de la migration de la base de données vers v2...")
        try:
            with db.atomic():
                output_format_field = CharField(default="json")
                created_at_field = DateTimeField(constraints=[SQL("DEFAULT CURRENT_TIMESTAMP")])

                migrate(
                    migrator.add_column("agents", "output_format", output_format_field),
                    migrator.add_column("agents", "created_at", created_at_field),
                )

            # Mise à jour de la version uniquement si la transaction réussit
            version_record.version = 2
            version_record.save()
            logging.info("Migration v2 réussie.")

        except OperationalError as e:
            # Gère le cas où l'utilisateur a déjà la colonne (ex: suite à vos tests manuels précédents)
            logging.warning(f"Migration v2 ignorée ou partiellement appliquée : {e}")
            version_record.version = 2
            version_record.save()

    # --- MIGRATIONS FUTURES (V2 -> V3, etc.) ---
    # if current_version < 3:
    #     ...
