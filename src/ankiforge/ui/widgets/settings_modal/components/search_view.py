"""Vue aplatie des résultats de recherche de paramètres du modal.

Affiche les résultats sous forme de cartes élégantes avec fil d'Ariane
(``Onglet &gt; Section &gt; Option``), surlignage des termes correspondants et
état vide. Aucune couleur en dur : les teintes sémantiques proviennent de
``DesignTokens``.
"""

from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.settings_modal.search_registry import (
    SettingDescriptor,
    SettingSearchResult,
    SettingsRegistry,
    _normalize,
)
from ankiforge.utils.icon_loader import load_phosphor_icon

if TYPE_CHECKING:
    from PySide6.QtGui import QMouseEvent


def _escape_html(text: str) -> str:
    """Échappe les caractères HTML spéciaux d'un texte brut."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Retourne le texte normalisé et la correspondance index normalisé → index original."""
    norm_chars: list[str] = []
    orig_map: list[int] = []
    for orig_i, ch in enumerate(text):
        for d in unicodedata.normalize("NFD", ch):
            if unicodedata.combining(d):
                continue
            norm_chars.append(d.casefold())
            orig_map.append(orig_i)
    return "".join(norm_chars), orig_map


def highlight_terms(text: str, terms: list[str]) -> str:
    """Entoure les occurrences des termes (insensibles accents/casse) d'un span d'accentuation."""
    if not terms:
        return _escape_html(text)
    norm, orig_map = _normalize_with_map(text)
    spans: list[tuple[int, int]] = []
    for term in terms:
        start = 0
        while True:
            idx = norm.find(term, start)
            if idx == -1:
                break
            spans.append((orig_map[idx], orig_map[idx + len(term) - 1] + 1))
            start = idx + 1
    if not spans:
        return _escape_html(text)
    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    parts: list[str] = []
    cursor = 0
    accent_bg = DesignTokens.ACCENT_BG
    accent_primary = DesignTokens.ACCENT_PRIMARY
    for start, end in merged:
        parts.append(_escape_html(text[cursor:start]))
        parts.append('<span style="background-color: ' + accent_bg + "; color: " + accent_primary + '; border-radius: 2px; padding: 0 1px;">' + _escape_html(text[start:end]) + "</span>")
        cursor = end
    parts.append(_escape_html(text[cursor:]))
    return "".join(parts)


class SearchResultCard(QFrame):
    """Carte présentant un résultat de recherche avec fil d'Ariane et surlignage."""

    clicked = Signal(object)  # SettingDescriptor

    def __init__(
        self,
        result: SettingSearchResult,
        query_terms: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SearchResultCard")
        self.result = result
        self.descriptor: SettingDescriptor = result.descriptor
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build_ui(query_terms)
        self._apply_style()

    def _build_ui(self, query_terms: list[str]) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        breadcrumb = f"{self.descriptor.tab} &gt; {self.descriptor.section} &gt; {self.descriptor.widget}"
        self.lbl_breadcrumb = QLabel(breadcrumb)
        self.lbl_breadcrumb.setObjectName("SearchResultBreadcrumb")
        self.lbl_breadcrumb.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: 600; letter-spacing: 0.2px; background: transparent; border: none;")
        layout.addWidget(self.lbl_breadcrumb)

        self.lbl_title = QLabel(highlight_terms(self.descriptor.label, query_terms))
        self.lbl_title.setObjectName("SearchResultTitle")
        self.lbl_title.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 13px; font-weight: 700; background: transparent; border: none;")
        layout.addWidget(self.lbl_title)

        self.lbl_description = QLabel(highlight_terms(self.descriptor.description, query_terms))
        self.lbl_description.setObjectName("SearchResultDescription")
        self.lbl_description.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_description.setWordWrap(True)
        self.lbl_description.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; background: transparent; border: none;")
        layout.addWidget(self.lbl_description)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame#SearchResultCard {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QFrame#SearchResultCard:hover {{
                border-color: {DesignTokens.ACCENT_BORDER};
                background-color: {DesignTokens.BG_HOVER};
            }}
            """
        )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.descriptor)
        super().mouseReleaseEvent(event)


class SettingsSearchView(QWidget):
    """Widget aplité listant les résultats de recherche de paramètres.

    Émet ``result_selected`` avec le :class:`SettingDescriptor` ciblé quand
    l'utilisateur clique sur une carte.
    """

    result_selected = Signal(object)  # SettingDescriptor

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsSearchView")
        self._query = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.lbl_title = QLabel(self.tr("Recherche de paramètres"))
        self.lbl_title.setObjectName("SettingsSearchTitle")
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 15px; font-weight: bold; padding: 12px 12px 8px 12px; background: transparent; border: none;")
        layout.addWidget(self.lbl_title)

        self.list_results = QListWidget(self)
        self.list_results.setObjectName("SearchResultsList")
        self.list_results.setStyleSheet("QListWidget { background: transparent; border: none; outline: none; } QListWidget::item { border: none; padding: 0; margin: 4px 8px; }")
        self.list_results.setUniformItemSizes(False)
        layout.addWidget(self.list_results, 1)

        self.empty_widget = QWidget(self)
        self.empty_widget.setObjectName("SearchEmptyState")
        empty_layout = QVBoxLayout(self.empty_widget)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty_icon = QLabel()
        self.lbl_empty_icon.setPixmap(load_phosphor_icon("ph.magnifying-glass", color=DesignTokens.TEXT_MUTED).pixmap(48, 48))
        self.lbl_empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty_icon.setStyleSheet("padding-bottom: 8px; background: transparent; border: none;")
        self.lbl_empty_text = QLabel(self.tr("Aucun réglage ne correspond à votre recherche."))
        self.lbl_empty_text.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 13px; background: transparent; border: none;")
        self.lbl_empty_hint = QLabel(self.tr("Essayez un autre mot-clé (ex: « température », « zip », « langue »)."))
        self.lbl_empty_hint.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        for w in (self.lbl_empty_icon, self.lbl_empty_text, self.lbl_empty_hint):
            empty_layout.addWidget(w)
        self.empty_widget.hide()
        layout.addWidget(self.empty_widget, 1)

    def set_results(self, results: list[SettingSearchResult], query: str) -> None:
        """Remplace la liste des résultats par ceux de la requête donnée."""
        self._query = query
        terms = [t for t in _normalize(query).split() if t]
        self.list_results.clear()
        has_results = bool(results)
        self.list_results.setVisible(has_results)
        self.empty_widget.setVisible(not has_results)
        if not has_results:
            return
        for result in results:
            card = SearchResultCard(result, terms)
            card.clicked.connect(self.result_selected.emit)
            item = QListWidgetItem(self.list_results)
            card.adjustSize()
            item.setSizeHint(card.sizeHint())
            self.list_results.addItem(item)
            self.list_results.setItemWidget(item, card)

    def query(self) -> str:
        return self._query


# Alias de compatibilité avec le registre (re-export pratique).
SettingsSearchResult = SettingSearchResult
SettingsRegistry = SettingsRegistry
