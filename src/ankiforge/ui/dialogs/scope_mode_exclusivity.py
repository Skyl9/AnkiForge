"""
Exclusivité stricte des modes de portée documentaire (Pages / Chapitres / Sections).

Ce module héberge le seul point d'entrée d'activation d'un mode de portée, partagé par
``DocumentScopeWidget`` (génération) et ``DocumentDelimitationDialog`` (délimitation) :

- toute interaction avec une catégorie (page, chapitre, section) active son mode sans clic
  préalable sur la barre d'onglets ;
- un mode actif est le seul à gouverner la portée : les sélections des autres catégories
  sont neutralisées (plus aucun filtrage croisé résiduel) ;
- le panneau ``pages_card`` n'est visible qu'en mode ``pages``.

Le mixin ne dépend pas de Qt : il ne manipule que le contrat déclaré par les widgets hôtes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Literal, Protocol

logger = logging.getLogger(__name__)

ScopeMode = Literal["pages", "chapters", "sections"]
PageSubMode = Literal["all", "range"]

SCOPE_MODES: tuple[ScopeMode, ...] = ("pages", "chapters", "sections")
PAGE_SUB_MODES: tuple[PageSubMode, ...] = ("all", "range")
DEFAULT_PAGE_SUB_MODE: PageSubMode = "all"


class CheckableButton(Protocol):
    """Contrat minimal d'un bouton de la barre de modes (satisfait par ``QPushButton``)."""

    def isChecked(self) -> bool: ...

    def setChecked(self, value: bool) -> None: ...


class IndexedSelector(Protocol):
    """Contrat minimal d'un sélecteur de plage indexé (satisfait par ``QComboBox``)."""

    def currentIndex(self) -> int: ...

    def setCurrentIndex(self, index: int) -> None: ...

    def blockSignals(self, block: bool) -> bool: ...


class ToggledChapterCard(Protocol):
    """Contrat minimal d'une carte de chapitre (satisfait par ``ChapterCardWidget``)."""

    chapter_index: int

    def set_checked(self, checked: bool) -> None: ...


def sync_chapter_cards_from_range(
    start: IndexedSelector,
    end: IndexedSelector,
    cards: Sequence[ToggledChapterCard],
    sync_preview: Callable[[int, int, set[int]], None] | None = None,
) -> tuple[int, int] | None:
    """Aligne les cartes chapitre sur la plage du sélecteur et renvoie cette plage.

    La plage du sélecteur est la source de vérité : elle borne le mode chapitres à un
    intervalle continu. ``sync_preview(min_page, max_page, pages)`` est appelé avec les pages
    des lignes cochées afin d'orienter l'aperçu (le dialogue décide s'il est pertinent).
    """
    idx_start = start.currentIndex()
    idx_end = end.currentIndex()
    if idx_start < 0 or idx_end < 0:
        return None
    if idx_start > idx_end:
        end.blockSignals(True)
        end.setCurrentIndex(idx_start)
        end.blockSignals(False)
        idx_end = idx_start

    for card in cards:
        card.set_checked(idx_start <= card.chapter_index <= idx_end)

    if sync_preview is not None:
        aligned = {card.chapter_index for card in cards if idx_start <= card.chapter_index <= idx_end}
        if aligned:
            sync_preview(min(aligned), max(aligned), aligned)
    return idx_start, idx_end


