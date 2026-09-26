"""
Utilitaires de manipulation et normalisation des tags AnkiForge.

Fournit des fonctions pour parser les tags sérialisés (JSON ou séparés par des espaces),
extraire les métadonnées de traçabilité documentaire (doc:ID, source:SLUG, page:NUM, section:SLUG)
et générer des tags normalisés.
Conforme aux Règles 2, 8, 19 et 20 de GEMINI.md.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def parse_note_tags(tags: str | list[str] | None) -> list[str]:
    """
    Parse et normalise les tags d'une note quel que soit leur format d'origine.

    Prend en charge :
    - Liste native Python : ['tag1', 'tag2']
    - JSON sérialisé : '["tag1", "tag2"]'
    - Chaîne délimitée par des espaces (format standard Anki) : 'tag1 tag2'
    - None ou chaîne vide : retourne une liste vide.

    Args:
        tags: La chaîne brute ou la liste de tags.

    Returns:
        list[str]: Liste ordonnée de tags uniques sans espaces superflus.
    """
    if not tags:
        return []

    if isinstance(tags, list):
        clean_list: list[str] = []
        for t in tags:
            s = str(t).strip()
            if s and s not in clean_list:
                clean_list.append(s)
        return clean_list

    raw_str = str(tags).strip()
    if not raw_str:
        return []

    # Tentative de désérialisation JSON
    if raw_str.startswith("[") and raw_str.endswith("]"):
        try:
            parsed = json.loads(raw_str)
            if isinstance(parsed, list):
                result: list[str] = []
                for item in parsed:
                    s = str(item).strip()
                    if s and s not in result:
                        result.append(s)
                return result
        except Exception as err:
            logger.debug("Parsing des tags JSON ignoré : %s", err)

    # Découpage par espaces si pas JSON ou échec
    result_tokens: list[str] = []
    for token in raw_str.split():
        token_clean = token.strip()
        if token_clean and token_clean not in result_tokens:
            result_tokens.append(token_clean)
    return result_tokens


def clean_source_slug(title: str) -> str:
    """
    Transforme un nom de document en slug propre pour le tag `source:<slug>`.

    Exemple : "Cours Anatomie Ch1.pdf" -> "cours_anatomie_ch1"
    """
    s = title.strip()
    # Supprimer les extensions courantes
    for ext in (".pdf", ".md", ".txt", ".pptx", ".epub", ".html", ".mp3", ".wav"):
        if s.lower().endswith(ext):
            s = s[: -len(ext)]
            break
    # Remplacer espaces, tirets et apostrophes par des underscores
    s = re.sub(r"[\s\-\'\.]+", "_", s)
    # Supprimer les caractères non alphanumériques ou underscores
    s = re.sub(r"[^\w_]", "", s)
    # Réduire les underscores multiples
    s = re.sub(r"_+", "_", s).strip("_")
    return s.lower() or "document"


def extract_tag_metadata(tags: str | list[str] | None) -> dict[str, Any]:
    """
    Extrait les métadonnées de traçabilité documentaire portées par les tags.

    Tags reconnus :
    - `doc:<id>` -> doc_id (int)
    - `source:<slug>` -> source_slug (str)
    - `page:<num>` -> page_number (int)
    - `section:<slug>` -> section_slug (str)
    - `chunk:<id>` -> chunk_id (int, résolution la plus fine)

    Args:
        tags: Tags bruts ou liste de tags.

    Returns:
        dict contenant :
        - doc_id: int | None
        - source_slug: str | None
        - page_number: int | None
        - section_slug: str | None
        - chunk_id: int | None
    """
    parsed = parse_note_tags(tags)
    metadata: dict[str, Any] = {
        "doc_id": None,
        "source_slug": None,
        "page_number": None,
        "section_slug": None,
        "chunk_id": None,
    }

    for tag in parsed:
        tag_lower = tag.lower()
        if tag_lower.startswith("doc:"):
            val_str = tag[4:].strip()
            if val_str.isdigit():
                metadata["doc_id"] = int(val_str)
        elif tag_lower.startswith("chunk:"):
            val_str = tag[6:].strip()
            if val_str.isdigit():
                metadata["chunk_id"] = int(val_str)
        elif tag_lower.startswith("source:"):
            metadata["source_slug"] = tag[7:].strip().lower()
        elif tag_lower.startswith("page:"):
            val_str = tag[5:].strip()
            if val_str.isdigit():
                metadata["page_number"] = int(val_str)
        elif tag_lower.startswith("section:"):
            metadata["section_slug"] = tag[8:].strip().lower()

    return metadata


def build_document_tags(
    doc_id: int | None = None,
    doc_title: str | None = None,
    page_number: int | None = None,
    section_name: str | None = None,
    chunk_id: int | None = None,
    extra_tags: list[str] | None = None,
) -> list[str]:
    """
    Construit la liste des tags normalisés pour une note issue d'un document.

    Args:
        doc_id: ID du document en base SQLite.
        doc_title: Titre du document.
        page_number: Numéro de la page ou diapositive (pour documents paginés).
        section_name: Nom ou slug de la section (pour documents continus).
        chunk_id: ID du fragment de document (DocumentChunkModel) le plus fin correspondant.
        extra_tags: Tags additionnels optionnels.

    Returns:
        list[str]: Liste des tags incluant 'ankiforge_generated' et les tags de traçabilité.
    """
    tags: list[str] = ["ankiforge_generated"]

    if doc_id is not None:
        tags.append(f"doc:{doc_id}")

    if doc_title and doc_title.strip().lower() not in ("saisie libre", "document"):
        slug = clean_source_slug(doc_title)
        if slug:
            tags.append(f"source:{slug}")

    if page_number is not None and page_number > 0:
        tags.append(f"page:{page_number}")

    if section_name and section_name.strip():
        slug = clean_source_slug(section_name)
        if slug:
            tags.append(f"section:{slug}")

    if chunk_id is not None and chunk_id > 0:
        tags.append(f"chunk:{chunk_id}")

    if extra_tags:
        for t in extra_tags:
            t_clean = str(t).strip()
            if t_clean and t_clean not in tags:
                tags.append(t_clean)

    return tags


# Alias de rétro-compatibilité et clarté sémantique RAG
build_provenance_tags = build_document_tags
