from __future__ import annotations

import pytest

from ankiforge.ui.dialogs.scope_mode_exclusivity import (
    ScopeModeExclusivityMixin,
    sync_chapter_cards_from_range,
)

pytestmark = pytest.mark.unit


class _FakeButton:
    def __init__(self) -> None:
        self.checked = False

    def isChecked(self) -> bool:
        return self.checked

    def setChecked(self, value: bool) -> None:
        self.checked = value


class _Host(ScopeModeExclusivityMixin):
    """Hôte minimal implémentant le contrat du mixin."""

    def __init__(self) -> None:
        self.selection_mode = "pages"
        self._page_sub_mode = "all"
        self._activating_scope_mode = False
        self.neutralized: list[str] = []
        self.views: list[tuple[str, str]] = []
        self.activations: list[tuple[str, str]] = []
        self.buttons = {
            ("pages", "all"): _FakeButton(),
            ("pages", "range"): _FakeButton(),
            ("chapters", "all"): _FakeButton(),
            ("sections", "all"): _FakeButton(),
        }

    def _mode_buttons_for(self) -> dict[tuple[str, str], object]:
        return dict(self.buttons)

    def _apply_mode_view(self, mode: str, sub_mode: str) -> None:
        self.views.append((mode, sub_mode))

    def _neutralize_foreign_selection(self, mode: str) -> None:
        self.neutralized.append(mode)

    def _on_mode_activated(self, mode: str, sub_mode: str) -> None:
        self.activations.append((mode, sub_mode))


def _checked_keys(host: _Host) -> set[tuple[str, str]]:
    return {key for key, btn in host.buttons.items() if btn.isChecked()}


class _FakeCard:
    def __init__(self, chapter_index: int) -> None:
        self.chapter_index = chapter_index
        self.checked = True

    def set_checked(self, checked: bool) -> None:
        self.checked = checked


class _FakeSelector:
    def __init__(self, index: int) -> None:
        self._index = index
        self.blocked = False

    def currentIndex(self) -> int:
        return self._index

    def setCurrentIndex(self, index: int) -> None:
        self._index = index

    def blockSignals(self, block: bool) -> bool:
        self.blocked = block
        return self.blocked


def test_unknown_mode_is_rejected() -> None:
    host = _Host()
    assert host.activate_scope_mode("bogus") is False  # type: ignore[arg-type]
    assert host.views == []
    assert host.neutralized == []


def test_ensure_scope_mode_is_idempotent_and_only_switches_once() -> None:
    host = _Host()

    assert host.ensure_scope_mode("chapters") is True
    assert host.ensure_scope_mode("chapters") is False
    assert host.neutralized == ["chapters"]
    assert host.activations == [("chapters", "all")]
    assert _checked_keys(host) == {("chapters", "all")}


def test_force_reactivates_the_active_mode() -> None:
    host = _Host()
    host.ensure_scope_mode("sections")

    assert host.activate_scope_mode("sections", force=True) is True
    assert host.neutralized == ["sections", "sections"]
    assert host.activations == [("sections", "all"), ("sections", "all")]


def test_page_sub_mode_is_part_of_the_activation_identity() -> None:
    host = _Host()
    assert host.activate_scope_mode("pages", "all", force=True) is True
    assert _checked_keys(host) == {("pages", "all")}

    assert host.ensure_scope_mode("pages", "range") is True
    assert host.current_page_sub_mode() == "range"
    assert _checked_keys(host) == {("pages", "range")}

    assert host.ensure_scope_mode("pages", "range") is False
    assert host.ensure_scope_mode("pages", "all") is True
    assert _checked_keys(host) == {("pages", "all")}


def test_switching_away_from_pages_preserves_page_sub_mode() -> None:
    host = _Host()
    host.ensure_scope_mode("pages", "range")
    host.ensure_scope_mode("chapters")
    assert host.current_page_sub_mode() == "range"
    assert host.current_mode() == "chapters"
    assert _checked_keys(host) == {("chapters", "all")}


def test_refresh_false_skips_recalculation() -> None:
    host = _Host()
    assert host.activate_scope_mode("sections", refresh=False) is True
    assert host.views == [("sections", "all")]
    assert host.neutralized == ["sections"]
    assert host.activations == []


def test_restore_scope_mode_keeps_the_persisted_selection() -> None:
    """La restauration réactive le mode mémorisé sans neutraliser la sélection persistée."""
    host = _Host()

    assert host.restore_scope_mode("sections") is True
    assert host.current_mode() == "sections"
    assert host.neutralized == []
    assert host.views == [("sections", "all")]
    assert host.activations == [("sections", "all")]
    assert _checked_keys(host) == {("sections", "all")}


def test_unknown_mode_attribute_falls_back_to_pages() -> None:
    host = _Host()
    host.selection_mode = "legacy"
    assert host.current_mode() == "pages"


def test_unknown_page_sub_mode_falls_back_to_all() -> None:
    host = _Host()
    host._page_sub_mode = "nope"
    assert host.current_page_sub_mode() == "all"


def test_reentrant_activation_is_ignored() -> None:
    reentered: list[bool] = []

    class _Reentrant(_Host):
        def _apply_mode_view(self, mode: str, sub_mode: str) -> None:
            super()._apply_mode_view(mode, sub_mode)
            reentered.append(self.activate_scope_mode("pages"))

    host = _Reentrant()
    host.ensure_scope_mode("chapters")
    assert reentered == [False]
    assert host.current_mode() == "chapters"


def test_is_mode_active_ignores_sub_mode_outside_pages() -> None:
    host = _Host()
    host.selection_mode = "chapters"
    assert host.is_mode_active("chapters", "range") is True
    assert host.is_mode_active("chapters") is True
    assert host.is_mode_active("pages") is False


def test_sync_chapter_cards_from_range_aligns_and_orders() -> None:
    """La plage du sélecteur borne les cartes chapters et l'ordre décroissant est réaligné."""
    cards = [_FakeCard(i) for i in range(4)]
    end = _FakeSelector(1)
    start = _FakeSelector(0)
    seen: list[tuple[int, int, set[int]]] = []

    result = sync_chapter_cards_from_range(start, end, cards, lambda lo, hi, ch: seen.append((lo, hi, ch)))

    assert result == (0, 1)
    assert [card.checked for card in cards] == [True, True, False, False]
    assert seen == [(0, 1, {0, 1})]


def test_sync_chapter_cards_from_range_ignores_empty_selector() -> None:
    """Un sélecteur sans chapitre sélectionné ne produit aucune contrainte."""
    cards = [_FakeCard(0)]
    assert sync_chapter_cards_from_range(_FakeSelector(-1), _FakeSelector(-1), cards) is None
    assert [card.checked for card in cards] == [True]
