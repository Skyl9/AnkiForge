"""Migration 045 : axe *Origine* du conteneur structurel et colonne des régions neutralisées (ADR 0010).

La 043 a persistant un booléen `is_structural_container` sans dire **pourquoi** un fragment
sortait du dénominateur de couverture. Deux causes cohabitaient sous le même drapeau : une
déduction de structure, et une décision de l'utilisateur. Les confondre rendait le verdict
inéditable et non gouvernable — impossible de distinguer un conteneur qu'on peut lever d'un
conteneur que l'utilisateur a explicitement neutralisé.

La migration ajoute donc deux colonnes :

- `document_chunks.container_origin`, l'**axe** du drapeau existant : `derived`, `declared`, ou
  `NULL` pour une unité de cours. Ce n'est pas un second drapeau, c'est la cause.
- `documentmodel.neutralized_regions`, les adresses de région que l'utilisateur **neutralise** —
  elles ne sortent que du dénominateur, le document les conservant. Colonne distincte
  d'`excluded_headings`, qui porte le verbe voisin mais différent : **écarter**.

`excluded_headings` n'est ni renommée ni repeuplée : ses entrées sans préfixe restent lues
comme des exclusions de lignée, si bien qu'aucune migration de données n'est nécessaire et
qu'un profil existant conserve exactement son comportement.

Les conteneurs déjà marqués sont estampillés `derived` : la 043 les ayant produits par la
seule heuristique structurelle, c'est l'origine exacte de ce qu'elle a écrit. Sans ce
remplissage, un profil existant verrait ses conteneurs retomber à « unité de cours » — donc
réintégrés au dénominateur — entre la migration et la prochaine réingestion.
"""

import logging

import peewee as pw
from peewee_migrate import Migrator

logger = logging.getLogger(__name__)


def backfill(database: pw.Database) -> None:
    """Estampille `derived` les conteneurs structurels déjà marqués.

    Exécuté par le migrateur *après* les ALTER TABLE, jamais par `migrate` lui-même.
    """
    from ankiforge.database.models.rag import DocumentChunkModel

    with DocumentChunkModel.bind_ctx(database):
        marked = DocumentChunkModel.update(container_origin="derived").where(DocumentChunkModel.is_structural_container == True, DocumentChunkModel.container_origin.is_null()).execute()  # noqa: E712
    if marked:
        logger.info("Migration 045 : %d conteneur(s) structurel(s) estampillé(s) « derived ».", marked)


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 045 : ajoute `container_origin` et `neutralized_regions`, puis estampille l'origine dérivée."""
    if fake:
        # peewee_migrate rejoue en `fake` les migrations déjà appliquées pour reconstruire son
        # instantané ORM, sans exécuter la moindre instruction SQL. Les colonnes doivent y figurer :
        # c'est ce que `remove_fields` retrouve au `rollback`. `execute_sql` étant simulé ici,
        # aucune introspection n'est possible.
        migrator.add_fields("document_chunks", container_origin=pw.CharField(null=True))
        migrator.add_fields("documentmodel", neutralized_regions=pw.TextField(null=True))
        return

    # La décision d'ajouter est prise *avant* l'empilement : `add_fields` ne vidange la file du
    # migrateur qu'après le retour de `migrate`, donc une colonne empilée ici reste invisible à
    # `get_columns` jusqu'à la migration suivante.
    needs_origin = database.table_exists("document_chunks") and "container_origin" not in [col.name for col in database.get_columns("document_chunks")]
    if needs_origin:
        migrator.add_fields("document_chunks", container_origin=pw.CharField(null=True))

    if database.table_exists("documentmodel") and "neutralized_regions" not in [col.name for col in database.get_columns("documentmodel")]:
        migrator.add_fields("documentmodel", neutralized_regions=pw.TextField(null=True))

    # Le remplissage est donc empilé à son tour : l'exécuter ici viserait une colonne absente.
    if needs_origin:
        migrator.run(backfill, database)


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 045 : suppression de `container_origin` et `neutralized_regions`.

    L'axe d'origine est reconstructible par la seule structure du document, mais
    `neutralized_regions` ne l'est pas : la rollback perd les neutralisations déclarées, comme
    toute migration qui retire une déclaration de l'utilisateur.
    """
    if fake:
        return

    if database.table_exists("document_chunks") and "container_origin" in [col.name for col in database.get_columns("document_chunks")]:
        migrator.remove_fields("document_chunks", "container_origin")
    if database.table_exists("documentmodel") and "neutralized_regions" in [col.name for col in database.get_columns("documentmodel")]:
        migrator.remove_fields("documentmodel", "neutralized_regions")
