"""Peewee migrations -- 001_initial.py.

Some examples (model - class or model name)::

    > Model = migrator.orm['table_name']            # Return model in current state by name
    > Model = migrator.ModelClass                   # Return model in current state by name

    > migrator.sql(sql)                             # Run custom SQL
    > migrator.run(func, *args, **kwargs)           # Run python function with the given args
    > migrator.create_model(Model)                  # Create a model (could be used as decorator)
    > migrator.remove_model(model, cascade=True)    # Remove a model
    > migrator.add_fields(model, **fields)          # Add fields to a model
    > migrator.change_fields(model, **fields)       # Change fields
    > migrator.remove_fields(model, *field_names, cascade=True)
    > migrator.rename_field(model, old_field_name, new_field_name)
    > migrator.rename_table(model, new_table_name)
    > migrator.add_index(model, *col_names, unique=False)
    > migrator.add_not_null(model, *field_names)
    > migrator.add_default(model, field_name, default)
    > migrator.add_constraint(model, name, sql)
    > migrator.drop_index(model, *col_names)
    > migrator.drop_not_null(model, *field_names)
    > migrator.drop_constraints(model, *constraints)

"""

from contextlib import suppress

import peewee as pw
from peewee_migrate import Migrator


with suppress(ImportError):
    pass


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your migrations here."""

    @migrator.create_model
    class AgentModel(pw.Model):
        id = pw.AutoField()
        name = pw.CharField(max_length=255, unique=True)
        description = pw.TextField(null=True)
        system_prompt = pw.TextField()
        output_format = pw.CharField(default="json", max_length=255)
        created_at = pw.DateTimeField(constraints=[pw.SQL("DEFAULT CURRENT_TIMESTAMP")])

        class Meta:
            table_name = "agents"

    @migrator.create_model
    class NoteTypeModel(pw.Model):
        id = pw.AutoField()
        anki_id = pw.BigIntegerField(null=True, unique=True)
        name = pw.CharField(max_length=255, unique=True)
        fields_schema = pw.TextField()
        templates = pw.TextField()
        css_style = pw.TextField()

        class Meta:
            table_name = "notetypemodel"

    @migrator.create_model
    class NoteModel(pw.Model):
        id = pw.AutoField()
        anki_id = pw.BigIntegerField(null=True, unique=True)
        guid = pw.CharField(max_length=255, unique=True)
        note_type = pw.ForeignKeyField(column_name="note_type_id", field="id", model=migrator.orm["notetypemodel"])
        tags = pw.TextField(null=True)
        status = pw.CharField(default="new", max_length=255)

        class Meta:
            table_name = "notemodel"

    @migrator.create_model
    class DeckModel(pw.Model):
        id = pw.AutoField()
        anki_id = pw.BigIntegerField(null=True, unique=True)
        parent_deck = pw.ForeignKeyField(column_name="parent_deck_id", field="id", model="self", null=True)
        name = pw.CharField(max_length=255, unique=True)
        description = pw.TextField(null=True)
        created_at = pw.DateTimeField()

        class Meta:
            table_name = "deckmodel"

    @migrator.create_model
    class CardModel(pw.Model):
        id = pw.AutoField()
        anki_id = pw.BigIntegerField(null=True, unique=True)
        note = pw.ForeignKeyField(column_name="note_id", field="id", model=migrator.orm["notemodel"], on_delete="CASCADE")
        deck = pw.ForeignKeyField(column_name="deck_id", field="id", model=migrator.orm["deckmodel"], on_delete="CASCADE")
        template_index = pw.IntegerField(default=0)

        class Meta:
            table_name = "cardmodel"

    @migrator.create_model
    class FolderModel(pw.Model):
        id = pw.AutoField()
        name = pw.CharField(max_length=255, unique=True)

        class Meta:
            table_name = "foldermodel"

    @migrator.create_model
    class DocumentModel(pw.Model):
        id = pw.AutoField()
        title = pw.CharField(max_length=255, unique=True)
        content = pw.TextField()
        created_at = pw.DateTimeField()
        folder = pw.ForeignKeyField(column_name="folder_id", field="id", model=migrator.orm["foldermodel"], null=True, on_delete="CASCADE")

        class Meta:
            table_name = "documentmodel"

    @migrator.create_model
    class IgnoredDuplicateModel(pw.Model):
        id = pw.AutoField()
        note_a = pw.ForeignKeyField(column_name="note_a_id", field="id", model=migrator.orm["notemodel"], on_delete="CASCADE")
        note_b = pw.ForeignKeyField(column_name="note_b_id", field="id", model=migrator.orm["notemodel"], on_delete="CASCADE")

        class Meta:
            table_name = "ignored_duplicates"
            indexes = [(("note_a", "note_b"), True)]

    @migrator.create_model
    class JobModel(pw.Model):
        id = pw.AutoField()
        job_type = pw.CharField(max_length=255)
        target = pw.CharField(max_length=255)
        status = pw.CharField(default="pending", max_length=255)
        progress = pw.IntegerField(default=0)
        params = pw.TextField(null=True)
        error_log = pw.TextField(null=True)
        created_at = pw.DateTimeField()
        updated_at = pw.DateTimeField()

        class Meta:
            table_name = "jobmodel"

    @migrator.create_model
    class LLMConfigModel(pw.Model):
        id = pw.AutoField()
        display_name = pw.CharField(max_length=255, unique=True)
        provider = pw.CharField(max_length=255)
        model_id = pw.CharField(max_length=255)
        context_limit = pw.IntegerField(default=8192)
        temperature = pw.FloatField(default=0.7)
        api_key = pw.CharField(max_length=255, null=True)

        class Meta:
            table_name = "llm_configs"

    @migrator.create_model
    class NoteVersionModel(pw.Model):
        id = pw.AutoField()
        note = pw.ForeignKeyField(column_name="note_id", field="id", model=migrator.orm["notemodel"], on_delete="CASCADE")
        version_number = pw.IntegerField(default=1)
        content = pw.TextField()
        created_at = pw.DateTimeField()
        source = pw.CharField(default="ai", max_length=255)
        is_active = pw.BooleanField(default=True)

        class Meta:
            table_name = "noteversionmodel"

    @migrator.create_model
    class PipelineModel(pw.Model):
        id = pw.AutoField()
        name = pw.CharField(max_length=255, unique=True)
        description = pw.TextField(null=True)

        class Meta:
            table_name = "pipelines"

    @migrator.create_model
    class PipelineStepModel(pw.Model):
        id = pw.AutoField()
        pipeline = pw.ForeignKeyField(column_name="pipeline_id", field="id", model=migrator.orm["pipelines"], on_delete="CASCADE")
        agent = pw.ForeignKeyField(column_name="agent_id", field="id", model=migrator.orm["agents"], on_delete="CASCADE")
        step_order = pw.IntegerField()

        class Meta:
            table_name = "pipeline_steps"
            indexes = [(("pipeline", "step_order"), True)]

    @migrator.create_model
    class PromptModel(pw.Model):
        id = pw.AutoField()
        name = pw.CharField(max_length=255, unique=True)
        content = pw.TextField()
        description = pw.TextField(null=True)
        is_active = pw.BooleanField(default=True)

        class Meta:
            table_name = "promptmodel"

    @migrator.create_model
    class TokenUsageModel(pw.Model):
        id = pw.AutoField()
        provider = pw.CharField(max_length=255)
        model_id = pw.CharField(max_length=255)
        prompt_tokens = pw.IntegerField(default=0)
        completion_tokens = pw.IntegerField(default=0)
        total_tokens = pw.IntegerField(default=0)
        estimated_cost_usd = pw.FloatField(default=0.0)
        created_at = pw.DateTimeField()

        class Meta:
            table_name = "token_usage"


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your rollback migrations here."""

    migrator.remove_model("token_usage")

    migrator.remove_model("promptmodel")

    migrator.remove_model("pipeline_steps")

    migrator.remove_model("pipelines")

    migrator.remove_model("noteversionmodel")

    migrator.remove_model("llm_configs")

    migrator.remove_model("jobmodel")

    migrator.remove_model("ignored_duplicates")

    migrator.remove_model("documentmodel")

    migrator.remove_model("foldermodel")

    migrator.remove_model("cardmodel")

    migrator.remove_model("deckmodel")

    migrator.remove_model("notemodel")

    migrator.remove_model("notetypemodel")

    migrator.remove_model("agents")
