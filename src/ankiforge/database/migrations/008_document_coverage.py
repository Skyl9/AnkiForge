import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Crée les tables pour le Diagnostic Documentaire (Chunks, Facettes, Liens)."""

    @migrator.create_model
    class CognitiveFacetModel(pw.Model):
        id = pw.AutoField()
        name = pw.CharField(max_length=255, unique=True)
        description = pw.TextField(null=True)
        is_active = pw.BooleanField(default=True)

        class Meta:
            table_name = "cognitive_facets"

    @migrator.create_model
    class DocumentChunkModel(pw.Model):
        id = pw.AutoField()
        document = pw.ForeignKeyField(column_name="document_id", field="id", model=migrator.orm["documentmodel"], on_delete="CASCADE")
        chunk_index = pw.IntegerField()
        content = pw.TextField()
        content_hash = pw.CharField(max_length=255, index=True)
        is_profiled = pw.BooleanField(default=False)

        class Meta:
            table_name = "document_chunks"

    @migrator.create_model
    class ChunkFacetRequirementModel(pw.Model):
        id = pw.AutoField()
        chunk = pw.ForeignKeyField(column_name="chunk_id", field="id", model=migrator.orm["document_chunks"], on_delete="CASCADE")
        facet = pw.ForeignKeyField(column_name="facet_id", field="id", model=migrator.orm["cognitive_facets"], on_delete="CASCADE")

        class Meta:
            table_name = "chunk_facet_requirements"
            indexes = [(("chunk", "facet"), True)]

    @migrator.create_model
    class NoteChunkLinkModel(pw.Model):
        id = pw.AutoField()
        note = pw.ForeignKeyField(column_name="note_id", field="id", model=migrator.orm["notemodel"], on_delete="CASCADE")
        chunk = pw.ForeignKeyField(column_name="chunk_id", field="id", model=migrator.orm["document_chunks"], on_delete="CASCADE")
        facet = pw.ForeignKeyField(column_name="facet_id", field="id", model=migrator.orm["cognitive_facets"], null=True, on_delete="SET NULL")
        is_hallucinating = pw.BooleanField(default=False)

        class Meta:
            table_name = "note_chunk_links"
            indexes = [(("note", "chunk", "facet"), True)]


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    migrator.remove_model("note_chunk_links")
    migrator.remove_model("chunk_facet_requirements")
    migrator.remove_model("document_chunks")
    migrator.remove_model("cognitive_facets")
