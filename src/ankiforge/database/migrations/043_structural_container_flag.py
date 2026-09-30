"""Migration 043 : drapeau « conteneur structurel » sur document_chunks.

Un titre parent réduit à sa ligne de titre et à moins de `MIN_CONTAINER_WORDS` mots
propres n'est pas une unité de cours : c'est un nœud d'organisation posé au-dessus de
sous-sections substantielles. Le compter comme une section à couvrir gonfle le
dénominateur de la couverture d'une unité qui ne se couvre pas, et l'affinement de liens
doit alors y loger une carte pour solder un trou qui n'existait pas.

Le drapeau est persisté pour que le score de couverture, l'arbre de l'inspecteur et
l'affinement de liens partagent une seule et même définition du conteneur, au lieu de
trois heuristiques divergentes recalculées séparément.

La colonne est Valuée pour les documents déjà indexés : sans ce remplissage, un profil
existant ne bénéficierait de la correction qu'à la prochaine réingestion, et son score de
couverture resterait faussé entre-temps.
"""

import re
from collections import defaultdict

import peewee as pw
from peewee_migrate import Migrator

#: Un titre parent sous ce nombre de mots (hors lignes de titre) n'est qu'un nœud d'organisation.
MIN_CONTAINER_WORDS = 25

#: Ligne de titre Markdown, dont le texte ne compte pas comme contenu de cours.
HEADING_LINE_REGEX = re.compile(r"^#{1,6}\s+")

#: Séparateur de niveaux dans un `heading_path` (« Chapitre > Sous-chapitre »).
HEADING_SEPARATOR = " > "

#: `(id, heading_path, content)` d'un fragment titré.
FragmentRow = tuple[int, str, "str | None"]


def _own_word_count(content: str | None) -> int:
    """Nombre de mots de contenu propre, lignes de titre exclues."""
    lines = (content or "").split("\n")
    return len(" ".join(line for line in lines if not HEADING_LINE_REGEX.match(line)).split())


def _descendant_prefixes(heading_paths: list[str]) -> set[str]:
    """Ensemble des préfixes de fil d'Ariane qui ouvrent au moins une sous-section.

    Un fil `P` a des descendants si et seulement si `P + " > "` ouvre l'un des autres
    fils. Recenser ces préfixes une fois pour toutes évite de comparer chaque fragment
    à tous les autres du document, coût qui devient quadratique sur un cours de
    plusieurs milliers de fragments.
    """
    prefixes: set[str] = set()
    for heading_path in heading_paths:
        start = 0
        while (index := heading_path.find(HEADING_SEPARATOR, start)) >= 0:
            prefixes.add(heading_path[: index + len(HEADING_SEPARATOR)])
            start = index + len(HEADING_SEPARATOR)
    return prefixes


def structural_container_ids(by_document: dict[int, list[FragmentRow]]) -> list[int]:
    """Identifiants des fragments qui ne sont que des conteneurs structurels.

    La parenté est résolue par document : deux documents peuvent porter le même fil
    d'Ariane, et « A > B » n'est un nœud d'organisation que s'il ouvre des
    sous-sections *de ce document-ci*.
    """
    container_ids: list[int] = []
    for doc_chunks in by_document.values():
        prefixes = _descendant_prefixes([heading_path for _id, heading_path, _content in doc_chunks])
        for chunk_id, heading_path, content in doc_chunks:
            if heading_path + HEADING_SEPARATOR in prefixes and _own_word_count(content) < MIN_CONTAINER_WORDS:
                container_ids.append(chunk_id)
    return container_ids


def backfill(database: pw.Database) -> None:
    """Marque les conteneurs structurels déjà indexés.

    Exécuté par le migrateur *après* l'ALTER TABLE, jamais par `migrate` lui-même.
    """
    cursor = database.execute_sql("SELECT id, document_id, heading_path, content FROM document_chunks WHERE heading_path IS NOT NULL AND heading_path != ''")
    by_document: dict[int, list[FragmentRow]] = defaultdict(list)
    for chunk_id, document_id, heading_path, content in cursor.fetchall():
        by_document[document_id].append((chunk_id, heading_path, content))

    container_ids = structural_container_ids(by_document)
    if not container_ids:
        return

    # peewee génère lui-même les placeholders du `IN (...)` : aucune chaîne SQL n'est
    # construite ici, donc rien à masquer d'un "# nosec B608". Les lots restent bornés
    # car SQLite plafonne le nombre de variables liées (SQLITE_MAX_VARIABLE_NUMBER).
    # `bind_ctx` (et non `bind`) car ce dernier rebind le modèle globalement et fuirait
    # la base du migrateur dans le reste du processus.
    from ankiforge.database.models.rag import DocumentChunkModel

    batch_size = 500
    with DocumentChunkModel.bind_ctx(database):
        for offset in range(0, len(container_ids), batch_size):
            batch = container_ids[offset : offset + batch_size]
            DocumentChunkModel.update(is_structural_container=True).where(DocumentChunkModel.id << batch).execute()


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 043 : ajout et remplissage de is_structural_container sur document_chunks."""
    if fake:
        # peewee_migrate rejoue en `fake` les migrations déjà appliquées pour reconstruire son
        # instantané ORM, sans exécuter la moindre instruction SQL. La colonne doit y figurer :
        # c'est elle que `remove_fields` retrouve au `rollback`, qui reste lui aussi muet sur
        # une base réelle. `execute_sql` étant simulé ici, aucune introspection n'est possible.
        migrator.add_fields("document_chunks", is_structural_container=pw.BooleanField(default=False))
        return

    if not database.table_exists("document_chunks"):
        return

    chunk_cols = [col.name for col in database.get_columns("document_chunks")]
    if "is_structural_container" in chunk_cols:
        return

    migrator.add_fields("document_chunks", is_structural_container=pw.BooleanField(default=False))

    # `add_fields` empile l'ALTER TABLE dans la file du migrateur, qui n'est vidée
    # qu'après le retour de `migrate`. Le remplissage doit donc être empilé à son tour
    # — l'exécuter ici viserait une colonne qui n'existe pas encore.
    migrator.run(backfill, database)


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 043 : suppression de is_structural_container de document_chunks."""
    if fake or not database.table_exists("document_chunks"):
        return

    chunk_cols = [col.name for col in database.get_columns("document_chunks")]
    if "is_structural_container" in chunk_cols:
        migrator.remove_fields("document_chunks", "is_structural_container")
