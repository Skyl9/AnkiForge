"""
TopBar principale AnkiForge.
Barre supérieure 60px : breadcrumb, omnibox, token tracker, import/export, notifications.
"""

import logging
from typing import Any, Optional

from PySide6.QtCore import Qt, Signal, QObject, QEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QWidget,
)

from ankiforge.ui.components.buttons import IconButton
from ankiforge.ui.components.inputs import GlowLineEdit
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class TopBar(QWidget):
    """Barre supérieure 60px : breadcrumb + omnibox + token tracker + actions."""

    search_clicked = Signal()
    import_clicked = Signal()
    export_clicked = Signal()
    notif_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(DesignTokens.TOPBAR_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(16)

        # ── Fil d'Ariane (Breadcrumb) ──
        self.breadcrumb_container = QWidget()
        breadcrumb_layout = QHBoxLayout(self.breadcrumb_container)
        breadcrumb_layout.setContentsMargins(0, 0, 0, 0)
        breadcrumb_layout.setSpacing(8)
        breadcrumb_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._current_breadcrumb_icon = "ph.house"
        self.breadcrumb_icon = QLabel()
        self.breadcrumb_icon.setPixmap(load_phosphor_icon(self._current_breadcrumb_icon, color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))
        self.breadcrumb_icon.setObjectName("TopBarBreadcrumbIcon")

        self.breadcrumb_lbl = QLabel("Tableau de bord")
        self.breadcrumb_lbl.setObjectName("TopBarBreadcrumbLabel")

        breadcrumb_layout.addWidget(self.breadcrumb_icon)
        breadcrumb_layout.addWidget(self.breadcrumb_lbl)
        layout.addWidget(self.breadcrumb_container, alignment=Qt.AlignmentFlag.AlignVCenter)

        # ── Omnibox ──
        self.omnibox = GlowLineEdit()
        self.omnibox.setPlaceholderText("Rechercher cartes, paquets ou commandes... (Ctrl+K)")
        self.omnibox.setMaximumWidth(420)
        self.omnibox.installEventFilter(self)
        layout.addWidget(self.omnibox)

        layout.addStretch()

        # ── Token cost tracker pill (28px compact, vertically centered) ──
        self.token_container = QWidget()
        self.token_container.setObjectName("TopBarTokenTracker")
        self.token_container.setFixedHeight(28)
        self.token_container.setProperty("card-style", "panel")
        self.token_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        token_layout = QHBoxLayout(self.token_container)
        token_layout.setContentsMargins(8, 0, 10, 0)
        token_layout.setSpacing(6)
        token_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.dollar_icon = QLabel()
        self.dollar_icon.setPixmap(load_phosphor_icon("currency-dollar", color=DesignTokens.COLOR_GREEN).pixmap(14, 14))
        self.dollar_icon.setObjectName("TopBarDollarIcon")

        self.token_lbl = QLabel("Dépenses : 0.00 $ (0 tk)")
        self.token_lbl.setObjectName("TopBarTokenLabel")

        token_layout.addWidget(self.dollar_icon)
        token_layout.addWidget(self.token_lbl)

        layout.addWidget(self.token_container, alignment=Qt.AlignmentFlag.AlignVCenter)

        # ── Import & Export Actions ──
        self.import_btn = IconButton("download-simple", tooltip="Importer un paquet Anki (Ctrl+Shift+I)", size=24)
        self.import_btn.clicked.connect(self.import_clicked.emit)
        layout.addWidget(self.import_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.export_btn = IconButton("upload-simple", tooltip="Exporter des cartes Anki (Ctrl+Shift+E)", size=24)
        self.export_btn.clicked.connect(self.export_clicked.emit)
        layout.addWidget(self.export_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        # ── Notifications ──
        self.notif_btn = IconButton("bell", tooltip="Notifications", size=24)
        self.notif_btn.clicked.connect(self.notif_clicked.emit)
        layout.addWidget(self.notif_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Badge compteur de notifications (invisible par défaut)
        self.notif_badge = QLabel("0")
        self.notif_badge.setObjectName("TopBarNotifBadge")
        self.notif_badge.setFixedSize(18, 18)
        self.notif_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notif_badge.setVisible(False)
        # Positionner le badge en superposition sur le bouton cloche
        self.notif_badge.setParent(self.notif_btn)
        self.notif_badge.move(14, -2)

    def update_notif_badge(self, count: int) -> None:
        """Met à jour le badge de notification avec le nombre d'alertes."""
        if count > 0:
            self.notif_badge.setText(str(min(count, 99)))
            self.notif_badge.setVisible(True)
            self.notif_btn.setToolTip(f"Notifications & Diagnostics ({count} alerte{'s' if count > 1 else ''})")
        else:
            self.notif_badge.setVisible(False)
            self.notif_btn.setToolTip("Notifications (Aucune alerte)")

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj == self.omnibox and event.type() == QEvent.Type.MouseButtonPress:
            self.search_clicked.emit()
            return True
        return super().eventFilter(obj, event)

    def update_breadcrumb(self, text: str, icon_name: str = "ph.folder") -> None:
        self._current_breadcrumb_icon = icon_name
        if hasattr(self, "breadcrumb_lbl"):
            self.breadcrumb_lbl.setText(text)
        if hasattr(self, "breadcrumb_icon"):
            self.breadcrumb_icon.setPixmap(load_phosphor_icon(icon_name, color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))

    def update_token_tracker(self, cost: str, tokens: str) -> None:
        clean_cost = str(cost).replace("$", "").strip()
        self.token_lbl.setText(f"Dépenses : {clean_cost} $ ({tokens} tk)")

    def refresh_theme(self, profile: Any) -> None:
        if hasattr(self, "breadcrumb_icon"):
            icon_name = getattr(self, "_current_breadcrumb_icon", "ph.folder")
            self.breadcrumb_icon.setPixmap(load_phosphor_icon(icon_name, color=profile.accent_primary).pixmap(16, 16))
        if hasattr(self, "dollar_icon"):
            self.dollar_icon.setPixmap(load_phosphor_icon("currency-dollar", color=profile.color_green).pixmap(14, 14))
        if hasattr(self, "notif_btn") and hasattr(self.notif_btn, "refresh_theme"):
            self.notif_btn.refresh_theme(profile)
        if hasattr(self, "import_btn") and hasattr(self.import_btn, "refresh_theme"):
            self.import_btn.refresh_theme(profile)
        if hasattr(self, "export_btn") and hasattr(self.export_btn, "refresh_theme"):
            self.export_btn.refresh_theme(profile)
