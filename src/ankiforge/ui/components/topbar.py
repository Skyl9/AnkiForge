"""
TopBar principale AnkiForge.
Barre supérieure 60px pleine largeur : section marque (logo + toggle sidebar)
alignée au pixel près avec la sidebar, fil d'Ariane, omnibox, token tracker,
import/export et cloche de notifications.
"""

import logging
from typing import Any, Optional

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QWidget,
)

from ankiforge.ui.components.buttons import IconButton
from ankiforge.ui.components.inputs import GlowLineEdit
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_logo_icon, load_phosphor_icon

logger = logging.getLogger(__name__)


class ClickableLabel(QLabel):
    """QLabel cliquable pour déclencher des signaux."""

    clicked = Signal()

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class TopBar(QWidget):
    """
    Barre supérieure 60px pleine largeur :
    - Section Marque (Logo + Titre + Toggle Sidebar) à gauche, alignée sur la largeur de la sidebar (260px <-> 68px).
    - Section Contenu à droite (Breadcrumb + Omnibox + Token Tracker + Actions Import/Export/Notif).
    """

    search_clicked = Signal()
    import_clicked = Signal()
    export_clicked = Signal()
    notif_clicked = Signal()
    toggle_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(DesignTokens.TOPBAR_HEIGHT)

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── 1. Section Marque & Toggle Sidebar (Largeur synchronisée avec la Sidebar) ──
        self.brand_container = QWidget()
        self.brand_container.setObjectName("TopBarBrand")
        self.brand_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.brand_container.setFixedHeight(DesignTokens.TOPBAR_HEIGHT)
        self.brand_container.setFixedWidth(DesignTokens.SIDEBAR_WIDTH_EXPANDED)

        self.brand_layout = QHBoxLayout(self.brand_container)
        self.brand_layout.setContentsMargins(16, 0, 16, 0)
        self.brand_layout.setSpacing(10)
        self.brand_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.logo_icon = ClickableLabel()
        self.logo_icon.setObjectName("TopBarLogoIcon")
        self.logo_icon.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logo_icon.setPixmap(load_logo_icon(DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        self.logo_icon.clicked.connect(self.toggle_requested.emit)

        self.logo_text = QLabel("AnkiForge")
        self.logo_text.setObjectName("SidebarLogoText")

        self.toggle_btn = IconButton("list", tooltip="Replier/Déplier la barre latérale", size=28)
        self.toggle_btn.clicked.connect(self.toggle_requested.emit)

        self.brand_layout.addWidget(self.logo_icon)
        self.brand_layout.addWidget(self.logo_text)
        self.brand_layout.addStretch()
        self.brand_layout.addWidget(self.toggle_btn)

        root_layout.addWidget(self.brand_container)

        # ── 2. Section Contenu TopBar (Breadcrumb, Omnibox, Token tracker, Actions) ──
        self.content_container = QWidget()
        self.content_container.setObjectName("TopBarContent")
        self.content_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        content_layout = QHBoxLayout(self.content_container)
        content_layout.setContentsMargins(18, 0, 18, 0)
        content_layout.setSpacing(14)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Fil d'Ariane (Breadcrumb)
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
        content_layout.addWidget(self.breadcrumb_container, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Omnibox
        self.omnibox = GlowLineEdit()
        self.omnibox.setPlaceholderText("Rechercher cartes, paquets ou commandes... (Ctrl+K)")
        self.omnibox.setMaximumWidth(420)
        self.omnibox.installEventFilter(self)
        content_layout.addWidget(self.omnibox)

        content_layout.addStretch()

        # Token cost tracker pill (28px compact, vertically centered)
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

        content_layout.addWidget(self.token_container, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Import & Export Actions (28px)
        self.import_btn = IconButton("download-simple", tooltip="Importer un paquet Anki (Ctrl+Shift+I)", size=28)
        self.import_btn.clicked.connect(self.import_clicked.emit)
        content_layout.addWidget(self.import_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.export_btn = IconButton("upload-simple", tooltip="Exporter des cartes Anki (Ctrl+Shift+E)", size=28)
        self.export_btn.clicked.connect(self.export_clicked.emit)
        content_layout.addWidget(self.export_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Notifications (28px)
        self.notif_btn = IconButton("bell", tooltip="Notifications", size=28)
        self.notif_btn.clicked.connect(self.notif_clicked.emit)
        content_layout.addWidget(self.notif_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Badge compteur de notifications (invisible par défaut)
        self.notif_badge = QLabel("0")
        self.notif_badge.setObjectName("TopBarNotifBadge")
        self.notif_badge.setFixedSize(18, 18)
        self.notif_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notif_badge.setVisible(False)
        self.notif_badge.setParent(self.notif_btn)
        self.notif_badge.move(14, -3)

        root_layout.addWidget(self.content_container, 1)

    def set_collapsed(self, collapsed: bool) -> None:
        """Ajuste la largeur de la section marque pour correspondre à la sidebar repliée/dépliée."""
        width = DesignTokens.SIDEBAR_WIDTH_COLLAPSED if collapsed else DesignTokens.SIDEBAR_WIDTH_EXPANDED
        self.brand_container.setFixedWidth(width)
        self.logo_text.setVisible(not collapsed)
        self.toggle_btn.setVisible(not collapsed)

        if collapsed:
            self.brand_layout.setContentsMargins(22, 0, 0, 0)
        else:
            self.brand_layout.setContentsMargins(16, 0, 16, 0)

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
        if hasattr(self, "logo_icon"):
            self.logo_icon.setPixmap(load_logo_icon(profile.accent_primary).pixmap(24, 24))
        if hasattr(self, "toggle_btn") and hasattr(self.toggle_btn, "refresh_theme"):
            self.toggle_btn.refresh_theme(profile)
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