class ScopeModeExclusivityMixin:
    """Point d'entrée unique d'activation d'un mode de portée, exclusif par construction.

    Les classes hôtes doivent fournir :

    - ``selection_mode`` : mode de portée courant (``"pages"``, ``"chapters"`` ou ``"sections"``) ;
    - ``_page_sub_mode`` : sous-mode pages courant (``"all"`` ou ``"range"``) ;
    - ``_mode_buttons_for()`` : association ``(mode, sous-mode) -> bouton`` de la barre de modes ;
    - ``_apply_mode_view(mode, sub_mode)`` : applique la visibilité des volets du mode
      (ne doit pas émettre de changement de portée) ;
    - ``_neutralize_foreign_selection(mode)`` : neutralise les sélections hors mode actif ;
    - ``_on_mode_activated(mode, sub_mode)`` : recalcul KPI / aperçu après activation.
    """

    selection_mode: str
    _page_sub_mode: str
    _activating_scope_mode: bool

    def _mode_buttons_for(self) -> Mapping[tuple[str, str], CheckableButton]:
        raise NotImplementedError

    def _apply_mode_view(self, mode: ScopeMode, sub_mode: PageSubMode) -> None:
        raise NotImplementedError

    def _neutralize_foreign_selection(self, mode: ScopeMode) -> None:
        raise NotImplementedError

    def _on_mode_activated(self, mode: ScopeMode, sub_mode: PageSubMode) -> None:
        raise NotImplementedError

    def current_mode(self) -> ScopeMode:
        """Retourne le mode de portée actif, normalisé sur une valeur supportée."""
        mode = str(self.selection_mode)
        if mode not in SCOPE_MODES:
            logger.debug("Mode de portée inconnu (%s), repli sur 'pages'.", mode)
            return "pages"
        return mode

    def current_page_sub_mode(self) -> PageSubMode:
        """Retourne le sous-mode pages actif, normalisé."""
        sub_mode = str(self._page_sub_mode)
        if sub_mode not in PAGE_SUB_MODES:
            return DEFAULT_PAGE_SUB_MODE
        return sub_mode

    def is_mode_active(self, mode: ScopeMode, sub_mode: PageSubMode | None = None) -> bool:
        """Indique si le mode (et éventuellement le sous-mode pages) est déjà actif."""
        if self.current_mode() != mode:
            return False
        if sub_mode is None or mode != "pages":
            return True
        return self.current_page_sub_mode() == sub_mode

    def activate_scope_mode(
        self,
        mode: ScopeMode,
        sub_mode: PageSubMode | None = None,
        *,
        force: bool = False,
        refresh: bool = True,
    ) -> bool:
        """Active ``mode`` de façon exclusive et renvoie ``True`` si l'activation a eu lieu.

        ``force=True`` rejoue l'activation même si le mode est déjà actif (boutons de la barre
        de modes, qui doivent toujours réinitialiser leur volet). ``refresh=False`` omet le
        recalcul KPI / aperçu (pendant la construction du widget).
        """
        if mode not in SCOPE_MODES:
            logger.debug("Activation de mode ignorée (mode inconnu : %s).", mode)
            return False
        resolved_sub: PageSubMode = DEFAULT_PAGE_SUB_MODE
        if mode == "pages" and sub_mode in PAGE_SUB_MODES:
            resolved_sub = sub_mode

        if self._activating_scope_mode:
            return False
        if not force and self.is_mode_active(mode, resolved_sub):
            return False

        self._activating_scope_mode = True
        try:
            self.selection_mode = mode
            if mode == "pages":
                self._page_sub_mode = resolved_sub
            self._sync_mode_buttons(mode, resolved_sub)
            self._neutralize_foreign_selection(mode)
            self._apply_mode_view(mode, resolved_sub)
        finally:
            self._activating_scope_mode = False

        if refresh:
            self._on_mode_activated(mode, resolved_sub)
        return True

    def ensure_scope_mode(self, mode: ScopeMode, sub_mode: PageSubMode | None = None) -> bool:
        """Active ``mode`` seulement s'il ne l'est pas déjà (activation automatique)."""
        return self.activate_scope_mode(mode, sub_mode, force=False)

    def _sync_mode_buttons(self, mode: ScopeMode, sub_mode: PageSubMode) -> None:
        """Aligne la barre de modes sur le mode actif (bouton coché = mode gouvernant)."""
        target_key = (mode, sub_mode) if mode == "pages" else (mode, DEFAULT_PAGE_SUB_MODE)
        for key, button in self._mode_buttons_for().items():
            checked = key == target_key
            if button.isChecked() != checked:
                button.setChecked(checked)
