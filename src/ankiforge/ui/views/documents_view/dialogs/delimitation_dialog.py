import html
import json
import logging
import re
from pathlib import Path
from typing import Any

import markdown
from peewee import fn
from PySide6.QtCore import QPointF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView

    HAVE_QTPDF = True
except ImportError:
    HAVE_QTPDF = False

from ankiforge.database.models import DocumentChunkModel, DocumentModel, DocumentPageModel, NoteChunkLinkModel
from ankiforge.services.ai.rag_service import RAGService
from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService
from ankiforge.services.parsing.chunking_service import ChunkingService, HeadingTreeNode
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.components import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon
from ankiforge.utils.paths import get_resource_path, resolve_media_path

logger = logging.getLogger(__name__)


def has_structured_heading_nodes(nodes: list[HeadingTreeNode]) -> bool:
    """Retourne vrai si l'arbre contient des titres Markdown plutôt que des pages synthétiques."""
    return any(node.children or node.level > 1 or not node.title.casefold().startswith(("page ", "planche ")) for node in nodes)


class SectionTreeWidgetItem(QTreeWidgetItem):
    """Élément d'arborescence pour QTreeWidget offrant une compatibilité API totale avec QListWidgetItem."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._tree_ref: DocumentStructureTreeWidget | None = None
        self._updating_check_state: bool = False

    def checkState(self, column: int = 0) -> Qt.CheckState:
        return super().checkState(column)

    def setCheckState(self, *args: Any) -> None:
        if self._updating_check_state:
            return
        self._updating_check_state = True
        try:
            if len(args) == 1:
                state = args[0]
                super().setCheckState(0, state)
            elif len(args) >= 2:
                state = args[1]
                super().setCheckState(args[0], state)
            else:
                return

            if self._tree_ref is not None:
                w = self._tree_ref.itemWidget(self, 0)
                if hasattr(w, "set_check_state"):
                    w.set_check_state(state)
        finally:
            self._updating_check_state = False

    def data(self, *args: Any) -> Any:
        if len(args) == 1:
            return super().data(0, args[0])
        return super().data(args[0], args[1])

    def setData(self, *args: Any) -> None:
        if len(args) == 2:
            super().setData(0, args[0], args[1])
        elif len(args) >= 3:
            super().setData(args[0], args[1], args[2])

    def setSizeHint(self, *args: Any) -> None:
        if len(args) == 1:
            super().setSizeHint(0, args[0])
        elif len(args) >= 2:
            super().setSizeHint(args[0], args[1])


class DocumentStructureTreeWidget(QTreeWidget):
    """QTreeWidget hiérarchique avec support des chevrons de repli et compatibilité rétrograde drop-in pour QListWidget."""

    itemClicked = Signal(object)
    currentRowChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(20)
        self.setAnimated(True)
        self.currentItemChanged.connect(self._on_current_item_changed)

    def _on_current_item_changed(self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None) -> None:
        if current is not None:
            self.currentRowChanged.emit(self.row(current))
        else:
            self.currentRowChanged.emit(-1)

    def all_items(self) -> list[QTreeWidgetItem]:
        res: list[QTreeWidgetItem] = []

        def _walk(it: QTreeWidgetItem) -> None:
            res.append(it)
            for i in range(it.childCount()):
                _walk(it.child(i))

        for i in range(self.topLevelItemCount()):
            _walk(self.topLevelItem(i))
        return res

    def count(self) -> int:
        return len(self.all_items())

    def item(self, index: int) -> QTreeWidgetItem | None:
        items = self.all_items()
        if 0 <= index < len(items):
            return items[index]
        return None

    def row(self, item: QTreeWidgetItem) -> int:
        items = self.all_items()
        try:
            return items.index(item)
        except ValueError:
            return -1

    def addItem(self, item: QTreeWidgetItem) -> None:
        self.addTopLevelItem(item)

    def itemWidget(self, item: QTreeWidgetItem, column: int = 0) -> QWidget:
        widget = super().itemWidget(item, column)
        if widget is None:
            raise RuntimeError("itemWidget returned None — item not registered in this tree")
        return widget

    def setItemWidget(self, item: QTreeWidgetItem, column_or_widget: Any, widget: QWidget | None = None) -> None:
        if isinstance(item, SectionTreeWidgetItem):
            item._tree_ref = self
        if widget is None:
            super().setItemWidget(item, 0, column_or_widget)
        else:
            super().setItemWidget(item, column_or_widget, widget)

    def currentRow(self) -> int:
        cur = self.currentItem()
        return self.row(cur) if cur else -1

    def setCurrentRow(self, row_idx: int) -> None:
        it = self.item(row_idx)
        if it:
            self.setCurrentItem(it)


class SectionRowWidget(QWidget):
    """Widget de ligne personnalisée pour afficher et basculer individuellement une section avec son diagnostic."""

    checked_changed = Signal(bool)
    state_changed = Signal(Qt.CheckState)

    def __init__(
        self,
        item: QTreeWidgetItem,
        tree_widget: QTreeWidget | None = None,
        title: str = "",
        is_checked: bool = True,
        page_number: int | None = None,
        end_page: int | None = None,
        level: int = 1,
        word_count: int = 0,
        cards_count: int = 0,
        is_noise: bool = False,
        is_leaf: bool = True,
        show_page: bool = True,
        list_widget: Any = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._item = item
        self._tree_widget = tree_widget or list_widget
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 8, 2)
        layout.setSpacing(8)

        # Checkbox explicite et interactive avec support tristate
        self.checkbox = QCheckBox()
        self.checkbox.setTristate(True)
        self.checkbox.setChecked(is_checked)
        self.checkbox.checkStateChanged.connect(self._on_check_state_changed)
        layout.addWidget(self.checkbox)

        # Badge de niveau de titre sémantique (H1, H2, H3)
        if level == 1:
            h_badge = QLabel("H1")
            h_badge.setStyleSheet(
                f"background-color: {DesignTokens.ACCENT_BG}; color: {DesignTokens.COLOR_PURPLE_TEXT}; border: 1px solid {DesignTokens.ACCENT_BORDER};"
                f" border-radius: 4px; padding: 1px 5px; font-weight: bold; font-size: 10px;"
            )
            layout.addWidget(h_badge)
        elif level == 2:
            h_badge = QLabel("H2")
            h_badge.setStyleSheet(
                f"background-color: {DesignTokens.COLOR_BLUE_BG}; color: {DesignTokens.COLOR_BLUE_TEXT}; border: 1px solid {DesignTokens.COLOR_BLUE_BORDER};"
                f" border-radius: 4px; padding: 1px 5px; font-weight: bold; font-size: 10px;"
            )
            layout.addWidget(h_badge)
        elif level >= 3:
            h_badge = QLabel(f"H{level}")
            h_badge.setStyleSheet(
                f"background-color: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_SECONDARY}; border: 1px solid {DesignTokens.BORDER_COLOR};"
                f" border-radius: 4px; padding: 1px 5px; font-size: 10px;"
            )
            layout.addWidget(h_badge)

        # Titre avec plage de pages facultative (uniquement pour documents paginés)
        if show_page and page_number is not None:
            p_span = f"p. {page_number}–{end_page}" if end_page is not None and end_page > page_number else f"p. {page_number}"
            page_suffix = f" <span style='color: {DesignTokens.TEXT_MUTED}; font-size: 11px;'>({p_span})</span>"
            full_tooltip = f"{title} ({p_span})"
        else:
            page_suffix = ""
            full_tooltip = title

        title_lbl = QLabel(f"{html.escape(title)}{page_suffix}")
        title_lbl.setTextFormat(Qt.TextFormat.RichText)
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500; border: none; background: transparent;")
        title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        title_lbl.setMinimumWidth(80)
        title_lbl.setToolTip(full_tooltip)
        layout.addWidget(title_lbl, 1)

        # Badge Volume de mots (compact) — avertissement jaune uniquement pour les feuilles
        if word_count < 25 and not is_noise and is_leaf:
            word_badge = QLabel(f"{word_count} mots")
            word_badge.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 10px; font-weight: 500; border: none; background: transparent;")
        else:
            word_badge = QLabel(f"{word_count} mots")
            word_badge.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; border: none; background: transparent;")
        layout.addWidget(word_badge)

        # Badge Cartes existantes — UNIQUEMENT si cartes > 0 (évite d'encombrer chaque ligne avec "0 carte")
        if cards_count > 0:
            card_badge = QLabel(f"{cards_count} carte{'s' if cards_count > 1 else ''}")
            card_badge.setStyleSheet(
                f"background-color: {DesignTokens.BG_ACTIVE}; color: {DesignTokens.ACCENT_PRIMARY}; "
                f"border: 1px solid {DesignTokens.ACCENT_PRIMARY}; border-radius: 4px; padding: 1px 5px; "
                "font-weight: bold; font-size: 10px;"
            )
            layout.addWidget(card_badge)

        # Badge Diagnostic / Recommandation — UNIQUEMENT pour les alertes réelles (Quasi vide, Exclu, Utile)
        if cards_count > 0:
            diag_badge = QLabel("Utile (Cartes)")
            diag_badge.setStyleSheet(
                f"background-color: {DesignTokens.COLOR_GREEN_BG}; color: {DesignTokens.COLOR_GREEN_TEXT}; border: 1px solid {DesignTokens.COLOR_GREEN_BORDER};"
                f" border-radius: 4px; padding: 1px 5px; font-size: 10px; font-weight: bold;"
            )
            layout.addWidget(diag_badge)
        elif is_noise:
            diag_badge = QLabel("Exclu")
            diag_badge.setStyleSheet(
                f"background-color: {DesignTokens.COLOR_RED_BG}; color: {DesignTokens.COLOR_RED_TEXT}; border: 1px solid {DesignTokens.COLOR_RED_BORDER};"
                f" border-radius: 4px; padding: 1px 5px; font-size: 10px; font-weight: bold;"
            )
            layout.addWidget(diag_badge)
        elif word_count < 25 and is_leaf:
            diag_badge = QLabel("Quasi vide")
            diag_badge.setStyleSheet(
                f"background-color: {DesignTokens.COLOR_YELLOW_BG}; color: {DesignTokens.COLOR_YELLOW_TEXT};"
                f" border: 1px solid {DesignTokens.COLOR_YELLOW_BORDER}; border-radius: 4px; padding: 1px 5px; font-size: 10px;"
            )
            layout.addWidget(diag_badge)

    def _on_check_state_changed(self, state: Qt.CheckState) -> None:
        self._tree_widget.setCurrentItem(self._item)
        self._item.setCheckState(0, state)
        self.state_changed.emit(state)
        self.checked_changed.emit(state == Qt.CheckState.Checked)

    def is_checked(self) -> bool:
        return self.checkbox.checkState() == Qt.CheckState.Checked

    def check_state(self) -> Qt.CheckState:
        return self.checkbox.checkState()

    def set_check_state(self, state: Qt.CheckState) -> None:
        self.checkbox.blockSignals(True)
        self.checkbox.setCheckState(state)
        QTreeWidgetItem.setCheckState(self._item, 0, state)
        self.checkbox.blockSignals(False)

    def set_checked(self, checked: bool) -> None:
        self.set_check_state(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def mousePressEvent(self, event: Any) -> None:
        self._tree_widget.setCurrentItem(self._item)
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if not self.checkbox.geometry().contains(pos):
            new_state = Qt.CheckState.Unchecked if self.checkbox.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
            self.checkbox.setCheckState(new_state)
        self._tree_widget.itemClicked.emit(self._item)


class ChapterCardWidget(QFrame):
    """Carte interactive pour la sélection d'un chapitre dans le mode Par Chapitres."""

    toggled = Signal(int, bool)

    def __init__(
        self,
        chapter_index: int,
        title: str,
        start_page: int | None = None,
        end_page: int | None = None,
        subsections_count: int = 0,
        word_count: int = 0,
        is_checked: bool = True,
        is_paginated: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.chapter_index = chapter_index
        self.setObjectName(f"chapterCard_{chapter_index}")
        self.setStyleSheet(f"""
            QFrame#{self.objectName()} {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius:  {DesignTokens.RADIUS_MD}px;
            }}
            QFrame#{self.objectName()}:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(is_checked)
        self.checkbox.stateChanged.connect(lambda s: self.toggled.emit(self.chapter_index, s == Qt.CheckState.Checked.value))
        layout.addWidget(self.checkbox)

        badge_h1 = QLabel(f"Ch. {chapter_index + 1}")
        badge_h1.setStyleSheet(
            f"background-color: {DesignTokens.ACCENT_BG}; color: {DesignTokens.COLOR_PURPLE_TEXT}; border: 1px solid {DesignTokens.ACCENT_BORDER};"
            f" border-radius: 4px; padding: 2px 6px; font-weight: bold; font-size: 10px;"
        )
        layout.addWidget(badge_h1)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 600; border: none; background: transparent;")
        title_lbl.setWordWrap(True)
        info_col.addWidget(title_lbl)

        meta_parts: list[str] = []
        if is_paginated and start_page is not None:
            p_span = f"Pages {start_page}–{end_page}" if end_page and end_page > start_page else f"Page {start_page}"
            meta_parts.append(p_span)
        if subsections_count > 0:
            meta_parts.append(f"{subsections_count} sous-section{'s' if subsections_count > 1 else ''}")
        meta_parts.append(f"~{word_count} mots")
        meta_str = " • ".join(meta_parts)

        meta_lbl = QLabel(meta_str)
        meta_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        info_col.addWidget(meta_lbl)

        layout.addLayout(info_col, 1)

    def set_checked(self, checked: bool) -> None:
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(checked)
        self.checkbox.blockSignals(False)

    def is_checked(self) -> bool:
        return self.checkbox.isChecked()


class ScopeRangeBarWidget(QWidget):
    """Barre visuelle interactive représentant l'étendue du document et la plage utile demandée."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(24)
        self._start = 1
        self._end = 1
        self._total = 1

    def set_range(self, start: int, end: int, total: int) -> None:
        self._start = max(1, start)
        self._end = max(self._start, min(end, total))
        self._total = max(1, total)
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        r = 4

        # Track fond (pages non sélectionnées)
        painter.setBrush(QBrush(QColor(DesignTokens.BG_INPUT)))
        painter.setPen(QPen(QColor(DesignTokens.BORDER_COLOR), 1))
        painter.drawRoundedRect(0, 2, w, h - 4, r, r)

        # Plage active
        total = max(1, self._total)
        start_ratio = (self._start - 1) / total
        end_ratio = self._end / total
        x_start = int(start_ratio * w)
        x_end = int(end_ratio * w)
        active_w = max(4, x_end - x_start)

        painter.setBrush(QBrush(QColor(DesignTokens.ACCENT_PRIMARY)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(x_start, 2, active_w, h - 4, r, r)

        # Texte centré
        painter.setPen(QPen(QColor("white")))
        font = QFont(DesignTokens.FONT_MAIN, 9)
        font.setBold(True)
        painter.setFont(font)
        text = f"Portée : Pages {self._start} à {self._end} ({self._end - self._start + 1} / {self._total} pages)"
        painter.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, text)
        painter.end()


class DocumentPreviewWidget(QWidget):
    """
    Visionneuse de document intégrée et synchronisée :
    Affiche directement le document tel que lisible en dehors de l'application :
    - PDF natif multipages avec navigation et zoom (via QPdfView)
    - Markdown enrichi et stylisé (via QTextBrowser avec feuille de style sombre et ancres de pagination)
    - Planches haute résolution pour les albums et documents d'images.
    """

    def __init__(self, doc: DocumentModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.doc = doc
        file_type = (getattr(self.doc, "file_type", "") or "").lower()
        if not file_type and getattr(self.doc, "title", "").lower().endswith(".pdf"):
            file_type = "pdf"
        self._is_paginated = file_type in ("pdf", "album")
        self._current_page = 1
        self._total_pages = int(doc.total_pages or 1)
        self._current_mode = "markdown"
        self._scope_start: int = 1
        self._scope_end: int = self._total_pages
        self._included_pages: set[int] = set(range(1, self._total_pages + 1))
        self._heading_highlight_timer = QTimer(self)
        self._heading_highlight_timer.setSingleShot(True)
        self._heading_highlight_timer.timeout.connect(self._clear_heading_highlight)

        self._setup_ui()
        self._load_document()

    def _setup_ui(self) -> None:
        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # Conteneur Carte
        self.card = QFrame()
        self.card.setObjectName("previewCard")
        self.card.setStyleSheet(f"""
            QFrame#previewCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius:  {DesignTokens.RADIUS_MD}px;
            }}
        """)
        inner_layout = QVBoxLayout(self.card)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(0)

        # --- Barre d'outils / En-tête ---
        self.header_frame = QFrame()
        self.header_frame.setObjectName("previewHeader")
        self.header_frame.setStyleSheet(f"""
            QFrame#previewHeader {{
                background-color: {DesignTokens.BG_INPUT};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-top-left-radius: {DesignTokens.RADIUS_MD}px;
                border-top-right-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(10, 6, 10, 6)
        header_layout.setSpacing(8)

        # Titre et badge type
        self.lbl_title = QLabel("Aperçu")
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 12px; border: none; background: transparent;")
        header_layout.addWidget(self.lbl_title)

        self.badge_type = QLabel("PDF")
        self.badge_type.setStyleSheet(
            f"background-color: {DesignTokens.BG_ACTIVE}; color: {DesignTokens.ACCENT_PRIMARY}; "
            f"border: 1px solid {DesignTokens.ACCENT_PRIMARY}; border-radius: 4px; padding: 2px 6px; "
            "font-weight: bold; font-size: 10px;"
        )
        header_layout.addWidget(self.badge_type)

        # Toggle Vue (si PDF et Markdown tous deux disponibles)
        self.toggle_group = QButtonGroup(self)
        self.btn_toggle_pdf = QPushButton("Vue PDF")
        self.btn_toggle_pdf.setCheckable(True)
        self.btn_toggle_pdf.setFixedHeight(26)
        self.btn_toggle_pdf.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {DesignTokens.TEXT_MUTED};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            }}
            QPushButton:checked {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                color: white;
                border-color: {DesignTokens.ACCENT_PRIMARY};
                font-weight: bold;
            }}
        """)
        self.btn_toggle_md = QPushButton("Vue Markdown")
        self.btn_toggle_md.setCheckable(True)
        self.btn_toggle_md.setFixedHeight(26)
        self.btn_toggle_md.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {DesignTokens.TEXT_MUTED};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            }}
            QPushButton:checked {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                color: white;
                border-color: {DesignTokens.ACCENT_PRIMARY};
                font-weight: bold;
            }}
        """)
        self.toggle_group.addButton(self.btn_toggle_pdf)
        self.toggle_group.addButton(self.btn_toggle_md)
        self.btn_toggle_pdf.clicked.connect(lambda: self._set_mode("pdf"))
        self.btn_toggle_md.clicked.connect(lambda: self._set_mode("markdown"))

        header_layout.addSpacing(6)
        header_layout.addWidget(self.btn_toggle_pdf)
        header_layout.addWidget(self.btn_toggle_md)
        header_layout.addStretch()

        # Indicateur visuel d'inclusion dans la portée
        self.lbl_scope_status = QLabel("")
        self.lbl_scope_status.hide()
        header_layout.addWidget(self.lbl_scope_status)
        header_layout.addSpacing(8)

        # Contrôles de navigation de page
        self.btn_prev_page = QPushButton()
        self.btn_prev_page.setIcon(load_phosphor_icon("ph.caret-left", color=DesignTokens.TEXT_PRIMARY))
        self.btn_prev_page.setFixedSize(26, 26)
        self.btn_prev_page.setToolTip("Page précédente")
        self.btn_prev_page.clicked.connect(self._on_prev_page)
        self.btn_prev_page.setStyleSheet(f"border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; background: {DesignTokens.BG_INPUT};")

        self.lbl_page = QLabel(f"Page {self._current_page} / {self._total_pages}")
        self.lbl_page.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: 500; border: none; background: transparent;")

        self.btn_next_page = QPushButton()
        self.btn_next_page.setIcon(load_phosphor_icon("ph.caret-right", color=DesignTokens.TEXT_PRIMARY))
        self.btn_next_page.setFixedSize(26, 26)
        self.btn_next_page.setToolTip("Page suivante")
        self.btn_next_page.clicked.connect(self._on_next_page)
        self.btn_next_page.setStyleSheet(f"border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; background: {DesignTokens.BG_INPUT};")

        header_layout.addWidget(self.btn_prev_page)
        header_layout.addWidget(self.lbl_page)
        header_layout.addWidget(self.btn_next_page)

        header_layout.addSpacing(10)

        # Contrôles de Zoom (pour PDF / Image)
        self.btn_zoom_out = QPushButton()
        self.btn_zoom_out.setIcon(load_phosphor_icon("ph.magnifying-glass-minus", color=DesignTokens.TEXT_PRIMARY))
        self.btn_zoom_out.setFixedSize(26, 26)
        self.btn_zoom_out.setToolTip("Zoom arrière")
        self.btn_zoom_out.clicked.connect(self._zoom_out)
        self.btn_zoom_out.setStyleSheet(f"border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; background: {DesignTokens.BG_INPUT};")

        self.btn_zoom_fit = QPushButton("Ajuster")
        self.btn_zoom_fit.setFixedHeight(26)
        self.btn_zoom_fit.setToolTip("Ajuster à la largeur")
        self.btn_zoom_fit.clicked.connect(self._zoom_fit)
        self.btn_zoom_fit.setStyleSheet(
            f"border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; padding: 2px 8px; font-size: 10px; background: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_PRIMARY};"
        )

        self.btn_zoom_in = QPushButton()
        self.btn_zoom_in.setIcon(load_phosphor_icon("ph.magnifying-glass-plus", color=DesignTokens.TEXT_PRIMARY))
        self.btn_zoom_in.setFixedSize(26, 26)
        self.btn_zoom_in.setToolTip("Zoom avant")
        self.btn_zoom_in.clicked.connect(self._zoom_in)
        self.btn_zoom_in.setStyleSheet(f"border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; background: {DesignTokens.BG_INPUT};")

        header_layout.addWidget(self.btn_zoom_out)
        header_layout.addWidget(self.btn_zoom_fit)
        header_layout.addWidget(self.btn_zoom_in)

        inner_layout.addWidget(self.header_frame)

        # --- Stack de visualisation ---
        self.view_stack = QStackedWidget()

        # 1. Vue PDF
        if HAVE_QTPDF:
            self.pdf_document = QPdfDocument(self)
            self.pdf_viewer = QPdfView()
            self.pdf_viewer.setDocument(self.pdf_document)
            self.pdf_viewer.setPageMode(QPdfView.PageMode.MultiPage)
            self.pdf_viewer.setZoomMode(QPdfView.ZoomMode.FitToWidth)
            self.pdf_viewer.setStyleSheet("border: none; background-color: #1e1e2e;")
            self.pdf_viewer.pageNavigator().currentPageChanged.connect(self._on_pdf_page_changed)
            self.view_stack.addWidget(self.pdf_viewer)
        else:
            self.pdf_viewer = None
            lbl_no_pdf = QLabel("Module PDF non disponible.")
            lbl_no_pdf.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.view_stack.addWidget(lbl_no_pdf)

        # 2. Vue Markdown stylisé
        self.markdown_viewer = QTextBrowser()
        self.markdown_viewer.setOpenExternalLinks(True)
        self.markdown_viewer.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: none;
                padding: 16px 20px;
                font-family: '{DesignTokens.FONT_MAIN}', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                font-size: 13px;
                line-height: 1.6;
            }}
        """)
        self.view_stack.addWidget(self.markdown_viewer)

        # 3. Vue Image / Planches (Album)
        self.image_scroll = QScrollArea()
        self.image_scroll.setWidgetResizable(True)
        self.image_scroll.setStyleSheet("border: none; background-color: #0f172a;")
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_scroll.setWidget(self.image_label)
        self.view_stack.addWidget(self.image_scroll)

        inner_layout.addWidget(self.view_stack, 1)
        card_layout.addWidget(self.card)

    def _load_document(self) -> None:
        file_type = (getattr(self.doc, "file_type", "") or "").lower()
        has_pdf = False
        pdf_path: Path | None = None

        if getattr(self.doc, "original_media", None):
            try:
                cand_path = resolve_media_path(self.doc.original_media.filename)
                if cand_path.exists():
                    pdf_path = cand_path
            except Exception as e:
                logger.debug("Resolution media path error: %s", e)

        if not pdf_path and getattr(self.doc, "source_url", None):
            try:
                cand_path = Path(self.doc.source_url)
                if cand_path.exists():
                    pdf_path = cand_path
            except Exception as err:
                logger.debug("Résolution du chemin source_url ignorée : %s", err)

        if not pdf_path and getattr(self.doc, "file_path", None):
            try:
                cand_path = Path(self.doc.file_path)
                if cand_path.exists():
                    pdf_path = cand_path
            except Exception as err:
                logger.debug("Résolution du chemin file_path ignorée : %s", err)

        if file_type == "pdf" and pdf_path and HAVE_QTPDF and self.pdf_viewer:
            try:
                self.pdf_document.load(str(pdf_path))
                self._total_pages = max(1, self.pdf_document.pageCount())
                has_pdf = True
            except Exception as e:
                logger.debug("Failed to load PDF file: %s", e)

        # Rendu du Markdown stylisé
        raw_md = getattr(self.doc, "content", "") or ""
        html_content = self._render_stylized_markdown(raw_md)
        self.markdown_viewer.setHtml(html_content)

        # Détermination du mode initial
        if file_type == "album":
            self.badge_type.setText("Album")
            self.btn_toggle_pdf.hide()
            self.btn_toggle_md.hide()
            self._set_mode("album")
        elif has_pdf:
            self.badge_type.setText("PDF")
            self.btn_toggle_pdf.show()
            self.btn_toggle_md.show()
            self.btn_toggle_pdf.setChecked(True)
            self._set_mode("pdf")
        else:
            self.badge_type.setText("Markdown" if file_type in ("md", "markdown") else file_type.upper() or "Texte")
            self.btn_toggle_pdf.hide()
            self.btn_toggle_md.hide()
            self._set_mode("markdown")

        self._update_page_label()

    def _render_stylized_markdown(self, raw_md: str) -> str:
        def _replace_page_tag(match: re.Match[str]) -> str:
            p_num = match.group(1)
            return (
                f'<div id="page-{p_num}" style="margin: 28px 0 14px 0; border-top: 2px dashed #475569; padding-top: 6px;">'
                f'<a name="page-{p_num}"></a>'
                f'<span style="background-color: #312e81; color: #c7d2fe; font-size: 11px; font-weight: bold; '
                f'padding: 3px 10px; border-radius:  12px; border: 1px solid #4338ca;">Page {p_num}</span>'
                f"</div>"
            )

        processed_md = re.sub(r"<!--\s*PAGE:\s*(\d+)\s*-->", _replace_page_tag, raw_md)
        body_html = markdown.markdown(processed_md, extensions=["fenced_code", "tables"])

        return f"""
        <html>
        <head>
        <style>
            body {{
                color: #f1f5f9;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                font-size: 13px;
                line-height: 1.6;
                padding: 12px;
            }}
            h1, h2, h3, h4 {{
                color: #ffffff;
                font-weight: 600;
                margin-top: 18px;
                margin-bottom: 8px;
            }}
            h1 {{
                font-size: 18px;
                color: #818cf8;
                border-bottom: 1px solid #334155;
                padding-bottom: 4px;
            }}
            h2 {{
                font-size: 15px;
                color: #93c5fd;
                border-bottom: 1px solid #1e293b;
                padding-bottom: 3px;
            }}
            h3 {{
                font-size: 13px;
                color: #cbd5e1;
            }}
            p {{
                margin-bottom: 10px;
            }}
            code {{
                background-color: #1e293b;
                color: #a5b4fc;
                padding: 2px 4px;
                border-radius: 4px;
                font-family: Menlo, Monaco, monospace;
                font-size: 12px;
            }}
            pre {{
                background-color: #1e293b;
                padding: 10px;
                border-radius:  6px;
                border: 1px solid #334155;
            }}
            blockquote {{
                border-left: 3px solid #6366f1;
                margin: 10px 0;
                padding-left: 10px;
                color: #94a3b8;
                background-color: rgba(99, 102, 241, 0.05);
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 12px 0;
            }}
            th, td {{
                border: 1px solid #334155;
                padding: 6px 8px;
                text-align: left;
            }}
            th {{
                background-color: #1e293b;
                font-weight: 600;
            }}
        </style>
        </head>
        <body>
        {body_html}
        </body>
        </html>
        """

    def _set_mode(self, mode: str) -> None:
        self._current_mode = mode
        if mode == "pdf" and HAVE_QTPDF and self.pdf_viewer:
            self.view_stack.setCurrentIndex(0)
            self.btn_zoom_out.show()
            self.btn_zoom_fit.show()
            self.btn_zoom_in.show()
        elif mode == "album":
            self.view_stack.setCurrentIndex(2)
            self.btn_zoom_out.show()
            self.btn_zoom_fit.show()
            self.btn_zoom_in.show()
            self._load_album_page(self._current_page)
        else:
            self.view_stack.setCurrentIndex(1)
            self.btn_zoom_out.hide()
            self.btn_zoom_fit.hide()
            self.btn_zoom_in.hide()
        self._update_page_label()

    def jump_to_page(self, page_number: int) -> None:
        """Navigue directement vers la page demandée."""
        self._current_page = max(1, min(page_number, self._total_pages))
        self._update_page_label()

        if self._current_mode == "pdf" and HAVE_QTPDF and self.pdf_viewer:
            self.pdf_viewer.pageNavigator().jump(self._current_page - 1, QPointF(0, 0), self.pdf_viewer.zoomFactor())
        elif self._current_mode == "album":
            self._load_album_page(self._current_page)
        elif self._current_mode == "markdown":
            self.markdown_viewer.scrollToAnchor(f"page-{self._current_page}")

    def jump_to_heading(self, heading_text: str, page_number: int | None = None) -> None:
        """Navigue vers un titre ou sa page associée."""
        if self._is_paginated and page_number is not None:
            self.jump_to_page(page_number)

        if self._current_mode == "markdown":
            if self._is_paginated and page_number is not None:
                self.markdown_viewer.scrollToAnchor(f"page-{page_number}")
            else:
                self._highlight_heading(heading_text)

    def _highlight_heading(self, heading_text: str) -> None:
        """Surligne temporairement le titre ciblé dans l'aperçu Markdown."""
        cursor = self.markdown_viewer.document().find(heading_text)
        if cursor.isNull():
            return
        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format.setBackground(QColor(DesignTokens.BG_ACTIVE))
        selection.format.setForeground(QColor(DesignTokens.TEXT_PRIMARY))
        self.markdown_viewer.setExtraSelections([selection])
        self.markdown_viewer.setTextCursor(cursor)
        self._heading_highlight_timer.start(2000)

    def _clear_heading_highlight(self) -> None:
        self.markdown_viewer.setExtraSelections([])

    def _on_pdf_page_changed(self, page_idx: int) -> None:
        self._current_page = page_idx + 1
        self._update_page_label()

    def _on_prev_page(self) -> None:
        if self._current_page > 1:
            self.jump_to_page(self._current_page - 1)

    def _on_next_page(self) -> None:
        if self._current_page < self._total_pages:
            self.jump_to_page(self._current_page + 1)

    def _zoom_in(self) -> None:
        if self._current_mode == "pdf" and HAVE_QTPDF and self.pdf_viewer:
            self.pdf_viewer.setZoomFactor(self.pdf_viewer.zoomFactor() * 1.2)

    def _zoom_out(self) -> None:
        if self._current_mode == "pdf" and HAVE_QTPDF and self.pdf_viewer:
            self.pdf_viewer.setZoomFactor(max(0.2, self.pdf_viewer.zoomFactor() / 1.2))

    def _zoom_fit(self) -> None:
        if self._current_mode == "pdf" and HAVE_QTPDF and self.pdf_viewer:
            self.pdf_viewer.setZoomMode(QPdfView.ZoomMode.FitToWidth)

    def set_scope_range(self, start_page: int, end_page: int, included_pages: set[int] | None = None) -> None:
        """Définit les bornes de la portée demandée et les pages incluses pour mettre à jour l'indicateur visuel."""
        self._scope_start = max(1, start_page)
        self._scope_end = max(self._scope_start, end_page)
        if included_pages is not None:
            self._included_pages = set(included_pages)
        else:
            self._included_pages = set(range(self._scope_start, self._scope_end + 1))
        self._update_scope_badge()

    def set_active_scope(self, start_page: int, end_page: int, included_pages: set[int] | None = None) -> None:
        """Alias pour set_scope_range avec support explicite des pages incluses."""
        self.set_scope_range(start_page, end_page, included_pages=included_pages)

    def _update_scope_badge(self) -> None:
        if not hasattr(self, "lbl_scope_status"):
            return
        if not self._is_paginated:
            self.lbl_scope_status.hide()
            return
        is_included = (self._current_page in self._included_pages) if self._included_pages else (self._scope_start <= self._current_page <= self._scope_end)
        if is_included:
            self.lbl_scope_status.setText(f"Page {self._current_page} INCLUSE (portée {self._scope_start}–{self._scope_end})")
            self.lbl_scope_status.setStyleSheet(
                f"background-color: {DesignTokens.COLOR_GREEN_BG}; color: {DesignTokens.COLOR_GREEN_TEXT}; border: 1px solid {DesignTokens.COLOR_GREEN_BORDER};"
                f" border-radius: 4px; padding: 2px 6px; font-size: 10px; font-weight: bold;"
            )
        else:
            self.lbl_scope_status.setText(f"Page {self._current_page} EXCLUE (portée {self._scope_start}–{self._scope_end})")
            self.lbl_scope_status.setStyleSheet(
                f"background-color: {DesignTokens.COLOR_RED_BG}; color: {DesignTokens.COLOR_RED_TEXT}; border: 1px solid {DesignTokens.COLOR_RED_BORDER};"
                f" border-radius: 4px; padding: 2px 6px; font-size: 10px; font-weight: bold;"
            )
        self.lbl_scope_status.show()

    def _update_page_label(self) -> None:
        if self._is_paginated:
            self.lbl_page.show()
            self.btn_prev_page.show()
            self.btn_next_page.show()
            self.lbl_page.setText(f"Page {self._current_page} / {self._total_pages}")
            self.btn_prev_page.setEnabled(self._current_page > 1)
            self.btn_next_page.setEnabled(self._current_page < self._total_pages)
            self._update_scope_badge()
        else:
            self.lbl_page.hide()
            self.btn_prev_page.hide()
            self.btn_next_page.hide()
            if hasattr(self, "lbl_scope_status"):
                self.lbl_scope_status.hide()

    def _load_album_page(self, page_num: int) -> None:
        page_rec = (
            DocumentPageModel.select()
            .where(
                DocumentPageModel.document == self.doc,
                DocumentPageModel.page_number == page_num,
            )
            .first()
        )
        if page_rec and page_rec.media:
            img_path = resolve_media_path(page_rec.media.filename)
            if img_path.exists():
                pix = QPixmap(str(img_path))
                self.image_label.setPixmap(pix.scaledToWidth(700, Qt.TransformationMode.SmoothTransformation))


