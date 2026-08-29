"""
Sidebar de navigation principale AnkiForge.
Barre latérale rétractable (260px <-> 68px) avec sections, profils et paramètres.
"""

import logging
from typing import Any, Dict, Optional, Tuple, cast

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.buttons import IconButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ClickableLabel(QLabel):
    """QLabel cliquable pour déclencher des signaux."""

    clicked = Signal()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class SidebarItem(QPushButton):
    """Bouton de navigation dans la sidebar."""

    def __init__(self, view_id: str, icon_name: str, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.view_id = view_id
        self.icon_name = icon_name
        self.title = title

        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)

        self._collapsed = False

        # Set icon
        self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.TEXT_SECONDARY))
        self.setIconSize(QSize(20, 20))
        self.setText(f"  {self.title.replace('&', '&&')}")
        self.toggled.connect(self._on_toggled)

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        if collapsed:
            self.setText("")
            self.setToolTip(self.title)
        else:
            self.setText(f"  {self.title.replace('&', '&&')}")
            self.setToolTip("")

    def _on_toggled(self, checked: bool) -> None:
        if checked:
            self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.ACCENT_PRIMARY))
        else:
            self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.TEXT_SECONDARY))

    def refresh_theme(self, profile: Any) -> None:
        color = profile.accent_primary if self.isChecked() else profile.text_secondary
        self.setIcon(load_phosphor_icon(self.icon_name, color=color))


class SidebarProfileItem(QPushButton):
    """Bouton de profil utilisateur dans le footer de la barre latérale."""

    def __init__(self, profile_name: str = "default", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarUserBtn")
        self.profile_name = profile_name
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)
        self._collapsed = False

        self.setIcon(load_phosphor_icon("cards", color=DesignTokens.TEXT_SECONDARY))
        self.setIconSize(QSize(20, 20))
        self._update_text()

    def set_profile_name(self, profile_name: str) -> None:
        self.profile_name = profile_name
        self._update_text()

    def _update_text(self) -> None:
        if self._collapsed:
            self.setText("")
            self.setToolTip(f"Profil : {self.profile_name} (Changer de profil)")
        else:
            self.setText(f"  Profil : {self.profile_name}")
            self.setToolTip("Changer d'espace de travail / profil")

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self._update_text()

    def refresh_theme(self, profile: Any) -> None:
        self.setIcon(load_phosphor_icon("cards", color=profile.text_secondary))


