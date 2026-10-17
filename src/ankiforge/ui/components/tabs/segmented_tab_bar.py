"""Composant d'onglets et de sous-onglets unifié pour AnkiForge.

Fournit une barre d'onglets segmentée ou de sous-panneaux avec gestion des styles
sémantiques via DesignTokens, badges d'état et navigation au clavier.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class SegmentedTabButton(QPushButton):
    """Bouton individuel au sein d'une SegmentedTabBar."""

    def __init__(
        self,
        tab_id: str,
        text: str,
        icon_name: str = "",
        badge_text: str = "",
        variant: str = "subtab",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.tab_id = tab_id
        self.raw_text = text
        self.icon_name = icon_name
        self.badge_text = badge_text
        self.variant = variant

        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(30 if variant == "subtab" else 32)
        self.setIconSize(QSize(15, 15))

        size_policy = self.sizePolicy()
        size_policy.setHorizontalPolicy(QSizePolicy.Policy.Minimum)
        self.setSizePolicy(size_policy)

        self._badge_label: QLabel | None = None
        self._setup_badge()
        self._update_display()
        self.toggled.connect(self._on_toggled)

    def set_active(self, active: bool) -> None:
        """Active ou désactive l'état sélectionné du bouton."""
        self.setChecked(active)

    def _setup_badge(self) -> None:
        if self.badge_text:
            if self._badge_label is None:
                self._badge_label = QLabel(self)
                self._badge_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._badge_label.setFixedHeight(16)
                self._badge_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._update_badge_style()

    def _update_badge_style(self) -> None:
        if self._badge_label is None:
            return
        is_active = self.isChecked()
        bg_color = DesignTokens.ACCENT_PRIMARY if not is_active else DesignTokens.BG_ACTIVE
        text_color = DesignTokens.TEXT_ON_ACCENT if not is_active else DesignTokens.TEXT_PRIMARY
        self._badge_label.setText(self.badge_text)
        self._badge_label.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                border-radius: 8px;
                padding: 0 5px;
                font-size: 10px;
                font-weight: bold;
            }}
        """)
        self._badge_label.adjustSize()

    def _badge_width(self) -> int:
        """Retourne la largeur effective du badge label pour réserver l'espacement."""
        if not self.badge_text or self._badge_label is None or self._badge_label.isHidden():
            return 0
        self._badge_label.adjustSize()
        return max(self._badge_label.sizeHint().width(), self._badge_label.width(), 16)

    def sizeHint(self) -> QSize:
        """Calcule la taille optimale de l'onglet en réservant l'espace du badge."""
        hint = super().sizeHint()
        bw = self._badge_width()
        if bw > 0:
            hint.setWidth(hint.width() + bw + 10)
        return hint

    def minimumSizeHint(self) -> QSize:
        """Retourne la taille minimale requise."""
        return self.sizeHint()

    def set_badge(self, text: str) -> None:
        """Met à jour le texte du badge."""
        self.badge_text = text
        if text:
            if self._badge_label is None:
                self._badge_label = QLabel(self)
                self._badge_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._badge_label.setFixedHeight(16)
                self._badge_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._update_badge_style()
            self._badge_label.show()
        elif self._badge_label is not None:
            self._badge_label.hide()
        self._update_display()
        self.updateGeometry()
        if self._badge_label is not None and text and not self._badge_label.isHidden():
            self._badge_label.adjustSize()
            badge_w = self._badge_label.width()
            badge_h = self._badge_label.height()
            self._badge_label.move(self.width() - badge_w - 8, (self.height() - badge_h) // 2)
            self._badge_label.raise_()

    def _update_display(self) -> None:
        suffix = f"  {self.badge_text}" if self.badge_text and self._badge_label is None else ""
        self.setText(f" {self.raw_text}{suffix}" if self.icon_name else f"{self.raw_text}{suffix}")
        self._apply_style(self.isChecked())

    def _on_toggled(self, checked: bool) -> None:
        self._apply_style(checked)
        if self._badge_label is not None and self.badge_text:
            self._update_badge_style()

    def _apply_style(self, active: bool) -> None:
        if self.icon_name:
            icon_color = DesignTokens.ACCENT_PRIMARY if active else DesignTokens.TEXT_MUTED
            self.setIcon(load_phosphor_icon(self.icon_name, color=icon_color))

        bw = self._badge_width()

        if self.variant == "segmented":
            base_pad = 12
            right_pad = (bw + 14) if bw > 0 else base_pad
            if active:
                self.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {DesignTokens.ACCENT_PRIMARY};
                        color: {DesignTokens.TEXT_ON_ACCENT};
                        border: none;
                        border-radius: {DesignTokens.RADIUS_SM}px;
                        padding: 0 {right_pad}px 0 {base_pad}px;
                        font-size: 12px;
                        font-weight: 600;
                    }}
                """)
            else:
                self.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: {DesignTokens.TEXT_SECONDARY};
                        border: none;
                        border-radius: {DesignTokens.RADIUS_SM}px;
                        padding: 0 {right_pad}px 0 {base_pad}px;
                        font-size: 12px;
                        font-weight: 500;
                    }}
                    QPushButton:hover {{
                        background-color: {DesignTokens.BG_HOVER};
                        color: {DesignTokens.TEXT_PRIMARY};
                    }}
                """)
        else:
            # Mode "subtab" par défaut (souligné accent style IDE)
            base_pad = 14
            right_pad = (bw + 16) if bw > 0 else base_pad
            if active:
                self.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {DesignTokens.BG_PANEL};
                        color: {DesignTokens.TEXT_PRIMARY};
                        border: 1px solid {DesignTokens.BORDER_COLOR};
                        border-bottom: 2px solid {DesignTokens.ACCENT_PRIMARY};
                        border-radius: {DesignTokens.RADIUS_SM}px;
                        padding: 2px {right_pad}px 2px {base_pad}px;
                        font-size: 11.5px;
                        font-weight: bold;
                    }}
                """)
            else:
                self.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: {DesignTokens.TEXT_SECONDARY};
                        border: 1px solid transparent;
                        border-radius: {DesignTokens.RADIUS_SM}px;
                        padding: 2px {right_pad}px 2px {base_pad}px;
                        font-size: 11.5px;
                    }}
                    QPushButton:hover {{
                        background-color: {DesignTokens.BG_HOVER};
                        color: {DesignTokens.TEXT_PRIMARY};
                    }}
                """)

    def set_text(self, text: str) -> None:
        """Met à jour le libellé texte de l'onglet."""
        self.raw_text = text
        self._update_display()
        self.updateGeometry()

    def set_icon(self, icon: Any) -> None:
        """Met à jour l'icône de l'onglet."""
        if isinstance(icon, str):
            self.icon_name = icon
            self._apply_style(self.isChecked())
        elif hasattr(icon, "pixmap") or hasattr(icon, "isNull"):
            self.setIcon(icon)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if self._badge_label is not None and self.badge_text and not self._badge_label.isHidden():
            self._badge_label.adjustSize()
            badge_w = self._badge_label.width()
            badge_h = self._badge_label.height()
            self._badge_label.move(self.width() - badge_w - 8, (self.height() - badge_h) // 2)
            self._badge_label.raise_()


class SegmentedTabBar(QWidget):
    """Barre de sous-onglets modulaire avec navigation clavier et adaptation au thème."""

    tab_changed = Signal(str)  # tab_id
    tab_index_changed = Signal(int)  # index
    currentChanged = tab_index_changed

    def __init__(
        self,
        variant: str = "subtab",
        parent: QWidget | None = None,
        mode: str | None = None,
    ) -> None:
        super().__init__(parent)
        actual_variant = mode if mode is not None else variant
        self.variant = actual_variant
        self._tabs: list[SegmentedTabButton] = []
        self._tabs_by_id: dict[str, SegmentedTabButton] = {}

        self.layout_h = QHBoxLayout(self)
        self.layout_h.setContentsMargins(0, 0, 0, 0)
        self.layout_h.setSpacing(4 if self.variant == "subtab" else 2)

        if self.variant == "segmented":
            self.setStyleSheet(f"""
                SegmentedTabBar {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                    padding: 2px;
                }}
            """)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)
        self.btn_group.idClicked.connect(self._on_id_clicked)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def add_tab(self, tab_id: str, text: str, icon_name: str = "", badge_text: str = "") -> SegmentedTabButton:
        """Ajoute un onglet et retourne le bouton créé."""
        index = len(self._tabs)
        btn = SegmentedTabButton(
            tab_id=tab_id,
            text=text,
            icon_name=icon_name,
            badge_text=badge_text,
            variant=self.variant,
            parent=self,
        )
        self.btn_group.addButton(btn, index)
        self._tabs.append(btn)
        self._tabs_by_id[tab_id] = btn
        self.layout_h.addWidget(btn)

        if len(self._tabs) == 1:
            btn.setChecked(True)

        return btn

    def set_active_tab(self, tab_id_or_index: str | int) -> None:
        """Active l'onglet spécifié par son identifiant ou son index numérique."""
        if isinstance(tab_id_or_index, int):
            if 0 <= tab_id_or_index < len(self._tabs):
                self._tabs[tab_id_or_index].setChecked(True)
                self.tab_index_changed.emit(tab_id_or_index)
                self.tab_changed.emit(self._tabs[tab_id_or_index].tab_id)
        elif isinstance(tab_id_or_index, str):
            btn = self._tabs_by_id.get(tab_id_or_index)
            if btn:
                btn.setChecked(True)
                idx = self._tabs.index(btn)
                self.tab_index_changed.emit(idx)
                self.tab_changed.emit(tab_id_or_index)

    def get_active_tab_id(self) -> str | None:
        """Retourne l'identifiant de l'onglet actif."""
        for btn in self._tabs:
            if btn.isChecked():
                return btn.tab_id
        return None

    def get_active_index(self) -> int:
        """Retourne l'index de l'onglet actif."""
        for i, btn in enumerate(self._tabs):
            if btn.isChecked():
                return i
        return -1

    def currentIndex(self) -> int:
        """Alias compatible QTabBar pour get_active_index."""
        return self.get_active_index()

    def setCurrentIndex(self, index: int) -> None:
        """Alias compatible QTabBar pour set_active_tab."""
        self.set_active_tab(index)

    def tabText(self, index: int) -> str:
        """Retourne le texte de l'onglet à l'index donné, incluant le badge le cas échéant."""
        if 0 <= index < len(self._tabs):
            btn = self._tabs[index]
            if btn.badge_text:
                return f"{btn.raw_text} ({btn.badge_text})"
            return btn.raw_text
        return ""

    def setTabText(self, index: int, text: str) -> None:
        """Met à jour le texte de l'onglet à l'index donné."""
        if 0 <= index < len(self._tabs):
            self._tabs[index].set_text(text)

    def set_tab_text(self, tab_id_or_index: str | int, text: str) -> None:
        """Met à jour le texte de l'onglet par identifiant ou index."""
        if isinstance(tab_id_or_index, int):
            self.setTabText(tab_id_or_index, text)
        else:
            btn = self._tabs_by_id.get(tab_id_or_index)
            if btn:
                btn.set_text(text)

    def setTabIcon(self, index: int, icon: Any) -> None:
        """Met à jour l'icône de l'onglet à l'index donné."""
        if 0 <= index < len(self._tabs):
            self._tabs[index].set_icon(icon)

    def set_tab_icon(self, tab_id_or_index: str | int, icon: Any) -> None:
        """Met à jour l'icône de l'onglet par identifiant ou index."""
        if isinstance(tab_id_or_index, int):
            self.setTabIcon(tab_id_or_index, icon)
        else:
            btn = self._tabs_by_id.get(tab_id_or_index)
            if btn:
                btn.set_icon(icon)

    def set_tab_badge(self, tab_id: str, badge_text: str) -> None:
        """Met à jour le badge d'un onglet."""
        btn = self._tabs_by_id.get(tab_id)
        if btn:
            btn.set_badge(badge_text)

    def tab_badge(self, tab_id: str) -> str:
        """Retourne le badge d'un onglet."""
        btn = self._tabs_by_id.get(tab_id)
        return btn.badge_text if btn else ""

    def set_tab_enabled(self, tab_id: str, enabled: bool) -> None:
        """Active ou désactive un onglet."""
        btn = self._tabs_by_id.get(tab_id)
        if btn:
            btn.setEnabled(enabled)

    def count(self) -> int:
        """Retourne le nombre d'onglets."""
        return len(self._tabs)

    def _on_id_clicked(self, index: int) -> None:
        if 0 <= index < len(self._tabs):
            tab_id = self._tabs[index].tab_id
            self.tab_index_changed.emit(index)
            self.tab_changed.emit(tab_id)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Permet de faire défiler les onglets avec les touches fléchées."""
        curr_idx = self.get_active_index()
        if curr_idx < 0:
            super().keyPressEvent(event)
            return

        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            new_idx = max(0, curr_idx - 1)
            self.set_active_tab(new_idx)
            event.accept()
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            new_idx = min(len(self._tabs) - 1, curr_idx + 1)
            self.set_active_tab(new_idx)
            event.accept()
        else:
            super().keyPressEvent(event)

    def refresh_theme(self, profile: Any = None) -> None:
        """Met à jour l'apparence de tous les onglets lors d'un changement de thème."""
        if self.variant == "segmented":
            self.setStyleSheet(f"""
                SegmentedTabBar {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                    padding: 2px;
                }}
            """)
        for btn in self._tabs:
            btn._apply_style(btn.isChecked())
            btn._update_badge_style()


class SubTabButton(SegmentedTabButton):
    """Bouton d'onglet style IDE avec relief et indicateur d'accent.

    Fourni pour la compatibilité avec l'ancienne classe SubTabButton.
    """

    def __init__(
        self,
        text: str,
        icon_name: str = "",
        is_active: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            tab_id=text,
            text=text,
            icon_name=icon_name,
            variant="subtab",
            parent=parent,
        )
        self.set_active(is_active)


__all__ = ["SegmentedTabBar", "SegmentedTabButton", "SubTabButton"]
