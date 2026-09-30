"""
Adresses de région : l'identité durable d'une portion de document qu'on **écarte** ou qu'on
**neutralise** (ADR 0010).

Un fragment de document est un artefact de découpage : son identifiant est réattribué à chaque
réingestion. Ce qui survit au découpage, c'est son *adresse* — un couple
``(portée, valeur)``, rendu sous forme textuelle :

``node:<fil d'Ariane>``
    Le contenu propre d'un titre, sans ses descendants. ``node:Cours > Ch1`` désigne le seul
    fragment porteur de ce fil d'Ariane.
``heading:<fil d'Ariane>``
    Le nœud **et sa lignée** : le nœud lui-même et tout ce qu'il contient.
    ``heading:Cours`` englobe ``Cours > Ch1 > 1.1`` mais pas ``Coursan``.
``page:<n>``
    La page ``n``.

Une entrée **sans préfixe** est lue comme ``heading:`` : les profils existants conservent
exactement leur comportement, sans migration de données. En revanche un ``"4"` nu n'est plus
un trou de page — il reste le titre « 4 ».

Ce module est volontairement **feuille** : ni base de données, ni Qt, ni import du
découpeur. Le dépôt, les dialogues, les vues et l'alignement de couverture l'interrogent tous
par le même prédicat, ce qui supprime la divergence « correspondance exacte » (dialogue de
délimitation) contre « correspondance par sous-chaîne » (dépôt) qui faisait renaître une
exclusion à la réouverture.
Conforme aux Règles 8, 19 et 20 de GEMINI.md.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ankiforge.utils.tags import HEADING_SEPARATOR, strip_heading_timestamp

__all__ = [
    "RegionAddress",
    "RegionScope",
    "covers_region",
    "parse_region_address",
    "parse_region_addresses",
    "render_region_addresses",
]


class RegionScope(StrEnum):
    """Portée d'une adresse de région : le nœud, sa lignée, ou la page."""

    NODE = "node"
    HEADING = "heading"
    PAGE = "page"


#: Ordre de sérialisation canonique des portées : du plus local au plus global.
_SCOPE_ORDER: dict[RegionScope, int] = {RegionScope.NODE: 0, RegionScope.HEADING: 1, RegionScope.PAGE: 2}


_ADDRESS_RE = re.compile(r"^(?P<scope>node|heading|page)\s*:\s*(?P<value>.*)$", re.IGNORECASE)


def _clean(value: str | None) -> str:
    """Nettoie un fil d'Ariane sans perdre sa casse : horodatages retirés, espaces réduits."""
    if not value:
        return ""
    parts = [strip_heading_timestamp(part) for part in value.split(HEADING_SEPARATOR)]
    return HEADING_SEPARATOR.join(" ".join(part.split()) for part in parts if part.split()).strip()


def _clean_page(value: str | None) -> str:
    """Nettoie un numéro de page : les zéros de remplissage n'ont pas de sens."""
    if not value or not value.strip().isdigit():
        return ""
    return str(int(value.strip()))


def _fold(value: str) -> str:
    """Clé de comparaison insensible à la casse — l'exclusion d'un titre ignore sa casse."""
    return value.casefold()


