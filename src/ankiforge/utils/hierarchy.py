"""
Utilitaires centralisés pour la gestion des hiérarchies séparées par double-deux-points.

AnkiForge représente les hiérarchies de paquets (decks), de dossiers de documents et de
tags à l'aide du séparateur ``::`` (ex: ``Science::Physique::Thermodynamique``).

Ce module centralise la découpe, la reconstitution, la recherche de descendants et les
conversions avec le séparateur unitaire Anki (``\\x1f``) afin d'éviter la duplication de
ce littéral à travers le codebase.
Conforme aux Règles 2, 8, 19 et 20 de GEMINI.md.
"""

from __future__ import annotations

from collections.abc import Iterable

SEPARATOR = "::"
"""Séparateur hiérarchique utilisé pour les paquets, dossiers de documents et tags."""

ANKI_UNIT_SEPARATOR = "\x1f"
"""Séparateur unitaire (Unit Separator) utilisé par Anki au sein des noms de paquets."""


def split_hierarchy(name: str, *, strip: bool = True) -> list[str]:
    """
    Découpe un nom hiérarchique en niveaux normalisés.

    Exemple : ``"Science:: Physique :: "`` -> ``["Science", "Physique"]``
    (les niveaux vides ou uniquement blancs sont ignorés).

    Args:
        name: Nom hiérarchique complet (ex: ``Science::Physique``).
        strip: Si True, nettoie chaque niveau (espaces superflus).

    Returns:
        list[str]: Liste ordonnée des niveaux (feuille en dernière position).
    """
    if not name:
        return []
    if strip:
        return [part.strip() for part in name.split(SEPARATOR) if part.strip()]
    return [part for part in name.split(SEPARATOR) if part]


def join_hierarchy(parts: Iterable[str]) -> str:
    """
    Reconstitue un nom hiérarchique à partir de ses niveaux.

    Exemple : ``join_hierarchy(["Science", "Physique"])`` -> ``"Science::Physique"``

    Args:
        parts: Niveaux hiérarchiques ordonnés (racine puis descendants).

    Returns:
        str: Nom hiérarchique séparé par le séparateur ``::``.
    """
    return SEPARATOR.join(part.strip() for part in parts if part and part.strip())


def leaf_name(path: str) -> str:
    """
    Retourne le dernier niveau d'un nom hiérarchique.

    Exemple : ``leaf_name("Science::Physique::Thermo")`` -> ``"Thermo"``

    Args:
        path: Nom hiérarchique complet.

    Returns:
        str: Niveau feuille (le nom lui-même s'il est déjà à la racine).
    """
    parts = split_hierarchy(path)
    return parts[-1] if parts else path


def parent_path(path: str) -> str | None:
    """
    Retourne le chemin parent d'un nom hiérarchique.

    Exemple : ``parent_path("Science::Physique::Thermo")`` -> ``"Science::Physique"``

    Args:
        path: Nom hiérarchique complet.

    Returns:
        str | None: Chemin du parent, ou None si le nom est déjà une racine.
    """
    parts = split_hierarchy(path)
    if len(parts) <= 1:
        return None
    return join_hierarchy(parts[:-1])


def descendants_prefix(name: str) -> str:
    """
    Retourne le préfixe permettant de cibler tous les descendants directs.

    Exemple : ``descendants_prefix("Science")`` -> ``"Science::"``

    Args:
        name: Nom hiérarchique racine.

    Returns:
        str: Préfixe ``<nom>::`` utilisable dans les requêtes ``startswith``.
    """
    return f"{name}{SEPARATOR}"


def descends_from(name: str, ancestor: str) -> bool:
    """
    Indique si ``name`` désigne ``ancestor`` lui-même ou l'un de ses descendants,
    en évitant les faux positifs de préfixe (ex: ``"Math"`` ne descend pas de
    ``"Mathématiques"``).

    Args:
        name: Nom hiérarchique à tester.
        ancestor: Nom hiérarchique racine.

    Returns:
        bool: True si ``name`` est ``ancestor`` ou commence par ``<ancestor>::``.
    """
    return name == ancestor or name.startswith(descendants_prefix(ancestor))


def to_filename_safe(hierarchy_name: str, *, replacement: str = "_") -> str:
    """
    Transforme un nom hiérarchique en nom de fichier sûr.

    Exemple : ``to_filename_safe("Science::Physique")`` -> ``"Science_Physique"``

    Args:
        hierarchy_name: Nom hiérarchique complet.
        replacement: Chaîne de remplacement du séparateur et des espaces.

    Returns:
        str: Nom compatible avec les systèmes de fichiers.
    """
    return hierarchy_name.replace(SEPARATOR, replacement).replace(" ", replacement)


def from_anki_unit_separator(name: str) -> str:
    """
    Convertit un nom de paquet Anki (séparateur unitaire ``\\x1f``) vers la forme
    hiérarchique ``::``.

    Exemple : ``from_anki_unit_separator("Science\\x1fPhysique")`` -> ``"Science::Physique"``

    Args:
        name: Nom brut issu d'une collection Anki.

    Returns:
        str: Nom hiérarchique séparé par ``::``.
    """
    return name.replace(ANKI_UNIT_SEPARATOR, SEPARATOR)


def to_anki_unit_separator(hierarchy_name: str) -> str:
    """
    Convertit un nom hiérarchique ``::`` vers le séparateur unitaire Anki ``\\x1f``.

    Exemple : ``to_anki_unit_separator("Science::Physique")`` -> ``"Science\\x1fPhysique"``

    Args:
        hierarchy_name: Nom hiérarchique séparé par ``::``.

    Returns:
        str: Nom compatible avec le format natif Anki.
    """
    return hierarchy_name.replace(SEPARATOR, ANKI_UNIT_SEPARATOR)
