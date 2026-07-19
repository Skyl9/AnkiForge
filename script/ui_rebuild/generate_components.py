import os

components_dir = "/Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/components"
os.makedirs(components_dir, exist_ok=True)

init_content = """from .buttons import PrimaryButton, SecondaryButton, DangerButton, IconButton, PremiumActionCard
from .panels import IdePanel, GlassPanel, MetricCard, StatCard
from .tabs import IdeTabBar, PillTabBar, SettingsTabBar
from .inputs import StyledLineEdit, StyledTextEdit, GlowLineEdit, ToggleSwitch, StyledComboBox
from .lists import StyledListItem, ActivityItem, DocTreeItem, ContextItem
from .badges import Badge, TagButton
from .tables import StyledTableWidget, CicdTable
from .misc import UserAvatar, StyledToolbar, DaemonStatusWidget

__all__ = [
    "PrimaryButton", "SecondaryButton", "DangerButton", "IconButton", "PremiumActionCard",
    "IdePanel", "GlassPanel", "MetricCard", "StatCard",
    "IdeTabBar", "PillTabBar", "SettingsTabBar",
    "StyledLineEdit", "StyledTextEdit", "GlowLineEdit", "ToggleSwitch", "StyledComboBox",
    "StyledListItem", "ActivityItem", "DocTreeItem", "ContextItem",
    "Badge", "TagButton",
    "StyledTableWidget", "CicdTable",
    "UserAvatar", "StyledToolbar", "DaemonStatusWidget",
]
"""

buttons_content = """from PySide6.QtWidgets import QPushButton, QWidget, QFrame, QVBoxLayout, QLabel, QGraphicsDropShadowEffect
from PySide6.QtCore import Signal, Qt, QPropertyAnimation, QEasingCurve, QEvent
from PySide6.QtGui import QColor, QCursor, QFont
from ankiforge.ui.theme import DesignTokens, apply_shadow

class HoverAnimMixin:
    def setup_hover_anim(self, effect: QGraphicsDropShadowEffect, default_blur: int, hover_blur: int) -> None:
        self.effect = effect
        self.anim = QPropertyAnimation(self.effect, b"blurRadius")
        self.anim.setDuration(150)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.default_blur = default_blur
        self.hover_blur = hover_blur

    def enterEvent(self, event: QEvent) -> None:
        if hasattr(self, 'anim'):
            self.anim.setEndValue(self.hover_blur)
            self.anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        if hasattr(self, 'anim'):
            self.anim.setEndValue(self.default_blur)
            self.anim.start()
        super().leaveEvent(event)


class PrimaryButton(QPushButton, HoverAnimMixin):
    \"\"\"Bouton principal indigo avec glow. Usage: actions primaires.\"\"\"
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(36)
        
        self.setStyleSheet(f\"\"\"
            QPushButton {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                color: {DesignTokens.TEXT_PRIMARY};
                border: none;
                border-radius: {DesignTokens.RADIUS_SM}px;
                font-family: "{DesignTokens.FONT_MAIN}";
                font-weight: 600;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.ACCENT_HOVER};
            }}
        \"\"\")
        apply_shadow(self, blur=10, offset_y=0, color="rgba(99,102,241,0.4)")
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            self.setup_hover_anim(effect, 10, 16)


class SecondaryButton(QPushButton):
    \"\"\"Bouton secondaire avec bordure. Usage: actions secondaires.\"\"\"
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(36)
        
        self.setStyleSheet(f\"\"\"
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                font-family: "{DesignTokens.FONT_MAIN}";
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        \"\"\")


class DangerButton(QPushButton):
    \"\"\"Bouton danger rouge. Variantes: filled et ghost.\"\"\"
    def __init__(self, text: str, ghost: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(36)
        
        if ghost:
            self.setStyleSheet(f\"\"\"
                QPushButton {{
                    background-color: transparent;
                    color: {DesignTokens.COLOR_RED};
                    border: 1px solid {DesignTokens.COLOR_RED};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    font-family: "{DesignTokens.FONT_MAIN}";
                    padding: 0 16px;
                }}
                QPushButton:hover {{
                    background-color: rgba(239, 68, 68, 0.1);
                }}
            \"\"\")
        else:
            self.setStyleSheet(f\"\"\"
                QPushButton {{
                    background-color: {DesignTokens.COLOR_RED};
                    color: {DesignTokens.TEXT_PRIMARY};
                    border: none;
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    font-family: "{DesignTokens.FONT_MAIN}";
                    font-weight: 600;
                    padding: 0 16px;
                }}
                QPushButton:hover {{
                    background-color: #dc2626;
                }}
            \"\"\")


class IconButton(QPushButton):
    \"\"\"Bouton icône 32x32 transparent. Usage: toolbars.\"\"\"
    def __init__(self, icon_name: str, tooltip: str = "", size: int = 32, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedSize(size, size)
        self.setToolTip(tooltip)
        self.setText(icon_name)
        
        self.setStyleSheet(f\"\"\"
            QPushButton {{
                background-color: transparent;
                color: {DesignTokens.TEXT_PRIMARY};
                border: none;
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        \"\"\")


class PremiumActionCard(QFrame):
    \"\"\"Grande carte d'action avec icône + titre + description. Usage: Dashboard.\"\"\"
    clicked = Signal()

    def __init__(self, icon_name: str, title: str, description: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMinimumHeight(100)
        self.setStyleSheet(f\"\"\"
            PremiumActionCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            PremiumActionCard:hover {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
        \"\"\")
        apply_shadow(self, blur=12, offset_y=4)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        
        self.icon_label = QLabel(icon_name)
        self.icon_label.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 24px;")
        
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        
        self.desc_label = QLabel(description)
        self.desc_label.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY};")
        self.desc_label.setWordWrap(True)
        
        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.desc_label)
        layout.addStretch()

    def mouseReleaseEvent(self, event: QEvent) -> None:
        from PySide6.QtGui import QMouseEvent
        if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)
"""

