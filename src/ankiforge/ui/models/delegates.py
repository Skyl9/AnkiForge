"""
Délégués graphiques haute performance (QStyledItemDelegate) pour l'architecture Model/View d'AnkiForge.
Tous les rendus sont exécutés directement au pinceau vectoriel (QPainter) sans créer aucun sous-widget Qt,
garantissant un taux de rafraîchissement constant à 60 FPS et une consommation mémoire minimale.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6.QtCore import QEvent, QModelIndex, QPersistentModelIndex, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from ankiforge.ui.theme import DesignTokens

logger = logging.getLogger(__name__)

# Rôles de données personnalisés pour les délégués
NOTE_ID_ROLE = Qt.ItemDataRole.UserRole + 1
TAGS_LIST_ROLE = Qt.ItemDataRole.UserRole + 2
BADGE_BG_COLOR_ROLE = Qt.ItemDataRole.UserRole + 3
BADGE_TEXT_COLOR_ROLE = Qt.ItemDataRole.UserRole + 4
IS_INVALID_CARD_ROLE = Qt.ItemDataRole.UserRole + 5
RAW_CONTENT_ROLE = Qt.ItemDataRole.UserRole + 6


class CheckboxItemDelegate(QStyledItemDelegate):
    """
    Délégué de case à cocher personnalisée ultra-rapide.
    Dessine une case à cocher stylée moderne (16x16px) avec bords arrondis (4px)
    et coche vectorielle blanche sans instancier de QCheckBox.
    """

    check_toggled = Signal(int, bool)  # (row, is_checked)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> None:
        # Fond de sélection / survol
        self._paint_selection_background(painter, option)

        check_state = index.data(Qt.ItemDataRole.CheckStateRole)
        if check_state is None:
            return

        is_checked = check_state == Qt.CheckState.Checked

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        box_size = 16
        x = option.rect.x() + (option.rect.width() - box_size) // 2
        y = option.rect.y() + (option.rect.height() - box_size) // 2
        box_rect = QRectF(x, y, box_size, box_size)

        if is_checked:
            # Fond actif violet/accent
            painter.setBrush(QColor(DesignTokens.ACCENT_PRIMARY))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(box_rect, 4, 4)

            # Coche blanche vectorielle
            pen = QPen(QColor("white"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            path = QPainterPath()
            path.moveTo(x + 4, y + 8)
            path.lineTo(x + 7, y + 11.5)
            path.lineTo(x + 12, y + 4.5)
            painter.drawPath(path)
        else:
            # Case décochée : fond sombre / bordure discrète
            painter.setBrush(QColor(DesignTokens.BG_INPUT))
            pen = QPen(QColor(DesignTokens.BORDER_COLOR), 1.2)
            painter.setPen(pen)
            painter.drawRoundedRect(box_rect, 4, 4)

        painter.restore()

    def editorEvent(
        self,
        event: QEvent,
        model: Any,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        if event.type() == QEvent.Type.MouseButtonRelease:
            mouse_event = event if isinstance(event, QMouseEvent) else None
            if mouse_event and mouse_event.button() == Qt.MouseButton.LeftButton:
                current_state = index.data(Qt.ItemDataRole.CheckStateRole)
                if current_state is not None:
                    new_state = Qt.CheckState.Unchecked if current_state == Qt.CheckState.Checked else Qt.CheckState.Checked
                    model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)
                    self.check_toggled.emit(index.row(), new_state == Qt.CheckState.Checked)
                    return True
        return super().editorEvent(event, model, option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(36, 34)

    def _paint_selection_background(self, painter: QPainter, option: QStyleOptionViewItem) -> None:
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(99, 102, 241, 35))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor(DesignTokens.BG_HOVER))


class BadgeItemDelegate(QStyledItemDelegate):
    """
    Délégué dessinant une pilule/badge textuel avec coins ultra-arrondis
    et couleurs sémantiques dynamiques (ex: Modèles, Statuts, Decks).
    """

    def __init__(
        self,
        default_bg: str = "rgba(99, 102, 241, 0.15)",
        default_text_color: str = DesignTokens.ACCENT_PRIMARY,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._default_bg = default_bg
        self._default_text_color = default_text_color

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> None:
        self._paint_selection_background(painter, option)

        text = index.data(Qt.ItemDataRole.DisplayRole)
        if not text:
            return

        bg_color_val = index.data(BADGE_BG_COLOR_ROLE) or self._default_bg
        text_color_val = index.data(BADGE_TEXT_COLOR_ROLE) or self._default_text_color

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        font = QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()

        padding_h = 8
        badge_h = 22
        text_w = fm.horizontalAdvance(str(text))
        badge_w = min(text_w + padding_h * 2, max(30, option.rect.width() - 12))

        x = option.rect.x() + 6
        y = option.rect.y() + (option.rect.height() - badge_h) // 2
        badge_rect = QRectF(x, y, badge_w, badge_h)

        # Fond pill
        bg_col = QColor(bg_color_val)
        painter.setBrush(bg_col)
        border_pen = QPen(bg_col.lighter(130) if bg_col.alpha() < 200 else bg_col, 1)
        painter.setPen(border_pen)
        painter.drawRoundedRect(badge_rect, 11, 11)

        # Texte pill
        painter.setPen(QColor(text_color_val))
        elided = fm.elidedText(str(text), Qt.TextElideMode.ElideRight, int(badge_w - padding_h * 2))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, elided)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(110, 34)

    def _paint_selection_background(self, painter: QPainter, option: QStyleOptionViewItem) -> None:
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(99, 102, 241, 35))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor(DesignTokens.BG_HOVER))


class TagItemDelegate(QStyledItemDelegate):
    """
    Délégué pour afficher des tags multiples sous forme de pastilles successives (#tag1, #tag2...)
    sans débordement et avec troncature propre.
    """

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> None:
        self._paint_selection_background(painter, option)

        tags_list = index.data(TAGS_LIST_ROLE)
        if not tags_list:
            display_text = index.data(Qt.ItemDataRole.DisplayRole)
            if display_text:
                tags_list = [t.strip().lstrip("#") for t in str(display_text).split() if t.strip()]

        if not tags_list:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        font = QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Medium)
        painter.setFont(font)
        fm = painter.fontMetrics()

        current_x = option.rect.x() + 6
        max_x = option.rect.right() - 6
        badge_h = 20
        y = option.rect.y() + (option.rect.height() - badge_h) // 2

        tag_bg = QColor(192, 132, 252, 35)  # Violet translucide
        tag_border = QPen(QColor(192, 132, 252, 100), 1)
        tag_text_color = QColor("#c084fc")

        for tag in tags_list:
            tag_label = f"#{tag}"
            text_w = fm.horizontalAdvance(tag_label)
            pill_w = text_w + 12

            if current_x + pill_w > max_x:
                # Indicateur d'autres tags "+N"
                remaining_tags = f"+{len(tags_list) - tags_list.index(tag)}"
                rem_w = fm.horizontalAdvance(remaining_tags) + 8
                if current_x + rem_w <= max_x:
                    rem_rect = QRectF(current_x, y, rem_w, badge_h)
                    painter.setBrush(QColor(DesignTokens.BG_INPUT))
                    painter.setPen(QPen(QColor(DesignTokens.BORDER_COLOR), 1))
                    painter.drawRoundedRect(rem_rect, 6, 6)
                    painter.setPen(QColor(DesignTokens.TEXT_MUTED))
                    painter.drawText(rem_rect, Qt.AlignmentFlag.AlignCenter, remaining_tags)
                break

            pill_rect = QRectF(current_x, y, pill_w, badge_h)
            painter.setBrush(tag_bg)
            painter.setPen(tag_border)
            painter.drawRoundedRect(pill_rect, 10, 10)

            painter.setPen(tag_text_color)
            painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, tag_label)

            current_x += int(pill_w) + 6

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(140, 34)

    def _paint_selection_background(self, painter: QPainter, option: QStyleOptionViewItem) -> None:
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(99, 102, 241, 35))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor(DesignTokens.BG_HOVER))


class TextSnippetDelegate(QStyledItemDelegate):
    """
    Délégué de texte avec police monospace et détection d'anomalies (cartes vides/invalides).
    """

    def __init__(self, is_code_font: bool = True, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._is_code_font = is_code_font

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> None:
        self._paint_selection_background(painter, option)

        text = index.data(Qt.ItemDataRole.DisplayRole)
        if text is None:
            return

        is_invalid = bool(index.data(IS_INVALID_CARD_ROLE))
        custom_color = index.data(Qt.ItemDataRole.ForegroundRole)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._is_code_font:
            font = QFont(DesignTokens.FONT_CODE, 10)
        else:
            font = QFont(DesignTokens.FONT_MAIN, 10)
        painter.setFont(font)
        fm = painter.fontMetrics()

        if is_invalid:
            painter.setPen(QColor(DesignTokens.COLOR_RED))
        elif custom_color:
            col = custom_color.color() if hasattr(custom_color, "color") else QColor(custom_color)
            painter.setPen(col)
        elif option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QColor(DesignTokens.TEXT_PRIMARY))
        else:
            painter.setPen(QColor(DesignTokens.TEXT_PRIMARY))

        rect = QRect(
            option.rect.x() + 8,
            option.rect.y(),
            option.rect.width() - 16,
            option.rect.height(),
        )

        elided = fm.elidedText(str(text), Qt.TextElideMode.ElideRight, rect.width())
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        # Ligne de séparation inférieure discrète
        painter.setPen(QColor(DesignTokens.BORDER_COLOR))
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(200, 34)

    def _paint_selection_background(self, painter: QPainter, option: QStyleOptionViewItem) -> None:
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(99, 102, 241, 35))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor(DesignTokens.BG_HOVER))


class ProgressBarItemDelegate(QStyledItemDelegate):
    """
    Délégué peignant directement une barre de progression moderne pour les files d'attente (Batch).
    """

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> None:
        self._paint_selection_background(painter, option)

        progress_val = index.data(Qt.ItemDataRole.UserRole)
        if progress_val is None:
            try:
                progress_val = int(index.data(Qt.ItemDataRole.DisplayRole) or 0)
            except Exception:
                progress_val = 0

        pct = max(0, min(100, int(progress_val)))

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bar_h = 10
        bar_w = option.rect.width() - 50
        x = option.rect.x() + 8
        y = option.rect.y() + (option.rect.height() - bar_h) // 2

        track_rect = QRectF(x, y, bar_w, bar_h)
        painter.setBrush(QColor(DesignTokens.BG_INPUT))
        painter.setPen(QPen(QColor(DesignTokens.BORDER_COLOR), 1))
        painter.drawRoundedRect(track_rect, 5, 5)

        if pct > 0:
            fill_w = (bar_w * pct) / 100.0
            fill_rect = QRectF(x, y, fill_w, bar_h)
            fill_color = QColor(DesignTokens.COLOR_GREEN if pct == 100 else DesignTokens.ACCENT_PRIMARY)
            painter.setBrush(fill_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(fill_rect, 5, 5)

        # Pourcentage textuel
        font = QFont(DesignTokens.FONT_MAIN, 8, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor(DesignTokens.TEXT_MUTED))
        text_rect = QRect(int(x + bar_w + 6), option.rect.y(), 34, option.rect.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{pct}%")

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(160, 34)

    def _paint_selection_background(self, painter: QPainter, option: QStyleOptionViewItem) -> None:
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(99, 102, 241, 35))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor(DesignTokens.BG_HOVER))


class SimilarityBadgeDelegate(QStyledItemDelegate):
    """
    Délégué peignant le badge de similarité (ex: 96.5% en rouge >95%, jaune sinon).
    """

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> None:
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(99, 102, 241, 35))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor(DesignTokens.BG_HOVER))

        val = index.data(Qt.ItemDataRole.DisplayRole)
        if val is None:
            return

        try:
            val_str = str(val).replace("%", "").strip()
            sim_float = float(val_str)
        except ValueError:
            sim_float = 0.0

        if sim_float > 95.0 or (0.95 < sim_float <= 1.0):
            bg_col = QColor(239, 68, 68, 45)
            text_col = QColor(DesignTokens.COLOR_RED)
        else:
            bg_col = QColor(245, 158, 11, 45)
            text_col = QColor(DesignTokens.COLOR_YELLOW)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        font = QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()

        pct_val = sim_float * 100.0 if sim_float <= 1.0 else sim_float
        text = f"{pct_val:.1f}%"
        badge_w = fm.horizontalAdvance(text) + 16
        badge_h = 20
        x = option.rect.x() + 8
        y = option.rect.y() + (option.rect.height() - badge_h) // 2
        rect = QRectF(x, y, badge_w, badge_h)

        painter.setBrush(bg_col)
        painter.setPen(QPen(text_col, 1))
        painter.drawRoundedRect(rect, 10, 10)

        painter.setPen(text_col)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(90, 34)


class SrsMasteryDelegate(QStyledItemDelegate):
    """
    Délégué peignant la comparaison de maîtrise SRS (ex: 🟢 Maîtrisée vs 🔴 Nouvelle)
    directement au pinceau sans aucun QLabel ni conteneur QWidget.
    """

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> None:
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(99, 102, 241, 35))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor(DesignTokens.BG_HOVER))

        srs_data = index.data(Qt.ItemDataRole.UserRole)
        display_str = index.data(Qt.ItemDataRole.DisplayRole)
        if not display_str and not srs_data:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        font_bold = QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold)
        font_normal = QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Normal)

        if isinstance(srs_data, (list, tuple)) and len(srs_data) == 2:
            (str_a, col_a), (str_b, col_b) = srs_data
        else:
            parts = str(display_str).split(" vs ")
            str_a = parts[0].strip() if len(parts) > 0 else ""
            str_b = parts[1].strip() if len(parts) > 1 else ""
            col_a = DesignTokens.COLOR_GREEN if "🟢" in str_a else (DesignTokens.COLOR_YELLOW if "🟡" in str_a else DesignTokens.COLOR_RED)
            col_b = DesignTokens.COLOR_GREEN if "🟢" in str_b else (DesignTokens.COLOR_YELLOW if "🟡" in str_b else DesignTokens.COLOR_RED)

        x = option.rect.x() + 8
        y = option.rect.y()
        h = option.rect.height()

        painter.setFont(font_bold)
        painter.setPen(QColor(col_a))
        fm = painter.fontMetrics()
        w_a = fm.horizontalAdvance(str_a)
        rect_a = QRect(x, y, w_a, h)
        painter.drawText(rect_a, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str_a)

        painter.setFont(font_normal)
        painter.setPen(QColor(DesignTokens.TEXT_MUTED))
        fm_norm = painter.fontMetrics()
        vs_text = " vs "
        w_vs = fm_norm.horizontalAdvance(vs_text)
        rect_vs = QRect(x + w_a, y, w_vs, h)
        painter.drawText(rect_vs, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, vs_text)

        painter.setFont(font_bold)
        painter.setPen(QColor(col_b))
        w_b = fm.horizontalAdvance(str_b)
        rect_b = QRect(x + w_a + w_vs, y, w_b, h)
        painter.drawText(rect_b, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str_b)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(220, 34)
