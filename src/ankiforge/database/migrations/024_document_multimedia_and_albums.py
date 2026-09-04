import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 024 : Albums d'images, DocumentPageModel et champs multimodaux pour les chunks."""
    if not fake:
        # 1. Total pages sur DocumentModel
        if database.table_exists("documentmodel"):
            cols = [col.name for col in database.get_columns("documentmodel")]
            if "total_pages" not in cols:
                migrator.add_fields("documentmodel", total_pages=pw.IntegerField(default=1))

        # 2. Table document_pages pour DocumentPageModel
        if not database.table_exists("document_pages"):

            @migrator.create_model
            class DocumentPageModel(pw.Model):
                id = pw.AutoField()
                document = pw.ForeignKeyField(
                    column_name="document_id",
                    field="id",
                    model=migrator.orm["documentmodel"],
                    on_delete="CASCADE",
                )
                media = pw.ForeignKeyField(
                    column_name="media_id",
                    field="id",
                    model=migrator.orm["mediamodel"],
                    on_delete="CASCADE",
                )
                page_number = pw.IntegerField(default=1)
                rotation = pw.IntegerField(default=0)
                crop_data = pw.CharField(max_length=255, null=True)
                ocr_text = pw.TextField(default="")
                bounding_boxes = pw.TextField(null=True)
                status = pw.CharField(max_length=255, default="ready")

                class Meta:
                    table_name = "document_pages"
                    indexes = [(("document", "page_number"), True)]

        # 3. Champs multimodaux sur document_chunks
        if database.table_exists("document_chunks"):
            chunk_cols = [col.name for col in database.get_columns("document_chunks")]
            if "start_time" not in chunk_cols:
                migrator.add_fields("document_chunks", start_time=pw.FloatField(null=True))
            if "end_time" not in chunk_cols:
                migrator.add_fields("document_chunks", end_time=pw.FloatField(null=True))
            if "media_id" not in chunk_cols:
                migrator.add_fields(
                    "document_chunks",
                    media_id=pw.ForeignKeyField(
                        column_name="media_id",
                        field="id",
                        model=migrator.orm["mediamodel"],
                        null=True,
                        on_delete="SET NULL",
                    ),
                )
            if "bounding_box" not in chunk_cols:
                migrator.add_fields("document_chunks", bounding_box=pw.CharField(max_length=255, null=True))


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 024 : Suppression de document_pages et des champs multimodaux."""
    if not fake:
        if database.table_exists("document_chunks"):
            chunk_cols = [col.name for col in database.get_columns("document_chunks")]
            to_remove = [c for c in ["start_time", "end_time", "media_id", "bounding_box"] if c in chunk_cols]
            if to_remove:
                migrator.remove_fields("document_chunks", *to_remove)

        if database.table_exists("document_pages"):
            migrator.remove_model("document_pages")

        if database.table_exists("documentmodel"):
            cols = [col.name for col in database.get_columns("documentmodel")]
            if "total_pages" in cols:
                migrator.remove_fields("documentmodel", "total_pages")