panels_content = """from PySide6.QtWidgets import QFrame, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget
from PySide6.QtCore import Signal
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.components.buttons import IconButton

class IdePanel(QFrame):
    \"\"\"Panneau IDE avec tab bar, titre, bouton détacher.\"\"\"
    detach_requested = Signal()

    def __init__(self, title: str, detachable: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f\"\"\"
            IdePanel {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        \"\"\")
        self.layout_v = QVBoxLayout(self)
        self.layout_v.setContentsMargins(0, 0, 0, 0)
        self.layout_v.setSpacing(0)
        
        self.header = QFrame()
        self.header.setStyleSheet(f"border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")
        self.header.setFixedHeight(36)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(16, 0, 8, 0)
        
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; border: none;")
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        if detachable:
            self.detach_btn = IconButton("⏏", "Détacher", 24)
            self.detach_btn.clicked.connect(self.detach_requested.emit)
            header_layout.addWidget(self.detach_btn)
            
        self.layout_v.addWidget(self.header)
        
        self.content_stack = QStackedWidget()
        self.layout_v.addWidget(self.content_stack)

    def add_tab(self, title: str, widget: QWidget, icon_name: str = "") -> None:
        self.content_stack.addWidget(widget)

    def set_active_tab(self, index: int) -> None:
        self.content_stack.setCurrentIndex(index)


class GlassPanel(QFrame):
    \"\"\"Panneau glassmorphism (semi-transparent + blur effect).\"\"\"
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f\"\"\"
            GlassPanel {{
                background-color: rgba(30, 33, 40, 0.6);
                border: 1px solid {DesignTokens.BORDER_LIGHT};
                border-radius: {DesignTokens.RADIUS_LG}px;
            }}
        \"\"\")
        apply_shadow(self, blur=DesignTokens.SHADOW_GLASS_BLUR, offset_y=4)


class MetricCard(QFrame):
    \"\"\"Carte métrique avec valeur, label, icône, trend. Usage: Batch CI/CD, Stats.\"\"\"
    def __init__(self, label: str, value: str, icon_name: str,
                 trend: str = "", trend_positive: bool = True,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f\"\"\"
            MetricCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        \"\"\")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        
        header = QHBoxLayout()
        self.lbl_label = QLabel(label)
        self.lbl_label.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px;")
        
        self.icon_label = QLabel(icon_name)
        self.icon_label.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED};")
        
        header.addWidget(self.lbl_label)
        header.addStretch()
        header.addWidget(self.icon_label)
        layout.addLayout(header)
        
        footer = QHBoxLayout()
        self.val_label = QLabel(value)
        self.val_label.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        footer.addWidget(self.val_label)
        
        if trend:
            self.trend_label = QLabel(trend)
            color = DesignTokens.COLOR_GREEN if trend_positive else DesignTokens.COLOR_RED
            self.trend_label.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: bold;")
            footer.addWidget(self.trend_label)
        
        footer.addStretch()
        layout.addLayout(footer)

    def set_value(self, value: str) -> None:
        self.val_label.setText(value)


class StatCard(QFrame):
    \"\"\"Carte statistique. Usage: Dashboard sidebar, Settings stats.\"\"\"
    def __init__(self, label: str, value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f\"\"\"
            StatCard {{
                background-color: {DesignTokens.BG_INPUT};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        \"\"\")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        
        self.lbl = QLabel(label)
        self.lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px;")
        
        self.val = QLabel(value)
        self.val.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 16px; font-weight: bold;")
        
        layout.addWidget(self.lbl)
        layout.addWidget(self.val)
"""

