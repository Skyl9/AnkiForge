import datetime

import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Crée les tables pour le linter modulaire et la persistance des audits."""

    @migrator.create_model
    class LinterRuleModel(pw.Model):
        id = pw.AutoField()
        name = pw.CharField(max_length=255, unique=True)
        description = pw.TextField(null=True)
        is_active = pw.BooleanField(default=True)
        prompt_injection = pw.TextField()
        example_bad = pw.TextField(null=True)
        example_good = pw.TextField(null=True)

        class Meta:
            table_name = "linter_rules"

    @migrator.create_model
    class AuditRecordModel(pw.Model):
        id = pw.AutoField()
        # Clés étrangères vers NoteModel et NoteVersionModel existants
        note = pw.ForeignKeyField(column_name="note_id", field="id", model=migrator.orm["notemodel"], on_delete="CASCADE")
        note_version = pw.ForeignKeyField(column_name="note_version_id", field="id", model=migrator.orm["noteversionmodel"], on_delete="CASCADE")

        is_compliant = pw.BooleanField(default=True)
        rule_broken = pw.CharField(max_length=255, null=True)
        reason = pw.TextField(null=True)
        suggestion = pw.TextField(null=True)
        analyzed_at = pw.DateTimeField(default=datetime.datetime.now)

        class Meta:
            table_name = "audit_records"
            # Index unique composite pour s'assurer qu'une version précise d'une note n'a qu'un seul résultat d'audit actif
            indexes = [(("note", "note_version"), True)]


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Supprime les tables du linter et des audits en cas d'annulation."""
    migrator.remove_model("audit_records")
    migrator.remove_model("linter_rules")
