"""
Composant fil d'Ariane prévisionnel interactif (HierarchyBreadcrumbBar).

Affiche en temps réel la décomposition horizontale d'un chemin hiérarchique (paquet,
dossier de documents ou tag), distingue visuellement les nœuds existants des nœuds
nouveaux via des badges contrastés, et permet de tronquer interactivement le chemin
par un simple clic sur un segment parent.

Conforme à l'ADR 0027, DESIGN.md et aux Règles d'ingénierie AnkiForge (ADR 0013, typage strict).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QWidget,
)

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.hierarchy import SEPARATOR as _DEFAULT_SEPARATOR
from ankiforge.utils.hierarchy import join_hierarchy, split_hierarchy
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class BreadcrumbSegmentButton(QPushButton):
    """
    Pastille cliquable représentant un niveau hiérarchique au sein du fil d'Ariane.

    Distingue visuellement les nœuds existants (icône dossier neutre / bleu)
    des nouveaux nœuds à créer (icône dossier avec plus, fond teinté création).
    """

    segment_clicked = Signal(str)

    def __init__(
        self,
        segment_name: str,
        subpath: str,
        is_existing: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.segment_name = segment_name
        self.subpath = subpath
        self.is_existing = is_existing

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(24)
        self.setIconSize(QSize(13, 13))

        # Échappement des esperluettes pour éviter l'interprétation de mnémoniques Qt
        clean_title = segment_name.replace("&", "&&")
        self.setText(clean_title)

        self._update_accessibility_and_tooltips()
        self._apply_style()

        self.clicked.connect(self._on_clicked)

    def _on_clicked(self) -> None:
        self.segment_clicked.emit(self.subpath)

    def set_existing_status(self, is_existing: bool) -> None:
        """Met à jour l'état existant/nouveau et réapplique le style adéquat."""
        if self.is_existing == is_existing:
            return
        self.is_existing = is_existing
        self._update_accessibility_and_tooltips()
        self._apply_style()

    def _update_accessibility_and_tooltips(self) -> None:
        if self.is_existing:
            tooltip_msg = tr(
                "Nœud existant : %1\nCliquer pour tronquer la saisie à ce niveau",
                self.subpath,
            )
            accessible_msg = tr("%1 (existant)", self.segment_name)
        else:
            tooltip_msg = tr(
                "Nouveau nœud : %1\nCliquer pour tronquer la saisie à ce niveau",
                self.subpath,
            )
            accessible_msg = tr("%1 (nouveau)", self.segment_name)

        self.setToolTip(tooltip_msg)
        self.setAccessibleName(accessible_msg)

    def _apply_style(self, profile: Any = None) -> None:
        # Résolution des jetons sémantiques
        bg_panel = profile.bg_panel if profile else DesignTokens.BG_PANEL
        bg_hover = profile.bg_hover if profile else DesignTokens.BG_HOVER
        border_col = profile.border_color if profile else DesignTokens.BORDER_COLOR
        text_primary = profile.text_primary if profile else DesignTokens.TEXT_PRIMARY
        color_green = profile.color_green if profile else DesignTokens.COLOR_GREEN
        color_green_bg = DesignTokens.COLOR_GREEN_BG
        color_green_border = DesignTokens.COLOR_GREEN_BORDER
        color_blue = profile.color_blue if profile else DesignTokens.COLOR_BLUE
        font_main = profile.font_main if profile else DesignTokens.FONT_MAIN

        if self.is_existing:
            # Nœud existant : style discret et neutre
            icon = load_phosphor_icon("folder", color=color_blue)
            self.setIcon(icon)
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg_panel};
                    color: {text_primary};
                    border: 1px solid {border_col};
                    border-radius: 12px;
                    padding: 2px 8px 2px 6px;
                    font-size: 11px;
                    font-weight: 500;
                    font-family: '{font_main}';
                }}
                QPushButton:hover {{
                    background-color: {bg_hover};
                    border-color: {color_blue};
                    color: {text_primary};
                }}
                QPushButton:pressed {{
                    background-color: {bg_panel};
                }}
            """)
        else:
            # Nouveau nœud : style teinté création
            icon = load_phosphor_icon("folder-plus", color=color_green)
            self.setIcon(icon)
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color_green_bg};
                    color: {color_green};
                    border: 1px solid {color_green_border};
                    border-radius: 12px;
                    padding: 2px 8px 2px 6px;
                    font-size: 11px;
                    font-weight: 600;
                    font-family: '{font_main}';
                }}
                QPushButton:hover {{
                    background-color: {color_green_bg};
                    border-color: {color_green};
                    color: {text_primary};
                }}
                QPushButton:pressed {{
                    background-color: {bg_hover};
                }}
            """)

    def refresh_theme(self, profile: Any = None) -> None:
        """Rafraîchit les styles et icônes lors d'un changement de thème."""
        self._apply_style(profile)


