"""
Sélecteur visuel en grille de miniatures pour les dispositions d'interface (Layouts).
Conforme aux tokens sémantiques AnkiForge et aux règles d'accessibilité WCAG.
"""

import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.layouts.layout_manager import LayoutManager
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class LayoutThumbnailCard(QFrame):
    """
    Carte interactive présentant la miniature et la description d'une disposition (Layout).
    Gère le survol, le focus clavier (Entrée/Espace) et le retour d'état d'accessibilité.
    """

    selected = Signal(str)  # layout_id

    def __init__(
        self,
        layout_id: str,
        name: str,
        description: str,
        icon_name: str = "ph.layout",
        thumbnail_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.layout_id = layout_id
        self.name = name
        self.description = description
        self.icon_name = icon_name
        self.thumbnail_path = thumbnail_path
        self.is_selected: bool = False
        self.is_fallback_active: bool = False
        self.fallback_label: QLabel | None = None

        self.setObjectName("LayoutThumbnailCard")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._setup_ui()
        self._update_accessibility()
        self._apply_style()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Zone d'aperçu de la miniature (hauteur 110px)
        self.preview_container = QFrame()
        self.preview_container.setFixedHeight(110)
        self.preview_container.setObjectName("LayoutCardPreview")
        preview_layout = QVBoxLayout(self.preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(4)
        preview_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pixmap: QPixmap | None = None
        if self.thumbnail_path and self.thumbnail_path.is_file():
            loaded = QPixmap(str(self.thumbnail_path))
            if not loaded.isNull():
                pixmap = loaded

        if pixmap is not None:
            self.lbl_thumbnail = QLabel()
            self.lbl_thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # Mise à l'échelle douce conservant le ratio
            scaled_pixmap = pixmap.scaled(
                QSize(360, 110),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            rounded_pixmap = self._round_top_corners(scaled_pixmap, DesignTokens.RADIUS_MD - 1)
            self.lbl_thumbnail.setPixmap(rounded_pixmap)
            self.lbl_thumbnail.setScaledContents(False)
            preview_layout.addWidget(self.lbl_thumbnail)
        else:
            # Repli explicite : icône structurelle distinctive + libellé
            self.is_fallback_active = True
            self.preview_container.setStyleSheet(f"background-color: {DesignTokens.BG_INPUT}; border-top-left-radius: {DesignTokens.RADIUS_MD}px; border-top-right-radius: {DesignTokens.RADIUS_MD}px;")

            fallback_icon = QLabel()
            fallback_icon.setPixmap(load_phosphor_icon(self.icon_name, color=DesignTokens.TEXT_MUTED, weight="regular").pixmap(36, 36))
            fallback_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            preview_layout.addWidget(fallback_icon)

            self.fallback_label = QLabel("Aperçu indisponible")
            self.fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.fallback_label.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: 500;")
            preview_layout.addWidget(self.fallback_label)

        layout.addWidget(self.preview_container)

        # 2. Zone d'informations textuelles
        self.info_container = QWidget()
        self.info_container.setObjectName("LayoutCardInfo")
        info_layout = QVBoxLayout(self.info_container)
        info_layout.setContentsMargins(10, 8, 10, 8)
        info_layout.setSpacing(3)

        # Ligne de titre : icône + nom + badge de sélection
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)

        self.icon_badge = QLabel()
        self.icon_badge.setPixmap(load_phosphor_icon(self.icon_name, color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))
        header_row.addWidget(self.icon_badge)

        self.lbl_name = QLabel(self.name)
        self.lbl_name.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 600;")
        header_row.addWidget(self.lbl_name)
        header_row.addStretch()

        self.check_badge = QLabel()
        self.check_badge.setPixmap(load_phosphor_icon("ph.check-circle", color=DesignTokens.ACCENT_PRIMARY, weight="bold").pixmap(16, 16))
        self.check_badge.setVisible(False)
        header_row.addWidget(self.check_badge)

        info_layout.addLayout(header_row)

        # Description
        self.lbl_desc = QLabel(self.description)
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; line-height: 1.2;")
        info_layout.addWidget(self.lbl_desc)

        layout.addWidget(self.info_container)

    @staticmethod
    def _round_top_corners(pixmap: QPixmap, radius: int = 8) -> QPixmap:
        """Découpe les coins supérieurs d'un pixmap avec un rayon d'arrondi."""
        if pixmap.isNull() or radius <= 0:
            return pixmap
        out = QPixmap(pixmap.size())
        out.fill(Qt.GlobalColor.transparent)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        w = float(pixmap.width())
        h = float(pixmap.height())
        r = float(radius)
        path.moveTo(0, r)
        path.arcTo(0, 0, r * 2, r * 2, 180, -90)
        path.lineTo(w - r, 0)
        path.arcTo(w - r * 2, 0, r * 2, r * 2, 90, -90)
        path.lineTo(w, h)
        path.lineTo(0, h)
        path.closeSubpath()
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        return out

    def set_selected(self, selected: bool) -> None:
        """Met à jour l'état de sélection visuelle et les propriétés d'accessibilité."""
        self.is_selected = selected
        self.check_badge.setVisible(selected)
        self.setProperty("selected", "true" if selected else "false")
        self._update_accessibility()
        self._apply_style()
        self.style().polish(self)

    def _update_accessibility(self) -> None:
        state_suffix = " (sélectionnée)" if self.is_selected else ""
        self.setAccessibleName(f"Disposition {self.name}{state_suffix}")
        self.setAccessibleDescription(self.description)

    def _apply_style(self) -> None:
        border_color = DesignTokens.ACCENT_PRIMARY if self.is_selected else DesignTokens.BORDER_COLOR
        border_width = "2px" if self.is_selected else "1px"
        bg_card = DesignTokens.BG_PANEL

        self.setStyleSheet(f"""
            QFrame#LayoutThumbnailCard {{
                background-color: {bg_card};
                border: {border_width} solid {border_color};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame#LayoutThumbnailCard:hover {{
                border: {border_width} solid {DesignTokens.ACCENT_HOVER};
            }}
            QFrame#LayoutThumbnailCard:focus {{
                border: 2px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.selected.emit(self.layout_id)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.selected.emit(self.layout_id)
            event.accept()
        else:
            super().keyPressEvent(event)


class LayoutGridSelector(QWidget):
    """
    Grille de sélection de dispositions (Layouts) avec miniatures d'aperçu.
    Expose une API compatible par duck-typing avec QComboBox pour faciliter l'intégration
    dans GeneralTab et la détection d'état sale (dirty).
    """

    layout_changed = Signal(str)  # layout_id
    currentIndexChanged = Signal(int)  # index pour duck-typing QComboBox

    def __init__(
        self,
        current_layout_id: str | None = None,
        columns: int = 2,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._columns = max(1, columns)
        self._ordered_layout_ids: list[str] = []
        self._cards: dict[str, LayoutThumbnailCard] = {}
        self._current_layout_id: str = LayoutManager.DEFAULT_LAYOUT_ID

        self._grid_layout = QGridLayout(self)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(10)

        self._populate_cards()

        target_id = current_layout_id or LayoutManager.DEFAULT_LAYOUT_ID
        self.set_current_layout_id(target_id)

    @property
    def cards(self) -> dict[str, LayoutThumbnailCard]:
        return self._cards

    def _populate_cards(self) -> None:
        # Nettoyage
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._cards.clear()
        self._ordered_layout_ids.clear()

        layouts = LayoutManager.get_available_layouts()
        for idx, item in enumerate(layouts):
            lid = item["id"]
            self._ordered_layout_ids.append(lid)
            thumb_path = LayoutManager.get_layout_thumbnail_path(lid)
            card = LayoutThumbnailCard(
                layout_id=lid,
                name=item["name"],
                description=item["description"],
                icon_name=item.get("icon", "ph.layout"),
                thumbnail_path=thumb_path,
                parent=self,
            )
            card.selected.connect(self._on_card_selected)

            row = idx // self._columns
            col = idx % self._columns
            self._grid_layout.addWidget(card, row, col)
            self._cards[lid] = card

    def _on_card_selected(self, layout_id: str) -> None:
        if layout_id != self._current_layout_id:
            self.set_current_layout_id(layout_id)

    def set_current_layout_id(self, layout_id: str) -> None:
        """Sélectionne le layout par son identifiant."""
        resolved = LayoutManager.resolve_layout_id(layout_id)
        self._current_layout_id = resolved

        for lid, card in self._cards.items():
            card.set_selected(lid == resolved)

        self.layout_changed.emit(resolved)
        try:
            idx = self._ordered_layout_ids.index(resolved)
            self.currentIndexChanged.emit(idx)
        except ValueError:
            pass

    def current_layout_id(self) -> str:
        """Retourne l'identifiant du layout sélectionné."""
        return self._current_layout_id

    # ── Duck-typing QComboBox pour GeneralTab et SettingsDirtyMixin ─────────

    def currentData(self, role: int = Qt.ItemDataRole.UserRole) -> str:
        return self._current_layout_id

    def currentText(self) -> str:
        card = self._cards.get(self._current_layout_id)
        return card.name if card else self._current_layout_id

    def currentIndex(self) -> int:
        try:
            return self._ordered_layout_ids.index(self._current_layout_id)
        except ValueError:
            return 0

    def setCurrentIndex(self, index: int) -> None:
        if 0 <= index < len(self._ordered_layout_ids):
            self.set_current_layout_id(self._ordered_layout_ids[index])

    def count(self) -> int:
        return len(self._ordered_layout_ids)

    def itemData(self, index: int, role: int = Qt.ItemDataRole.UserRole) -> str | None:
        if 0 <= index < len(self._ordered_layout_ids):
            return self._ordered_layout_ids[index]
        return None

    # ── Navigation au Clavier (Flèches directionnelles) ───────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        curr_idx = self.currentIndex()
        row = curr_idx // self._columns
        col = curr_idx % self._columns
        total = len(self._ordered_layout_ids)
        total_rows = (total + self._columns - 1) // self._columns

        key = event.key()
        new_idx = curr_idx

        if key == Qt.Key.Key_Right:
            new_idx = (curr_idx + 1) % total
        elif key == Qt.Key.Key_Left:
            new_idx = (curr_idx - 1 + total) % total
        elif key == Qt.Key.Key_Down:
            target_row = (row + 1) % total_rows
            cand = target_row * self._columns + col
            new_idx = cand if cand < total else curr_idx
        elif key == Qt.Key.Key_Up:
            target_row = (row - 1 + total_rows) % total_rows
            cand = target_row * self._columns + col
            new_idx = cand if cand < total else curr_idx
        else:
            super().keyPressEvent(event)
            return

        if new_idx != curr_idx:
            target_lid = self._ordered_layout_ids[new_idx]
            self.set_current_layout_id(target_lid)
            card = self._cards.get(target_lid)
            if card:
                card.setFocus(Qt.FocusReason.TabFocusReason)
            event.accept()
