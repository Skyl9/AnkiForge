import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 042 : traçabilité du palier de résolution sur note_chunk_links.

    Le rattachement d'une note à un fragment est un raisonnement **permissif** à paliers
    (identité exacte → section → page → recouvrement lexical). Sans trace du palier gagnant,
    la couverture affichée est indiscernable d'un rattachement prouvé et d'un rattachement
    seulement présumé — et un faux lien silencieux est plus trompeur que son absence.

    La colonne est nullable : les liens écrits avant cette migration n'ont pas de palier
    connu, et inscrire `NULL = lexique` serait une affirmation fausse.

    Une seule opération `add_fields` suffit : `index=True` fait que l'opération `add_column`
    de peewee_migrate enchaîne elle-même le `CREATE INDEX`. Appeler en plus `add_index`
    produirait deux `CREATE INDEX` de même nom, le second en échec.
    """
    if not fake and database.table_exists("note_chunk_links"):
        cols = [col.name for col in database.get_columns("note_chunk_links")]
        if "resolution" not in cols:
            migrator.add_fields("note_chunk_links", resolution=pw.CharField(null=True, index=True))


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 042 : Suppression de resolution de note_chunk_links.

    Le `DROP INDEX` est exécuté immédiatement, alors que `remove_fields` est différé et
    appliqué au flush du migrateur : l'ordre est donc le bon, l'index devant disparaître
    avant la colonne (SQLite refuse de supprimer une colonne indexée).
    `migrator.drop_index` n'est pas utilisé : il reconstruit un nom d'index vide et
    produirait un `DROP INDEX note_chunk_links` sur un index inexistant.
    """
    if not fake and database.table_exists("note_chunk_links"):
        database.execute_sql("DROP INDEX IF EXISTS note_chunk_links_resolution;")
        cols = [col.name for col in database.get_columns("note_chunk_links")]
        if "resolution" in cols:
            migrator.remove_fields("note_chunk_links", "resolution")
