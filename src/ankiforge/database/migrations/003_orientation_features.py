import datetime

import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Ajoute les champs pour la synchro bidirectionnelle, les pipelines conditionnels et la gestion des médias."""

    # 1. Ajout des champs sur la table notemodel
    migrator.add_fields(
        "notemodel",
        last_synced_at=pw.DateTimeField(null=True),
        anki_content_hash=pw.CharField(max_length=255, null=True),
    )

    # 2. Ajout des champs sur la table pipeline_steps
    migrator.add_fields(
        "pipeline_steps",
        on_success_step=pw.ForeignKeyField(column_name="on_success_step_id", field="id", model="self", null=True, on_delete="SET NULL"),
        on_failure_step=pw.ForeignKeyField(column_name="on_failure_step_id", field="id", model="self", null=True, on_delete="SET NULL"),
        failure_behavior=pw.CharField(default="stop", max_length=255),
    )

    # 3. Création du modèle MediaModel (table mediamodel)
    @migrator.create_model
    class MediaModel(pw.Model):
        id = pw.AutoField()
        filename = pw.CharField(max_length=255, unique=True)
        original_name = pw.CharField(max_length=255)
        checksum = pw.CharField(max_length=255, unique=True)
        mime_type = pw.CharField(max_length=255)
        created_at = pw.DateTimeField(default=datetime.datetime.now)

        class Meta:
            table_name = "mediamodel"

    # 4. Création du modèle NoteVersionMediaModel (table noteversionmediamodel)
    @migrator.create_model
    class NoteVersionMediaModel(pw.Model):
        id = pw.AutoField()
        note_version = pw.ForeignKeyField(column_name="note_version_id", field="id", model=migrator.orm["noteversionmodel"], on_delete="CASCADE")
        media = pw.ForeignKeyField(column_name="media_id", field="id", model=migrator.orm["mediamodel"], on_delete="RESTRICT")

        class Meta:
            table_name = "noteversionmediamodel"


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Annule la migration et retire les tables et champs créés."""

    # 1. Suppression des modèles créés (dans l'ordre inverse des dépendances)
    migrator.remove_model("noteversionmediamodel")
    migrator.remove_model("mediamodel")

    # 2. Suppression des champs ajoutés à pipeline_steps
    migrator.remove_fields("pipeline_steps", "on_success_step", "on_failure_step", "failure_behavior")

    # 3. Suppression des champs ajoutés à notemodel
    migrator.remove_fields("notemodel", "last_synced_at", "anki_content_hash")
