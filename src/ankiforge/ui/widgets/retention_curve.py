"""
Widget de courbe de rétention projetée (courbe d'oubli) et de charge à l'équilibre.

Rendu 100 % natif Qt / PySide6 via QPainter, piloté par les données de
``FsrsProjectionService`` : la courbe est ancrée à la révision (100 % à J0) et
décroît selon la loi de puissance FSRS. Aucune donnée n'est fabriquée ; en
l'absence de cartes révisées, le widget affiche un état vide explicite.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

#: Borne basse de l'axe des ordonnées (les valeurs inférieures sont écrêtées au plancher).
_Y_MIN = 0.50
#: Graduations affichées sur l'axe des ordonnées (fractions de rétention).
_Y_GRID = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5)
#: Marge haute réservée à l'en-tête et marge basse aux libellés de jours.
_MARGIN_TOP = 34
_MARGIN_BOTTOM = 24
_MARGIN_LEFT = 42
_MARGIN_RIGHT = 18


class RetentionCurveWidget(QWidget):
    """Courbe d'oubli projetée (data-driven et thémable) rendue dans le Cockpit."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(180)

        self._projection: dict[str, Any] = {}
        self._curve: list[dict[str, float]] = []
        self._checkpoints: list[dict[str, float]] = []
        self._target: float = 0.90
        self._available: bool = False
        self._accent: str = DesignTokens.ACCENT_PRIMARY
        self._target_color: str = DesignTokens.COLOR_GREEN

        self._setup_ui()

    # ── Construction ─────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self._title_icon = QLabel()
        self._title_icon.setPixmap(load_phosphor_icon("ph.chart-line-up", color=DesignTokens.ACCENT_PRIMARY).pixmap(15, 15))
        self._title_icon.setStyleSheet("border: none; background: transparent;")

        self._title_label = QLabel(self.tr("Rétention projetée (courbe d'oubli)"))
        self._title_label.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        self._title_label.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

        self._load_badge = QLabel(self.tr("Charge : —"))
        self._load_badge.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        self._load_badge.setStyleSheet(
            f"background-color: {DesignTokens.COLOR_BLUE_BG}; color: {DesignTokens.COLOR_BLUE_TEXT}; border: 1px solid {DesignTokens.COLOR_BLUE_BORDER}; border-radius: 9999px; padding: 2px 10px;"
        )

        self._stability_label = QLabel(self.tr("S moy. : —"))
        self._stability_label.setFont(QFont(DesignTokens.FONT_MAIN, 9))
        self._stability_label.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")

        header.addWidget(self._title_icon)
        header.addWidget(self._title_label)
        header.addStretch()
        header.addWidget(self._stability_label)
        header.addWidget(self._load_badge)
        layout.addLayout(header)
        layout.addStretch()

    # ── Données ──────────────────────────────────────────────────────────────

    def set_projection(self, projection: dict[str, Any] | None) -> None:
        """Met à jour la projection affichée (sortie de ``FsrsProjectionService``)."""
        self._projection = projection or {}
        self._available = bool(self._projection.get("available"))
        self._curve = list(self._projection.get("curve") or [])
        self._checkpoints = list(self._projection.get("checkpoints") or [])
        self._target = float(self._projection.get("retention_target", 0.90))

        if self._available:
            load = float(self._projection.get("equilibrium_load_per_day", 0.0))
            self._load_badge.setText(tr("Charge : %1 révisions/j", f"{load:.1f}"))
            stability = float(self._projection.get("mean_stability_days", 0.0))
            self._stability_label.setText(tr("S moy. : %1 j", f"{stability:.0f}"))
        else:
            self._load_badge.setText(self.tr("Charge : —"))
            self._stability_label.setText(self.tr("S moy. : —"))

        self.update()

    # ── Rendu ────────────────────────────────────────────────────────────────

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        plot_w = max(10, width - _MARGIN_LEFT - _MARGIN_RIGHT)
        plot_h = max(10, height - _MARGIN_TOP - _MARGIN_BOTTOM)
        base_y = _MARGIN_TOP + plot_h

        if not self._available or len(self._curve) < 2:
            painter.setPen(QColor(DesignTokens.TEXT_MUTED))
            painter.setFont(QFont(DesignTokens.FONT_MAIN, 10))
            painter.drawText(
                QRectF(0, _MARGIN_TOP, width, plot_h),
                Qt.AlignmentFlag.AlignCenter,
                self.tr("Aucune donnée SRS — importez et révisez des cartes dans Anki."),
            )
            return

        max_day = float(self._curve[-1]["day"]) or 1.0

        def x_for(day: float) -> float:
            return _MARGIN_LEFT + (day / max_day) * plot_w

        def y_for(retention: float) -> float:
            clamped = min(1.0, max(_Y_MIN, retention))
            return _MARGIN_TOP + (1.0 - (clamped - _Y_MIN) / (1.0 - _Y_MIN)) * plot_h

        # 1. Grille horizontale + graduations.
        painter.setFont(QFont(DesignTokens.FONT_MAIN, 8))
        for level in _Y_GRID:
            y = y_for(level)
            pen_grid = QPen(QColor(DesignTokens.BORDER_LIGHT), 1, Qt.PenStyle.DashLine)
            painter.setPen(pen_grid)
            painter.drawLine(_MARGIN_LEFT, int(y), _MARGIN_LEFT + plot_w, int(y))
            painter.setPen(QColor(DesignTokens.TEXT_MUTED))
            painter.drawText(4, int(y) + 3, f"{level * 100:.0f}%")

        # 2. Ligne cible (rétention visée par Anki).
        y_target = y_for(self._target)
        painter.setPen(QPen(QColor(self._target_color), 1.2, Qt.PenStyle.DashLine))
        painter.drawLine(_MARGIN_LEFT, int(y_target), _MARGIN_LEFT + plot_w, int(y_target))

        # 3. Aire sous la courbe (dégradé accent).
        area = QPainterPath()
        area.moveTo(x_for(float(self._curve[0]["day"])), base_y)
        for point in self._curve:
            area.lineTo(x_for(float(point["day"])), y_for(float(point["retention"])))
        area.lineTo(x_for(max_day), base_y)
        area.closeSubpath()
        accent = QColor(self._accent)
        gradient = QLinearGradient(0, _MARGIN_TOP, 0, base_y)
        gradient.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 80))
        gradient.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
        painter.fillPath(area, QBrush(gradient))

        # 4. Courbe.
        curve_path = QPainterPath()
        curve_path.moveTo(x_for(float(self._curve[0]["day"])), y_for(float(self._curve[0]["retention"])))
        for point in self._curve[1:]:
            curve_path.lineTo(x_for(float(point["day"])), y_for(float(point["retention"])))
        painter.setPen(QPen(QColor(self._accent), 2.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(curve_path)

        # 5. Repères J+1/J+3/J+7/J+14 (points + libellés).
        painter.setFont(QFont(DesignTokens.FONT_MAIN, 8, QFont.Weight.Bold))
        for checkpoint in self._checkpoints:
            day = float(checkpoint["day"])
            x = x_for(day)
            y = y_for(float(checkpoint["retention"]))
            painter.setPen(QPen(QColor(DesignTokens.BG_PANEL), 2))
            painter.setBrush(QBrush(QColor(self._accent)))
            painter.drawEllipse(QRectF(x - 3.5, y - 3.5, 7, 7))
            painter.setPen(QColor(DesignTokens.TEXT_MUTED))
            painter.drawText(QRectF(x - 16, base_y + 4, 32, 14), Qt.AlignmentFlag.AlignCenter, f"J+{day:.0f}")

        # 6. Ancre J0.
        painter.setPen(QColor(DesignTokens.TEXT_MUTED))
        painter.drawText(QRectF(_MARGIN_LEFT - 16, base_y + 4, 32, 14), Qt.AlignmentFlag.AlignCenter, "J0")

    # ── Thème ────────────────────────────────────────────────────────────────

    def refresh_theme(self, profile: Any) -> None:
        """Réapplique les couleurs du thème actif."""
        self._accent = profile.accent_primary
        self._target_color = profile.color_green
        self._title_icon.setPixmap(load_phosphor_icon("ph.chart-line-up", color=profile.accent_primary).pixmap(15, 15))
        self._title_label.setStyleSheet(f"color: {profile.text_primary}; border: none; background: transparent;")
        self._stability_label.setStyleSheet(f"color: {profile.text_muted}; border: none; background: transparent;")
        self._load_badge.setStyleSheet(
            f"background-color: {DesignTokens.COLOR_BLUE_BG}; color: {DesignTokens.COLOR_BLUE_TEXT}; border: 1px solid {DesignTokens.COLOR_BLUE_BORDER}; border-radius: 9999px; padding: 2px 10px;"
        )
        self.update()
