import datetime
import logging

import peewee as pw
from peewee_migrate import Migrator

logger = logging.getLogger(__name__)


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 041 : Table des patchs chirurgicaux en attente (StagedPatchModel)."""

    @migrator.create_model
    class StagedPatchModel(pw.Model):
        id = pw.AutoField()
        patch_id = pw.CharField(unique=True, index=True)
        patch_type = pw.CharField()
        target_id = pw.IntegerField(default=0)
        original_version_id = pw.IntegerField(null=True)
        diff_payload = pw.TextField()
        status = pw.CharField(default="pending", index=True)
        created_at = pw.DateTimeField(default=datetime.datetime.now)
        applied_at = pw.DateTimeField(null=True)

        class Meta:
            table_name = "staged_patches"

    if not fake:
        try:
            database.execute_sql("CREATE INDEX IF NOT EXISTS idx_staged_patches_status ON staged_patches (status);")
            database.execute_sql("CREATE INDEX IF NOT EXISTS idx_staged_patches_patch_id ON staged_patches (patch_id);")
        except Exception as e:
            logger.warning("Erreur création index staged_patches : %s", e)
