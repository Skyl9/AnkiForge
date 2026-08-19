import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Ajoute les colonnes de catégories, labels et style pour les règles d'audit Linter."""
    migrator.add_fields(
        "linter_rules",
        category=pw.CharField(max_length=255, default="cat-atomicite"),
        category_label=pw.CharField(max_length=255, default="Atomicité & Restructuration"),
        color=pw.CharField(max_length=50, default="#f87171"),
        icon_name=pw.CharField(max_length=100, default="squares-four"),
    )


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Supprime les colonnes de catégories lors du rollback."""
    migrator.remove_fields("linter_rules", "category", "category_label", "color", "icon_name")
