import datetime
import logging

import peewee as pw
from peewee_migrate import Migrator

logger = logging.getLogger(__name__)


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 039 : Crée la table pipeline_runs pour la persistance et la reprise des runs DAG."""

    @migrator.create_model
    class PipelineRunModel(pw.Model):
        id = pw.AutoField()
        pipeline_id = pw.IntegerField(index=True)
        status = pw.CharField(max_length=50, default="running", index=True)
        current_step_order = pw.IntegerField(null=True)
        state_data = pw.TextField(default="{}")
        error_message = pw.TextField(null=True)
        created_at = pw.DateTimeField(default=datetime.datetime.now, index=True)
        updated_at = pw.DateTimeField(default=datetime.datetime.now)

        class Meta:
            table_name = "pipeline_runs"

    if not fake:
        try:
            database.execute_sql("CREATE INDEX IF NOT EXISTS idx_pipeline_runs_pipeline_status ON pipeline_runs (pipeline_id, status);")
        except Exception as err:
            logger.debug("Création index pipeline_runs ignorée : %s", err)


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 039 : Supprime la table pipeline_runs."""
    migrator.remove_model("pipeline_runs")
