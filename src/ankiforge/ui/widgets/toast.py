"""
Système de Notifications Flottantes Réactives (Toasts & ToastManager).
Notifications temporaires non-bloquantes avec niveaux visuels (Success, Info, Warning, Error),
animation de fondu, barre de progression et empilement vertical sans chevauchement.
"""

from __future__ import annotations

import contextlib
import logging
from enum import StrEnum
from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ToastLevel(StrEnum):
    """Niveaux sémantiques des notifications Toast."""

    SUCCESS = "success"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class _ToastProgressBar(QProgressBar):
    """Barre de défilement temporelle en bas du toast."""

    def __init__(self, color_hex: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(3)
        self.setTextVisible(False)
        self.setStyleSheet(f"""
            QProgressBar {{
                background-color: rgba(255, 255, 255, 0.15);
                border: none;
                border-bottom-left-radius: {DesignTokens.RADIUS_MD}px;
                border-bottom-right-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QProgressBar::chunk {{
                background-color: {color_hex};
                border-bottom-left-radius: {DesignTokens.RADIUS_MD}px;
                border-bottom-right-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)


class Toast(QWidget):
    """
    Notification flottante unitaire non-intrusive.
    Supporte 4 niveaux sémantiques, barre de progression temporelle et fermeture manuelle.
    """

    dismissed = Signal(object)

    LEVEL_CONFIG: dict[ToastLevel, dict[str, Any]] = {
        ToastLevel.SUCCESS: {
            "color": "#10B981",
            "icon": "check-circle",
            "title": "Succès",
        },
        ToastLevel.INFO: {
            "color": "#3B82F6",
            "icon": "info",
            "title": "Information",
        },
        ToastLevel.WARNING: {
            "color": "#F59E0B",
            "icon": "warning",
            "title": "Attention",
        },
        ToastLevel.ERROR: {
            "color": "#EF4444",
            "icon": "warning-octagon",
            "title": "Erreur",
        },
    }

    def __init__(
        self,
        message: str,
        level: ToastLevel = ToastLevel.INFO,
        title: str = "",
        duration_ms: int = 4000,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.level = level
        self.duration_ms = duration_ms
        self.remaining_ms = duration_ms
        self._is_closing = False

        cfg = self.LEVEL_CONFIG.get(level, self.LEVEL_CONFIG[ToastLevel.INFO])
        accent_color = cfg["color"]
        icon_name = cfg["icon"]
        display_title = title or cfg["title"]

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.ToolTip)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedWidth(340)

        # Conteneur principal avec ombre et bordure gauche colorée
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.card = QFrame(self)
        self.card.setObjectName("ToastCard")
        self.card.setStyleSheet(f"""
            QFrame#ToastCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-left: 4px solid {accent_color};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(12, 10, 12, 6)
        card_layout.setSpacing(6)

        # Ligne du haut : Icône + Titre + Bouton Fermer
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        icon_label = QLabel(self)
        icon_label.setPixmap(load_phosphor_icon(icon_name, color=accent_color, weight="fill").pixmap(20, 20))
        header_layout.addWidget(icon_label)

        title_label = QLabel(display_title, self)
        title_label.setStyleSheet(f"""
            color: {DesignTokens.TEXT_PRIMARY};
            font-weight: 700;
            font-size: 13px;
        """)
        header_layout.addWidget(title_label, 1)

        btn_close = QPushButton(self)
        btn_close.setFixedSize(18, 18)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setIcon(load_phosphor_icon("x", color=DesignTokens.TEXT_MUTED))
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        btn_close.clicked.connect(self.close_toast)
        header_layout.addWidget(btn_close)

        card_layout.addLayout(header_layout)

        # Message
        msg_label = QLabel(message, self)
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet(f"""
            color: {DesignTokens.TEXT_SECONDARY};
            font-size: 12px;
            line-height: 1.3;
        """)
        card_layout.addWidget(msg_label)

        # Barre de progression
        self.progress_bar = _ToastProgressBar(accent_color, self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        card_layout.addWidget(self.progress_bar)

        main_layout.addWidget(self.card)

        # Ombre portée
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.card.setGraphicsEffect(shadow)

        # Animation d'opacité native (évite les conflits QPainter / QWidgetEffectSourcePrivate avec QGraphicsDropShadowEffect)
        self.setWindowOpacity(0.0)

        self.fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self.fade_anim.setDuration(220)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Timer de progression (tick tous les 40ms)
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(40)
        self._tick_timer.timeout.connect(self._on_tick)

    def show_toast(self) -> None:
        """Déclenche l'affichage et l'animation d'entrée."""
        self.show()
        self.fade_anim.stop()
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.start()
        if self.duration_ms > 0:
            self._tick_timer.start()

    def _on_tick(self) -> None:
        self.remaining_ms -= self._tick_timer.interval()
        if self.duration_ms > 0:
            pct = int(max(0, (self.remaining_ms / self.duration_ms) * 100))
            self.progress_bar.setValue(pct)
        if self.remaining_ms <= 0:
            self._tick_timer.stop()
            self.close_toast()

    def close_toast(self) -> None:
        """Ferme le toast avec animation de sortie."""
        if self._is_closing:
            return
        self._is_closing = True
        self._tick_timer.stop()

        self.fade_anim.stop()
        self.fade_anim.setStartValue(self.windowOpacity())
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.finished.connect(self._on_fade_out_finished)
        self.fade_anim.start()

    def _on_fade_out_finished(self) -> None:
        self.dismissed.emit(self)
        self.deleteLater()

    def enterEvent(self, event: Any) -> None:
        """Met en pause le timer lorsque l'utilisateur survole le toast."""
        self._tick_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        """Reprend le timer lorsque le curseur quitte le toast."""
        if not self._is_closing and self.duration_ms > 0:
            self._tick_timer.start()
        super().leaveEvent(event)


class ToastManager:
    """
    Gestionnaire centralisé des toasts pour une fenêtre ou l'application.
    Positionne les toasts en bas à droite et gère l'empilement vertical fluide.
    """

    _instance: ToastManager | None = None

    def __init__(self) -> None:
        self._active_toasts: list[Toast] = []
        self._margin_bottom = 24
        self._margin_right = 24
        self._spacing = 10

    @classmethod
    def get_instance(cls) -> ToastManager:
        if cls._instance is None:
            cls._instance = ToastManager()
        return cls._instance

    def _resolve_host_window(self, parent: QWidget | None) -> QWidget | None:
        """
        Résout la fenêtre hôte durable (QMainWindow ou fenêtre principale active).
        Évite d'ancrer un toast à une boîte de dialogue (QDialog) temporaire qui va être détruite.
        """
        from PySide6.QtWidgets import QApplication, QDialog, QMainWindow

        host: QWidget | None = parent
        if host and isinstance(host, QDialog):
            host = host.parentWidget() or (host.parent() if isinstance(host.parent(), QWidget) else None)

        if host and hasattr(host, "window"):
            host = host.window()

        if host is None or not host.isVisible():
            app = QApplication.instance()
            if app:
                for widget in app.topLevelWidgets():
                    if isinstance(widget, QMainWindow) and widget.isVisible():
                        host = widget
                        break
                if host is None:
                    host = app.activeWindow()

        return host

    def show(
        self,
        parent: QWidget | None,
        message: str,
        level: ToastLevel | str = ToastLevel.INFO,
        title: str = "",
        duration_ms: int = 4000,
    ) -> Toast | None:
        """Affiche un toast flottant et repositionne la pile."""
        from PySide6.QtWidgets import QApplication

        if QApplication.instance() is None:
            return None

        host_window = self._resolve_host_window(parent)

        if isinstance(level, str):
            try:
                level_enum = ToastLevel(level.lower().strip())
            except ValueError:
                level_enum = ToastLevel.INFO
        else:
            level_enum = level

        toast = Toast(
            message=message,
            level=level_enum,
            title=title,
            duration_ms=duration_ms,
            parent=host_window,
        )
        toast.dismissed.connect(self._on_toast_dismissed)
        self._active_toasts.append(toast)
        self._reposition_toasts(host_window)
        toast.show_toast()
        return toast

    def _on_toast_dismissed(self, toast: Toast) -> None:
        if toast in self._active_toasts:
            self._active_toasts.remove(toast)
            try:
                parent = toast.parentWidget()
                self._reposition_toasts(self._resolve_host_window(parent))
            except RuntimeError as err:
                logger.debug("Repositionnement toast ignoré (widget détruit) : %s", err)

    def _reposition_toasts(self, parent: QWidget | None) -> None:
        """Repositionne tous les toasts actifs empilés verticalement depuis le bas à droite."""
        host = self._resolve_host_window(parent)
        if not host or not self._active_toasts:
            return

        from shiboken6 import isValid

        # Filtrer d'abord les objets C++ encore valides
        self._active_toasts = [t for t in self._active_toasts if isValid(t)]
        if not self._active_toasts:
            return

        try:
            win_geom = host.geometry()
            right_x = win_geom.x() + win_geom.width() - self._margin_right
            current_bottom_y = win_geom.y() + win_geom.height() - self._margin_bottom

            for toast in reversed(self._active_toasts):
                if isValid(toast):
                    toast.adjustSize()
                    t_width = toast.width()
                    t_height = toast.height()
                    target_x = right_x - t_width
                    target_y = current_bottom_y - t_height
                    toast.move(QPoint(target_x, target_y))
                    current_bottom_y = target_y - self._spacing
        except RuntimeError as err:
            logger.debug("Erreur géométrie toast (widget détruit) : %s", err)

    def clear(self) -> None:
        """Ferme immédiatement tous les toasts actifs."""
        from shiboken6 import isValid

        for t in list(self._active_toasts):
            if isValid(t):
                with contextlib.suppress(Exception):
                    t.close_toast()
        self._active_toasts.clear()


def show_toast(
    parent: QWidget | None,
    message: str,
    is_error: bool | None = None,
    level: ToastLevel | str | None = None,
    title: str = "",
    duration_ms: int = 4000,
) -> Toast | None:
    """
    Fonction globale pour afficher un toast flottant.
    100% rétrocompatible avec les signatures historiques :
    - show_toast(parent, message, is_error=True/False)
    - show_toast(parent, message, level='success'|'info'|'warning'|'error', title='...')
    """
    target_level: ToastLevel | str
    if level is not None:
        target_level = level
    elif is_error is True:
        target_level = ToastLevel.ERROR
    elif is_error is False:
        target_level = ToastLevel.SUCCESS
    else:
        target_level = ToastLevel.INFO

    return ToastManager.get_instance().show(
        parent=parent,
        message=message,
        level=target_level,
        title=title,
        duration_ms=duration_ms,
    )


def show_import_toast(parent: QWidget | None, summary: dict[str, int]) -> Toast | None:
    """
    Affiche une notification Toast détaillée récapitulant les résultats d'une importation Anki.
    Fournit un retour utilisateur clair et exhaustif (cartes créées, mises à jour, fusions, médias).
    """
    created = summary.get("created", 0)
    updated = summary.get("updated", 0)
    merged = summary.get("merged", 0)
    media = summary.get("media", 0)
    total = created + updated + merged

    if total == 0 and media == 0:
        return show_toast(
            parent=parent,
            message="Aucune nouvelle carte ni modification détectée dans le paquet.",
            level=ToastLevel.INFO,
            title="Importation Terminée",
            duration_ms=4500,
        )

    lines: list[str] = []
    if created > 0:
        lines.append(f"✨ {created} carte{'s' if created > 1 else ''} créée{'s' if created > 1 else ''}")
    if updated > 0:
        lines.append(f"🔄 {updated} mise{'s' if updated > 1 else ''} à jour silencieuse{'s' if updated > 1 else ''}")
    if merged > 0:
        lines.append(f"🤝 {merged} fusion{'s' if merged > 1 else ''} arbitrée{'s' if merged > 1 else ''}")
    if media > 0:
        lines.append(f"📎 {media} média{'s' if media > 1 else ''} indexé{'s' if media > 1 else ''}")

    return show_toast(
        parent=parent,
        message="\n".join(lines),
        level=ToastLevel.SUCCESS,
        title="Importation Réussie",
        duration_ms=6000,
    )
