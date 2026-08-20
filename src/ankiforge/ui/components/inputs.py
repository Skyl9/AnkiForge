import typing
from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QWidget, QComboBox
from PySide6.QtCore import Signal, Qt, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPainter, QColor, QPaintEvent
from ankiforge.ui.theme import DesignTokens, apply_shadow


class StyledLineEdit(QLineEdit):
    """Input avec style design system. Focus = glow indigo."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)


class StyledTextEdit(QPlainTextEdit):
    """Textarea avec style design system."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def setText(self, text: str) -> None:
        """Alias pour setPlainText pour compatibilité d'interface."""
        self.setPlainText(text)


class GlowLineEdit(QLineEdit):
    """Input avec glow accentué au focus. Usage: recherche, omnibox."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(40)
        apply_shadow(self, blur=8, offset_y=2)


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

    def set_checked(self, checked: bool) -> None:
        if self._checked == checked:
            return
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
    """ComboBox avec style design system."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet(f"""
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
        """)


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