tabs_content = """from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QButtonGroup
from PySide6.QtCore import Signal, Qt
from ankiforge.ui.theme import DesignTokens

class IdeTabBar(QWidget):
    \"\"\"Tab bar style JetBrains avec indicateur accent 2px en haut.\"\"\"
    tab_changed = Signal(int)
    tab_reordered = Signal(int, int)
    tab_close_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)
        self.layout_h = QHBoxLayout(self)
        self.layout_h.setContentsMargins(0, 0, 0, 0)
        self.layout_h.setSpacing(0)
        self.btn_group = QButtonGroup(self)
        self.btn_group.idClicked.connect(self.tab_changed.emit)
        self.tabs: list[QPushButton] = []
        self.layout_h.addStretch()

    def add_tab(self, title: str, icon_name: str = "", closable: bool = False) -> int:
        idx = len(self.tabs)
        btn = QPushButton(f"{icon_name} {title}".strip())
        btn.setCheckable(True)
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        btn.setStyleSheet(f\"\"\"
            QPushButton {{
                background-color: transparent;
                color: {DesignTokens.TEXT_SECONDARY};
                border: none;
                border-top: 2px solid transparent;
                padding: 0 16px;
                font-family: "{DesignTokens.FONT_MAIN}";
            }}
            QPushButton:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
            QPushButton:checked {{
                color: {DesignTokens.TEXT_PRIMARY};
                border-top: 2px solid {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_PANEL};
            }}
        \"\"\")
        
        self.btn_group.addButton(btn, idx)
        self.tabs.append(btn)
        self.layout_h.insertWidget(idx, btn)
        
        if len(self.tabs) == 1:
            btn.setChecked(True)
            
        return idx

    def set_active(self, index: int) -> None:
        if 0 <= index < len(self.tabs):
            self.tabs[index].setChecked(True)
            self.tab_changed.emit(index)


class PillTabBar(QWidget):
    \"\"\"Tab bar style pill/segment. Usage: sous-navigation dans les panneaux.\"\"\"
    tab_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        self.layout_h = QHBoxLayout(self)
        self.layout_h.setContentsMargins(2, 2, 2, 2)
        self.layout_h.setSpacing(2)
        self.setStyleSheet(f\"\"\"
            PillTabBar {{
                background-color: {DesignTokens.BG_INPUT};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        \"\"\")
        self.btn_group = QButtonGroup(self)
        self.btn_group.idClicked.connect(self.tab_changed.emit)
        self.tabs: list[QPushButton] = []

    def add_tab(self, title: str) -> int:
        idx = len(self.tabs)
        btn = QPushButton(title)
        btn.setCheckable(True)
        btn.setFixedHeight(28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        btn.setStyleSheet(f\"\"\"
            QPushButton {{
                background-color: transparent;
                color: {DesignTokens.TEXT_SECONDARY};
                border: none;
                border-radius: {DesignTokens.RADIUS_SM - 2}px;
                padding: 0 12px;
                font-family: "{DesignTokens.FONT_MAIN}";
            }}
            QPushButton:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QPushButton:checked {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        \"\"\")
        
        self.btn_group.addButton(btn, idx)
        self.tabs.append(btn)
        self.layout_h.addWidget(btn)
        
        if len(self.tabs) == 1:
            btn.setChecked(True)
            
        return idx


class SettingsTabBar(QWidget):
    \"\"\"Tab bar verticale pour le modal Settings.\"\"\"
    tab_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.layout_v = QVBoxLayout(self)
        self.layout_v.setContentsMargins(0, 0, 0, 0)
        self.layout_v.setSpacing(4)
        self.btn_group = QButtonGroup(self)
        self.btn_group.idClicked.connect(self.tab_changed.emit)
        self.tabs: list[QPushButton] = []
        self.layout_v.addStretch()

    def add_tab(self, title: str, icon_name: str) -> int:
        idx = len(self.tabs)
        btn = QPushButton(f"{icon_name}  {title}")
        btn.setCheckable(True)
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        btn.setStyleSheet(f\"\"\"
            QPushButton {{
                text-align: left;
                background-color: transparent;
                color: {DesignTokens.TEXT_SECONDARY};
                border: none;
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 0 12px;
                font-family: "{DesignTokens.FONT_MAIN}";
            }}
            QPushButton:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
            QPushButton:checked {{
                background-color: {DesignTokens.BG_ACTIVE};
                color: {DesignTokens.ACCENT_PRIMARY};
                font-weight: bold;
            }}
        \"\"\")
        
        self.btn_group.addButton(btn, idx)
        self.tabs.append(btn)
        self.layout_v.insertWidget(idx, btn)
        
        if len(self.tabs) == 1:
            btn.setChecked(True)
            
        return idx
"""

