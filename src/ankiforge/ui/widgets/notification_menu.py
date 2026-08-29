"""
Menu / Fenêtre popup des notifications et diagnostics proactifs d'AnkiForge.
Accessible depuis la cloche de notification de la barre supérieure (TopBar).
"""

from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.buttons import SecondaryButton
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.utils.icon_loader import load_phosphor_icon


class NotificationItemWidget(QFrame):
    """Tuile individuelle représentant une alerte ou diagnostic dans le menu de notification."""

    action_clicked = Signal(str, object)

    def __init__(self, notif_data: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.notif_data = notif_data
        self.setObjectName("NotificationItemWidget")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._apply_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # 1. En-tête : Icône + Titre + Badge Sévérité
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        icon_name = notif_data.get("icon", "ph.bell")
        severity = notif_data.get("severity", "info")
        color = DesignTokens.COLOR_BLUE
        if severity == "warning":
            color = DesignTokens.COLOR_YELLOW
        elif severity == "danger":
            color = DesignTokens.COLOR_RED

        self.icon_lbl = QLabel()
        self.icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=color).pixmap(16, 16))
        header.addWidget(self.icon_lbl)

        self.title_lbl = QLabel(notif_data.get("title", "Alerte"))
        self.title_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        header.addWidget(self.title_lbl)
        header.addStretch()

        layout.addLayout(header)

        # 2. Corps du message
        self.msg_lbl = QLabel(notif_data.get("message", ""))
        self.msg_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        self.msg_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        self.msg_lbl.setWordWrap(True)
        layout.addWidget(self.msg_lbl)

        # 3. Bouton d'action proactif
        action_label = notif_data.get("action_label", "Voir")
        self.btn_action = SecondaryButton(action_label)
        self.btn_action.setFixedHeight(24)
        self.btn_action.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        self.btn_action.clicked.connect(self._on_action)
        layout.addWidget(self.btn_action, 0, Qt.AlignmentFlag.AlignRight)

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            NotificationItemWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            NotificationItemWidget:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

    def _on_action(self) -> None:
        view_id = self.notif_data.get("target_view", "dashboard")
        tab_id = self.notif_data.get("target_tab")
        data = {"tab": tab_id} if tab_id else None
        self.action_clicked.emit(view_id, data)


class NotificationMenuPopup(QFrame):
    """Fenêtre popup affichant la liste des alertes proactives au clic sur la cloche TopBar."""

    action_triggered = Signal(str, object)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("NotificationMenuPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(360)
        self.setMaximumHeight(420)
        self._apply_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # En-tête de la modale popup
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        self.header_icon = QLabel()
        self.header_icon.setPixmap(load_phosphor_icon("ph.bell", color=DesignTokens.ACCENT_PRIMARY).pixmap(18, 18))
        self.header_title = QLabel("Diagnostics & Alertes")
        self.header_title.setFont(QFont(DesignTokens.FONT_MAIN, 13, QFont.Weight.Bold))
        self.header_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

        header_layout.addWidget(self.header_icon)
        header_layout.addWidget(self.header_title)
        header_layout.addStretch()

        self.count_badge = QLabel("0")
        self.count_badge.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        self.count_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.BG_ACTIVE};
                color: {DesignTokens.ACCENT_PRIMARY};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: 9px;
                padding: 1px 7px;
            }}
        """)
        header_layout.addWidget(self.count_badge)

        layout.addLayout(header_layout)

        # Zone déroulante des notifications
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.items_container = QWidget()
        self.items_container.setStyleSheet("background: transparent;")
        self.items_layout = QVBoxLayout(self.items_container)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(8)
        self.items_layout.addStretch(1)

        self.scroll_area.setWidget(self.items_container)
        layout.addWidget(self.scroll_area, 1)

        # Message d'état vide
        self.empty_label = QLabel("✨ Tout est parfait !\nAucune anomalie détectée dans votre collection.")
        self.empty_label.setFont(QFont(DesignTokens.FONT_MAIN, 11))
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; padding: 24px 0; border: none; background: transparent;")
        self.items_layout.insertWidget(0, self.empty_label)

        apply_shadow(self, blur=24, offset_y=6, color="rgba(0, 0, 0, 0.4)")

    def paintEvent(self, event: Any) -> None:
        """Dessine un fond opaque avec coins arrondis et bordure thématique."""
        from ankiforge.ui.style_engine import get_style_engine

        engine = get_style_engine()
        profile = getattr(engine, "current_profile", None)
        bg_color = QColor(profile.bg_panel if profile else DesignTokens.BG_PANEL)
        border_color = QColor(profile.border_color if profile else DesignTokens.BORDER_COLOR)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(bg_color)
        painter.setPen(border_color)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), DesignTokens.RADIUS_MD, DesignTokens.RADIUS_MD)

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QFrame#NotificationMenuPopup {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)

    def set_notifications(self, alerts: List[Dict[str, Any]]) -> None:
        """Remplit la popup avec les alertes proactives."""
        # Nettoyer les anciens items (sauf le stretch et empty label)
        while self.items_layout.count() > 1:
            item = self.items_layout.takeAt(0)
            if item.widget() and item.widget() != self.empty_label:
                item.widget().deleteLater()

        count = len(alerts)
        self.count_badge.setText(str(count))

        if count == 0:
            self.empty_label.show()
            self.items_layout.insertWidget(0, self.empty_label)
        else:
            self.empty_label.hide()
            for idx, alert in enumerate(alerts):
                item_widget = NotificationItemWidget(alert, self.items_container)
                item_widget.action_clicked.connect(self._on_action_forward)
                self.items_layout.insertWidget(idx, item_widget)

    def _on_action_forward(self, view_id: str, data: Any) -> None:
        self.hide()
        self.action_triggered.emit(view_id, data)

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les couleurs lors du switch de thème."""
        self._apply_style()
        self.header_title.setStyleSheet(f"color: {profile.text_primary}; border: none; background: transparent;")
        self.header_icon.setPixmap(load_phosphor_icon("ph.bell", color=profile.accent_primary).pixmap(18, 18))
        self.empty_label.setStyleSheet(f"color: {profile.text_muted}; padding: 24px 0; border: none; background: transparent;")
