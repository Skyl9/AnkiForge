"""Migration 011 : profils de facettes cognitives et rattachement optionnel des facettes."""

from contextlib import suppress

import peewee as pw
from peewee_migrate import Migrator

with suppress(ImportError):
    pass


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Crée la table `facet_profiles` et rattache les facettes cognitives à un profil."""

    @migrator.create_model
    class FacetProfileModel(pw.Model):
        id = pw.AutoField()
        name = pw.CharField(max_length=255, unique=True)
        description = pw.TextField(null=True)
        is_active = pw.BooleanField(default=False)

        class Meta:
            table_name = "facet_profiles"

    if "cognitive_facets" in migrator.orm:
        migrator.add_fields("cognitive_facets", profile=pw.ForeignKeyField(column_name="profile_id", field="id", model=migrator.orm["facet_profiles"], null=True, on_delete="CASCADE"))


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Détache les facettes cognitives puis supprime la table `facet_profiles`."""
    migrator.remove_fields("cognitive_facets", "profile")
    migrator.drop_index("cognitive_facets", "profile")
    migrator.remove_model("facet_profiles")
