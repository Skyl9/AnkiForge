"""
Widget de mini-graphique d'activité sur 7 jours (cartes créées vs modifiées).
Rendu 100% natif Qt / PySide6 via QPainter, avec infobulle interactive et réactivité aux thèmes.
"""

from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QPainterPath
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolTip

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class ActivityChartWidget(QWidget):
    """Mini-graphique à barres 7 jours affichant le volume de cartes créées et éditées."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumHeight(135)
        self.setMaximumHeight(155)
        self.setMouseTracking(True)

        self._data: List[Dict[str, Any]] = []
        self._hovered_index: int = -1

        # Configuration UI
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 6)
        layout.setSpacing(4)

        # En-tête compact avec titre et légende
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        self.title_icon = QLabel()
        self.title_icon.setPixmap(load_phosphor_icon("ph.chart-bar", color=DesignTokens.TEXT_PRIMARY).pixmap(14, 14))
        self.title_label = QLabel("Activité (7j)")
        self.title_label.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        self.title_label.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

        header_layout.addWidget(self.title_icon)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        # Légende compacte
        self.legend_created_dot = QLabel("■")
        self.legend_created_dot.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        self.legend_created_dot.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; border: none; background: transparent;")
        self.legend_created_lbl = QLabel("Créées")
        self.legend_created_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        self.legend_created_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")

        self.legend_modified_dot = QLabel("■")
        self.legend_modified_dot.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        self.legend_modified_dot.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; border: none; background: transparent;")
        self.legend_modified_lbl = QLabel("Modifiées")
        self.legend_modified_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        self.legend_modified_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")

        header_layout.addWidget(self.legend_created_dot)
        header_layout.addWidget(self.legend_created_lbl)
        header_layout.addSpacing(4)
        header_layout.addWidget(self.legend_modified_dot)
        header_layout.addWidget(self.legend_modified_lbl)

        layout.addLayout(header_layout)
        layout.addStretch()

    def set_data(self, data: List[Dict[str, Any]]) -> None:
        """Met à jour les données du graphique."""
        self._data = data or []
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        top_margin = 32  # Place pour l'en-tête
        bottom_margin = 20  # Place pour les labels de jours
        chart_height = max(10, h - top_margin - bottom_margin)
        chart_width = max(10, w - 20)

        if not self._data:
            painter.setPen(QColor(DesignTokens.TEXT_MUTED))
            painter.setFont(QFont(DesignTokens.FONT_MAIN, 10))
            painter.drawText(
                QRectF(0, top_margin, w, chart_height),
                Qt.AlignmentFlag.AlignCenter,
                "Aucune donnée d'activité",
            )
            return

        num_items = len(self._data)
        slot_width = chart_width / num_items
        bar_width = max(8.0, min(16.0, slot_width * 0.45))

        # Trouver le maximum pour l'échelle (au moins 5)
        max_val = max([item.get("total", 0) for item in self._data] + [5])

        start_x = 10.0
        base_y = top_margin + chart_height

        # Ligne de base subtile
        painter.setPen(QPen(QColor(DesignTokens.BORDER_LIGHT), 1, Qt.PenStyle.SolidLine))
        painter.drawLine(int(start_x), int(base_y), int(start_x + chart_width), int(base_y))

        for i, item in enumerate(self._data):
            slot_center_x = start_x + (i + 0.5) * slot_width
            bar_x = slot_center_x - (bar_width / 2.0)

            created = item.get("created", 0)
            modified = item.get("modified", 0)
            total = created + modified

            # Hauteurs relatives
            total_bar_height = (total / max_val) * chart_height if max_val > 0 else 0
            created_bar_height = (created / max_val) * chart_height if max_val > 0 else 0
            modified_bar_height = (modified / max_val) * chart_height if max_val > 0 else 0

            is_hovered = i == self._hovered_index

            # 1. Fond de colonne / rail arrondi fin
            rail_rect = QRectF(bar_x, top_margin + 2, bar_width, chart_height - 2)
            rail_color = QColor(DesignTokens.BG_HOVER) if is_hovered else QColor("rgba(255, 255, 255, 0.04)")
            painter.setBrush(QBrush(rail_color))
            painter.setPen(Qt.PenStyle.NoPen)
            rail_path = QPainterPath()
            rail_path.addRoundedRect(rail_rect, 3, 3)
            painter.drawPath(rail_path)

            # 2. Barre "Modifiées" (partie haute)
            if modified_bar_height > 0:
                mod_rect = QRectF(bar_x, base_y - total_bar_height, bar_width, modified_bar_height)
                mod_color = QColor(DesignTokens.COLOR_BLUE)
                if is_hovered:
                    mod_color = mod_color.lighter(115)
                painter.setBrush(QBrush(mod_color))
                painter.setPen(Qt.PenStyle.NoPen)
                mod_path = QPainterPath()
                mod_path.addRoundedRect(mod_rect, 3, 3)
                painter.drawPath(mod_path)

            # 3. Barre "Créées" (partie basse)
            if created_bar_height > 0:
                created_rect = QRectF(bar_x, base_y - created_bar_height, bar_width, created_bar_height)
                created_color = QColor(DesignTokens.ACCENT_PRIMARY)
                if is_hovered:
                    created_color = created_color.lighter(115)
                painter.setBrush(QBrush(created_color))
                painter.setPen(Qt.PenStyle.NoPen)
                created_path = QPainterPath()
                created_path.addRoundedRect(created_rect, 3, 3)
                painter.drawPath(created_path)

            # 4. Total au-dessus de la barre si hovered ou si > 0
            if total > 0:
                painter.setFont(
                    QFont(
                        DesignTokens.FONT_MAIN,
                        8,
                        QFont.Weight.Bold if is_hovered else QFont.Weight.Normal,
                    )
                )
                painter.setPen(QColor(DesignTokens.TEXT_PRIMARY if is_hovered else DesignTokens.TEXT_MUTED))
                label_y = max(top_margin - 2, base_y - total_bar_height - 12)
                painter.drawText(
                    QRectF(slot_center_x - 15, label_y, 30, 10),
                    Qt.AlignmentFlag.AlignCenter,
                    str(total),
                )

            # 5. Label du jour propre (ex: "Dim", "Lun", "Mar")
            raw_label = item.get("label", "")
            # Extraire les 3 premières lettres pour éviter tout chevauchement
            day_abbr = raw_label.split()[0] if " " in raw_label else raw_label
            painter.setFont(
                QFont(
                    DesignTokens.FONT_MAIN,
                    9,
                    QFont.Weight.Bold if is_hovered else QFont.Weight.Normal,
                )
            )
            painter.setPen(QColor(DesignTokens.ACCENT_PRIMARY if is_hovered else DesignTokens.TEXT_MUTED))
            painter.drawText(
                QRectF(slot_center_x - (slot_width / 2.0), base_y + 3, slot_width, 14),
                Qt.AlignmentFlag.AlignCenter,
                day_abbr,
            )

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        w = self.width()
        chart_width = max(10, w - 20)
        num_items = len(self._data)

        if num_items > 0:
            x = event.position().x() - 10.0
            slot_width = chart_width / num_items
            idx = int(x // slot_width)

            if 0 <= idx < num_items:
                if self._hovered_index != idx:
                    self._hovered_index = idx
                    self.update()

                    # Tooltip informatif
                    item = self._data[idx]
                    date_str = item.get("date", "")
                    created = item.get("created", 0)
                    modified = item.get("modified", 0)
                    total = item.get("total", 0)

                    tooltip_text = (
                        f"<b>{item.get('label', '')} ({date_str})</b><br>" f"⚡ <b>{created}</b> cartes créées<br>" f"✏️ <b>{modified}</b> cartes révisées<br>" f"📊 Total : <b>{total}</b> actions"
                    )
                    QToolTip.showText(event.globalPosition().toPoint(), tooltip_text, self)
                return

        if self._hovered_index != -1:
            self._hovered_index = -1
            self.update()
            QToolTip.hideText()

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hovered_index != -1:
            self._hovered_index = -1
            self.update()
            QToolTip.hideText()
        super().leaveEvent(event)

    def refresh_theme(self, profile: Any) -> None:
        """Réapplique les couleurs thématiques dynamiques."""
        self.title_icon.setPixmap(load_phosphor_icon("ph.chart-bar", color=profile.text_primary).pixmap(14, 14))
        self.title_label.setStyleSheet(f"color: {profile.text_primary}; border: none; background: transparent;")
        self.legend_created_dot.setStyleSheet(f"color: {profile.accent_primary}; border: none; background: transparent;")
        self.legend_created_lbl.setStyleSheet(f"color: {profile.text_muted}; border: none; background: transparent;")
        self.legend_modified_dot.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; border: none; background: transparent;")
        self.legend_modified_lbl.setStyleSheet(f"color: {profile.text_muted}; border: none; background: transparent;")
        self.update()