class HierarchyBreadcrumbBar(QWidget):
    """
    Bandeau horizontal interactif de fil d'Ariane pour chemins hiérarchiques.

    Affiche la chaîne de nœuds découpée, distingue ceux qui existent déjà en base
    de ceux en cours de création, et transmet un signal lorsqu'un segment parent
    est cliqué afin de tronquer la saisie.
    """

    segment_clicked = Signal(str)

    def __init__(
        self,
        initial_path: str = "",
        existing_paths: Iterable[str] | None = None,
        separator: str = _DEFAULT_SEPARATOR,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._separator = separator
        self._current_path: str = ""
        self._existing_paths: set[str] = set()
        self._segment_buttons: list[BreadcrumbSegmentButton] = []
        self._separator_labels: list[QLabel] = []

        if existing_paths is not None:
            self._existing_paths = {p.strip() for p in existing_paths if p and p.strip()}

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(28)

        self._setup_ui()

        if initial_path:
            self.set_path(initial_path)

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Zone scrollable sans ascenseur ni bordure pour gérer les chemins profonds
        self._scroll_area = QScrollArea(self)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:horizontal {
                height: 4px;
                background: transparent;
            }
            QScrollBar::handle:horizontal {
                background: rgba(255, 255, 255, 0.15);
                border-radius: 2px;
            }
        """)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent; border: none;")
        self._items_layout = QHBoxLayout(self._container)
        self._items_layout.setContentsMargins(0, 2, 0, 2)
        self._items_layout.setSpacing(4)
        self._items_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._scroll_area.setWidget(self._container)
        main_layout.addWidget(self._scroll_area)

    def current_path(self) -> str:
        """Retourne le chemin complet actuellement représenté."""
        return self._current_path

    def segments(self) -> list[str]:
        """Retourne la liste ordonnée des noms de segments individuels."""
        return [btn.segment_name for btn in self._segment_buttons]

    def subpaths(self) -> list[str]:
        """Retourne la liste ordonnée des sous-chemins cumulés jusqu'à chaque niveau."""
        return [btn.subpath for btn in self._segment_buttons]

    def segment_count(self) -> int:
        """Retourne le nombre de segments actuellement affichés."""
        return len(self._segment_buttons)

    def is_segment_existing(self, index: int) -> bool:
        """Indique si le segment à l'index donné correspond à un chemin déjà existant."""
        if 0 <= index < len(self._segment_buttons):
            return self._segment_buttons[index].is_existing
        return False

    def segment_buttons(self) -> list[BreadcrumbSegmentButton]:
        """Retourne une copie de la liste des boutons de segments (utile pour les tests et l'inspection)."""
        return list(self._segment_buttons)

    def separator_labels(self) -> list[QLabel]:
        """Retourne une copie de la liste des labels séparateurs."""
        return list(self._separator_labels)

    def set_existing_paths(self, existing_paths: Iterable[str]) -> None:
        """
        Met à jour la collection des chemins existants et rafraîchit les statuts visuels.
        """
        self._existing_paths = {p.strip() for p in existing_paths if p and p.strip()}
        for btn in self._segment_buttons:
            is_existing = btn.subpath in self._existing_paths
            btn.set_existing_status(is_existing)

    def set_path(
        self,
        path: str,
        existing_paths: Iterable[str] | None = None,
    ) -> None:
        """
        Découpe et affiche réactivement le chemin hiérarchique en segments.

        Args:
            path: Chemin hiérarchique complet (ex: "Sciences::Physique::Thermodynamique").
            existing_paths: Collection optionnelle des chemins existants en base.
        """
        if existing_paths is not None:
            self._existing_paths = {p.strip() for p in existing_paths if p and p.strip()}

        self._current_path = path or ""

        # Découpage du chemin selon le séparateur configuré
        raw_segments = split_hierarchy(self._current_path, strip=True) if self._separator == _DEFAULT_SEPARATOR else [p.strip() for p in self._current_path.split(self._separator) if p.strip()]

        self._rebuild_items(raw_segments)

    def clear(self) -> None:
        """Efface tous les segments et réinitialise le chemin courant."""
        self._current_path = ""
        self._rebuild_items([])

    def _rebuild_items(self, segments: list[str]) -> None:
        """Reconstruit les boutons de segments et les chevrons intercalaires."""
        # Nettoyage complet des anciens widgets
        for btn in self._segment_buttons:
            self._items_layout.removeWidget(btn)
            btn.deleteLater()
        self._segment_buttons.clear()

        for lbl in self._separator_labels:
            self._items_layout.removeWidget(lbl)
            lbl.deleteLater()
        self._separator_labels.clear()

        if not segments:
            return

        cumulated_parts: list[str] = []

        for idx, segment in enumerate(segments):
            cumulated_parts.append(segment)
            subpath = join_hierarchy(cumulated_parts) if self._separator == _DEFAULT_SEPARATOR else self._separator.join(cumulated_parts)

            is_existing = subpath in self._existing_paths

            # Si ce n'est pas le premier segment, insérer un séparateur chevron
            if idx > 0:
                sep_lbl = QLabel(self._container)
                sep_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                sep_icon = load_phosphor_icon("caret-right", color=DesignTokens.TEXT_MUTED)
                sep_lbl.setPixmap(sep_icon.pixmap(12, 12))
                sep_lbl.setStyleSheet("background: transparent; border: none; padding: 0 1px;")
                self._items_layout.addWidget(sep_lbl)
                self._separator_labels.append(sep_lbl)

            btn = BreadcrumbSegmentButton(
                segment_name=segment,
                subpath=subpath,
                is_existing=is_existing,
                parent=self._container,
            )
            btn.segment_clicked.connect(self.segment_clicked.emit)
            self._items_layout.addWidget(btn)
            self._segment_buttons.append(btn)

    def refresh_theme(self, profile: Any = None) -> None:
        """Rafraîchit l'ensemble des éléments enfants selon le profil de thème actif."""
        text_muted = profile.text_muted if profile else DesignTokens.TEXT_MUTED
        sep_icon = load_phosphor_icon("caret-right", color=text_muted)
        pix = sep_icon.pixmap(12, 12)
        for lbl in self._separator_labels:
            lbl.setPixmap(pix)
        for btn in self._segment_buttons:
            btn.refresh_theme(profile)
