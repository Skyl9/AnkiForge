"""
Utilitaires de manipulation et normalisation des tags AnkiForge.

Fournit des fonctions pour parser les tags sérialisés (JSON ou séparés par des espaces),
extraire les métadonnées de traçabilité documentaire (doc:ID, source:SLUG, page:NUM, section:SLUG)
et générer des tags normalisés.

Invariant de rattachement : l'identité durable d'un bout de document est sa **section**
(le fil d'Ariane, `section_key()`), jamais l'identifiant de base d'un fragment, qui est
réattribué à chaque réingestion. Le tag `chunk:` n'est donc plus écrit — il reste lu, par
tolérance, sur les notes antérieures à ce changement.
Conforme aux Règles 2, 8, 19 et 20 de GEMINI.md.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
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


#: Séparateur de fil d'Ariane porté par `DocumentChunkModel.heading_path`.
HEADING_SEPARATOR = " > "

#: Horodatage de transcription en tête de titre : « [00:01] », « (1:02:03) », « [00:01.5] ».
_HEADING_TIMESTAMP_RE = re.compile(r"^\s*[\[(]\s*\d{1,3}(?::\d{2}){1,2}(?:[.,]\d+)?\s*[\])]\s*")


def strip_heading_timestamp(heading: str) -> str:
    """Retire l'horodatage de transcription qui préfixe un titre de section.

    Les transcriptions audio/vidéo et certaines sorties OCR préfixent chaque titre par son
    horodatage (« [00:01] Suffixes de Fichiers »). Cet horodatage décrit *quand* la section a
    été prononcée, pas *quoi* elle contient : il ne doit donc pas entrer dans l'identité
    canonique d'une section, sous peine de rendre ses étiquettes instables et illisibles.

    Exemple : ``"[00:01] Suffixes de Fichiers"`` -> ``"Suffixes de Fichiers"``.
    """
    stripped = _HEADING_TIMESTAMP_RE.sub("", heading or "", count=1).strip()
    return stripped or (heading or "").strip()


def section_key(heading_path: str | None) -> str:
    """Clé canonique et déterministe d'une section, stable à travers les réingestions.

    La clé est le slug du fil d'Ariane dont chaque niveau a été dépouillé de son horodatage
    de transcription. Elle ne dépend ni du découpage en fragments, ni des identifiants de
    base, ni des numéros de page : réingérer un document en déplaçant les frontières de
    fragments ne change pas cette clé.

    Exemple :
        ``"Java Software File Suffixes and Names (Archive) > [00:01] Suffixes de Fichiers"``
        -> ``"java_software_file_suffixes_and_names_archive_suffixes_de_fichiers"``

    Une section dont le titre ne serait qu'un horodatage retombe sur le slug historique :
    retirer l'horodatage ne doit jamais produire une clé vide.
    """
    if not heading_path or not heading_path.strip():
        return ""
    parts = [strip_heading_timestamp(part) for part in heading_path.split(HEADING_SEPARATOR)]
    kept = [part for part in parts if part.strip()]
    if not kept:
        return clean_source_slug(heading_path)
    return clean_source_slug(HEADING_SEPARATOR.join(kept))


def legacy_section_key(heading_path: str | None) -> str:
    """Clé de section historique (horodatages conservés), lue pour tolérance.

    Les notes créées avant l'adoption de :func:`section_key` portent une clé calculée par
    :func:`clean_source_slug` sur le fil d'Ariane brut. Cette fonction restitue exactement
    cette forme afin que la résolution accepte les deux générations de tags : une note
    ancienne reste rattachable, et sera réécrite dans la forme canonique au passage suivant
    de la réconciliation.
    """
    if not heading_path or not heading_path.strip():
        return ""
    return clean_source_slug(heading_path)


def extract_tag_metadata(tags: str | list[str] | None) -> dict[str, Any]:
    """
    Extrait les métadonnées de traçabilité documentaire portées par les tags.

    Tags reconnus :
    - `doc:<id>` -> doc_id (int)
    - `source:<slug>` -> source_slug (str)
    - `page:<num>` -> page_number (int)
    - `section:<slug>` -> section_slug (str) — clé canonique de section
    - `chunk:<id>` -> chunk_id (int) — **hérité**, jamais écrit depuis l'adoption de la
      section comme identité ; lu par tolérance sur les notes antérieures, et ignoré
      s'il ne désigne plus aucun fragment

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
    extra_tags: list[str] | None = None,
) -> list[str]:
    """
    Construit la liste des tags normalisés pour une note issue d'un document.

    Seuls des faits vérifiés sur la source sont étiquetés : ``page:`` n'est écrit que si la
    page a effectivement été résolue sur un fragment (un document Markdown non paginé n'en
    porte pas), et ``section:`` est la clé canonique du fil d'Ariane.

    Le tag ``chunk:`` n'est **plus écrit** : l'identifiant de fragment est un identifiant de
    base, réattribué à chaque réingestion, et un cache périmé est indiscernable d'un cache
    valide. La précision au fragment est conservée par ``NoteChunkLinkModel.chunk_id``, et
    l'identité durable par ``section:``. Les notes anciennes portant encore ``chunk:`` sont
    lues et réécrites par la réconciliation.

    Args:
        doc_id: ID du document en base SQLite.
        doc_title: Titre du document.
        page_number: Numéro de page **résolu** (documents paginés uniquement).
        section_name: Fil d'Ariane ou titre de la section source.
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
        slug = section_key(section_name)
        if slug:
            tags.append(f"section:{slug}")

    if extra_tags:
        for t in extra_tags:
            t_clean = str(t).strip()
            if t_clean and t_clean not in tags:
                tags.append(t_clean)

    return tags


# Alias de rétro-compatibilité et clarté sémantique RAG
build_provenance_tags = build_document_tags


#: Préfixes de traçabilité réécrivables par :func:`replace_provenance_tags`.
_REWRITABLE_PROVENANCE_PREFIXES: dict[str, str] = {"section": "section:", "page": "page:", "chunk": "chunk:"}


def replace_provenance_tags(
    tags: str | list[str] | None,
    overrides: Mapping[str, str | int | None] | None = None,
) -> str:
    """Réécrit les tags de provenance `section:`, `page:` et `chunk:` d'une note, sans toucher aux autres.

    Seuls les préfixes présents dans ``overrides`` sont traités : la valeur remplace le tag
    existant à sa position d'origine (ou est ajoutée en fin de liste s'il était absent), et
    ``None`` retire le tag correspondant. La provenance la plus fine d'une note peut ainsi
    être resserrée sur une sous-section sans perdre les autres tags (``doc:``, ``source:``,
    tags métier ou d'examen).

    Args:
        tags: Tags bruts ou liste de tags, quel que soit le format de sérialisation.
        overrides: Clés ``"section"`` (clé canonique de section), ``"page"`` (numéro de page)
            et ``"chunk"`` (ID de fragment — désormais jamais écrit, seulement retiré).
            Une valeur ``None`` ou vide retire le tag ; une clé absente le laisse inchangé.

    Returns:
        str: Tags re-sérialisés dans le format d'origine (JSON ou séparés par des espaces).
    """
    parsed = parse_note_tags(tags)

    for key, raw_value in (overrides or {}).items():
        prefix = _REWRITABLE_PROVENANCE_PREFIXES.get(key)
        if prefix is None:
            logger.debug("replace_provenance_tags : préfixe de provenance inconnu %r, ignoré.", key)
            continue
        value = "" if raw_value is None else str(raw_value).strip()
        new_tag = f"{prefix}{value}" if value else None
        rebuilt: list[str] = []
        for tag in parsed:
            if tag.lower().startswith(prefix):
                if new_tag is not None and new_tag not in rebuilt:
                    rebuilt.append(new_tag)
                continue
            rebuilt.append(tag)
        if new_tag is not None and new_tag not in rebuilt:
            rebuilt.append(new_tag)
        parsed = rebuilt

    raw = tags.strip() if isinstance(tags, str) else ""
    if raw and not raw.startswith("["):
        return " ".join(parsed)
    return json.dumps(parsed, ensure_ascii=False)
