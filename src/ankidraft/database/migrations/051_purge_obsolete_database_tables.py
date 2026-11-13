"""Migration 051 : Dépose physique des tables obsolètes (jobmodel, promptmodel, ai_cache, noteversionmediamodel, batch_tasks, batch_runs)."""

from __future__ import annotations

import datetime
import logging

import peewee as pw
from peewee_migrate import Migrator

logger = logging.getLogger(__name__)

OBSOLETE_TABLES: list[str] = [
    "noteversionmediamodel",
    "batch_tasks",
    "batch_runs",
    "jobmodel",
    "promptmodel",
    "ai_cache",
]

OBSOLETE_INDEXES: list[str] = [
    "idx_batch_tasks_status",
    "batch_tasks_status",
    "idx_batch_tasks_task_id",
    "batch_tasks_task_id",
    "idx_batch_tasks_created_at",
    "batch_tasks_created_at",
    "idx_batch_runs_started_at",
    "batch_runs_started_at",
    "idx_ai_cache_prompt_hash",
    "ai_cache_prompt_hash",
    "ai_cache_prompt_hash_system_prompt_hash_model_id_temperature",
    "idx_jobmodel_target",
    "jobmodel_target",
    "idx_promptmodel_name",
    "promptmodel_name",
    "idx_noteversionmediamodel_note_version_id",
    "noteversionmediamodel_note_version_id",
    "idx_noteversionmediamodel_media_id",
    "noteversionmediamodel_media_id",
]


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 051 : Supprime de façon ordonnée et idempotente les tables et index obsolètes."""
    if fake:
        return

    # 1. Suppression défensive des index associés
    for idx_name in OBSOLETE_INDEXES:
        try:
            database.execute_sql(f"DROP INDEX IF EXISTS {idx_name};")
        except Exception as err:
            logger.debug("Suppression défensive index %s ignorée : %s", idx_name, err)

    # 2. Suppression ordonnée des tables
    for table in OBSOLETE_TABLES:
        if database.table_exists(table):
            try:
                migrator.remove_model(table)
            except Exception as err:
                logger.debug("remove_model(%s) a échoué (%s), repli sur DROP TABLE :", table, err)
                database.execute_sql(f"DROP TABLE IF EXISTS {table};")

    migrator()

    logger.info("Migration 051 : 6 tables obsolètes et leurs index supprimés avec succès.")


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 051 : Recrée fidèlement la structure DDL des 6 tables obsolètes."""
    if fake:
        return

    # 1. JobModel (table jobmodel)
    if not database.table_exists("jobmodel"):

        @migrator.create_model
        class JobModel(pw.Model):
            id = pw.AutoField()
            job_type = pw.CharField(max_length=255)
            target = pw.CharField(max_length=255)
            status = pw.CharField(default="pending", max_length=255)
            progress = pw.IntegerField(default=0)
            params = pw.TextField(null=True)
            error_log = pw.TextField(null=True)
            created_at = pw.DateTimeField(default=datetime.datetime.now)
            updated_at = pw.DateTimeField(default=datetime.datetime.now)

            class Meta:
                table_name = "jobmodel"

    # 2. PromptModel (table promptmodel)
    if not database.table_exists("promptmodel"):

        @migrator.create_model
        class PromptModel(pw.Model):
            id = pw.AutoField()
            name = pw.CharField(max_length=255, unique=True)
            content = pw.TextField()
            description = pw.TextField(null=True)
            is_active = pw.BooleanField(default=True)

            class Meta:
                table_name = "promptmodel"

    # 3. AICacheModel (table ai_cache)
    if not database.table_exists("ai_cache"):

        @migrator.create_model
        class AICacheModel(pw.Model):
            id = pw.AutoField()
            prompt_hash = pw.CharField(max_length=255, index=True)
            system_prompt_hash = pw.CharField(max_length=255)
            model_id = pw.CharField(max_length=255)
            temperature = pw.FloatField()
            response_content = pw.TextField()
            created_at = pw.DateTimeField(default=datetime.datetime.now)

            class Meta:
                table_name = "ai_cache"
                indexes = [(("prompt_hash", "system_prompt_hash", "model_id", "temperature"), True)]

    # 4. NoteVersionMediaModel (table noteversionmediamodel)
    if not database.table_exists("noteversionmediamodel"):
        if "noteversionmodel" in migrator.orm and "mediamodel" in migrator.orm:

            @migrator.create_model
            class NoteVersionMediaModel(pw.Model):
                id = pw.AutoField()
                note_version = pw.ForeignKeyField(
                    column_name="note_version_id",
                    field="id",
                    model=migrator.orm["noteversionmodel"],
                    on_delete="CASCADE",
                )
                media = pw.ForeignKeyField(
                    column_name="media_id",
                    field="id",
                    model=migrator.orm["mediamodel"],
                    on_delete="RESTRICT",
                )

                class Meta:
                    table_name = "noteversionmediamodel"

        else:

            @migrator.create_model
            class NoteVersionMediaModelFallback(pw.Model):
                id = pw.AutoField()
                note_version_id = pw.IntegerField(index=True)
                media_id = pw.IntegerField(index=True)

                class Meta:
                    table_name = "noteversionmediamodel"

    # 5. BatchRunModel (table batch_runs)
    if not database.table_exists("batch_runs"):

        @migrator.create_model
        class BatchRunModel(pw.Model):
            id = pw.AutoField()
            total_tasks = pw.IntegerField(default=0)
            success_count = pw.IntegerField(default=0)
            error_count = pw.IntegerField(default=0)
            total_cards = pw.IntegerField(default=0)
            started_at = pw.DateTimeField(default=datetime.datetime.now, index=True)
            finished_at = pw.DateTimeField(null=True)
            meta_data = pw.TextField(default="{}")

            class Meta:
                table_name = "batch_runs"

    # 6. BatchTaskModel (table batch_tasks)
    if not database.table_exists("batch_tasks"):

        @migrator.create_model
        class BatchTaskModel(pw.Model):
            id = pw.AutoField()
            task_id = pw.CharField(index=True)
            doc_id = pw.IntegerField(null=True)
            doc_title = pw.CharField(default="")
            deck_id = pw.IntegerField(null=True)
            deck_name = pw.CharField(default="Général")
            model_id = pw.IntegerField(null=True)
            model_name = pw.CharField(default="Basic")
            pipeline_id = pw.IntegerField(null=True)
            pipeline_name = pw.CharField(default="Standard")
            llm_id = pw.IntegerField(null=True)
            selection_mode = pw.CharField(default="sections")
            scope_json = pw.TextField(default="{}")
            config_json = pw.TextField(default="{}")
            status = pw.CharField(default="queued", index=True)
            attempt = pw.IntegerField(default=0)
            cards_json = pw.TextField(default="[]")
            error = pw.TextField(null=True)
            auto_validation = pw.BooleanField(default=False)
            use_vision = pw.BooleanField(default=False)
            temperature = pw.FloatField(default=0.7)
            max_tokens = pw.IntegerField(default=16384)
            strict_source_grounding = pw.BooleanField(default=True)
            created_at = pw.DateTimeField(default=datetime.datetime.now)
            updated_at = pw.DateTimeField(default=datetime.datetime.now)

            class Meta:
                table_name = "batch_tasks"

        try:
            database.execute_sql("CREATE INDEX IF NOT EXISTS idx_batch_tasks_status ON batch_tasks (status);")
        except Exception as err:
            logger.debug("Recréation index idx_batch_tasks_status ignorée : %s", err)

    migrator()

    logger.info("Rollback 051 : 6 tables et index recréés avec succès.")