inputs_content = """from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QWidget, QComboBox
from PySide6.QtCore import Signal, Qt, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPainter, QColor, QPaintEvent
from ankiforge.ui.theme import DesignTokens, apply_shadow

class StyledLineEdit(QLineEdit):
    \"\"\"Input avec style design system. Focus = glow indigo.\"\"\"
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet(f\"\"\"
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 0 12px;
                font-family: "{DesignTokens.FONT_MAIN}";
            }}
            QLineEdit:focus {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        \"\"\")


class StyledTextEdit(QPlainTextEdit):
    \"\"\"Textarea avec style design system.\"\"\"
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f\"\"\"
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 8px 12px;
                font-family: "{DesignTokens.FONT_CODE}";
            }}
            QPlainTextEdit:focus {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        \"\"\")


class GlowLineEdit(QLineEdit):
    \"\"\"Input avec glow accentué au focus. Usage: recherche, omnibox.\"\"\"
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setStyleSheet(f\"\"\"
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 0 16px;
                font-size: 14px;
                font-family: "{DesignTokens.FONT_MAIN}";
            }}
            QLineEdit:focus {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_PANEL};
            }}
        \"\"\")
        apply_shadow(self, blur=8, offset_y=2)


class ToggleSwitch(QWidget):
    \"\"\"Toggle iOS-style (36x20px). Usage: Settings.\"\"\"
    toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(36, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._checked = False
        self._thumb_pos = 2
        
        self.anim = QPropertyAnimation(self, b"thumb_pos")
        self.anim.setDuration(150)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)

    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, checked: bool) -> None:
        if self._checked == checked: return
        self._checked = checked
        self.anim.setEndValue(18 if self._checked else 2)
        self.anim.start()
        self.toggled.emit(self._checked)

    def get_thumb_pos(self) -> int:
        return self._thumb_pos

    def set_thumb_pos(self, pos: int) -> None:
        self._thumb_pos = pos
        self.update()

    thumb_pos = Property(int, get_thumb_pos, set_thumb_pos)

    def mouseReleaseEvent(self, event) -> None:
        from PySide6.QtGui import QMouseEvent
        if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.LeftButton:
            self.set_checked(not self._checked)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        bg_color = QColor(DesignTokens.ACCENT_PRIMARY) if self._checked else QColor(DesignTokens.BG_INPUT)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg_color)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 10, 10)
        
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(self._thumb_pos, 2, 16, 16)


class StyledComboBox(QComboBox):
    \"\"\"ComboBox avec style design system.\"\"\"
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet(f\"\"\"
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 0 12px;
                font-family: "{DesignTokens.FONT_MAIN}";
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox::down-arrow {{
                image: none;
            }}
            QComboBox:focus {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
            QComboBox QAbstractItemView {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                selection-background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        \"\"\")
"""

