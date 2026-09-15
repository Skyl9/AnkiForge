from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QSize
from PySide6.QtGui import QHelpEvent, QPaintEvent
from PySide6.QtWidgets import QToolTip, QWidget

from ankiforge.ui.components.code_editor.color_utils import extract_colors_from_text

if TYPE_CHECKING:
    from ankiforge.ui.components.code_editor.widgets.native_editor import NativeCodeEditor


class LineNumberArea(QWidget):
    """Gouttière native peinte avec QPainter, incluant numéros de lignes, pastilles de couleur et alertes."""

    def __init__(self, editor: NativeCodeEditor) -> None:
        super().__init__(editor)
        self.code_editor = editor
        self.setMouseTracking(True)

    def sizeHint(self) -> QSize:
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event: QPaintEvent) -> None:
        self.code_editor.line_number_area_paint_event(event)

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            pos_y = event.pos().y()
            block = self.code_editor.firstVisibleBlock()
            top = int(self.code_editor.blockBoundingGeometry(block).translated(self.code_editor.contentOffset()).top())
            bottom = top + int(self.code_editor.blockBoundingRect(block).height())

            while block.isValid() and top <= self.height():
                if top <= pos_y <= bottom:
                    line_text = block.text()
                    colors = extract_colors_from_text(line_text)
                    if colors:
                        tip_parts = [f"🎨 Couleur : {c_str}" for c_str, _ in colors]
                        QToolTip.showText(event.globalPos(), "\n".join(tip_parts), self)
                        return True
                    break
                block = block.next()
                top = bottom
                bottom = top + int(self.code_editor.blockBoundingRect(block).height())

        return super().event(event)
