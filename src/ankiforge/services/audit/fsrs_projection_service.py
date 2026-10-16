"""Projection de rétention et charge à l'équilibre, dérivées du seul intervalle courant.

La Forge ne stocke ni la stabilité calculée par Anki, ni les dates d'échéance, ni
d'historique de révision. La projection s'appuie donc exclusivement sur l'intervalle
`ivl` réellement présent sur chaque carte (ADR 0020) :

- stabilité estimée ``S ≈ ivl`` (exact à 90 % de rétention cible) ;
- rétention projetée ``R(t, S) = (1 + (19/81) · t / S)^{-0.5}``, ancrée à la révision
  (100 % à ``t = 0``) — jamais une date du calendrier ;
- charge à l'équilibre ``Σ 1/ivl``, exprimée en révisions par jour.

Ce service fait autorité sur le calcul : le tableau de bord et l'onglet Analyse/SRS
le consomment tous deux.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import numpy as np

from ankiforge.database.models import CardModel
from ankiforge.repositories.deck_repository import DeckRepository

logger = logging.getLogger(__name__)


class FsrsProjectionService:
    """Calcule la courbe d'oubli projetée et la charge d'équilibre d'une collection."""

    #: Rétention visée par Anki lors du dimensionnement de l'intervalle.
    RETENTION_TARGET: float = 0.90
    #: Constante de décroissance de la loi de puissance FSRS : ``19/81``.
    FSRS_DECAY: float = 19.0 / 81.0
    #: Repères temporels explicitement mis en avant sur la courbe (en jours).
    DEFAULT_CHECKPOINTS: tuple[int, ...] = (1, 3, 7, 14)
    #: Horizon de tracé de la courbe (en jours).
    CURVE_MAX_DAY: int = 14
    #: Pas d'échantillonnage de la courbe (en jours) — 4 points par jour.
    CURVE_STEP_DAYS: float = 0.25

    @staticmethod
    def estimate_stability_days(interval_days: int) -> float:
        """Estime la stabilité d'oubli à partir de l'intervalle courant (``S ≈ ivl``).

        Un intervalle nul (carte neuve ou jamais révisée) ne porte aucune stabilité :
        la carte est hors du périmètre de projection et totalisée séparément.
        """
        return float(interval_days) if interval_days > 0 else 0.0

    @classmethod
    def projected_retention(cls, day: float, stability_days: float) -> float:
        """Rétention de rappel projetée à ``day`` jours pour une stabilité ``S``.

        Renvoie la fraction attendue dans ``[0, 1]``. La courbe est ancrée à la
        révision : ``projected_retention(0, S) == 1.0``.
        """
        if stability_days <= 0:
            return 0.0
        return float(cls._retention_array(day, np.asarray([stability_days], dtype=float))[0])

    @classmethod
    def _retention_array(cls, day: float, stabilities: np.ndarray) -> np.ndarray:
        """Formule unique de la courbe d'oubli, vectorisée sur un vecteur de stabilités ``> 0``."""
        elapsed = max(0.0, float(day))
        return (1.0 + cls.FSRS_DECAY * elapsed / stabilities) ** -0.5

    @classmethod
    def project(cls, deck_id: int | None = None) -> dict[str, Any]:
        """Projette la rétention et la charge d'équilibre, éventuellement filtrées par paquet.

        Args:
            deck_id: Paquet racine ciblé. Les sous-paquets sont inclus. ``None`` couvre
                l'ensemble de la collection.

        Returns:
            Un dictionnaire déterministe décrivant la projection. ``available`` est
            ``False`` lorsqu'aucune carte n'a d'intervalle exploitable.
        """
        try:
            rows = cls._fetch_rows(deck_id)
        except Exception as e:  # pragma: no cover - dépend de l'état de la base
            logger.warning("Erreur lors du calcul de la projection de rétention : %s", e)
            return cls._empty_projection(deck_id)

        total_cards = len(rows)
        # « Nouvelles » au sens strict : intervalle nul (jamais révisée). Les intervalles
        # négatifs (cartes en apprentissage, encodés en secondes par Anki) ne portent pas
        # davantage d'intervalle exploitable et restent donc hors du périmètre de projection.
        new_cards = sum(1 for ivl, _suspended in rows if ivl == 0)
        studied = [ivl for ivl, _suspended in rows if ivl > 0]
        suspended_cards = sum(1 for ivl, suspended in rows if ivl > 0 and suspended)
        load_intervals = [ivl for ivl, suspended in rows if ivl > 0 and not suspended]

        if not studied:
            result = cls._empty_projection(deck_id)
            result["total_cards"] = total_cards
            result["new_cards"] = new_cards
            return result

        stabilities = np.asarray(studied, dtype=float)
        mean_stability = round(float(np.mean(stabilities)), 1)

        checkpoints = [{"day": day, "retention": cls._mean_retention(stabilities, float(day))} for day in cls.DEFAULT_CHECKPOINTS]
        curve = cls._build_curve(stabilities)

        equilibrium_load = 0.0
        if load_intervals:
            equilibrium_load = round(float(np.sum(1.0 / np.asarray(load_intervals, dtype=float))), 2)

        return {
            "deck_id": deck_id,
            "available": True,
            "retention_target": cls.RETENTION_TARGET,
            "total_cards": total_cards,
            "new_cards": new_cards,
            "studied_cards": len(studied),
            "suspended_cards": suspended_cards,
            "load_cards": len(load_intervals),
            "mean_stability_days": mean_stability,
            "checkpoints": checkpoints,
            "curve": curve,
            "equilibrium_load_per_day": equilibrium_load,
        }

    @classmethod
    def _fetch_rows(cls, deck_id: int | None) -> list[tuple[int, bool]]:
        """Charge les couples ``(intervalle, suspendue)`` des cartes du périmètre."""
        query = CardModel.select(CardModel.ivl, CardModel.is_suspended)
        deck_ids = cls._resolve_deck_ids(deck_id)
        if deck_ids is not None:
            if not deck_ids:
                return []
            query = query.where(CardModel.deck.in_(deck_ids))
        rows = cast("list[tuple[Any, ...]]", query.tuples())
        return [(int(ivl or 0), bool(suspended)) for ivl, suspended in rows]

    @staticmethod
    def _resolve_deck_ids(deck_id: int | None) -> list[int] | None:
        """Résout le paquet ciblé et ses sous-paquets. ``None`` = pas de restriction."""
        if deck_id is None:
            return None
        deck = DeckRepository().get_deck_by_id(deck_id)
        if deck is None:
            return []
        return [d.id for d in DeckRepository().get_descendant_decks(deck.name)]

    @classmethod
    def _mean_retention(cls, stabilities: np.ndarray, day: float) -> float:
        """Rétention moyenne de la collection à ``day`` jours (moyenne des rétentions par carte)."""
        return round(float(np.mean(cls._retention_array(day, stabilities))), 4)

    @classmethod
    def _build_curve(cls, stabilities: np.ndarray) -> list[dict[str, float]]:
        """Échantillonne la courbe d'oubli projetée de ``J0`` à l'horizon configuré."""
        days = np.arange(0.0, cls.CURVE_MAX_DAY + cls.CURVE_STEP_DAYS, cls.CURVE_STEP_DAYS)
        return [{"day": round(float(day), 2), "retention": cls._mean_retention(stabilities, float(day))} for day in days]

    @classmethod
    def _empty_projection(cls, deck_id: int | None) -> dict[str, Any]:
        """Projection vide (aucune carte exploitable) au format canonique."""
        return {
            "deck_id": deck_id,
            "available": False,
            "retention_target": cls.RETENTION_TARGET,
            "total_cards": 0,
            "new_cards": 0,
            "studied_cards": 0,
            "suspended_cards": 0,
            "load_cards": 0,
            "mean_stability_days": 0.0,
            "checkpoints": [{"day": day, "retention": 0.0} for day in cls.DEFAULT_CHECKPOINTS],
            "curve": [],
            "equilibrium_load_per_day": 0.0,
        }
