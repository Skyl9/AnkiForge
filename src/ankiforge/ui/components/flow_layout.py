"""
Layout Fluide (Flow / Wrap Layout) et Conteneur Fluide pour PySide6.
Permet d'aligner des widgets horizontalement avec retour à la ligne automatique sans débordement ni collision.
"""

from __future__ import annotations

from typing import List, Optional
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QSizePolicy, QWidget


class FlowLayout(QLayout):
    """
    Un layout fluide (Flow / Wrap Layout) qui dispose ses widgets de gauche à droite
    et passe automatiquement à la ligne lorsque la largeur du conteneur est atteinte.
    Idéal pour les balises d'aides Anki, filtres, tags et badges dynamiques.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        margin: int = 0,
        h_spacing: int = 6,
        v_spacing: int = 6,
    ) -> None:
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._item_list: List[QLayoutItem] = []

    def __del__(self) -> None:
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item: QLayoutItem) -> None:
        self._item_list.append(item)

    def horizontalSpacing(self) -> int:
        return self._h_spacing

    def verticalSpacing(self) -> int:
        return self._v_spacing

    def count(self) -> int:
        return len(self._item_list)

    def itemAt(self, index: int) -> Optional[QLayoutItem]:
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index: int) -> Optional[QLayoutItem]:
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, max(1, width), 0), apply_geometry=False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, apply_geometry=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, apply_geometry: bool) -> int:
        margins = self.contentsMargins()
        effective_rect = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0

        for item in self._item_list:
            widget = item.widget()
            if widget and not widget.isVisible():
                continue

            item_size = item.sizeHint()
            space_x = self._h_spacing
            space_y = self._v_spacing

            next_x = x + item_size.width() + space_x
            if next_x - space_x > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + space_y
                next_x = x + item_size.width() + space_x
                line_height = 0

            if apply_geometry:
                item.setGeometry(QRect(QPoint(x, y), item_size))

            x = next_x
            line_height = max(line_height, item_size.height())

        return y + line_height - rect.y() + margins.bottom()


class FlowWidget(QWidget):
    """
    Conteneur spécialisé pour FlowLayout avec nettoyage propre et politique d'expansion fluide.
    """

    def __init__(
        self,
        margin: int = 0,
        h_spacing: int = 6,
        v_spacing: int = 6,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        self.flow_layout = FlowLayout(self, margin=margin, h_spacing=h_spacing, v_spacing=v_spacing)

    def clear(self) -> None:
        """Supprime immédiatement tous les widgets enfants du layout."""
        while self.flow_layout.count():
            child = self.flow_layout.takeAt(0)
            if child:
                w = child.widget()
                if w:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
        self.updateGeometry()
