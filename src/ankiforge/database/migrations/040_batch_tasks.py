import datetime
import logging

import peewee as pw
from peewee_migrate import Migrator

logger = logging.getLogger(__name__)


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 040 : persistance de la file par lots (batch_runs + batch_tasks)."""

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

    if not fake:
        try:
            database.execute_sql("CREATE INDEX IF NOT EXISTS idx_batch_tasks_status ON batch_tasks (status);")
        except Exception as err:
            logger.debug("Création index batch_tasks ignorée : %s", err)


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 040 : Supprime les tables de la file par lots."""
    migrator.remove_model("batch_tasks")
    migrator.remove_model("batch_runs")