lists_content = """from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Signal, Qt
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.components.buttons import IconButton

class StyledListItem(QWidget):
    \"\"\"Item de liste générique avec hover/active.\"\"\"
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f\"\"\"
            StyledListItem {{
                background-color: transparent;
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            StyledListItem:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        \"\"\")

    def mouseReleaseEvent(self, event) -> None:
        from PySide6.QtGui import QMouseEvent
        if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ActivityItem(QWidget):
    \"\"\"Item d'activité : icône + texte principal + texte secondaire + timestamp.\"\"\"
    def __init__(self, icon_name: str, title: str, subtitle: str,
                 timestamp: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        
        self.icon_lbl = QLabel(icon_name)
        self.icon_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY};")
        layout.addWidget(self.icon_lbl)
        
        vbox = QVBoxLayout()
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold;")
        self.sub_lbl = QLabel(subtitle)
        self.sub_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        vbox.addWidget(self.title_lbl)
        vbox.addWidget(self.sub_lbl)
        layout.addLayout(vbox)
        
        layout.addStretch()
        
        self.time_lbl = QLabel(timestamp)
        self.time_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(self.time_lbl)


class DocTreeItem(QWidget):
    \"\"\"Item d'arbre de fichiers avec icône, caret expand, nom.\"\"\"
    def __init__(self, text: str, is_dir: bool = False, expanded: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(28)
        self.setStyleSheet(f\"\"\"
            DocTreeItem {{
                background-color: transparent;
                border-radius: {DesignTokens.RADIUS_SM - 2}px;
            }}
            DocTreeItem:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        \"\"\")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)
        
        self.caret = QLabel("▼" if expanded else "▶")
        self.caret.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px;")
        if not is_dir:
            self.caret.setVisible(False)
        layout.addWidget(self.caret)
        
        icon = "📁" if is_dir else "📄"
        self.icon_lbl = QLabel(icon)
        layout.addWidget(self.icon_lbl)
        
        self.text_lbl = QLabel(text)
        self.text_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY};")
        layout.addWidget(self.text_lbl)
        layout.addStretch()


class ContextItem(QWidget):
    \"\"\"Item de contexte AI avec badge type + nom + bouton supprimer.\"\"\"
    removed = Signal()

    def __init__(self, type_badge: str, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(32)
        self.setStyleSheet(f\"\"\"
            ContextItem {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        \"\"\")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 4, 0)
        
        self.badge = QLabel(type_badge)
        self.badge.setStyleSheet(f\"\"\"
            background-color: {DesignTokens.BG_PANEL};
            color: {DesignTokens.ACCENT_PRIMARY};
            border-radius: 4px;
            padding: 2px 4px;
            font-size: 10px;
            font-weight: bold;
        \"\"\")
        layout.addWidget(self.badge)
        
        self.name_lbl = QLabel(name)
        self.name_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")
        layout.addWidget(self.name_lbl)
        
        layout.addStretch()
        
        self.del_btn = IconButton("✕", "Remove", 24)
        self.del_btn.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        self.del_btn.clicked.connect(self.removed.emit)
        layout.addWidget(self.del_btn)
"""

