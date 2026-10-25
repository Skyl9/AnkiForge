"""Migration 047 : Table staged_bundles et ajout de bundle_id et step_order sur staged_patches."""

from __future__ import annotations

import datetime
import logging

import peewee as pw
from peewee_migrate import Migrator

logger = logging.getLogger(__name__)


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 047 : Création de staged_bundles et extension de staged_patches."""
    if fake:
        return

    if not database.table_exists("staged_bundles"):

        @migrator.create_model
        class StagedBundleModel(pw.Model):
            id = pw.AutoField()
            bundle_id = pw.CharField(unique=True, index=True)
            title = pw.CharField(max_length=255)
            explanation = pw.TextField(default="")
            status = pw.CharField(default="pending", index=True)
            total_steps = pw.IntegerField(default=0)
            current_step = pw.IntegerField(default=1)
            created_at = pw.DateTimeField(default=datetime.datetime.now)
            applied_at = pw.DateTimeField(null=True)

            class Meta:
                table_name = "staged_bundles"

    if database.table_exists("staged_patches"):
        cols = [col.name for col in database.get_columns("staged_patches")]
        if "bundle_id" not in cols:
            try:
                if "staged_bundles" in migrator.orm:
                    migrator.add_fields(
                        "staged_patches",
                        bundle=pw.ForeignKeyField(
                            column_name="bundle_id",
                            field="id",
                            model=migrator.orm["staged_bundles"],
                            null=True,
                            on_delete="CASCADE",
                        ),
                    )
                else:
                    migrator.add_fields(
                        "staged_patches",
                        bundle_id=pw.IntegerField(null=True, index=True),
                    )
            except Exception as e:
                logger.warning("Erreur add_fields bundle_id sur staged_patches : %s", e)
        if "step_order" not in cols:
            try:
                migrator.add_fields("staged_patches", step_order=pw.IntegerField(default=1))
            except Exception as e:
                logger.warning("Erreur add_fields step_order sur staged_patches : %s", e)

    logger.info("Migration 047 : Table staged_bundles et colonnes de bundle enregistrées avec succès.")


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 047 : Suppression des colonnes bundle et de la table staged_bundles."""
    if fake:
        return

    if database.table_exists("staged_patches"):
        try:
            database.execute_sql("DROP INDEX IF EXISTS idx_staged_patches_bundle_id;")
            database.execute_sql("DROP INDEX IF EXISTS idx_staged_patches_step_order;")
        except Exception as e:
            logger.debug("Remarque suppression index staged_patches : %s", e)

        cols = [col.name for col in database.get_columns("staged_patches")]
        if "bundle_id" in cols:
            try:
                database.execute_sql("ALTER TABLE staged_patches DROP COLUMN bundle_id;")
            except Exception as e:
                logger.warning("Erreur suppression colonne bundle_id : %s", e)
        if "step_order" in cols:
            try:
                database.execute_sql("ALTER TABLE staged_patches DROP COLUMN step_order;")
            except Exception as e:
                logger.warning("Erreur suppression colonne step_order : %s", e)

    if database.table_exists("staged_bundles"):
        try:
            database.execute_sql("DROP TABLE IF EXISTS staged_bundles;")
        except Exception as e:
            logger.warning("Erreur suppression table staged_bundles : %s", e)

    logger.info("Rollback 047 achevé.")
