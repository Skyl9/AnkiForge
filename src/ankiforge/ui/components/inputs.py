import logging
import typing
from typing import Any

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QComboBox, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QWidget

from ankiforge.ui.theme import DesignTokens, apply_shadow

logger = logging.getLogger(__name__)


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

    def _start_anim(self, end_val: float) -> None:
        if not hasattr(self, "anim"):
            return
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            if self.anim.targetObject() is not effect:
                self.anim.setTargetObject(effect)
            self.anim.stop()
            self.anim.setEndValue(end_val)
            self.anim.start()

    def enterEvent(self, event: Any) -> None:
        if not (self.hasFocus() or self._is_focused):
            self._start_anim(self.hover_blur)
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        if not (self.hasFocus() or self._is_focused):
            self._start_anim(self.default_blur)
        super().leaveEvent(event)

    def focusInEvent(self, event: Any) -> None:
        self._is_focused = True
        self._start_anim(self.focus_blur)
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            accent_qcolor = QColor(DesignTokens.ACCENT_PRIMARY)
            accent_qcolor.setAlpha(120)
            effect.setColor(accent_qcolor)
        super().focusInEvent(event)

    def focusOutEvent(self, event: Any) -> None:
        self._is_focused = False
        self._start_anim(self.default_blur)
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            effect.setColor(QColor(0, 0, 0, 56))
        super().focusOutEvent(event)


class ToggleSwitch(QWidget):
    """Toggle iOS-style (36x20px). Usage: Settings, Batch Factory, Options."""

    toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(36, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._checked: bool = False
        self._thumb_pos: float = 2.0
        self._profile: Any = None

        self.anim = QPropertyAnimation(self, b"thumb_pos")
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)

    def is_checked(self) -> bool:
        return self._checked

    def isChecked(self) -> bool:
        return self._checked

    def toggle(self, animated: bool = True) -> None:
        self.set_checked(not self._checked, animated=animated)

    def set_checked(self, checked: bool, animated: bool = True) -> None:
        if self._checked == checked:
            return
        self._checked = checked
        target_pos = 18.0 if self._checked else 2.0

        if animated and self.isVisible():
            self.anim.stop()
            self.anim.setStartValue(self._thumb_pos)
            self.anim.setEndValue(target_pos)
            remaining_dist = abs(target_pos - self._thumb_pos)
            duration = max(40, int(150 * (remaining_dist / 16.0)))
            self.anim.setDuration(duration)
            self.anim.start()
        else:
            self.anim.stop()
            self._thumb_pos = target_pos
            self.update()

        self.toggled.emit(self._checked)

    def setChecked(self, checked: bool) -> None:
        self.set_checked(checked)

    def get_thumb_pos(self) -> float:
        return self._thumb_pos

    def set_thumb_pos(self, pos: float) -> None:
        self._thumb_pos = pos
        self.update()

    thumb_pos = Property(float, get_thumb_pos, set_thumb_pos)

    def apply_theme_profile(self, profile: Any = None) -> None:
        self._profile = profile
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle(animated=True)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Interpolation fluide de la couleur d'arrière-plan
        t = max(0.0, min(1.0, (self._thumb_pos - 2.0) / 16.0))
        bg_input = self._profile.bg_input if self._profile else DesignTokens.BG_INPUT
        accent_color = self._profile.accent_primary if self._profile else DesignTokens.ACCENT_PRIMARY

        c_off = QColor(bg_input)
        c_on = QColor(accent_color)
        r = int(c_off.red() + (c_on.red() - c_off.red()) * t)
        g = int(c_off.green() + (c_on.green() - c_off.green()) * t)
        b = int(c_off.blue() + (c_on.blue() - c_off.blue()) * t)
        bg_color = QColor(r, g, b)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg_color)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 10, 10)

        # Curseur circulaire avec coordonnées sous-pixel
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(self._thumb_pos, 2.0, 16.0, 16.0))


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
        self.icon_name = icon_name
        self._checked: bool = checked
        self._profile: Any = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(6)

        if icon_name:
            self.icon_lbl = QLabel()
            self.icon_lbl.setStyleSheet("border: none; background: transparent;")
            layout.addWidget(self.icon_lbl)

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: 500; border: none; background: transparent;")
        layout.addWidget(self.title_lbl, 1)

        self.switch = ToggleSwitch(self)
        # Rendre le switch transparent aux événements souris pour que la rangée entière réagisse de manière unifiée
        self.switch.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.switch.set_checked(checked, animated=False)
        self.switch.toggled.connect(self._on_switch_toggled)
        layout.addWidget(self.switch)

        self._update_style()

    def _update_style(self) -> None:
        if self._profile is not None:
            accent = self._profile.accent_primary
            border = accent if self._checked else self._profile.border_color
            bg = self._profile.bg_panel
            text_color = self._profile.text_primary
            icon_color = accent if self._checked else self._profile.text_secondary
        else:
            accent = DesignTokens.ACCENT_PRIMARY
            border = accent if self._checked else DesignTokens.BORDER_COLOR
            bg = DesignTokens.BG_PANEL
            text_color = DesignTokens.TEXT_PRIMARY
            icon_color = accent if self._checked else DesignTokens.TEXT_SECONDARY

        self.setStyleSheet(f"""
            QWidget#optionToggleRow {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 6px;
            }}
            QWidget#optionToggleRow:hover {{
                border-color: {accent};
            }}
        """)
        if hasattr(self, "title_lbl"):
            self.title_lbl.setStyleSheet(f"color: {text_color}; font-size: 11px; font-weight: 500; border: none; background: transparent;")
        if hasattr(self, "icon_lbl") and self.icon_name:
            from ankiforge.utils.icon_loader import load_phosphor_icon

            self.icon_lbl.setPixmap(load_phosphor_icon(self.icon_name, color=icon_color).pixmap(14, 14))

    def apply_theme_profile(self, profile: Any = None) -> None:
        self._profile = profile
        self.switch.apply_theme_profile(profile)
        self._update_style()

    def _on_switch_toggled(self, state: bool) -> None:
        self._checked = state
        self._update_style()
        self.toggled.emit(state)

    def is_checked(self) -> bool:
        return self.switch.is_checked()

    def isChecked(self) -> bool:
        return self.switch.is_checked()

    def set_checked(self, checked: bool, animated: bool = True) -> None:
        self._checked = checked
        self.switch.set_checked(checked, animated=animated)
        self._update_style()

    def setChecked(self, checked: bool) -> None:
        self.set_checked(checked)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_checked(not self.is_checked(), animated=True)
            event.accept()
        else:
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
        prev_data = self.currentData()
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

            if prev_data is not None:
                for i in range(self.count()):
                    if self.itemData(i) == prev_data:
                        self.setCurrentIndex(i)
                        break
        except Exception as err:
            logger.debug("Rechargement du modèle dans le combo ignoré : %s", err)

    def refresh_data(self) -> None:
        """Alias pour refresh_from_model."""
        self.refresh_from_model()