badges_content = """from PySide6.QtWidgets import QLabel, QPushButton, QWidget, QHBoxLayout
from PySide6.QtCore import Signal, Qt
from ankiforge.ui.theme import DesignTokens

class Badge(QLabel):
    \"\"\"Pill badge. Variantes: filled, outline, status, glass.\"\"\"
    def __init__(self, text: str, variant: str = "filled",
                 color: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        base_color = color or DesignTokens.ACCENT_PRIMARY
        
        style = f\"\"\"
            border-radius: 10px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: bold;
        \"\"\"
        
        if variant == "filled":
            style += f"background-color: {base_color}; color: #ffffff;"
        elif variant == "outline":
            style += f"background-color: transparent; border: 1px solid {base_color}; color: {base_color};"
        elif variant == "status":
            style += f"background-color: rgba(99, 102, 241, 0.1); color: {base_color}; border: 1px solid rgba(99, 102, 241, 0.2);"
        elif variant == "glass":
            style += f"background-color: rgba(255, 255, 255, 0.1); color: #ffffff; border: 1px solid rgba(255, 255, 255, 0.2);"
            
        self.setStyleSheet(style)


class TagButton(QPushButton):
    \"\"\"Tag pill avec code font + tint accent. Usage: tags de notes.\"\"\"
    removed = Signal(str)

    def __init__(self, text: str, removable: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tag_text = text
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(4)
        
        lbl = QLabel(text)
        lbl.setStyleSheet(f\"\"\"
            color: {DesignTokens.ACCENT_PRIMARY};
            font-family: "{DesignTokens.FONT_CODE}";
            font-size: 11px;
        \"\"\")
        layout.addWidget(lbl)
        
        if removable:
            del_lbl = QLabel("×")
            del_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 14px;")
            layout.addWidget(del_lbl)
            
        self.setStyleSheet(f\"\"\"
            TagButton {{
                background-color: {DesignTokens.BG_ACTIVE};
                border: 1px solid rgba(99, 102, 241, 0.2);
                border-radius: 12px;
            }}
            TagButton:hover {{
                background-color: rgba(99, 102, 241, 0.15);
                border: 1px solid rgba(99, 102, 241, 0.4);
            }}
        \"\"\")

    def mouseReleaseEvent(self, event) -> None:
        from PySide6.QtGui import QMouseEvent
        if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.LeftButton:
            self.removed.emit(self.tag_text)
        super().mouseReleaseEvent(event)
"""

tables_content = """from PySide6.QtWidgets import QTableWidget, QWidget, QAbstractItemView, QHeaderView
from PySide6.QtCore import Qt
from ankiforge.ui.theme import DesignTokens

class StyledTableWidget(QTableWidget):
    \"\"\"Table avec style design system: sticky headers, hover rows, active row.\"\"\"
    def __init__(self, columns: list[str], parent: QWidget | None = None) -> None:
        super().__init__(0, len(columns), parent)
        self.setHorizontalHeaderLabels(columns)
        
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        self.setStyleSheet(f\"\"\"
            QTableWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QHeaderView::section {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_SECONDARY};
                padding: 8px 16px;
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                font-weight: bold;
            }}
            QTableWidget::item {{
                padding: 8px 16px;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
            QTableWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QTableWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        \"\"\")

    def set_active_row(self, row: int) -> None:
        self.selectRow(row)


class CicdTable(StyledTableWidget):
    \"\"\"Variante CI/CD : headers uppercase, wider padding.\"\"\"
    def __init__(self, columns: list[str], parent: QWidget | None = None) -> None:
        cols = [c.upper() for c in columns]
        super().__init__(cols, parent)
        
        self.setStyleSheet(self.styleSheet() + f\"\"\"
            QHeaderView::section {{
                font-size: 11px;
                letter-spacing: 1px;
                padding: 12px 16px;
            }}
            QTableWidget::item {{
                padding: 12px 16px;
            }}
        \"\"\")
"""