class DocumentDelimitationDialog(QDialog):
    """
    Dialogue interactif de délimitation de documents :
    Permet de sélectionner des plages de pages utiles, de filtrer les sections
    et d'exclure les parties non pédagogiques (sommaires, remerciements, bibliographies).
    Sauvegarde durablement les bornes et exclut le bruit de la couverture et du RAG.
    """

    def __init__(self, doc: DocumentModel, context: str = "global", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if getattr(doc, "id", None):
            try:
                doc = DocumentModel.get_by_id(doc.id)
            except Exception as err:
                logger.debug("Rechargement du document de délimitation ignoré : %s", err)
        self.doc = doc
        self.context = context
        self._chunk_cards: dict[int, int] = {}
        self._page_cards: dict[int, int] = {}
        self._hash_cards: dict[str, int] = {}
        self._heading_page_cards: dict[tuple[str | None, int | None], int] = {}
        self._section_meta: dict[int, dict[str, Any]] = {}
        self._syncing_selection: bool = False

        self._manual_exclusions: set[str] = set()
        raw_excl = getattr(self.doc, "excluded_headings", None)
        if raw_excl:
            try:
                parsed = json.loads(raw_excl)
                if isinstance(parsed, list):
                    self._manual_exclusions = {str(x).lower().strip() for x in parsed if str(x).strip()}
            except Exception:
                self._manual_exclusions = set()

        self._load_document_stats()

        # Détection de pagination : physique uniquement pour les PDF et Albums
        file_type = (getattr(self.doc, "file_type", "") or "").lower()
        if not file_type and getattr(self.doc, "title", "").lower().endswith(".pdf"):
            file_type = "pdf"
        self.is_paginated = file_type in ("pdf", "album")
        self.selection_mode = "pages" if self.is_paginated else "chapters"

        # 1. Extraction universelle des fragments et calcul du nombre total de pages
        pages_query = list(DocumentPageModel.select().where(DocumentPageModel.document == doc).order_by(DocumentPageModel.page_number))
        if doc.file_type == "album" or pages_query:
            self._all_chunks = [
                {
                    "index": p.page_number - 1,
                    "page_number": p.page_number,
                    "heading_path": f"Planche {p.page_number}",
                    "content": p.ocr_text or f"Planche {p.page_number}",
                    "content_hash": ChunkingService.hash_content(p.ocr_text or f"Planche {p.page_number}"),
                }
                for p in pages_query
            ]
            self._max_page = max([int(p.page_number) for p in pages_query], default=int(doc.total_pages or 1))
        else:
            self._all_chunks = ChunkingService.extract_chunks(doc.content or "", file_type=doc.file_type or "md", strategy=ChunkingService.preferred_strategy(doc.file_type))
            if not self._all_chunks and getattr(doc, "id", None):
                existing_recs = list(DocumentChunkModel.select().where(DocumentChunkModel.document == self.doc).order_by(DocumentChunkModel.chunk_index))
                self._all_chunks = [
                    {
                        "index": c.chunk_index,
                        "heading_path": c.heading_path,
                        "page_number": c.page_number,
                        "content": c.content,
                        "content_hash": c.content_hash,
                    }
                    for c in existing_recs
                ]
            page_numbers = [int(p) for p in (chunk.get("page_number") for chunk in self._all_chunks) if p is not None and isinstance(p, int | float | str)]
            self._max_page = max(page_numbers, default=int(doc.total_pages or 1))
            if doc.total_pages and doc.total_pages > self._max_page:
                self._max_page = int(doc.total_pages)

        self._chapter_cards: list[ChapterCardWidget] = []
        self._tree_nodes: list[HeadingTreeNode] = []

        win_title = f"Découpage & Délimitation pour génération par lots — {doc.title}" if self.context == "batch" else f"Délimitation & Assainissement global — {doc.title}"
        self.setWindowTitle(win_title)
        self.resize(1280, 780)
        self.setMinimumSize(960, 600)
        check_icon_path = str(get_resource_path("src", "ressources", "icons", "check_white.svg")).replace("\\", "/")
        dash_icon_path = str(get_resource_path("src", "ressources", "icons", "dash_white.svg")).replace("\\", "/")
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QFrame#headerCard, QFrame#pagesCard, QFrame#sectionsCard, QFrame#allCard, QFrame#chaptersCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius:  {DesignTokens.RADIUS_MD}px;
            }}
            QSplitter::handle:horizontal {{
                background-color: {DesignTokens.BORDER_COLOR};
                width: 3px;
                border-radius:  1px;
            }}
            QSplitter::handle:horizontal:hover {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
            QCheckBox {{
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 11px;
                spacing: 8px;
                border: none;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {DesignTokens.TEXT_MUTED};
                border-radius: 4px;
                background-color: {DesignTokens.BG_INPUT};
            }}
            QCheckBox::indicator:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QCheckBox::indicator:checked {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-color: {DesignTokens.ACCENT_PRIMARY};
                image: url({check_icon_path});
            }}
            QCheckBox::indicator:indeterminate {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-color: {DesignTokens.ACCENT_PRIMARY};
                image: url({dash_icon_path});
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Panneau gauche : configuration de la délimitation
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # 1. En-tête descriptif
        header_card = QFrame()
        header_card.setObjectName("headerCard")
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(10, 8, 10, 8)
        h_layout.setSpacing(4)

        header_top = QHBoxLayout()
        header_top.setSpacing(8)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.scissors", color=DesignTokens.COLOR_YELLOW).pixmap(20, 20))
        title_lbl = QLabel(f"Délimitation globale : <b>{doc.title}</b>")
        title_lbl.setStyleSheet(f"font-size: 14px; color: {DesignTokens.TEXT_PRIMARY}; border: none;")
        header_top.addWidget(icon_lbl)
        header_top.addWidget(title_lbl)

        badge_global = QLabel("DÉLIMITATION GLOBALE (STRUCTURE DU DOCUMENT)")
        badge_global.setStyleSheet(
            f"background-color: {DesignTokens.COLOR_YELLOW_BG}; color: {DesignTokens.COLOR_YELLOW_TEXT}; border: 1px solid {DesignTokens.COLOR_YELLOW_BORDER};"
            f" border-radius: 4px; padding: 2px 8px; font-size: 10px; font-weight: bold;"
        )
        header_top.addWidget(badge_global)
        header_top.addStretch()
        h_layout.addLayout(header_top)

        desc_lbl = QLabel(
            "Éliminez définitivement les parties non pertinentes (pages blanches, répétitions, sommaires, préfaces). "
            "Cette délimitation assainit durablement la structure du document dans la bibliothèque et réindexe le moteur de recherche IA (RAG)."
        )
        desc_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none;")
        desc_lbl.setWordWrap(True)
        h_layout.addWidget(desc_lbl)
        left_layout.addWidget(header_card)

        self.left_layout = left_layout

        # Sélecteur de mode de portée (persistant en haut du panneau gauche)
        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(6)
        mode_btn_style = f"""
            QPushButton {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_SECONDARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 500;
            }}
            QPushButton:checked {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                color: white;
                border-color: {DesignTokens.ACCENT_PRIMARY};
                font-weight: bold;
            }}
            QPushButton:hover:!checked {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """
        self.btn_scope_mode_all = QPushButton("Tout le document")
        self.btn_scope_mode_all.setIcon(load_phosphor_icon("ph.files", color=DesignTokens.TEXT_PRIMARY))
        self.btn_scope_mode_all.setCheckable(True)
        self.btn_scope_mode_all.setStyleSheet(mode_btn_style)

        self.btn_scope_mode_range = QPushButton("Plage de pages")
        self.btn_scope_mode_range.setIcon(load_phosphor_icon("ph.frame-corners", color=DesignTokens.TEXT_PRIMARY))
        self.btn_scope_mode_range.setCheckable(True)
        self.btn_scope_mode_range.setStyleSheet(mode_btn_style)

        self.btn_scope_mode_structure = QPushButton("Par Chapitres")
        self.btn_scope_mode_structure.setIcon(load_phosphor_icon("ph.tree-structure", color=DesignTokens.TEXT_PRIMARY))
        self.btn_scope_mode_structure.setCheckable(True)
        self.btn_scope_mode_structure.setStyleSheet(mode_btn_style)

        self.btn_scope_mode_sections = QPushButton("Par Sections")
        self.btn_scope_mode_sections.setIcon(load_phosphor_icon("ph.list-dashes", color=DesignTokens.TEXT_PRIMARY))
        self.btn_scope_mode_sections.setCheckable(True)
        self.btn_scope_mode_sections.setStyleSheet(mode_btn_style)

        self.scope_mode_group = QButtonGroup(self)
        self.scope_mode_group.addButton(self.btn_scope_mode_all)
        self.scope_mode_group.addButton(self.btn_scope_mode_range)
        self.scope_mode_group.addButton(self.btn_scope_mode_structure)
        self.scope_mode_group.addButton(self.btn_scope_mode_sections)
        self.btn_scope_mode_all.clicked.connect(self._on_mode_all_clicked)
        self.btn_scope_mode_range.clicked.connect(self._on_mode_range_clicked)
        self.btn_scope_mode_structure.clicked.connect(self._on_mode_structure_clicked)
        self.btn_scope_mode_sections.clicked.connect(self._on_mode_sections_clicked)

        mode_row.addWidget(self.btn_scope_mode_all)
        mode_row.addWidget(self.btn_scope_mode_range)
        mode_row.addWidget(self.btn_scope_mode_structure)
        mode_row.addWidget(self.btn_scope_mode_sections)
        lbl_max_info = QLabel(f"(Total : {self._max_page} pages)")
        lbl_max_info.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none;")
        mode_row.addWidget(lbl_max_info)
        mode_row.addStretch()

        self.mode_card = QFrame()
        self.mode_card.setObjectName("pagesCard")
        mode_card_layout = QVBoxLayout(self.mode_card)
        mode_card_layout.setContentsMargins(10, 8, 10, 8)
        mode_card_layout.setSpacing(0)
        mode_card_layout.addLayout(mode_row)
        left_layout.addWidget(self.mode_card)

        # 2. Carte Mode Pages (Plage de pages & barre visuelle)
        self.pages_card = QFrame()
        self.pages_card.setObjectName("pagesCard")
        pages_card_layout = QVBoxLayout(self.pages_card)
        pages_card_layout.setContentsMargins(12, 10, 12, 10)
        pages_card_layout.setSpacing(8)

        lbl_sec1 = QLabel("1. BORNES DE PAGINATION UTILE")
        lbl_sec1.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: bold; font-size: 10px; letter-spacing: 0.5px; border: none;")
        pages_card_layout.addWidget(lbl_sec1)

        self.range_bar = ScopeRangeBarWidget(self)
        pages_card_layout.addWidget(self.range_bar)

        # Conteneur des curseurs (slider) et spinboxes — Visible UNIQUEMENT en mode Plage de pages
        self.slider_scope_container = QWidget()
        slider_scope_layout = QVBoxLayout(self.slider_scope_container)
        slider_scope_layout.setContentsMargins(0, 4, 0, 0)
        slider_scope_layout.setSpacing(6)

        start_val = doc.start_page if (doc.start_page and doc.start_page > 0) else 1
        end_val = doc.end_page if (doc.end_page and doc.end_page >= start_val) else self._max_page

        # Ligne début : SpinBox + Slider début
        start_row = QHBoxLayout()
        start_row.setContentsMargins(0, 0, 0, 0)
        start_row.setSpacing(8)
        lbl_p_start = QLabel("Début :")
        lbl_p_start.setFixedWidth(44)
        lbl_p_start.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; border: none;")
        self.spin_p_start = QSpinBox()
        self.spin_p_start.setRange(1, self._max_page)
        self.spin_p_start.setValue(min(start_val, self._max_page))
        self.spin_p_start.setStyleSheet(f"""
            QSpinBox {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 2px 4px;
                min-width: 50px;
                font-size: 11px;
            }}
        """)
        self.slider_p_start = QSlider(Qt.Orientation.Horizontal)
        self.slider_p_start.setRange(1, self._max_page)
        self.slider_p_start.setValue(self.spin_p_start.value())
        self.slider_p_start.valueChanged.connect(self._on_slider_start_changed)

        start_row.addWidget(lbl_p_start)
        start_row.addWidget(self.spin_p_start)
        start_row.addWidget(self.slider_p_start, 1)
        slider_scope_layout.addLayout(start_row)

        # Ligne fin : SpinBox + Slider fin
        end_row = QHBoxLayout()
        end_row.setContentsMargins(0, 0, 0, 0)
        end_row.setSpacing(8)
        lbl_p_end = QLabel("Fin :")
        lbl_p_end.setFixedWidth(44)
        lbl_p_end.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; border: none;")
        self.spin_p_end = QSpinBox()
        self.spin_p_end.setRange(1, self._max_page)
        self.spin_p_end.setValue(min(end_val, self._max_page))
        self.spin_p_end.setStyleSheet(f"""
            QSpinBox {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 2px 4px;
                min-width: 50px;
                font-size: 11px;
            }}
        """)
        self.slider_p_end = QSlider(Qt.Orientation.Horizontal)
        self.slider_p_end.setRange(1, self._max_page)
        self.slider_p_end.setValue(self.spin_p_end.value())
        self.slider_p_end.valueChanged.connect(self._on_slider_end_changed)

        end_row.addWidget(lbl_p_end)
        end_row.addWidget(self.spin_p_end)
        end_row.addWidget(self.slider_p_end, 1)
        slider_scope_layout.addLayout(end_row)

        pages_card_layout.addWidget(self.slider_scope_container)

        # Préréglages rapides de pagination
        self.range_presets_container = QWidget()
        presets_layout = QHBoxLayout(self.range_presets_container)
        presets_layout.setContentsMargins(0, 2, 0, 2)
        presets_layout.setSpacing(6)
        lbl_presets = QLabel("Préréglages :")
        lbl_presets.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none;")
        presets_layout.addWidget(lbl_presets)

        preset_btn_style = f"""
            QPushButton {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_SECONDARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """
        btn_preset_all = QPushButton("100% (Tout)")
        btn_preset_all.setStyleSheet(preset_btn_style)
        btn_preset_all.clicked.connect(lambda: self._apply_page_preset(1, self._max_page))
        btn_preset_h1 = QPushButton("1ère moitié")
        btn_preset_h1.setStyleSheet(preset_btn_style)
        btn_preset_h1.clicked.connect(lambda: self._apply_page_preset(1, max(1, self._max_page // 2)))
        btn_preset_h2 = QPushButton("2ème moitié")
        btn_preset_h2.setStyleSheet(preset_btn_style)
        btn_preset_h2.clicked.connect(lambda: self._apply_page_preset(min(self._max_page, self._max_page // 2 + 1), self._max_page))
        btn_preset_10 = QPushButton("10 premières p.")
        btn_preset_10.setStyleSheet(preset_btn_style)
        btn_preset_10.clicked.connect(lambda: self._apply_page_preset(1, min(10, self._max_page)))

        presets_layout.addWidget(btn_preset_all)
        presets_layout.addWidget(btn_preset_h1)
        presets_layout.addWidget(btn_preset_h2)
        presets_layout.addWidget(btn_preset_10)
        presets_layout.addStretch()
        pages_card_layout.addWidget(self.range_presets_container)

        # Récapitulatif d'impact et de couverture de pagination
        self.range_info_card = QFrame()
        self.range_info_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius:  {DesignTokens.RADIUS_SM}px;
            }}
        """)
        ric_layout = QVBoxLayout(self.range_info_card)
        ric_layout.setContentsMargins(10, 8, 10, 8)
        ric_layout.setSpacing(4)
        lbl_ric_title = QLabel("RÉCAPITULATIF DE LA PLAGE SÉLECTIONNÉE")
        lbl_ric_title.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: bold; font-size: 10px; letter-spacing: 0.5px; border: none;")
        ric_layout.addWidget(lbl_ric_title)
        self.lbl_range_coverage_kpi = QLabel("")
        self.lbl_range_coverage_kpi.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: bold; border: none;")
        ric_layout.addWidget(self.lbl_range_coverage_kpi)
        self.lbl_range_words_kpi = QLabel("")
        self.lbl_range_words_kpi.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none;")
        ric_layout.addWidget(self.lbl_range_words_kpi)
        self.lbl_range_chapters_kpi = QLabel("")
        self.lbl_range_chapters_kpi.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; font-size: 11px; border: none;")
        self.lbl_range_chapters_kpi.setWordWrap(True)
        ric_layout.addWidget(self.lbl_range_chapters_kpi)
        pages_card_layout.addWidget(self.range_info_card)

        self.range_bar.set_range(self.spin_p_start.value(), self.spin_p_end.value(), self._max_page)
        self.lbl_page_impact = QLabel()
        self.lbl_page_impact.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        pages_card_layout.addWidget(self.lbl_page_impact)

        # 3. Mode All: Carte récapitulative complète
        self.all_card = QFrame()
        self.all_card.setObjectName("allCard")
        all_layout = QVBoxLayout(self.all_card)
        all_layout.setContentsMargins(14, 14, 14, 14)
        all_layout.setSpacing(12)

        hero_banner = QFrame()
        hero_banner.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(34, 197, 94, 0.08);
                border: 1px solid rgba(34, 197, 94, 0.25);
                border-radius:  {DesignTokens.RADIUS_SM}px;
            }}
        """)
        hero_layout = QHBoxLayout(hero_banner)
        hero_layout.setContentsMargins(10, 8, 10, 8)
        hero_layout.setSpacing(10)
        hero_icon = QLabel()
        hero_icon.setPixmap(load_phosphor_icon("ph.check-circle", color=DesignTokens.COLOR_GREEN).pixmap(24, 24))
        hero_layout.addWidget(hero_icon)
        hero_text_col = QVBoxLayout()
        hero_text_col.setSpacing(2)
        hero_title = QLabel("Document intégralement sélectionné")
        hero_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        hero_subtitle = QLabel("Toutes les pages utiles et sections du document sont actives pour l'analyse et la génération.")
        hero_subtitle.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        hero_text_col.addWidget(hero_title)
        hero_text_col.addWidget(hero_subtitle)
        hero_layout.addLayout(hero_text_col, 1)
        all_layout.addWidget(hero_banner)

        kpi_grid = QHBoxLayout()
        kpi_grid.setSpacing(8)

        def _make_kpi_box(title: str, default_val: str, subtitle: str) -> tuple[QFrame, QLabel]:
            box = QFrame()
            box.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius:  {DesignTokens.RADIUS_SM}px;
                }}
            """)
            b_layout = QVBoxLayout(box)
            b_layout.setContentsMargins(8, 6, 8, 6)
            b_layout.setSpacing(2)
            lbl_t = QLabel(title)
            lbl_t.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: 600; text-transform: uppercase; border: none;")
            lbl_v = QLabel(default_val)
            lbl_v.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: bold; border: none;")
            lbl_s = QLabel(subtitle)
            lbl_s.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; border: none;")
            b_layout.addWidget(lbl_t)
            b_layout.addWidget(lbl_v)
            b_layout.addWidget(lbl_s)
            return box, lbl_v

        box_pages, self.lbl_all_kpi_pages = _make_kpi_box("Pages utiles", f"{self._max_page} p.", "100% actif")
        box_chapters, self.lbl_all_kpi_chapters = _make_kpi_box("Chapitres", "—", "Structure globale")
        box_sections, self.lbl_all_kpi_sections = _make_kpi_box("Sections", "—", "Titres détectés")
        box_words, self.lbl_all_kpi_words = _make_kpi_box("Volume texte", "—", "Estimation mots")
        kpi_grid.addWidget(box_pages)
        kpi_grid.addWidget(box_chapters)
        kpi_grid.addWidget(box_sections)
        kpi_grid.addWidget(box_words)
        all_layout.addLayout(kpi_grid)

        lbl_outline_title = QLabel("SOMMAIRE DU CONTENU INCLUS")
        lbl_outline_title.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: bold; font-size: 10px; letter-spacing: 0.5px; border: none;")
        all_layout.addWidget(lbl_outline_title)

        self.all_outline_scroll = QScrollArea()
        self.all_outline_scroll.setWidgetResizable(True)
        self.all_outline_scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: transparent;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius:  {DesignTokens.RADIUS_SM}px;
            }}
        """)
        self.all_outline_container = QWidget()
        self.all_outline_container.setStyleSheet("background: transparent;")
        self.all_outline_layout = QVBoxLayout(self.all_outline_container)
        self.all_outline_layout.setContentsMargins(6, 6, 6, 6)
        self.all_outline_layout.setSpacing(4)
        self.all_outline_scroll.setWidget(self.all_outline_container)
        all_layout.addWidget(self.all_outline_scroll, 1)

        # 4. Mode Chapters: Carte de sélection par chapitres
        self.chapters_card = QFrame()
        self.chapters_card.setObjectName("chaptersCard")
        chapters_layout = QVBoxLayout(self.chapters_card)
        chapters_layout.setContentsMargins(14, 12, 14, 12)
        chapters_layout.setSpacing(10)

        ch_header = QHBoxLayout()
        lbl_ch_title = QLabel("SÉLECTION PAR CHAPITRES")
        lbl_ch_title.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: bold; font-size: 10px; letter-spacing: 0.5px; border: none;")
        ch_header.addWidget(lbl_ch_title)
        ch_header.addStretch()

        self.lbl_chapters_kpi = QLabel("")
        self.lbl_chapters_kpi.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; font-size: 11px; font-weight: bold; border: none;")
        ch_header.addWidget(self.lbl_chapters_kpi)
        chapters_layout.addLayout(ch_header)

        # Toolbar : Sélecteur de plage de chapitres + Boutons rapides
        ch_toolbar = QHBoxLayout()
        ch_toolbar.setContentsMargins(0, 0, 0, 0)
        ch_toolbar.setSpacing(8)

        self.structure_scope_container = QWidget()
        struct_scope_layout = QHBoxLayout(self.structure_scope_container)
        struct_scope_layout.setContentsMargins(0, 0, 0, 0)
        struct_scope_layout.setSpacing(6)

        combo_style = f"""
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                min-height: 22px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                selection-background-color: {DesignTokens.BG_ACTIVE};
                border: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """
        lbl_c_start = QLabel("De :")
        lbl_c_start.setFixedWidth(24)
        lbl_c_start.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; border: none;")
        self.combo_c_start = QComboBox()
        self.combo_c_start.setStyleSheet(combo_style)
        lbl_c_end = QLabel("À :")
        lbl_c_end.setFixedWidth(16)
        lbl_c_end.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; border: none;")
        self.combo_c_end = QComboBox()
        self.combo_c_end.setStyleSheet(combo_style)
        self.combo_c_start.currentIndexChanged.connect(self._on_chapter_range_changed)
        self.combo_c_end.currentIndexChanged.connect(self._on_chapter_range_changed)
        struct_scope_layout.addWidget(lbl_c_start)
        struct_scope_layout.addWidget(self.combo_c_start, 1)
        struct_scope_layout.addWidget(lbl_c_end)
        struct_scope_layout.addWidget(self.combo_c_end, 1)
        ch_toolbar.addWidget(self.structure_scope_container, 1)

        btn_ch_all = SecondaryButton("Tout cocher")
        btn_ch_all.setFixedHeight(28)
        btn_ch_all.setStyleSheet(f"font-size: 11px; padding: 4px 10px; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px;")
        btn_ch_all.clicked.connect(self._on_check_all_chapters)

        btn_ch_none = SecondaryButton("Tout décocher")
        btn_ch_none.setFixedHeight(28)
        btn_ch_none.setStyleSheet(f"font-size: 11px; padding: 4px 10px; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px;")
        btn_ch_none.clicked.connect(self._on_uncheck_all_chapters)

        ch_toolbar.addWidget(btn_ch_all)
        ch_toolbar.addWidget(btn_ch_none)
        chapters_layout.addLayout(ch_toolbar)

        self.chapters_scroll = QScrollArea()
        self.chapters_scroll.setWidgetResizable(True)
        self.chapters_scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: transparent;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius:  {DesignTokens.RADIUS_SM}px;
            }}
        """)
        self.chapters_list_container = QWidget()
        self.chapters_list_container.setStyleSheet("background: transparent;")
        self.chapters_list_layout = QVBoxLayout(self.chapters_list_container)
        self.chapters_list_layout.setContentsMargins(6, 6, 6, 6)
        self.chapters_list_layout.setSpacing(6)
        self.chapters_scroll.setWidget(self.chapters_list_container)
        chapters_layout.addWidget(self.chapters_scroll, 1)

        self.lbl_chapters_summary = QLabel("")
        self.lbl_chapters_summary.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        chapters_layout.addWidget(self.lbl_chapters_summary)

        if self.is_paginated:
            left_layout.addWidget(self.pages_card)
        else:
            self.pages_card.hide()
        left_layout.addWidget(self.all_card, 1)
        left_layout.addWidget(self.chapters_card, 1)

        # Détermination du mode initial et visibilité
        has_custom_pages = bool(doc.start_page and doc.end_page and (doc.start_page > 1 or doc.end_page < self._max_page))
        if has_custom_pages:
            self.btn_scope_mode_range.setChecked(True)
            self.slider_scope_container.show()
            self.range_presets_container.show()
            self.range_info_card.show()
            self.all_card.hide()
            self.chapters_card.hide()
            left_layout.setStretchFactor(self.pages_card, 1)
        else:
            self.btn_scope_mode_all.setChecked(True)
            self.slider_scope_container.hide()
            self.range_presets_container.hide()
            self.range_info_card.hide()
            self.all_card.show()
            self.chapters_card.hide()
            left_layout.setStretchFactor(self.pages_card, 0)
        self.btn_scope_mode_sections.setEnabled(True)

        # 3. Liste des sections et chapitres cochables
        sections_card = QFrame()
        self.sections_card = sections_card
        sections_card.setObjectName("sectionsCard")
        sections_layout = QVBoxLayout(sections_card)
        sections_layout.setContentsMargins(12, 10, 12, 10)
        sections_layout.setSpacing(8)

        sec_header = QHBoxLayout()
        sec_title = "2. SECTIONS & TITRES DÉTECTÉS" if self.is_paginated else "SECTIONS & TITRES DÉTECTÉS"
        lbl_sec2 = QLabel(sec_title)
        lbl_sec2.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: bold; font-size: 10px; letter-spacing: 0.5px; border: none;")
        sec_header.addWidget(lbl_sec2)
        sec_header.addStretch()

        self.lbl_selection_kpi = QLabel("")
        self.lbl_selection_kpi.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; font-size: 11px; font-weight: bold; border: none;")
        sec_header.addWidget(self.lbl_selection_kpi)
        sections_layout.addLayout(sec_header)

        # Actions rapides
        self.section_actions = QWidget()
        quick_btns = QHBoxLayout(self.section_actions)
        btn_check_all = SecondaryButton("Tout sélectionner")
        btn_check_all.setFixedHeight(28)
        btn_check_all.setStyleSheet(f"font-size: 11px; padding: 4px 10px; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px;")
        btn_check_all.clicked.connect(lambda: self._set_all_checked(True))

        btn_uncheck_all = SecondaryButton("Tout désélectionner")
        btn_uncheck_all.setFixedHeight(28)
        btn_uncheck_all.setStyleSheet(f"font-size: 11px; padding: 4px 10px; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px;")
        btn_uncheck_all.clicked.connect(lambda: self._set_all_checked(False))

        quick_btns.addWidget(btn_check_all)
        quick_btns.addWidget(btn_uncheck_all)
        quick_btns.addStretch()
        sections_layout.addWidget(self.section_actions)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filtrer les sections et leurs titres...")
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.setFixedHeight(28)
        self.filter_input.setStyleSheet(
            f"QLineEdit {{ background-color: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_PRIMARY}; "
            f"border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius:  6px; padding: 4px 8px; }}"
            f"QLineEdit:focus {{ border-color: {DesignTokens.ACCENT_PRIMARY}; }}"
        )
        self.filter_input.textChanged.connect(self._on_filter_changed)
        sections_layout.addWidget(self.filter_input)

        self.section_tree_container = QWidget()
        tree_container_layout = QVBoxLayout(self.section_tree_container)
        tree_container_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_list = DocumentStructureTreeWidget()
        self.sections_list.setIndentation(16)
        self.sections_tree = self.sections_list
        self.sections_list.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius:  6px;
                padding: 4px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QTreeWidget::item {{
                padding: 2px 4px;
                border-radius: 4px;
                margin-bottom: 2px;
                border: none;
            }}
            QTreeWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QTreeWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
            }}
            QTreeWidget::indicator {{
                width: 0px;
                height: 0px;
                border: none;
                background: transparent;
            }}
        """)
        self.sections_list.setMinimumHeight(240)
        self.sections_list.setVerticalScrollMode(QTreeWidget.ScrollMode.ScrollPerPixel)
        self.sections_list.currentRowChanged.connect(self._on_section_selected)
        self.sections_list.itemClicked.connect(lambda item: self._on_section_selected(self.sections_list.row(item)))
        tree_container_layout.addWidget(self.sections_list)
        sections_layout.addWidget(self.section_tree_container, 1)
        left_layout.addWidget(sections_card, 1)

        # Splitter principal : Panneau gauche (sélection) + Panneau droit (visionneuse de document)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(left_container)

        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        view_switch_bar = QHBoxLayout()
        view_switch_bar.setContentsMargins(0, 0, 0, 0)
        view_switch_bar.setSpacing(6)
        self.btn_view_source = QPushButton("Document Source")
        self.btn_view_source.setIcon(load_phosphor_icon("ph.file-text", color=DesignTokens.TEXT_PRIMARY))
        self.btn_view_source.setCheckable(True)
        self.btn_view_source.setChecked(True)
        self.btn_view_source.setStyleSheet(mode_btn_style)
        self.btn_view_final = QPushButton("Vue Finale Assemblée")
        self.btn_view_final.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_PRIMARY))
        self.btn_view_final.setCheckable(True)
        self.btn_view_final.setStyleSheet(mode_btn_style)
        self.view_switch_group = QButtonGroup(self)
        self.view_switch_group.addButton(self.btn_view_source)
        self.view_switch_group.addButton(self.btn_view_final)
        self.btn_view_source.clicked.connect(self._on_view_source_clicked)
        self.btn_view_final.clicked.connect(self._on_view_final_clicked)
        view_switch_bar.addWidget(self.btn_view_source)
        view_switch_bar.addWidget(self.btn_view_final)
        view_switch_bar.addStretch()
        right_layout.addLayout(view_switch_bar)

        self.preview_stack = QStackedWidget()
        self.preview_widget = DocumentPreviewWidget(doc)
        self.preview_stack.addWidget(self.preview_widget)

        self.final_preview_card = QFrame()
        self.final_preview_card.setObjectName("finalPreviewCard")
        self.final_preview_card.setStyleSheet(
            f"QFrame#finalPreviewCard {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius:  {DesignTokens.RADIUS_MD}px; }}"
        )
        final_layout = QVBoxLayout(self.final_preview_card)
        final_layout.setContentsMargins(12, 10, 12, 10)
        final_layout.setSpacing(8)
        self.lbl_final_preview_kpi = QLabel("")
        self.lbl_final_preview_kpi.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        final_layout.addWidget(self.lbl_final_preview_kpi)
        self.final_preview_browser = QTextBrowser()
        self.final_preview_browser.setStyleSheet(
            f"QTextBrowser {{ background-color: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; "
            f"border-radius:  6px; padding: 12px; color: {DesignTokens.TEXT_PRIMARY}; font-family: {DesignTokens.FONT_MAIN}; font-size: 12px; }}"
        )
        final_layout.addWidget(self.final_preview_browser, 1)
        self.preview_stack.addWidget(self.final_preview_card)
        right_layout.addWidget(self.preview_stack, 1)

        self.main_splitter.addWidget(right_container)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.setSizes([480, 800])
        layout.addWidget(self.main_splitter, 1)

        self._populate_sections()
        self.setFocus()

        # Connecteurs réactifs pour les spinboxes (si paginé)
        if self.is_paginated:
            self.spin_p_start.valueChanged.connect(self._on_start_page_changed)
            self.spin_p_end.valueChanged.connect(self._on_end_page_changed)

        # 4. Pied de page & validation
        footer = QHBoxLayout()
        saved_revec = bool(SettingsService.get("documents/revectorize_after_delimitation", True))
        self.chk_revectorize = QCheckBox("Réindexer automatiquement dans FAISS (RAG) après délimitation")
        self.chk_revectorize.setChecked(saved_revec)
        self.chk_revectorize.stateChanged.connect(lambda s: SettingsService.set("documents/revectorize_after_delimitation", s == Qt.CheckState.Checked.value, category="documents"))
        footer.addWidget(self.chk_revectorize)
        footer.addStretch()

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        self.btn_reset = SecondaryButton("↩ Réinitialiser")
        self.btn_reset.setToolTip("Réinitialiser les bornes et exclusions du document")
        self.btn_reset.clicked.connect(self._on_reset)
        footer.addWidget(self.btn_reset)
        footer.addWidget(btn_cancel)

        apply_text = "Valider le découpage pour le lot" if self.context == "batch" else "Enregistrer la délimitation globale"
        btn_apply = PrimaryButton(apply_text)
        btn_apply.setIcon(load_on_accent_icon("ph.check-circle"))
        btn_apply.clicked.connect(self._on_apply)
        footer.addWidget(btn_apply)

        layout.addLayout(footer)
        self._update_kpi()

    def _on_filter_changed(self, text: str) -> None:
        """Filtre l'arbre sans modifier les états cochés, en conservant les ancêtres utiles."""
        query = text.casefold().strip()

        def filter_item(item: QTreeWidgetItem) -> bool:
            row = self.sections_list.row(item)
            meta = self._section_meta.get(row, {})
            haystack = " ".join(str(meta.get(key) or "") for key in ("title", "heading_path")).casefold()
            own_match = not query or query in haystack
            child_match = False
            for index in range(item.childCount()):
                child_match = filter_item(item.child(index)) or child_match
            visible = own_match or child_match
            item.setHidden(not visible)
            if visible and query and child_match:
                item.setExpanded(True)
            return visible

        for index in range(self.sections_list.topLevelItemCount()):
            filter_item(self.sections_list.topLevelItem(index))

    def _set_section_controls_visible(self, visible: bool) -> None:
        """Affiche les contrôles de sélection fine uniquement en mode sections."""
        self.sections_card.setVisible(visible)
        self.section_actions.setVisible(visible)
        self.filter_input.setVisible(visible)
        self.section_tree_container.setVisible(visible)
        self.sections_list.setVisible(visible)

    def _on_reset(self) -> None:
        """Réinitialise la délimitation après confirmation explicite."""
        reply = QMessageBox.question(
            self,
            "Réinitialiser la délimitation",
            "Réinitialiser les bornes et les exclusions pour retrouver le document original ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._manual_exclusions.clear()
        self.selection_mode = "pages"
        self._set_all_checked(True)
        self.btn_scope_mode_all.setChecked(True)
        self._set_section_controls_visible(False)
        self.structure_scope_container.hide()
        self.slider_scope_container.hide()
        self._syncing_selection = True
        try:
            self.spin_p_start.setValue(1)
            self.spin_p_end.setValue(self._max_page)
            self.slider_p_start.setValue(1)
            self.slider_p_end.setValue(self._max_page)
            self.range_bar.set_range(1, self._max_page, self._max_page)
        finally:
            self._syncing_selection = False
        self.doc.start_page = None
        self.doc.end_page = None
        self.doc.excluded_headings = json.dumps([], ensure_ascii=False)
        self.doc.save()
        # Réutilise le chemin d'enregistrement différentiel pour restaurer aussi
        # les chunks supprimés par une délimitation précédente.
        self._on_apply()

    def _on_section_selected(self, row: int) -> None:
        """Fait défiler l'aperçu du document vers la section sélectionnée."""
        if row < 0 or row not in self._section_meta:
            return
        meta = self._section_meta[row]
        title = str(meta.get("title") or "")
        page = meta.get("page_number")
        self.preview_widget.jump_to_heading(title, page)

    def _on_view_source_clicked(self) -> None:
        self.preview_stack.setCurrentIndex(0)

    def _on_view_final_clicked(self) -> None:
        self._refresh_final_preview()
        self.preview_stack.setCurrentIndex(1)

    def _selected_chunks_for_mode(self) -> list[dict[str, Any]]:
        """Retourne les fragments gouvernés par le mode actif."""
        if self.selection_mode == "pages":
            start_page = self.spin_p_start.value()
            end_page = self.spin_p_end.value()
            return [chunk for chunk in self._all_chunks if chunk.get("page_number") is None or start_page <= chunk.get("page_number", start_page) <= end_page]

        selected: list[dict[str, Any]] = []
        if self.selection_mode == "chapters":
            start = self.combo_c_start.currentIndex()
            end = self.combo_c_end.currentIndex()
            if start < 0 or end < 0:
                return selected
            for i in range(self.sections_list.count()):
                item = self.sections_list.item(i)
                meta = self._section_meta.get(i, {})
                if item.childCount() == 0 and start <= meta.get("root_index", -1) <= end:
                    chunk = meta.get("chunk")
                    if isinstance(chunk, dict):
                        selected.append(chunk)
            return selected

        for i in range(self.sections_list.count()):
            item = self.sections_list.item(i)
            if item.checkState(0) != Qt.CheckState.Checked or item.childCount() > 0:
                continue
            chunk = self._section_meta.get(i, {}).get("chunk")
            if isinstance(chunk, dict):
                selected.append(chunk)
        return selected

    def _refresh_final_preview(self) -> None:
        """Construit en mémoire l'aperçu assemblé des feuilles actuellement retenues."""
        selected_chunks = self._selected_chunks_for_mode()
        checked_items = [
            (
                next(
                    (meta for meta in self._section_meta.values() if meta.get("chunk") is chunk),
                    {"title": chunk.get("title", ""), "page_number": chunk.get("page_number"), "tokens": 0},
                ),
                chunk,
            )
            for chunk in selected_chunks
        ]

        if not checked_items:
            self.lbl_final_preview_kpi.setText("Aucun fragment sélectionné pour la vue finale.")
            self.final_preview_browser.setHtml(f"<p style='color: {DesignTokens.TEXT_MUTED}; font-style: italic;'>Cochez au moins une section pour prévisualiser le contenu assemblé.</p>")
            return

        total_words = sum(len(str(chunk.get("content", "")).split()) for _, chunk in checked_items)
        total_tokens = sum(int(meta.get("tokens", 0)) for meta, _ in checked_items)
        approx_cards = max(1, total_words // 180) if total_words else 0
        self.lbl_final_preview_kpi.setText(f"{len(checked_items)} fragment(s) assemblé(s) • ~{total_tokens:,} tokens • ~{total_words:,} mots • ~{approx_cards} cartes estimées".replace(",", " "))

        html_blocks: list[str] = []
        for meta, chunk in checked_items:
            title = html.escape(str(meta.get("title") or ""))
            page = meta.get("page_number")
            page_info = f" <span style='color: {DesignTokens.TEXT_MUTED};'>(Page {page})</span>" if page else ""
            content = html.escape(str(chunk.get("content") or ""))
            html_blocks.append(
                f'<div style="background-color: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; '
                f'border-radius:  6px; padding: 12px; margin-bottom: 12px;">'
                f'<div style="color: {DesignTokens.ACCENT_PRIMARY}; font-weight: bold; margin-bottom: 8px;">'
                f"{title}{page_info}</div>"
                f'<div style="color: {DesignTokens.TEXT_PRIMARY}; white-space: pre-wrap;">{content}</div></div>'
            )
        self.final_preview_browser.setHtml("".join(html_blocks))

    def _apply_page_preset(self, start: int, end: int) -> None:
        """Applique un préréglage de pagination et met à jour l'interface."""
        self.spin_p_start.setValue(start)
        self.spin_p_end.setValue(end)

    def _on_check_all_chapters(self) -> None:
        """Coche tous les chapitres dans la vue chapitres."""
        for card in self._chapter_cards:
            card.set_checked(True)
        if hasattr(self, "combo_c_start") and hasattr(self, "combo_c_end") and self.combo_c_start.count() > 0:
            self.combo_c_start.blockSignals(True)
            self.combo_c_end.blockSignals(True)
            self.combo_c_start.setCurrentIndex(0)
            self.combo_c_end.setCurrentIndex(self.combo_c_start.count() - 1)
            self.combo_c_start.blockSignals(False)
            self.combo_c_end.blockSignals(False)
        self._set_all_checked(True)

    def _on_uncheck_all_chapters(self) -> None:
        """Décoche tous les chapitres dans la vue chapitres."""
        for card in self._chapter_cards:
            card.set_checked(False)
        self._set_all_checked(False)

    def _on_chapter_card_toggled(self, chapter_index: int, is_checked: bool) -> None:
        """Met à jour les sections et l'aperçu lorsqu'une carte de chapitre est basculée."""
        self._syncing_selection = True
        try:
            for i in range(self.sections_list.count()):
                meta = self._section_meta.get(i, {})
                if meta.get("root_index") == chapter_index:
                    it = self.sections_list.item(i)
                    if it:
                        w = self.sections_list.itemWidget(it, 0)
                        if isinstance(w, SectionRowWidget):
                            w.set_checked(is_checked)
                        else:
                            it.setCheckState(0, Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
        finally:
            self._syncing_selection = False
        self._refresh_final_preview()
        self._update_kpi()

    def _on_mode_all_clicked(self) -> None:
        self.selection_mode = "pages"
        self._set_section_controls_visible(False)
        self.all_card.show()
        self.chapters_card.hide()
        if self.is_paginated:
            self.pages_card.show()
            self.slider_scope_container.hide()
            self.range_presets_container.hide()
            self.range_info_card.hide()
            self.left_layout.setStretchFactor(self.pages_card, 0)
        if hasattr(self, "structure_scope_container"):
            self.structure_scope_container.hide()
        self._manual_exclusions.clear()
        self.spin_p_start.blockSignals(True)
        self.spin_p_end.blockSignals(True)
        self.slider_p_start.blockSignals(True)
        self.slider_p_end.blockSignals(True)

        self.spin_p_start.setValue(1)
        self.spin_p_end.setValue(self._max_page)
        self.slider_p_start.setValue(1)
        self.slider_p_end.setValue(self._max_page)

        self.spin_p_start.blockSignals(False)
        self.spin_p_end.blockSignals(False)
        self.slider_p_start.blockSignals(False)
        self.slider_p_end.blockSignals(False)

        self.range_bar.set_range(1, self._max_page, self._max_page)
        self._set_all_checked(True)
        for card in self._chapter_cards:
            card.set_checked(True)
        if hasattr(self, "preview_widget"):
            self.preview_widget.set_scope_range(1, self._max_page, included_pages=set(range(1, self._max_page + 1)))
        self._update_kpi()

    def _on_mode_range_clicked(self) -> None:
        self.selection_mode = "pages"
        self._set_section_controls_visible(False)
        self.all_card.hide()
        self.chapters_card.hide()
        if self.is_paginated:
            self.pages_card.show()
            self.slider_scope_container.show()
            self.range_presets_container.show()
            self.range_info_card.show()
            self.left_layout.setStretchFactor(self.pages_card, 1)
        if hasattr(self, "structure_scope_container"):
            self.structure_scope_container.hide()
        sp = self.spin_p_start.value()
        ep = self.spin_p_end.value()
        self.range_bar.set_range(sp, ep, self._max_page)
        self._filter_sections_by_pages(sp, ep)
        checked_pages = {
            self._section_meta[i]["page_number"]
            for i in range(self.sections_list.count())
            if self.sections_list.item(i).checkState(0) == Qt.CheckState.Checked and self._section_meta.get(i, {}).get("page_number") is not None
        }
        if hasattr(self, "preview_widget"):
            self.preview_widget.set_scope_range(sp, ep, included_pages=checked_pages)
        self._update_kpi()

    def _on_mode_structure_clicked(self) -> None:
        self.selection_mode = "chapters"
        self.all_card.hide()
        self.chapters_card.show()
        if self.is_paginated:
            self.pages_card.show()
            self.slider_scope_container.hide()
            self.range_presets_container.hide()
            self.range_info_card.hide()
            self.left_layout.setStretchFactor(self.pages_card, 0)
        self._set_section_controls_visible(False)
        if hasattr(self, "structure_scope_container"):
            self.structure_scope_container.show()
        self._on_chapter_range_changed()

    def _on_mode_sections_clicked(self) -> None:
        self.selection_mode = "sections"
        self.all_card.hide()
        self.chapters_card.hide()
        if self.is_paginated:
            self.pages_card.show()
            self.slider_scope_container.hide()
            self.range_presets_container.hide()
            self.range_info_card.hide()
            self.left_layout.setStretchFactor(self.pages_card, 0)
        if hasattr(self, "structure_scope_container"):
            self.structure_scope_container.hide()
        self._set_section_controls_visible(True)
        self._update_kpi()

    def _on_chapter_range_changed(self) -> None:
        if not hasattr(self, "combo_c_start") or not hasattr(self, "combo_c_end"):
            return
        idx_start = self.combo_c_start.currentIndex()
        idx_end = self.combo_c_end.currentIndex()
        if idx_start < 0 or idx_end < 0:
            return
        if idx_start > idx_end:
            self.combo_c_end.blockSignals(True)
            self.combo_c_end.setCurrentIndex(idx_start)
            self.combo_c_end.blockSignals(False)
            idx_end = idx_start

        for card in self._chapter_cards:
            card.set_checked(idx_start <= card.chapter_index <= idx_end)

        if self.selection_mode == "chapters":
            checked_pages = [
                self._section_meta[i]["page_number"]
                for i in range(self.sections_list.count())
                if self.sections_list.item(i).childCount() == 0
                and idx_start <= self._section_meta.get(i, {}).get("root_index", -1) <= idx_end
                and self._section_meta.get(i, {}).get("page_number") is not None
            ]
            if self.is_paginated and checked_pages:
                min_p = min(checked_pages)
                max_p = max(checked_pages)
                if hasattr(self, "preview_widget"):
                    self.preview_widget.set_scope_range(min_p, max_p, included_pages=set(checked_pages))
                    self.preview_widget.jump_to_page(min_p)
        self._update_kpi()

    def _on_slider_start_changed(self, val: int) -> None:
        if val > self.spin_p_end.value():
            self.spin_p_end.setValue(val)
        self.spin_p_start.setValue(val)

    def _on_slider_end_changed(self, val: int) -> None:
        if val < self.spin_p_start.value():
            self.spin_p_start.setValue(val)
        self.spin_p_end.setValue(val)

    def _on_start_page_changed(self, val: int) -> None:
        if self._syncing_selection:
            return
        if self.selection_mode != "pages":
            return
        if hasattr(self, "btn_scope_mode_range") and (val > 1 or self.spin_p_end.value() < self._max_page):
            self.btn_scope_mode_range.setChecked(True)
            self.slider_scope_container.show()
            if hasattr(self, "structure_scope_container"):
                self.structure_scope_container.hide()
        self.slider_p_start.blockSignals(True)
        self.slider_p_start.setValue(val)
        self.slider_p_start.blockSignals(False)
        if hasattr(self, "range_bar"):
            self.range_bar.set_range(val, self.spin_p_end.value(), self._max_page)
        self._filter_sections_by_pages(val, self.spin_p_end.value())
        checked_pages = {
            self._section_meta[i]["page_number"]
            for i in range(self.sections_list.count())
            if self.sections_list.item(i).checkState(0) == Qt.CheckState.Checked and self._section_meta.get(i, {}).get("page_number") is not None
        }
        if hasattr(self, "preview_widget"):
            self.preview_widget.set_scope_range(val, self.spin_p_end.value(), included_pages=checked_pages)
            self.preview_widget.jump_to_page(val)
        self._update_kpi()

    def _on_end_page_changed(self, val: int) -> None:
        if self._syncing_selection:
            return
        if self.selection_mode != "pages":
            return
        if hasattr(self, "btn_scope_mode_range") and (self.spin_p_start.value() > 1 or val < self._max_page):
            self.btn_scope_mode_range.setChecked(True)
            self.slider_scope_container.show()
            if hasattr(self, "structure_scope_container"):
                self.structure_scope_container.hide()
        self.slider_p_end.blockSignals(True)
        self.slider_p_end.setValue(val)
        self.slider_p_end.blockSignals(False)
        if hasattr(self, "range_bar"):
            self.range_bar.set_range(self.spin_p_start.value(), val, self._max_page)
        self._filter_sections_by_pages(self.spin_p_start.value(), val)
        checked_pages = {
            self._section_meta[i]["page_number"]
            for i in range(self.sections_list.count())
            if self.sections_list.item(i).checkState(0) == Qt.CheckState.Checked and self._section_meta.get(i, {}).get("page_number") is not None
        }
        if hasattr(self, "preview_widget"):
            self.preview_widget.set_scope_range(self.spin_p_start.value(), val, included_pages=checked_pages)
            self.preview_widget.jump_to_page(val)
        self._update_kpi()

    def _filter_sections_by_pages(self, start_p: int, end_p: int) -> None:
        """Coche ou décoche automatiquement les fragments selon leur appartenance à la plage de pages sélectionnée sans écraser les exclusions manuelles."""
        if not self.is_paginated or self.selection_mode != "pages" or self._syncing_selection:
            return
        self._syncing_selection = True
        try:
            self.sections_list.blockSignals(True)
            for i in range(self.sections_list.count()):
                meta = self._section_meta.get(i, {})
                p_num = meta.get("page_number")
                title = str(meta.get("title") or "").lower().strip()
                if p_num is not None:
                    in_range = start_p <= p_num <= end_p
                    should_check = in_range and (title not in self._manual_exclusions)
                    item = self.sections_list.item(i)
                    if item:
                        target_state = Qt.CheckState.Checked if should_check else Qt.CheckState.Unchecked
                        item.setCheckState(0, target_state)
                        w = self.sections_list.itemWidget(item, 0)
                        if isinstance(w, SectionRowWidget):
                            w.set_check_state(target_state)
            for i in range(self.sections_list.count()):
                it = self.sections_list.item(i)
                if it and it.childCount() > 0:
                    self._update_parent_from_children(it)
            self.sections_list.blockSignals(False)
        finally:
            self._syncing_selection = False

    def _on_tree_item_state_changed(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        """Synchronisation dynamique unifiée arborescence -> sliders, mémorisation des exclusions et cascade parent-enfant."""
        row = self.sections_list.row(item)
        meta = self._section_meta.get(row, {})
        title = str(meta.get("title") or "").lower().strip()
        orig_title = str(meta.get("title") or "")
        p_num = meta.get("page_number")

        # 1. Navigation immédiate vers la section concernée dans l'aperçu
        if hasattr(self, "preview_widget"):
            self.preview_widget.jump_to_heading(orig_title, p_num)

        # 2. Cascade parent/enfant
        if not self._syncing_selection:
            self._syncing_selection = True
            try:
                if state in (Qt.CheckState.Checked, Qt.CheckState.Unchecked):
                    self._cascade_down(item, state)
                self._cascade_up(item)

                if state == Qt.CheckState.Unchecked and title:
                    self._manual_exclusions.add(title)
                elif state == Qt.CheckState.Checked and title:
                    self._manual_exclusions.discard(title)
            finally:
                self._syncing_selection = False

        if self.selection_mode == "pages" or self._syncing_selection:
            self._update_kpi()
            return

        self._update_kpi()

    def _cascade_down(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            w = self.sections_list.itemWidget(child, 0)
            if isinstance(w, SectionRowWidget):
                w.set_check_state(state)
            meta = self._section_meta.get(self.sections_list.row(child), {})
            child_title = str(meta.get("title") or "").lower().strip()
            if state == Qt.CheckState.Unchecked and child_title:
                self._manual_exclusions.add(child_title)
            elif state == Qt.CheckState.Checked and child_title:
                self._manual_exclusions.discard(child_title)
            self._cascade_down(child, state)

    def _cascade_up(self, item: QTreeWidgetItem) -> None:
        parent = item.parent()
        if parent is None:
            return
        self._update_parent_from_children(parent)
        self._cascade_up(parent)

    def _update_parent_from_children(self, parent: QTreeWidgetItem) -> None:
        child_states = [parent.child(i).checkState(0) for i in range(parent.childCount())]
        if all(s == Qt.CheckState.Checked for s in child_states):
            parent_state = Qt.CheckState.Checked
        elif all(s == Qt.CheckState.Unchecked for s in child_states):
            parent_state = Qt.CheckState.Unchecked
        else:
            parent_state = Qt.CheckState.PartiallyChecked

        parent.setCheckState(0, parent_state)
        w = self.sections_list.itemWidget(parent, 0)
        if isinstance(w, SectionRowWidget):
            w.set_check_state(parent_state)

    def _load_document_stats(self) -> None:
        """Charge la distribution des cartes créées par fragment et par page avec indexation robuste."""
        self._chunk_cards = {}
        self._page_cards = {}
        self._hash_cards = {}
        self._heading_page_cards = {}

        if not getattr(self.doc, "id", None):
            return

        try:
            CoverageAlignmentService.sync_coverage_from_tags(self.doc.id)
        except Exception as e:
            logger.debug("Sync couverture silencieuse dans délimitation: %s", e)

        try:
            links = (
                NoteChunkLinkModel.select(
                    DocumentChunkModel.chunk_index,
                    DocumentChunkModel.page_number,
                    DocumentChunkModel.content_hash,
                    DocumentChunkModel.heading_path,
                    fn.COUNT(NoteChunkLinkModel.note).alias("cnt"),
                )
                .join(DocumentChunkModel)
                .where(DocumentChunkModel.document == self.doc)
                .group_by(
                    DocumentChunkModel.chunk_index,
                    DocumentChunkModel.page_number,
                    DocumentChunkModel.content_hash,
                    DocumentChunkModel.heading_path,
                )
            )
            for row in links:
                c_idx = row.chunk.chunk_index
                p_num = row.chunk.page_number
                c_hash = row.chunk.content_hash
                h_path = row.chunk.heading_path
                cnt = int(getattr(row, "cnt", 0))
                if c_idx is not None:
                    self._chunk_cards[c_idx] = self._chunk_cards.get(c_idx, 0) + cnt
                if p_num is not None:
                    self._page_cards[p_num] = self._page_cards.get(p_num, 0) + cnt
                if c_hash:
                    self._hash_cards[c_hash] = self._hash_cards.get(c_hash, 0) + cnt
                if h_path:
                    key = (h_path, p_num)
                    self._heading_page_cards[key] = self._heading_page_cards.get(key, 0) + cnt
        except Exception as e:
            logger.debug("Erreur comptage des cartes par fragment: %s", e)

    def _populate_sections(self) -> None:
        """Remplit l'arborescence avec les sections sémantiques en affichant volume, cartes créées et avis d'utilité."""
        self.sections_list.blockSignals(True)
        self.sections_list.clear()
        self._section_meta.clear()

        # 1. Extraction arborescente des titres
        tree_nodes: list[HeadingTreeNode] = []
        if self.doc.content:
            tree_nodes = ChunkingService.extract_heading_tree_with_pages(self.doc.content, self._max_page, self.doc.file_type or "md")
        if not tree_nodes:
            chunks_to_display = self._all_chunks
            if not chunks_to_display and getattr(self.doc, "id", None):
                existing = list(DocumentChunkModel.select().where(DocumentChunkModel.document == self.doc).order_by(DocumentChunkModel.chunk_index))
                chunks_to_display = [
                    {
                        "index": c.chunk_index,
                        "heading_path": c.heading_path,
                        "page_number": c.page_number,
                        "content": c.content,
                        "content_hash": c.content_hash,
                    }
                    for c in existing
                ]
            tree_nodes = ChunkingService.build_tree_from_chunks(chunks_to_display)

        has_headings = has_structured_heading_nodes(tree_nodes)

        # Remplissage des sélecteurs de chapitres
        if hasattr(self, "combo_c_start") and hasattr(self, "combo_c_end"):
            self.combo_c_start.blockSignals(True)
            self.combo_c_end.blockSignals(True)
            self.combo_c_start.clear()
            self.combo_c_end.clear()
            if has_headings:
                for idx, root_n in enumerate(tree_nodes):
                    p_span = ""
                    if self.is_paginated and root_n.start_page is not None:
                        p_span = f" (p. {root_n.start_page}–{root_n.end_page})" if root_n.end_page and root_n.end_page > root_n.start_page else f" (p. {root_n.start_page})"
                    label = f"{root_n.title}{p_span}"
                    self.combo_c_start.addItem(label, idx)
                    self.combo_c_end.addItem(label, idx)
                self.combo_c_start.setCurrentIndex(0)
                self.combo_c_end.setCurrentIndex(len(tree_nodes) - 1)
                self.btn_scope_mode_structure.show()
                if not self.is_paginated:
                    self.structure_scope_container.show()
            else:
                self.btn_scope_mode_structure.hide()
                if hasattr(self, "structure_scope_container"):
                    self.structure_scope_container.hide()
            self.combo_c_start.blockSignals(False)
            self.combo_c_end.blockSignals(False)

        self.btn_scope_mode_sections.setVisible(has_headings)
        self.btn_scope_mode_sections.setEnabled(has_headings)
        self.btn_scope_mode_all.setEnabled(self.is_paginated)
        self.btn_scope_mode_range.setEnabled(self.is_paginated)
        if has_headings:
            if self.is_paginated:
                self.selection_mode = "pages"
                if self.btn_scope_mode_range.isChecked():
                    self._set_section_controls_visible(False)
                else:
                    self.btn_scope_mode_all.setChecked(True)
                    self._set_section_controls_visible(False)
            else:
                self.selection_mode = "sections"
                self.btn_scope_mode_sections.setChecked(True)
                self.structure_scope_container.hide()
                self._set_section_controls_visible(True)
        else:
            self.selection_mode = "chapters" if self.combo_c_start.count() else "pages"
            if self.is_paginated:
                self.btn_scope_mode_all.setChecked(True)
            elif self.combo_c_start.count():
                self.btn_scope_mode_structure.setChecked(True)
                self.structure_scope_container.show()
            self._set_section_controls_visible(False)

        # 2. Peuplement récursif du QTreeWidget
        def _add_node_recursive(node: HeadingTreeNode, parent_item: QTreeWidgetItem | None = None, root_index: int = -1) -> None:
            if parent_item is None:
                item = SectionTreeWidgetItem(self.sections_list)
                self.sections_list.addTopLevelItem(item)
                root_index = self.sections_list.topLevelItemCount() - 1
            else:
                item = SectionTreeWidgetItem(parent_item)
            item.setExpanded(True)

            flat_idx = len(self._section_meta)
            title_str = node.heading_path or node.title
            page_num = node.start_page
            end_p = node.end_page
            chunk_idx = node.chunk_index if node.chunk_index is not None else flat_idx
            word_count = node.word_count
            level = node.level
            chunk_dict: dict[str, Any] | None = None
            for candidate in self._all_chunks:
                if candidate.get("heading_path") == node.heading_path:
                    candidate_page = candidate.get("page_number")
                    if page_num is None or candidate_page is None or candidate_page == page_num:
                        chunk_dict = candidate
                        break
            if chunk_dict is None:
                chunk_dict = next(
                    (candidate for candidate in self._all_chunks if candidate.get("index") == chunk_idx),
                    None,
                )

            cards_count = 0
            if (node.heading_path, page_num) in self._heading_page_cards:
                cards_count = self._heading_page_cards[(node.heading_path, page_num)]
            elif (node.title, page_num) in self._heading_page_cards:
                cards_count = self._heading_page_cards[(node.title, page_num)]
            elif chunk_idx in self._chunk_cards:
                cards_count = self._chunk_cards[chunk_idx]
            elif page_num is not None:
                cards_count = self._page_cards.get(page_num, 0)

            low_title = node.title.lower().strip()
            low_h_path = (node.heading_path or "").lower().strip()
            is_noise = False

            self._section_meta[flat_idx] = {
                "title": node.title,
                "heading_path": node.heading_path,
                "page_number": page_num,
                "end_page": end_p,
                "level": level,
                "word_count": word_count,
                "tokens": node.token_count,
                "cards_count": cards_count,
                "is_noise": is_noise,
                "is_leaf": not node.children,
                "root_index": root_index,
                "chunk": chunk_dict,
                "item": item,
            }

            in_range = True
            if self.is_paginated and page_num is not None and hasattr(self, "spin_p_start") and hasattr(self, "spin_p_end"):
                in_range = self.spin_p_start.value() <= page_num <= self.spin_p_end.value()
            is_checked = in_range and (low_title not in self._manual_exclusions) and (low_h_path not in self._manual_exclusions)

            item.setCheckState(0, Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
            item.setData(0, Qt.ItemDataRole.UserRole, title_str)

            row_widget = SectionRowWidget(
                item=item,
                tree_widget=self.sections_list,
                title=node.title,
                is_checked=is_checked,
                page_number=page_num,
                end_page=end_p,
                level=level,
                word_count=word_count,
                cards_count=cards_count,
                is_noise=is_noise,
                is_leaf=not node.children,
                show_page=self.is_paginated,
            )
            row_widget.state_changed.connect(lambda st, it=item: self._on_tree_item_state_changed(it, st))
            item.setSizeHint(0, QSize(0, 36))

            self.sections_list.setItemWidget(item, 0, row_widget)

            # Tooltip
            rec_text = "À conserver impérativement (Cartes déjà créées)" if cards_count > 0 else ("Section courte / à vérifier" if word_count < 25 else "Contenu de cours standard")
            p_str = f" (Pages {page_num}–{end_p})" if (self.is_paginated and page_num and end_p and end_p > page_num) else (f" (Page {page_num})" if (self.is_paginated and page_num) else "")
            item.setToolTip(0, f"<b>{node.title}</b>{p_str}<br>• Volume : {word_count} mots<br>• Cartes créées : {cards_count} carte(s)<br>• Diagnostic : <b>{rec_text}</b>")

            for child in node.children:
                _add_node_recursive(child, item, root_index)

        for root_node in tree_nodes:
            _add_node_recursive(root_node, None)

        self._tree_nodes = tree_nodes
        self._chapter_cards.clear()
        while self.chapters_list_layout.count():
            item_c = self.chapters_list_layout.takeAt(0)
            w_c = item_c.widget()
            if w_c:
                w_c.deleteLater()

        while self.all_outline_layout.count():
            item_o = self.all_outline_layout.takeAt(0)
            w_o = item_o.widget()
            if w_o:
                w_o.deleteLater()

        def _gather_chapter_stats(n: HeadingTreeNode) -> tuple[int, int]:
            sub_c = len(n.children)
            words = n.word_count
            for ch in n.children:
                sc, w = _gather_chapter_stats(ch)
                sub_c += sc
                words += w
            return sub_c, words

        for idx, root_n in enumerate(tree_nodes):
            subsections_count, chapter_words = _gather_chapter_stats(root_n)
            ch_card = ChapterCardWidget(
                chapter_index=idx,
                title=root_n.title,
                start_page=root_n.start_page,
                end_page=root_n.end_page,
                subsections_count=subsections_count,
                word_count=chapter_words,
                is_checked=True,
                is_paginated=self.is_paginated,
            )
            ch_card.toggled.connect(self._on_chapter_card_toggled)
            self._chapter_cards.append(ch_card)
            self.chapters_list_layout.addWidget(ch_card)

            outline_row = QFrame()
            outline_row.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius:  {DesignTokens.RADIUS_SM}px;
                }}
            """)
            or_layout = QHBoxLayout(outline_row)
            or_layout.setContentsMargins(8, 6, 8, 6)
            or_layout.setSpacing(8)

            ch_badge = QLabel(f"Ch. {idx + 1}")
            ch_badge.setStyleSheet(
                f"background-color: {DesignTokens.ACCENT_BG}; color: {DesignTokens.COLOR_PURPLE_TEXT}; border: 1px solid {DesignTokens.ACCENT_BORDER};"
                f" border-radius: 4px; padding: 2px 6px; font-weight: bold; font-size: 10px;"
            )
            or_layout.addWidget(ch_badge)

            or_title = QLabel(root_n.title)
            or_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: 500; border: none; background: transparent;")
            or_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            or_layout.addWidget(or_title, 1)

            p_parts: list[str] = []
            if self.is_paginated and root_n.start_page is not None:
                p_span = f"p. {root_n.start_page}–{root_n.end_page}" if root_n.end_page and root_n.end_page > root_n.start_page else f"p. {root_n.start_page}"
                p_parts.append(p_span)
            if subsections_count > 0:
                p_parts.append(f"{subsections_count} sec.")
            p_parts.append(f"~{chapter_words:,} mots".replace(",", " "))
            or_meta = QLabel(" • ".join(p_parts))
            or_meta.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; border: none; background: transparent;")
            or_layout.addWidget(or_meta)

            self.all_outline_layout.addWidget(outline_row)

        self.chapters_list_layout.addStretch()
        self.all_outline_layout.addStretch()

        for i in range(self.sections_list.count()):
            it = self.sections_list.item(i)
            if it and it.childCount() > 0:
                self._update_parent_from_children(it)

        self.sections_list.blockSignals(False)
        self._refresh_final_preview()

    def _update_kpi(self) -> None:
        """Met à jour l'indicateur de sections retenues et exclues ainsi que l'alerte d'impact de pagination."""
        total = self.sections_list.count()
        selected_chunks = self._selected_chunks_for_mode()
        selected_ids = {id(chunk) for chunk in selected_chunks}
        checked_count = 0
        excluded_count = 0
        checked_words = 0
        excluded_words = 0
        checked_cards = 0
        excluded_cards = 0

        for i in range(total):
            item = self.sections_list.item(i)
            if not item:
                continue
            meta = self._section_meta.get(i, {})
            w_cnt = int(meta.get("word_count", 0))
            c_cnt = int(meta.get("cards_count", 0))

            if item.childCount() > 0:
                continue
            if id(meta.get("chunk")) in selected_ids:
                checked_count += 1
                checked_words += w_cnt
                checked_cards += c_cnt
            else:
                excluded_count += 1
                excluded_words += w_cnt
                excluded_cards += c_cnt

        total_words = checked_words + excluded_words
        pct_words = int(round((checked_words / total_words) * 100)) if total_words > 0 else 100

        if excluded_cards > 0:
            self.lbl_selection_kpi.setText(f"{checked_count} retenues ({pct_words}% mots) • {excluded_count} exclues (dont {excluded_cards} carte{'s' if excluded_cards > 1 else ''} !)")
            self.lbl_selection_kpi.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        else:
            self.lbl_selection_kpi.setText(f"{checked_count} retenues ({pct_words}% mots • {checked_cards} cartes) • {excluded_count} exclues ({100 - pct_words}%)")
            self.lbl_selection_kpi.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; font-size: 11px; font-weight: bold; border: none; background: transparent;")

        # Mise à jour des KPIs du Mode All
        if hasattr(self, "lbl_all_kpi_pages"):
            self.lbl_all_kpi_pages.setText(f"{self._max_page} p.")
            self.lbl_all_kpi_chapters.setText(f"{len(self._chapter_cards)} chap.")
            self.lbl_all_kpi_sections.setText(f"{len(self._section_meta)} sec.")
            self.lbl_all_kpi_words.setText(f"~{total_words:,} mots".replace(",", " "))

        # Mise à jour des informations du Mode Range
        if hasattr(self, "lbl_range_coverage_kpi") and hasattr(self, "spin_p_start") and hasattr(self, "spin_p_end"):
            sp = self.spin_p_start.value()
            ep = self.spin_p_end.value()
            p_cnt = ep - sp + 1
            p_pct = (p_cnt / self._max_page * 100) if self._max_page > 0 else 100.0
            self.lbl_range_coverage_kpi.setText(f"Pages {sp} à {ep} ({p_cnt} / {self._max_page} pages — {p_pct:.1f}%)")
            words_in_range = sum(m.get("word_count", 0) for m in self._section_meta.values() if m.get("page_number") and sp <= m.get("page_number") <= ep and m.get("is_leaf"))
            chs_in_range = [c.title for c in self._tree_nodes if (c.start_page is not None and c.end_page is not None and max(sp, c.start_page) <= min(ep, c.end_page))]
            self.lbl_range_words_kpi.setText(f"Volume estimé dans la plage : ~{words_in_range:,} mots".replace(",", " "))
            ch_txt = ", ".join(chs_in_range[:3]) + (f" (+{len(chs_in_range) - 3})" if len(chs_in_range) > 3 else "") if chs_in_range else "Tous"
            self.lbl_range_chapters_kpi.setText(f"Chapitres concernés : {ch_txt}")

        # Mise à jour des KPIs du Mode Chapitres
        if hasattr(self, "lbl_chapters_kpi") and hasattr(self, "_chapter_cards"):
            checked_chs = [c for c in self._chapter_cards if c.is_checked()]
            self.lbl_chapters_kpi.setText(f"{len(checked_chs)} / {len(self._chapter_cards)} chapitres sélectionnés")
            ch_plural = "s" if len(checked_chs) > 1 else ""
            self.lbl_chapters_summary.setText(f"{len(checked_chs)} chapitre{ch_plural} actif{ch_plural} • {checked_words:,} mots sélectionnés".replace(",", " "))

        # Impact sur la pagination (uniquement si le document est un PDF / paginé)
        if self.is_paginated and self.selection_mode == "pages":
            self.lbl_page_impact.show()
            start_p = self.spin_p_start.value()
            end_p = self.spin_p_end.value()
            excluded_pages = [p for p in self._page_cards if p < start_p or p > end_p]
            excluded_page_cards = sum(self._page_cards[p] for p in excluded_pages)

            if excluded_page_cards > 0:
                p_str = ", ".join(f"p.{p}" for p in sorted(excluded_pages))
                self.lbl_page_impact.setText(f"{excluded_page_cards} carte(s) existante(s) dans les pages exclues ({p_str}) — la délimitation restreindra leur couverture.")
                self.lbl_page_impact.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; font-weight: 500; border: none; background: transparent;")
            else:
                self.lbl_page_impact.setText("Aucune carte n'est impactée par les bornes de pagination choisies.")
                self.lbl_page_impact.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 11px; border: none; background: transparent;")
        else:
            self.lbl_page_impact.hide()

    def _set_all_checked(self, checked: bool) -> None:
        self.sections_list.blockSignals(True)
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.sections_list.count()):
            item = self.sections_list.item(i)
            item.setCheckState(state)
            widget = self.sections_list.itemWidget(item)
            if isinstance(widget, SectionRowWidget):
                widget.set_checked(checked)
            meta = self._section_meta.get(i, {})
            title = str(meta.get("title") or "").lower().strip()
            if not checked:
                if title:
                    self._manual_exclusions.add(title)
            else:
                if title:
                    self._manual_exclusions.discard(title)
        self.sections_list.blockSignals(False)

        self._update_kpi()

    def _on_apply(self) -> None:
        if self.selection_mode == "pages" and self.is_paginated:
            page_start = self.spin_p_start.value()
            page_end = self.spin_p_end.value()
            if page_start > page_end:
                show_toast(self, "La page de début doit être inférieure ou égale à la page de fin.", is_error=True)
                return
            if page_end > self._max_page:
                show_toast(self, f"La page de fin ne peut pas dépasser la dernière page détectée ({self._max_page}).", is_error=True)
                return
            if hasattr(self, "btn_scope_mode_all") and self.btn_scope_mode_all.isChecked() and page_start == 1 and page_end == self._max_page:
                page_start = None
                page_end = None
        else:
            page_start = None
            page_end = None

        effective_exclusions: set[str] = set()
        if self.selection_mode == "sections":
            for i in range(self.sections_list.count()):
                item = self.sections_list.item(i)
                val = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
                if item.checkState() == Qt.CheckState.Unchecked and val:
                    effective_exclusions.add(val)
                    effective_exclusions.add(val.lower())
            effective_exclusions.update(ex for ex in self._manual_exclusions if ex)

        retained_chunks = []
        selected_chunks = self._selected_chunks_for_mode()
        selected_ids = {id(chunk) for chunk in selected_chunks}
        low_exclusions = {e.lower().strip() for e in effective_exclusions}
        for chunk in self._all_chunks:
            if self.selection_mode in ("sections", "chapters") and id(chunk) not in selected_ids:
                continue
            if self.selection_mode == "pages" and page_start is not None and page_end is not None:
                page_number = chunk.get("page_number")
                if page_number is not None and not (page_start <= page_number <= page_end):
                    continue
            h_path = (chunk.get("heading_path") or "").strip()
            title_str = h_path or (f"Page {chunk.get('page_number')}" if chunk.get("page_number") else f"Section #{chunk.get('index', 0) + 1}")
            low_title = title_str.lower().strip()
            low_h_path = h_path.lower()
            if self.selection_mode == "sections" and (low_title in low_exclusions or (low_h_path and any(ex in low_h_path for ex in low_exclusions))):
                continue
            retained_chunks.append(chunk)

        if not retained_chunks:
            show_toast(self, "Aucun contenu ne correspond à cette sélection.", is_error=True)
            return

        # 1. Persistance durable sur DocumentModel
        self.doc.start_page = page_start
        self.doc.end_page = page_end
        self.doc.excluded_headings = json.dumps(sorted(list(effective_exclusions)), ensure_ascii=False)
        if getattr(self, "_max_page", 0) and self._max_page > 1:
            self.doc.total_pages = self._max_page
        self.doc.save()

        # 2. Mise à jour différentielle atomique des chunks actifs en base (préserve NoteChunkLinkModel !)
        with DocumentChunkModel._meta.database.atomic():
            existing_chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == self.doc).order_by(DocumentChunkModel.chunk_index))
            existing_by_hash: dict[str, list[DocumentChunkModel]] = {}
            existing_by_heading_page: dict[tuple[str | None, int | None], list[DocumentChunkModel]] = {}
            for c in existing_chunks:
                if c.content_hash:
                    existing_by_hash.setdefault(c.content_hash, []).append(c)
                if c.heading_path:
                    existing_by_heading_page.setdefault((c.heading_path, c.page_number), []).append(c)

            matched_chunk_ids: set[int] = set()

            for idx, c_data in enumerate(retained_chunks):
                c_content = c_data["content"]
                c_hash = c_data.get("content_hash") or ChunkingService.hash_content(c_content)
                c_page = c_data.get("page_number")
                c_heading = c_data.get("heading_path")

                matched_chunk: DocumentChunkModel | None = None
                if c_hash in existing_by_hash:
                    for cand in existing_by_hash[c_hash]:
                        if cand.id not in matched_chunk_ids:
                            matched_chunk = cand
                            break

                if matched_chunk is None and (c_heading, c_page) in existing_by_heading_page:
                    for cand in existing_by_heading_page[(c_heading, c_page)]:
                        if cand.id not in matched_chunk_ids:
                            matched_chunk = cand
                            break

                if matched_chunk is not None:
                    matched_chunk_ids.add(matched_chunk.id)
                    matched_chunk.chunk_index = idx
                    matched_chunk.content = c_content
                    matched_chunk.page_number = c_page
                    matched_chunk.heading_path = c_heading
                    matched_chunk.content_hash = c_hash
                    matched_chunk.save()
                else:
                    created = DocumentChunkModel.create(
                        document=self.doc,
                        chunk_index=idx,
                        content=c_content,
                        page_number=c_page,
                        heading_path=c_heading,
                        content_hash=c_hash,
                    )
                    matched_chunk_ids.add(created.id)

            chunks_to_delete = [c.id for c in existing_chunks if c.id not in matched_chunk_ids]
            if chunks_to_delete:
                DocumentChunkModel.delete().where(DocumentChunkModel.id.in_(chunks_to_delete)).execute()

        from ankiforge.services.reindex_service import mark_document_version

        mark_document_version(self.doc)

        # 3. Réindexation RAG si demandée
        if self.chk_revectorize.isChecked():
            try:
                rag = RAGService()
                rag.create_index(self.doc.id)
            except Exception as e:
                logger.warning("Erreur réindexation FAISS : %s", e)

        self.accept()
