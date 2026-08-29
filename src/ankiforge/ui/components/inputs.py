from typing import Any
import typing
from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QWidget, QComboBox
from PySide6.QtCore import Signal, Qt, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPainter, QColor, QPaintEvent
from ankiforge.ui.theme import DesignTokens, apply_shadow


class StyledLineEdit(QLineEdit):
    """Input avec style design system et relief subtil."""

    def __init__(self, icon_name: str = "", placeholder: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(34)
        if placeholder:
            self.setPlaceholderText(placeholder)
        self.icon_name = icon_name
        self._action = None
        if icon_name:
            from ankiforge.utils.icon_loader import load_phosphor_icon

            icon = load_phosphor_icon(icon_name, color=DesignTokens.TEXT_MUTED)
            self._action = self.addAction(icon, QLineEdit.ActionPosition.LeadingPosition)

    def refresh_theme(self, profile: Any = None) -> None:
        if self.icon_name and hasattr(self, "_action") and self._action:
            from ankiforge.utils.icon_loader import load_phosphor_icon

            color = profile.text_muted if profile else DesignTokens.TEXT_MUTED
            self._action.setIcon(load_phosphor_icon(self.icon_name, color=color))


class StyledTextEdit(QPlainTextEdit):
    """Textarea avec style design system."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def setText(self, text: str) -> None:
        """Alias pour setPlainText pour compatibilité d'interface."""
        self.setPlainText(text)


class GlowLineEdit(QLineEdit):
    """Input de recherche avec loupe intégrée, animation d'ombre au survol et contour accentué au focus."""

    def __init__(self, placeholder: str = "Rechercher...", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(34)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setProperty("role", "search")
        self._is_focused = False
        if placeholder:
            self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)

        from ankiforge.utils.icon_loader import load_phosphor_icon
        from PySide6.QtWidgets import QGraphicsDropShadowEffect

        self._search_icon = load_phosphor_icon("ph.magnifying-glass", color=DesignTokens.TEXT_MUTED)
        self.addAction(self._search_icon, QLineEdit.ActionPosition.LeadingPosition)

        self._apply_base_style()

        apply_shadow(self, blur=4, offset_y=1, color="rgba(0,0,0,0.22)")
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            self._shadow_effect = effect
            self.anim = QPropertyAnimation(effect, b"blurRadius")
            self.anim.setDuration(160)
            self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.default_blur = 4
            self.hover_blur = 12
            self.focus_blur = 18

    def _apply_base_style(self, profile: Any = None) -> None:
        bg_input = profile.bg_input if profile else DesignTokens.BG_INPUT
        border_color = profile.border_color if profile else DesignTokens.BORDER_COLOR
        border_light = profile.border_light if profile else DesignTokens.BORDER_LIGHT
        radius_sm = profile.radius_sm if profile else DesignTokens.RADIUS_SM
        text_primary = profile.text_primary if profile else DesignTokens.TEXT_PRIMARY
        accent_primary = profile.accent_primary if profile else DesignTokens.ACCENT_PRIMARY
        bg_hover = profile.bg_hover if profile else DesignTokens.BG_HOVER
        bg_panel = profile.bg_panel if profile else DesignTokens.BG_PANEL

        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {bg_input};
                border: 1px solid {border_color};
                border-top: 1px solid {border_light};
                border-radius: {radius_sm}px;
                color: {text_primary};
                padding: 4px 10px;
                font-size: 12px;
                selection-background-color: {accent_primary};
                selection-color: #ffffff;
            }}
            QLineEdit:hover {{
                background-color: {bg_hover};
                border: 1.5px solid {accent_primary};
                color: {text_primary};
            }}
            QLineEdit:focus {{
                background-color: {bg_panel};
                border: 2px solid {accent_primary};
                color: {text_primary};
            }}
        """)

    def refresh_theme(self, profile: Any = None) -> None:
        self._apply_base_style(profile)

    def enterEvent(self, event) -> None:
        if hasattr(self, "anim") and not (self.hasFocus() or self._is_focused):
            self.anim.stop()
            self.anim.setEndValue(self.hover_blur)
            self.anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if hasattr(self, "anim") and not (self.hasFocus() or self._is_focused):
            self.anim.stop()
            self.anim.setEndValue(self.default_blur)
            self.anim.start()
        super().leaveEvent(event)

    def focusInEvent(self, event) -> None:
        self._is_focused = True
        if hasattr(self, "anim"):
            self.anim.stop()
            self.anim.setEndValue(self.focus_blur)
            self.anim.start()
            if hasattr(self, "_shadow_effect") and self._shadow_effect:
                accent_qcolor = QColor(DesignTokens.ACCENT_PRIMARY)
                accent_qcolor.setAlpha(120)
                self._shadow_effect.setColor(accent_qcolor)
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._is_focused = False
        if hasattr(self, "anim"):
            self.anim.stop()
            self.anim.setEndValue(self.default_blur)
            self.anim.start()
            if hasattr(self, "_shadow_effect") and self._shadow_effect:
                self._shadow_effect.setColor(QColor(0, 0, 0, 56))
        super().focusOutEvent(event)


class ToggleSwitch(QWidget):
    """Toggle iOS-style (36x20px). Usage: Settings."""

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

    def isChecked(self) -> bool:
        return self._checked

    def set_checked(self, checked: bool) -> None:
        if self._checked == checked:
            return
        self._checked = checked
        self.anim.setEndValue(18 if self._checked else 2)
        self.anim.start()
        self.toggled.emit(self._checked)

    def setChecked(self, checked: bool) -> None:
        self.set_checked(checked)

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


class OptionToggleRow(QWidget):
    """Ligne d'option moderne et interactive avec icône Phosphor, libellé et ToggleSwitch."""

    toggled = Signal(bool)

    def __init__(
        self,
        title: str,
        icon_name: str = "",
        checked: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("optionToggleRow")
        self.setFixedHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QWidget#optionToggleRow {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
            }}
            QWidget#optionToggleRow:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        from PySide6.QtWidgets import QHBoxLayout, QLabel

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(6)

        if icon_name:
            from ankiforge.utils.icon_loader import load_phosphor_icon

            self.icon_lbl = QLabel()
            self.icon_name = icon_name
            self.icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_SECONDARY).pixmap(14, 14))
            self.icon_lbl.setStyleSheet("border: none; background: transparent;")
            layout.addWidget(self.icon_lbl)

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: 500; border: none; background: transparent;")
        layout.addWidget(self.title_lbl, 1)

        self.switch = ToggleSwitch()
        self.switch.set_checked(checked)
        self.switch.toggled.connect(self._on_switch_toggled)
        layout.addWidget(self.switch)

    def _on_switch_toggled(self, state: bool) -> None:
        self.toggled.emit(state)

    def is_checked(self) -> bool:
        return self.switch.is_checked()

    def isChecked(self) -> bool:
        return self.switch.is_checked()

    def set_checked(self, checked: bool) -> None:
        self.switch.set_checked(checked)

    def setChecked(self, checked: bool) -> None:
        self.switch.set_checked(checked)

    def mouseReleaseEvent(self, event) -> None:
        from PySide6.QtGui import QMouseEvent

        if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.LeftButton:
            self.set_checked(not self.is_checked())
        super().mouseReleaseEvent(event)


class StyledComboBox(QComboBox):
    """ComboBox avec style design system."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)


class DBComboBox(StyledComboBox):
    """ComboBox peuplée dynamiquement à partir d'un modèle Peewee."""

    def __init__(
        self,
        model_class: typing.Any = None,
        display_field: str = "name",
        sort_field: str = "name",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.model_class = model_class
        self.display_field = display_field
        self.sort_field = sort_field
        if model_class is not None:
            self.refresh_from_model()

    def refresh_from_model(self) -> None:
        self.clear()
        if self.model_class is None:
            return
        try:
            query = self.model_class.select()
            if hasattr(self.model_class, self.sort_field):
                query = query.order_by(getattr(self.model_class, self.sort_field))
            for item in query:
                text = getattr(item, self.display_field, str(item))
                val = getattr(item, "id", text)
                self.addItem(text, val)
        except Exception:
            pass  # nosec B110
