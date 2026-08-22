from typing import Any
from PySide6.QtWidgets import QLabel, QPushButton, QWidget, QHBoxLayout
from PySide6.QtCore import Signal, Qt
from ankiforge.ui.theme import DesignTokens


class Badge(QLabel):
    """Pill badge. Variantes: filled, outline, status, glass."""

    def __init__(self, text: str, variant: str = "filled", color: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.base_color = color
        self.current_variant = variant
        self.set_variant(variant)

    def set_variant(self, variant: str, profile: Any = None) -> None:
        self.current_variant = variant
        accent = profile.accent_primary if profile else DesignTokens.ACCENT_PRIMARY
        border_col = profile.border_color if profile else DesignTokens.BORDER_COLOR
        bg_active = profile.bg_active if profile else DesignTokens.BG_ACTIVE
        bg_hover = profile.bg_hover if profile else DesignTokens.BG_HOVER
        bg_panel = profile.bg_panel if profile else DesignTokens.BG_PANEL
        text_primary = profile.text_primary if profile else DesignTokens.TEXT_PRIMARY
        text_muted = profile.text_muted if profile else DesignTokens.TEXT_MUTED
        color_green = profile.color_green if profile else DesignTokens.COLOR_GREEN
        color_yellow = profile.color_yellow if profile else DesignTokens.COLOR_YELLOW
        color_blue = profile.color_blue if profile else DesignTokens.COLOR_BLUE
        color_red = profile.color_red if profile else DesignTokens.COLOR_RED

        base_color = self.base_color or accent

        style = """
            border-radius: 9999px;
            padding: 3px 12px;
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 0.4px;
        """

        if variant == "filled":
            style += f"background-color: {base_color}; color: #ffffff;"
        elif variant == "outline":
            style += f"background-color: transparent; border: 1px solid {base_color}; color: {base_color};"
        elif variant == "status":
            style += f"background-color: {bg_active}; color: {base_color}; border: 1px solid {border_col};"
        elif variant == "glass":
            style += f"background-color: {bg_hover}; color: {text_primary}; border: 1px solid {border_col};"
        elif variant == "success":
            style += f"background-color: rgba(16, 185, 129, 0.15); color: {color_green};"
        elif variant == "warning":
            style += f"background-color: rgba(245, 158, 11, 0.15); color: {color_yellow};"
        elif variant == "info":
            style += f"background-color: rgba(59, 130, 246, 0.15); color: {color_blue};"
        elif variant == "danger":
            style += f"background-color: rgba(239, 68, 68, 0.15); color: {color_red};"
        elif variant == "neutral":
            style += f"background-color: {bg_panel}; color: {text_muted}; border: 1px solid {border_col};"

        self.setStyleSheet(f"QLabel {{ {style} }}")

    def refresh_theme(self, profile: Any) -> None:
        self.set_variant(self.current_variant, profile)


class StatusBadge(QWidget):
    """Pill badge élégant avec icône Phosphor vectorielle et texte stylisé."""

    def __init__(self, text: str, icon_name: str = "", variant: str = "neutral", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.badge_text = text
        self.icon_name = icon_name
        self.current_variant = variant

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.icon_lbl = QLabel()
        self.icon_lbl.setStyleSheet("border: none; background: transparent;")

        self.text_lbl = QLabel(text)
        self.text_lbl.setStyleSheet("border: none; background: transparent; font-size: 10px; font-weight: bold; letter-spacing: 0.4px;")

        layout.addWidget(self.icon_lbl)
        layout.addWidget(self.text_lbl)

        self._apply_style()

    def set_status(self, text: str, icon_name: str, variant: str) -> None:
        self.badge_text = text
        self.icon_name = icon_name
        self.current_variant = variant
        self.text_lbl.setText(text)
        self._apply_style()

    def _apply_style(self, profile: Any = None) -> None:
        from ankiforge.utils.icon_loader import load_phosphor_icon

        _ = profile.accent_primary if profile else DesignTokens.ACCENT_PRIMARY
        border_col = profile.border_color if profile else DesignTokens.BORDER_COLOR
        bg_panel = profile.bg_panel if profile else DesignTokens.BG_PANEL
        text_muted = profile.text_muted if profile else DesignTokens.TEXT_MUTED
        color_green = profile.color_green if profile else DesignTokens.COLOR_GREEN
        color_yellow = profile.color_yellow if profile else DesignTokens.COLOR_YELLOW
        color_blue = profile.color_blue if profile else DesignTokens.COLOR_BLUE
        color_red = profile.color_red if profile else DesignTokens.COLOR_RED

        variant = self.current_variant
        bg_style = ""
        fg_color = text_muted

        if variant == "success":
            bg_style = "background-color: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.3);"
            fg_color = color_green
        elif variant == "warning":
            bg_style = "background-color: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.3);"
            fg_color = color_yellow
        elif variant == "info":
            bg_style = "background-color: rgba(59, 130, 246, 0.15); border: 1px solid rgba(59, 130, 246, 0.3);"
            fg_color = color_blue
        elif variant in ("danger", "error"):
            bg_style = "background-color: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.3);"
            fg_color = color_red
        else:
            bg_style = f"background-color: {bg_panel}; border: 1px solid {border_col};"
            fg_color = text_muted

        self.setStyleSheet(f"""
            QWidget {{
                {bg_style}
                border-radius: 9999px;
            }}
        """)
        self.text_lbl.setStyleSheet(f"color: {fg_color}; border: none; background: transparent; font-size: 10px; font-weight: bold; letter-spacing: 0.4px;")
        if self.icon_name:
            icon = load_phosphor_icon(self.icon_name, color=fg_color)
            self.icon_lbl.setPixmap(icon.pixmap(12, 12))
            self.icon_lbl.show()
        else:
            self.icon_lbl.hide()

    def refresh_theme(self, profile: Any) -> None:
        self._apply_style(profile)


class TagButton(QPushButton):
    """Tag pill avec code font + tint accent. Usage: tags de notes."""

    removed = Signal(str)

    def __init__(self, text: str, removable: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tag_text = text
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(4)

        self.lbl = QLabel(text)
        self.lbl.setStyleSheet(f"""
            color: {DesignTokens.ACCENT_PRIMARY};
            font-family: "{DesignTokens.FONT_CODE}";
            font-size: 11px;
        """)
        layout.addWidget(self.lbl)

        if removable:
            self.del_lbl = QLabel("×")
            self.del_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 14px;")
            layout.addWidget(self.del_lbl)

        self._apply_style()

    def _apply_style(self, profile: Any = None) -> None:
        accent = profile.accent_primary if profile else DesignTokens.ACCENT_PRIMARY
        bg_active = profile.bg_active if profile else DesignTokens.BG_ACTIVE
        self.setStyleSheet(f"""
            TagButton {{
                background-color: {bg_active};
                border: 1px solid {accent};
                border-radius: 9999px;
            }}
            TagButton:hover {{
                background-color: {bg_active};
                border: 1px solid {accent};
            }}
        """)

    def refresh_theme(self, profile: Any) -> None:
        self._apply_style(profile)
        if hasattr(self, "lbl"):
            self.lbl.setStyleSheet(f"""
                color: {profile.accent_primary};
                font-family: "{profile.font_code}";
                font-size: 11px;
            """)
        if hasattr(self, "del_lbl"):
            self.del_lbl.setStyleSheet(f"color: {profile.text_muted}; font-size: 14px;")

    def mouseReleaseEvent(self, event) -> None:
        from PySide6.QtGui import QMouseEvent

        if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.LeftButton:
            self.removed.emit(self.tag_text)
        super().mouseReleaseEvent(event)
