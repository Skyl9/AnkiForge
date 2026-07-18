from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QFrame, QVBoxLayout
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPainter, QColor
from ..theme import DesignTokens


class UserAvatar(QWidget):
    """Avatar 32px avec gradient. Affiche les initiales."""

    def __init__(self, initials: str, size: int = 32, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.initials = initials

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(DesignTokens.ACCENT_PRIMARY))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, self.width(), self.height())

        painter.setPen(QColor("#ffffff"))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.initials)


class StyledToolbar(QWidget):
    """Toolbar flex avec gap-8. Variantes: left, right, space-between."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.layout_main = QHBoxLayout(self)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        self.layout_main.setSpacing(8)

    def add_widget(self, widget: QWidget) -> None:
        self.layout_main.addWidget(widget)

    def add_stretch(self) -> None:
        self.layout_main.addStretch()

    def add_separator(self) -> None:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {DesignTokens.BORDER_COLOR};")
        self.layout_main.addWidget(sep)


class DaemonStatusWidget(QWidget):
    """Pill statut daemon : spinning icon + texte. Usage: topbar."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_INPUT}; border-radius: 12px;")

        self.icon_lbl = QLabel("○")
        self.text_lbl = QLabel("Idle")
        self.text_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")

        layout.addWidget(self.icon_lbl)
        layout.addWidget(self.text_lbl)

    def set_status(self, status: str, text: str) -> None:
        self.text_lbl.setText(text)
        if status == "active":
            self.icon_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW};")
        elif status == "pending":
            self.icon_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE};")
        else:
            self.icon_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED};")


class ProgressBarWidget(QWidget):
    """Barre de progression 6px avec glow fill."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self._progress = 0

    def set_progress(self, value: int) -> None:
        self._progress = min(max(value, 0), 100)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setBrush(QColor(DesignTokens.BG_INPUT))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 3, 3)

        if self._progress > 0:
            width = int((self._progress / 100.0) * self.width())
            painter.setBrush(QColor(DesignTokens.ACCENT_PRIMARY))
            painter.drawRoundedRect(0, 0, width, self.height(), 3, 3)


class DropZone(QFrame):
    """Zone de drag & drop avec bordure dashed. Usage: Dashboard, Wizard."""

    files_dropped = Signal(list)

    def __init__(self, text: str = "Glissez vos fichiers ici", accept_extensions: list[str] | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAcceptDrops(True)
        self.accept_extensions = accept_extensions or []
        self.setStyleSheet(f"""
            #DropZone {{
                border: 2px dashed {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                background-color: {DesignTokens.BG_PANEL};
            }}
            #DropZone:hover {{
                border: 2px dashed {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        layout = QVBoxLayout(self)
        self.setMinimumHeight(150)
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY};")
        layout.addWidget(lbl)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        files = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if self.accept_extensions:
            files = [f for f in files if any(f.endswith(ext) for ext in self.accept_extensions)]
        if files:
            self.files_dropped.emit(files)