misc_content = """from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QFont, QPaintEvent
from ankiforge.ui.theme import DesignTokens

class UserAvatar(QWidget):
    \"\"\"Avatar 32px avec gradient. Affiche les initiales.\"\"\"
    def __init__(self, initials: str, size: int = 32, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.initials = initials[:2].upper()
        self.size_val = size

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        grad = QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0, QColor(DesignTokens.ACCENT_PRIMARY))
        grad.setColorAt(1, QColor(DesignTokens.COLOR_PURPLE))
        
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(0, 0, self.width(), self.height())
        
        p.setPen(QColor("#ffffff"))
        font = QFont(DesignTokens.FONT_MAIN, self.size_val // 3, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.initials)


class StyledToolbar(QWidget):
    \"\"\"Toolbar flex avec gap-8. Variantes: left, right, space-between.\"\"\"
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(48)
        self.layout_h = QHBoxLayout(self)
        self.layout_h.setContentsMargins(16, 0, 16, 0)
        self.layout_h.setSpacing(8)

    def add_widget(self, widget: QWidget) -> None:
        self.layout_h.addWidget(widget)

    def add_stretch(self) -> None:
        self.layout_h.addStretch()

    def add_separator(self) -> None:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet(f"color: {DesignTokens.BORDER_COLOR};")
        self.layout_h.addWidget(sep)


class DaemonStatusWidget(QWidget):
    \"\"\"Pill statut daemon : spinning icon + texte. Usage: topbar.\"\"\"
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        self.layout_h = QHBoxLayout(self)
        self.layout_h.setContentsMargins(8, 0, 12, 0)
        self.layout_h.setSpacing(6)
        
        self.icon_lbl = QLabel("⚙")
        self.text_lbl = QLabel("Idle")
        self.text_lbl.setStyleSheet(f"font-size: 12px; font-weight: bold;")
        
        self.layout_h.addWidget(self.icon_lbl)
        self.layout_h.addWidget(self.text_lbl)
        self.set_status("idle", "Idle")

    def set_status(self, status: str, text: str) -> None:
        self.text_lbl.setText(text)
        
        if status == "active":
            color = DesignTokens.COLOR_YELLOW
            icon = "⚙"
            bg = f"rgba(245, 158, 11, 0.1)"
        elif status == "pending":
            color = DesignTokens.COLOR_BLUE
            icon = "◷"
            bg = f"rgba(59, 130, 246, 0.1)"
        else:
            color = DesignTokens.TEXT_MUTED
            icon = "✓"
            bg = f"transparent"
            
        self.icon_lbl.setText(icon)
        self.icon_lbl.setStyleSheet(f"color: {color};")
        self.text_lbl.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: bold;")
        
        self.setStyleSheet(f\"\"\"
            DaemonStatusWidget {{
                background-color: {bg};
                border: 1px solid {color if status != 'idle' else DesignTokens.BORDER_COLOR};
                border-radius: 14px;
            }}
        \"\"\")
"""

files = {
    "__init__.py": init_content,
    "buttons.py": buttons_content,
    "panels.py": panels_content,
    "tabs.py": tabs_content,
    "inputs.py": inputs_content,
    "lists.py": lists_content,
    "badges.py": badges_content,
    "tables.py": tables_content,
    "misc.py": misc_content,
}

for filename, content in files.items():
    path = os.path.join(components_dir, filename)
    with open(path, "w") as f:
        f.write(content)

print("Created components successfully.")