@dataclass(frozen=True, eq=False)
class RegionAddress:
    """Adresse d'une région de document, comparable et stable à travers les réingestions.

    L'identité d'une adresse est insensible à la casse, mais ``value`` conserve la casse
    d'origine : la valeur affichée doit rester lisible dans le dialogue de délimitation.
    """

    scope: RegionScope
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _clean_page(self.value) if self.scope is RegionScope.PAGE else _clean(self.value))

    @property
    def key(self) -> tuple[str, str]:
        """Identité comparable de l'adresse, insensible à la casse."""
        return (self.scope.value, _fold(self.value))

    @property
    def sort_key(self) -> tuple[int, str]:
        """Ordre de sérialisation canonique : la portée, puis la valeur.

        L'ordre suit l'échelle du document — le nœud, sa lignée, la page — et non l'ordre
        alphabétique des libellés de portée, pour que deux écritures de la même règle
        produisent la même chaîne quelle que soit leur date.
        """
        return (_SCOPE_ORDER[self.scope], _fold(self.value))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RegionAddress) and self.key == other.key

    def __hash__(self) -> int:
        return hash(self.key)

    def render(self) -> str:
        """Forme canonique textuelle, préfixée : seule forme écrite en base."""
        return f"{self.scope.value}:{self.value}"

    def _engulfs(self, target: str) -> bool:
        """Règle d'englobement, dans le vocabulaire d'un fil d'Ariane.

        `heading:` englobe le nœud et sa lignée ; `node:` n'englobe que le nœud. La portée
        `page:` n'a pas de fil d'Ariane et n'est donc jamais concernée ici.
        """
        mine, target_folded = _fold(self.value), _fold(target)
        if not mine or not target_folded:
            return False
        if self.scope is RegionScope.NODE:
            return mine == target_folded
        return mine == target_folded or target_folded.startswith(f"{mine}{_fold(HEADING_SEPARATOR)}")

    def covers(self, *, heading_path: str | None, page_number: int | None) -> bool:
        """Indique si cette adresse englobe la région décrite par ``heading_path``/``page_number``."""
        if self.scope is RegionScope.PAGE:
            if page_number is None or not self.value:
                return False
            return int(self.value) == page_number
        return self._engulfs(_clean(heading_path))

    def covers_address(self, other: RegionAddress) -> bool:
        """Une adresse en englobe-t-elle une autre ? Symétrique de :meth:`covers`.

        Sert au retrait d'une exclusion : on retire toute entrée *encore appliquée* à la région
        ré-incluse, y compris une entrée plus large qui la recouvre. Une entrée plus étroite, ou
        d'une autre portée, reste en place : elle désigne une autre région.
        """
        if self.scope is RegionScope.PAGE or other.scope is RegionScope.PAGE:
            return self.scope is other.scope is RegionScope.PAGE and self.value == other.value
        return self._engulfs(other.value)


def parse_region_address(raw: str | None) -> RegionAddress | None:
    """Lit une entrée de région brute. Sans préfixe reconnu, l'entrée est une lignée (``heading:``)."""
    if not raw or not raw.strip():
        return None
    text = str(raw).strip()
    matched = _ADDRESS_RE.match(text)
    if matched is None:
        return RegionAddress(RegionScope.HEADING, text)
    value = matched.group("value").strip()
    if not value:
        # Préfixe reconnu mais valeur absente : l'entrée est illisible, pas une exclusion nue.
        return None
    scope = RegionScope(matched.group("scope").lower())
    if scope is RegionScope.PAGE and not value.isdigit():
        # Un `page:` non numérique ne peut désigner aucune page : c'est une entrée résiduelle
        # d'une version antérieure, pas une exclusion à propager silencieusement.
        return None
    return RegionAddress(scope, value)


def parse_region_addresses(raw: Any) -> list[RegionAddress]:
    """Lit une collection d'adresses depuis un JSON, une chaîne, ou une séquence déjà lue.

    Les entrées illisibles sont ignorées : une exclusion mémorisée doit rester chargeable même
    si elle contient une reliquate d'une version antérieure.
    """
    if raw is None:
        return []
    if isinstance(raw, RegionAddress):
        return [raw]
    if isinstance(raw, list | tuple | set | frozenset):
        items: list[Any] = list(raw)
    else:
        text = str(raw).strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                decoded = json.loads(text)
            except (ValueError, TypeError):
                return []
            items = decoded if isinstance(decoded, list) else []
        else:
            items = [text]
    seen: dict[RegionAddress, None] = {}
    for item in items:
        if isinstance(item, RegionAddress):
            address: RegionAddress | None = item
        elif isinstance(item, dict):
            scope, value = item.get("scope"), item.get("value")
            address = RegionAddress(RegionScope(scope), str(value)) if scope and value else None
        else:
            address = parse_region_address(str(item) if item is not None else None)
        if address is not None and address.value:
            seen.setdefault(address, None)
    return list(seen)


def render_region_addresses(addresses: Iterable[RegionAddress] | str | None) -> str:
    """Sérialise une collection d'adresses en JSON canonique, dédupliquée et triée."""
    return json.dumps([address.render() for address in sorted(parse_region_addresses(addresses), key=lambda address: address.sort_key)], ensure_ascii=False)


def covers_region(addresses: Iterable[RegionAddress] | str | None, *, heading_path: str | None, page_number: int | None) -> bool:
    """Prédicat d'appartenance unique : la région est-elle couverte par l'une de ces adresses ?"""
    return any(address.covers(heading_path=heading_path, page_number=page_number) for address in parse_region_addresses(addresses))
