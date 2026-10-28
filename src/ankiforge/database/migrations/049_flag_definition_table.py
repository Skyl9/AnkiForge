"""Migration 049 : Table de référence FlagDefinitionModel + ProfileFlagLabelModel + FK sur CardModel (idempotent)."""

import contextlib
import logging

logger = logging.getLogger(__name__)


def migrate(migrator, database, fake=False, **kwargs):
    # 1. Créer FlagDefinitionModel (idempotent)
    database.execute_sql(
        """
        CREATE TABLE IF NOT EXISTS flag_definition (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            value INTEGER NOT NULL UNIQUE CHECK (value BETWEEN 0 AND 7),
            name VARCHAR NOT NULL,
            color_hex VARCHAR NOT NULL,
            is_customizable BOOLEAN NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0
        );
        """
    )

    # 2. Pré-peupler les 8 drapeaux canoniques (idempotent : INSERT OR IGNORE)
    flags_data = [
        (0, "Aucun", "transparent", 0, 0),
        (1, "Rouge", "#ef4444", 1, 1),
        (2, "Orange", "#f97316", 1, 2),
        (3, "Vert", "#10b981", 1, 3),
        (4, "Bleu", "#3b82f6", 1, 4),
        (5, "Rose", "#ec4899", 1, 5),
        (6, "Turquoise", "#06b6d4", 1, 6),
        (7, "Violet", "#a855f7", 1, 7),
    ]

    for value, name, color_hex, is_customizable, sort_order in flags_data:
        database.execute_sql(
            "INSERT OR IGNORE INTO flag_definition (value, name, color_hex, is_customizable, sort_order) VALUES (?, ?, ?, ?, ?);",
            (value, name, color_hex, is_customizable, sort_order),
        )

    # 3. Créer ProfileFlagLabelModel (idempotent)
    database.execute_sql(
        """
        CREATE TABLE IF NOT EXISTS profile_flag_label (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_name VARCHAR NOT NULL,
            flag_definition_id INTEGER NOT NULL,
            custom_label VARCHAR,
            FOREIGN KEY (flag_definition_id) REFERENCES flag_definition (id) ON DELETE CASCADE,
            UNIQUE (profile_name, flag_definition_id)
        );
        """
    )

    # 4. Ajouter FK sur CardModel.flags → FlagDefinitionModel.value (idempotent)
    cols = [col.name for col in database.get_columns("cardmodel")]
    if "flag_definition_id" not in cols:
        database.execute_sql("ALTER TABLE cardmodel ADD COLUMN flag_definition_id INTEGER REFERENCES flag_definition(id) ON DELETE SET NULL;")

    # 5. Backfill : UPDATE cardmodel SET flag_definition_id = (SELECT id FROM flag_definition WHERE value = cardmodel.flags)
    # Sécurisé à réexécuter : met à jour seulement les lignes où flag_definition_id est NULL
    database.execute_sql(
        """
        UPDATE cardmodel
        SET flag_definition_id = (
            SELECT id FROM flag_definition WHERE flag_definition.value = cardmodel.flags
        )
        WHERE flag_definition_id IS NULL;
        """
    )

    # 6. La contrainte CHECK (flags BETWEEN 0 AND 7) est déjà définie dans CardModel
    # via constraints=[Check("flags BETWEEN 0 AND 7")]. SQLite ne supporte pas
    # ALTER TABLE ADD CONSTRAINT, donc on s'en remet à la validation Peewee.

    # 7. Migrer les libellés personnalisés existants depuis SettingsService (JSON)
    # Cela se fait via le service au démarrage, pas en SQL pur car il faut décoder le JSON par profil

    logger.info("Migration 049 : Table flag_definition, profile_flag_label et FK cardmodel appliquées (idempotent).")


def rollback(migrator, database, fake=False, **kwargs):
    # La contrainte CHECK est gérée au niveau modèle, pas de DROP CONSTRAINT en SQLite

    # Supprimer la colonne flag_definition_id de cardmodel
    with contextlib.suppress(Exception):
        database.execute_sql("ALTER TABLE cardmodel DROP COLUMN flag_definition_id;")

    # Supprimer les tables
    with contextlib.suppress(Exception):
        database.execute_sql("DROP TABLE IF EXISTS profile_flag_label;")
    with contextlib.suppress(Exception):
        database.execute_sql("DROP TABLE IF EXISTS flag_definition;")
