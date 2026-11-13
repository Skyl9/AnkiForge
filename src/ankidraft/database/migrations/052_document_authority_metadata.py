"""Migration 052 : Ajout des métadonnées d'autorité épistémique aux documents.

Ajoute sur DocumentModel :
- authority_score : score de fiabilité normalisé (0.0 - 100.0), indexé
- authority_type : type d'autorité (RFC, ACADEMIC, OFFICIAL_DOC, COURSE, etc.), indexé
- authority_certificate : payload JSON complet du certificat d'autorité
- source_sha256 : empreinte cryptographique du contenu source (64 chars), indexée
"""

from peewee import CharField, FloatField, TextField
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database, fake=False, **kwargs):
    """Ajoute les colonnes d'autorité épistémique à la table documents."""
    migrator.add_fields(
        "documentmodel",
        authority_score=FloatField(null=True, index=True),
        authority_type=CharField(null=True, index=True, max_length=64),
        authority_certificate=TextField(null=True),
        source_sha256=CharField(max_length=64, null=True, index=True),
    )


def rollback(migrator: Migrator, database, fake=False, **kwargs):
    """Supprime les colonnes d'autorité épistémique."""
    migrator.remove_fields(
        "documentmodel",
        "authority_score",
        "authority_type",
        "authority_certificate",
        "source_sha256",
    )
