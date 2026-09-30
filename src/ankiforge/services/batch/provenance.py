"""Estampillage de la provenance documentaire des cartes batch.

Une *partie* du Batch Slice Composer est une unité d'exécution qui peut agréger
plusieurs fragments de document (``BatchSourceBlock``). La provenance transmise à
``CoverageAlignmentService.resolve_finest_chunk_for_card`` doit alors être
honnête : mono-bloc exacte quand la partie tient dans un seul fragment,
explicitement multi-blocs sinon.

Ce module est la seule écriture de la provenance de portée : concaténer les fils
d'Ariane de tous les blocs, ou ne garder que la page du premier, produirait un
rattachement arbitraire (et donc des liens de couverture absents ou erronés).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, TypedDict

from ankiforge.services.batch.models import BatchSourceBlock


class BlockProvenance(TypedDict):
    """Route de résolution d'un fragment source vers un fragment de document."""

    chunk_id: int | None
    heading_path: str | None
    page_number: int | None


def scope_provenance(blocks: Iterable[BatchSourceBlock]) -> list[BlockProvenance]:
    """Décrit les blocs d'une partie comme routes de résolution, sans agrégation.

    Les blocs qui ne portent aucune route (ni identifiant de fragment, ni fil
    d'Ariane, ni page) sont écartés : ils ne peuvent conduire à aucun rattachement
    et ne doivent pas faire croître un faux multi-blocs. Les doublons exacts
    (même fil d'Ariane, même page, même identifiant) sont fusionnés.
    """
    routes: list[BlockProvenance] = []
    seen: set[tuple[int | None, str | None, int | None]] = set()
    for block in blocks:
        route: BlockProvenance = {
            "chunk_id": block.chunk_id,
            "heading_path": str(block.heading_path) if block.heading_path else None,
            "page_number": int(block.page_number) if block.page_number is not None else None,
        }
        if route["chunk_id"] is None and route["heading_path"] is None and route["page_number"] is None:
            continue
        key = (route["chunk_id"], route["heading_path"], route["page_number"])
        if key in seen:
            continue
        seen.add(key)
        routes.append(route)
    return routes


def mono_block_provenance(routes: Sequence[BlockProvenance]) -> BlockProvenance | None:
    """Retourne la route exacte d'une partie mono-bloc, ``None`` si elle est multi-blocs."""
    return routes[0] if len(routes) == 1 else None


def stamp_scope_provenance(cards: list[dict[str, Any]], blocks: Sequence[BatchSourceBlock]) -> None:
    """Estampe la provenance de portée sur chaque carte d'une partie.

    - partie mono-bloc : provenance scalaire exacte (fragment, fil d'Ariane, page) ;
    - partie multi-blocs : les scalaires restent ``None`` et la liste ``_source_blocks``
      porte toutes les routes — la résolution retombe alors sur le recouvrement lexical
      à l'intérieur de la partie, jamais sur la page du premier bloc.

    Une provenance déjà résolue par le pipeline (``_source_chunk_id`` renseigné par le
    chemin mono-chunk) n'est jamais écrasée.
    """
    routes = scope_provenance(blocks)
    exact = mono_block_provenance(routes)

    for card in cards:
        card.setdefault("_documentation_enabled", True)
        if card.get("_source_chunk_id"):
            card.setdefault("_source_blocks", [dict(route) for route in routes])
            continue
        card["_source_blocks"] = [dict(route) for route in routes]
        if exact is None:
            card["_source_chunk_id"] = None
            card["_source_heading_path"] = None
            card["_source_page_number"] = None
        else:
            card.setdefault("_source_chunk_id", exact["chunk_id"])
            card.setdefault("_source_heading_path", exact["heading_path"])
            card.setdefault("_source_page_number", exact["page_number"])