class Sidebar(QWidget):
    """Sidebar collapsible 260px <-> 68px."""

    view_selected = Signal(str)
    settings_requested = Signal()
    toggle_requested = Signal()
    profile_switch_requested = Signal()

    def __init__(self, profile_name: str = "default", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(DesignTokens.SIDEBAR_WIDTH_EXPANDED)

        self.profile_name = profile_name
        self.is_collapsed = False
        self._items: Dict[str, SidebarItem] = {}
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Compatibility attributes (Brand header is in TopBar)
        self.logo_icon = ClickableLabel(self)
        self.logo_icon.hide()
        self.logo_icon.clicked.connect(self.toggle_requested.emit)
        from ankiforge.utils.icon_loader import load_logo_icon

        self.logo_icon.setPixmap(load_logo_icon(DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        self.logo_text = QLabel("AnkiForge", self)
        self.logo_text.hide()
        self.toggle_btn = IconButton("list", tooltip="Toggle Sidebar", size=24, parent=self)
        self.toggle_btn.hide()
        self.toggle_btn.clicked.connect(self.toggle_requested.emit)

        # 2. ScrollArea for sections
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.scroll_content = QWidget()
        self.sections_layout = QVBoxLayout(self.scroll_content)
        self.sections_layout.setContentsMargins(12, 12, 12, 12)
        self.sections_layout.setSpacing(24)
        self.sections_layout.addStretch()

        self.scroll.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll)

        # 3. Footer
        self.footer = QWidget()
        self.footer.setObjectName("SidebarFooter")
        self.footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        footer_layout = QVBoxLayout(self.footer)
        footer_layout.setContentsMargins(12, 12, 12, 12)
        footer_layout.setSpacing(4)

        self.settings_btn = SidebarItem("settings", "gear", "Paramètres")
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        footer_layout.addWidget(self.settings_btn)

        self.user_widget = SidebarProfileItem(profile_name=profile_name)
        self.user_widget.clicked.connect(self.profile_switch_requested.emit)
        footer_layout.addWidget(self.user_widget)

        main_layout.addWidget(self.footer)

    def _update_user_label(self, profile_name: str, color_green: str = "") -> None:
        """Met à jour le label utilisateur avec le nom du profil."""
        if hasattr(self, "user_widget"):
            self.user_widget.set_profile_name(profile_name)

    def set_profile_name(self, profile_name: str) -> None:
        """Met à jour le nom du profil affiché dans le footer de la barre latérale."""
        self.profile_name = profile_name
        self._update_user_label(profile_name)

    def refresh_theme(self, profile: Any) -> None:
        from ankiforge.utils.icon_loader import load_logo_icon

        if hasattr(self, "logo_icon") and hasattr(self.logo_icon, "setPixmap"):
            self.logo_icon.setPixmap(load_logo_icon(profile.accent_primary).pixmap(24, 24))
        if hasattr(self, "toggle_btn") and hasattr(self.toggle_btn, "refresh_theme"):
            self.toggle_btn.refresh_theme(profile)
        for item in self._items.values():
            item.refresh_theme(profile)
        if hasattr(self, "settings_btn"):
            self.settings_btn.refresh_theme(profile)
        if hasattr(self, "user_widget"):
            self.user_widget.refresh_theme(profile)

    def add_section(self, title: str, items: list[Tuple[str, str, str]]) -> None:
        """Ajoute une section avec un titre, une ligne séparatrice et une liste de (view_id, icon, text)."""
        section_widget = QWidget()
        layout = QVBoxLayout(section_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header_container = QWidget()
        header_container.setFixedHeight(24)
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(12, 0, 0, 0)
        header_layout.setSpacing(0)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        title_lbl = QLabel(title.upper())
        title_lbl.setObjectName("SidebarSectionTitle")
        title_lbl.setFixedHeight(20)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        sep_line = QFrame()
        sep_line.setObjectName("SidebarSectionSep")
        sep_line.setFrameShape(QFrame.Shape.HLine)
        sep_line.setFixedHeight(1)
        sep_line.setVisible(False)

        header_layout.addWidget(title_lbl)
        header_layout.addWidget(sep_line)

        layout.addWidget(header_container)

        for view_id, icon, text in items:
            btn = SidebarItem(view_id, icon, text)
            btn.clicked.connect(lambda checked=False, vid=view_id: self.view_selected.emit(vid))
            self._items[view_id] = btn
            self._button_group.addButton(btn)
            layout.addWidget(btn)

        # Insert before the stretch
        self.sections_layout.insertWidget(self.sections_layout.count() - 1, section_widget)
        section_widget.title_lbl = title_lbl
        section_widget.sep_line = sep_line

    def set_collapsed(self, collapsed: bool) -> None:
        self.is_collapsed = collapsed
        width = DesignTokens.SIDEBAR_WIDTH_COLLAPSED if collapsed else DesignTokens.SIDEBAR_WIDTH_EXPANDED

        # Direct fixed width update (prevents 16ms layout thrashing reflow loop)
        self.setFixedWidth(width)

        for i in range(self.sections_layout.count() - 1):
            item = self.sections_layout.itemAt(i)
            if item is not None:
                widget = item.widget()
                if widget and hasattr(widget, "title_lbl") and hasattr(widget, "sep_line"):
                    w = cast(Any, widget)
                    w.title_lbl.setVisible(not collapsed)
                    w.sep_line.setVisible(collapsed)

        for btn in self._items.values():
            btn.set_collapsed(collapsed)

        self.settings_btn.set_collapsed(collapsed)
        if hasattr(self, "user_widget"):
            self.user_widget.set_collapsed(collapsed)

    def set_active_view(self, view_id: str) -> None:
        for vid, btn in self._items.items():
            is_active = vid == view_id
            btn.setChecked(is_active)
            btn._on_toggled(is_active)
