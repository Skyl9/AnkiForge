import json
import logging
import re
from pathlib import Path
from typing import Any

import markdown
from peewee import fn
from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
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
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.components import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.paths import get_resource_path, resolve_media_path

logger = logging.getLogger(__name__)


class SectionRowWidget(QWidget):
    """Widget de ligne personnalisée pour afficher et basculer individuellement une section avec son diagnostic."""

    checked_changed = Signal(bool)

    def __init__(
        self,
        item: QListWidgetItem,
        list_widget: QListWidget,
        title: str,
        is_checked: bool = True,
        page_number: int | None = None,
        word_count: int = 0,
        cards_count: int = 0,
        is_noise: bool = False,
        show_page: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._item = item
        self._list_widget = list_widget
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 8, 2)
        layout.setSpacing(8)

        # Checkbox explicite et directement interactive
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(is_checked)
        self.checkbox.toggled.connect(self._on_toggled)
        layout.addWidget(self.checkbox)

        # Titre avec numéro de page facultatif (uniquement pour documents paginés)
        page_suffix = f" <span style='color: {DesignTokens.TEXT_MUTED}; font-size: 11px;'>(p. {page_number})</span>" if (show_page and page_number) else ""
        title_lbl = QLabel(f"{title}{page_suffix}")
        title_lbl.setTextFormat(Qt.TextFormat.RichText)
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500; border: none; background: transparent;")
        layout.addWidget(title_lbl, 1)

        # Badge Volume de mots
        if word_count < 25 and not is_noise:
            word_badge = QLabel(f"⚠️ {word_count} mots")
            word_badge.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; border: none; background: transparent;")
        else:
            word_badge = QLabel(f"{word_count} mots")
            word_badge.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        layout.addWidget(word_badge)

        # Badge Cartes existantes
        if cards_count > 0:
            card_badge = QLabel(f"🎴 {cards_count} carte{'s' if cards_count > 1 else ''}")
            card_badge.setStyleSheet(
                f"background-color: {DesignTokens.BG_ACTIVE}; color: {DesignTokens.ACCENT_PRIMARY}; "
                f"border: 1px solid {DesignTokens.ACCENT_PRIMARY}; border-radius: 4px; padding: 2px 6px; "
                "font-weight: bold; font-size: 11px;"
            )
        else:
            card_badge = QLabel("0 carte")
            card_badge.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        layout.addWidget(card_badge)

        # Badge Diagnostic / Recommandation
        if cards_count > 0:
            diag_badge = QLabel("⭐ Utile (Cartes)")
            diag_badge.setStyleSheet(
                "background-color: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 4px; padding: 2px 6px; font-size: 10px; font-weight: bold;"
            )
        elif word_count < 25:
            diag_badge = QLabel("⚠️ Quasi vide")
            diag_badge.setStyleSheet("background-color: rgba(148, 163, 184, 0.15); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.3); border-radius: 4px; padding: 2px 6px; font-size: 10px;")
        else:
            diag_badge = QLabel("📖 Cours")
            diag_badge.setStyleSheet(f"background-color: rgba(99, 102, 241, 0.1); color: {DesignTokens.TEXT_SECONDARY}; border-radius: 4px; padding: 2px 6px; font-size: 10px;")
        layout.addWidget(diag_badge)

    def _on_toggled(self, checked: bool) -> None:
        self._list_widget.setCurrentItem(self._item)
        self._item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.checked_changed.emit(checked)

    def is_checked(self) -> bool:
        return self.checkbox.isChecked()

    def set_checked(self, checked: bool) -> None:
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(checked)
        self._item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.checkbox.blockSignals(False)

    def mousePressEvent(self, event: Any) -> None:
        self._list_widget.setCurrentItem(self._item)
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if not self.checkbox.geometry().contains(pos):
            self.checkbox.setChecked(not self.checkbox.isChecked())
        super().mousePressEvent(event)


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
                border-radius: {DesignTokens.RADIUS_MD}px;
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
            except Exception:
                pass

        if not pdf_path and getattr(self.doc, "file_path", None):
            try:
                cand_path = Path(self.doc.file_path)
                if cand_path.exists():
                    pdf_path = cand_path
            except Exception:
                pass

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
                f'padding: 3px 10px; border-radius: 12px; border: 1px solid #4338ca;">📄 Page {p_num}</span>'
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
                border-radius: 6px;
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
                self.markdown_viewer.find(heading_text)

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
            self.lbl_scope_status.setText(f"✅ Page {self._current_page} INCLUSE (portée {self._scope_start}–{self._scope_end})")
            self.lbl_scope_status.setStyleSheet(
                "background-color: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 4px; padding: 2px 6px; font-size: 10px; font-weight: bold;"
            )
        else:
            self.lbl_scope_status.setText(f"🚫 Page {self._current_page} EXCLUE (portée {self._scope_start}–{self._scope_end})")
            self.lbl_scope_status.setStyleSheet(
                "background-color: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 4px; padding: 2px 6px; font-size: 10px; font-weight: bold;"
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

    def __init__(self, doc: DocumentModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if getattr(doc, "id", None):
            try:
                doc = DocumentModel.get_by_id(doc.id)
            except Exception:
                pass
        self.doc = doc
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
            self._all_chunks = ChunkingService.extract_chunks(doc.content or "", file_type=doc.file_type or "md")
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
            page_numbers = [int(chunk["page_number"]) for chunk in self._all_chunks if chunk.get("page_number") is not None]
            self._max_page = max(page_numbers, default=int(doc.total_pages or 1))
            if doc.total_pages and doc.total_pages > self._max_page:
                self._max_page = int(doc.total_pages)

        win_title = f"Délimitation & Assainissement global — {doc.title}"
        self.setWindowTitle(win_title)
        self.resize(1280, 780)
        self.setMinimumSize(960, 600)
        check_icon_path = str(get_resource_path("src", "ressources", "icons", "check_white.svg")).replace("\\", "/")
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QFrame#headerCard, QFrame#pagesCard, QFrame#sectionsCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QSplitter::handle:horizontal {{
                background-color: {DesignTokens.BORDER_COLOR};
                width: 3px;
                border-radius: 1px;
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
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Panneau gauche : configuration de la délimitation
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # 1. En-tête descriptif
        header_card = QFrame()
        header_card.setObjectName("headerCard")
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(12, 10, 12, 10)
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
            "background-color: rgba(234, 179, 8, 0.15); color: #facc15; border: 1px solid rgba(234, 179, 8, 0.3); border-radius: 4px; padding: 2px 8px; font-size: 10px; font-weight: bold;"
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

        # 2. Plage de pages (uniquement pour documents paginés comme les PDF)
        self.pages_card = QFrame()
        self.pages_card.setObjectName("pagesCard")
        pages_card_layout = QVBoxLayout(self.pages_card)
        pages_card_layout.setContentsMargins(12, 10, 12, 10)
        pages_card_layout.setSpacing(8)

        lbl_sec1 = QLabel("1. BORNES DE PAGINATION UTILE")
        lbl_sec1.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: bold; font-size: 10px; letter-spacing: 0.5px; border: none;")
        pages_card_layout.addWidget(lbl_sec1)

        # Barre visuelle de la portée sélectionnée
        self.range_bar = ScopeRangeBarWidget(self)
        pages_card_layout.addWidget(self.range_bar)

        # Sélecteur de mode de portée : Tout le document vs Plage personnalisée
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
        self.btn_scope_mode_all.setCheckable(True)
        self.btn_scope_mode_all.setStyleSheet(mode_btn_style)

        self.btn_scope_mode_range = QPushButton("Plage de pages")
        self.btn_scope_mode_range.setCheckable(True)
        self.btn_scope_mode_range.setStyleSheet(mode_btn_style)

        self.scope_mode_group = QButtonGroup(self)
        self.scope_mode_group.addButton(self.btn_scope_mode_all)
        self.scope_mode_group.addButton(self.btn_scope_mode_range)
        self.btn_scope_mode_all.clicked.connect(self._on_mode_all_clicked)
        self.btn_scope_mode_range.clicked.connect(self._on_mode_range_clicked)

        mode_row.addWidget(self.btn_scope_mode_all)
        mode_row.addWidget(self.btn_scope_mode_range)
        lbl_max_info = QLabel(f"(Total : {self._max_page} pages)")
        lbl_max_info.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none;")
        mode_row.addWidget(lbl_max_info)
        mode_row.addStretch()
        pages_card_layout.addLayout(mode_row)

        # Conteneur des curseurs (slider) et spinboxes — Visible UNIQUEMENT en mode Plage de pages
        self.slider_scope_container = QWidget()
        slider_scope_layout = QVBoxLayout(self.slider_scope_container)
        slider_scope_layout.setContentsMargins(0, 4, 0, 0)
        slider_scope_layout.setSpacing(6)

        slider_style = f"""
            QSlider::groove:horizontal {{
                height: 4px;
                background: {DesignTokens.BORDER_COLOR};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {DesignTokens.ACCENT_PRIMARY};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {DesignTokens.ACCENT_PRIMARY};
                width: 14px;
                height: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
                border: 2px solid white;
            }}
            QSlider::handle:horizontal:hover {{
                background: white;
                border: 2px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """

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
        self.slider_p_start.setStyleSheet(slider_style)
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
        self.slider_p_end.setStyleSheet(slider_style)
        self.slider_p_end.valueChanged.connect(self._on_slider_end_changed)

        end_row.addWidget(lbl_p_end)
        end_row.addWidget(self.spin_p_end)
        end_row.addWidget(self.slider_p_end, 1)
        slider_scope_layout.addLayout(end_row)

        pages_card_layout.addWidget(self.slider_scope_container)

        # Détermination du mode initial et visibilité du curseur
        has_custom_pages = bool(doc.start_page and doc.end_page and (doc.start_page > 1 or doc.end_page < self._max_page))
        if has_custom_pages:
            self.btn_scope_mode_range.setChecked(True)
            self.slider_scope_container.show()
        else:
            self.btn_scope_mode_all.setChecked(True)
            self.slider_scope_container.hide()

        self.range_bar.set_range(self.spin_p_start.value(), self.spin_p_end.value(), self._max_page)

        self.lbl_page_impact = QLabel()
        self.lbl_page_impact.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        pages_card_layout.addWidget(self.lbl_page_impact)

        if self.is_paginated:
            left_layout.addWidget(self.pages_card)
        else:
            self.pages_card.hide()

        # 3. Liste des sections et chapitres cochables
        sections_card = QFrame()
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
        quick_btns = QHBoxLayout()
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
        sections_layout.addLayout(quick_btns)

        self.sections_list = QListWidget()
        self.sections_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 4px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QListWidget::item {{
                padding: 2px 4px;
                border-radius: 4px;
                margin-bottom: 2px;
                border: none;
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
            }}
            QListWidget::indicator {{
                width: 0px;
                height: 0px;
                border: none;
                background: transparent;
            }}
        """)
        self.sections_list.setMinimumHeight(240)
        self.sections_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.sections_list.currentRowChanged.connect(self._on_section_selected)
        self.sections_list.itemClicked.connect(lambda item: self._on_section_selected(self.sections_list.row(item)))
        sections_layout.addWidget(self.sections_list, 1)
        left_layout.addWidget(sections_card, 1)

        # Splitter principal : Panneau gauche (sélection) + Panneau droit (visionneuse de document)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(left_container)
        self.preview_widget = DocumentPreviewWidget(doc)
        self.main_splitter.addWidget(self.preview_widget)
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
        footer.addWidget(btn_cancel)

        btn_apply = PrimaryButton("Enregistrer la délimitation globale")
        btn_apply.setIcon(load_phosphor_icon("ph.check-circle", color="white"))
        btn_apply.clicked.connect(self._on_apply)
        footer.addWidget(btn_apply)

        layout.addLayout(footer)
        self._update_kpi()

    def _on_section_selected(self, row: int) -> None:
        """Fait défiler l'aperçu du document vers la section sélectionnée."""
        if row < 0 or row not in self._section_meta:
            return
        meta = self._section_meta[row]
        title = str(meta.get("title") or "")
        page = meta.get("page_number")
        self.preview_widget.jump_to_heading(title, page)

    def _on_mode_all_clicked(self) -> None:
        self.slider_scope_container.hide()
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
        if hasattr(self, "preview_widget"):
            self.preview_widget.set_scope_range(1, self._max_page, included_pages=set(range(1, self._max_page + 1)))
        self._update_kpi()

    def _on_mode_range_clicked(self) -> None:
        self.slider_scope_container.show()
        sp = self.spin_p_start.value()
        ep = self.spin_p_end.value()
        self.range_bar.set_range(sp, ep, self._max_page)
        self._filter_sections_by_pages(sp, ep)
        checked_pages = {
            self._section_meta[i]["page_number"]
            for i in range(self.sections_list.count())
            if self.sections_list.item(i).checkState() == Qt.CheckState.Checked and self._section_meta.get(i, {}).get("page_number") is not None
        }
        if hasattr(self, "preview_widget"):
            self.preview_widget.set_scope_range(sp, ep, included_pages=checked_pages)
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
        if hasattr(self, "btn_scope_mode_range") and (val > 1 or self.spin_p_end.value() < self._max_page):
            self.btn_scope_mode_range.setChecked(True)
            self.slider_scope_container.show()
        self.slider_p_start.blockSignals(True)
        self.slider_p_start.setValue(val)
        self.slider_p_start.blockSignals(False)
        if hasattr(self, "range_bar"):
            self.range_bar.set_range(val, self.spin_p_end.value(), self._max_page)
        self._filter_sections_by_pages(val, self.spin_p_end.value())
        checked_pages = {
            self._section_meta[i]["page_number"]
            for i in range(self.sections_list.count())
            if self.sections_list.item(i).checkState() == Qt.CheckState.Checked and self._section_meta.get(i, {}).get("page_number") is not None
        }
        if hasattr(self, "preview_widget"):
            self.preview_widget.set_scope_range(val, self.spin_p_end.value(), included_pages=checked_pages)
            self.preview_widget.jump_to_page(val)
        self._update_kpi()

    def _on_end_page_changed(self, val: int) -> None:
        if self._syncing_selection:
            return
        if hasattr(self, "btn_scope_mode_range") and (self.spin_p_start.value() > 1 or val < self._max_page):
            self.btn_scope_mode_range.setChecked(True)
            self.slider_scope_container.show()
        self.slider_p_end.blockSignals(True)
        self.slider_p_end.setValue(val)
        self.slider_p_end.blockSignals(False)
        if hasattr(self, "range_bar"):
            self.range_bar.set_range(self.spin_p_start.value(), val, self._max_page)
        self._filter_sections_by_pages(self.spin_p_start.value(), val)
        checked_pages = {
            self._section_meta[i]["page_number"]
            for i in range(self.sections_list.count())
            if self.sections_list.item(i).checkState() == Qt.CheckState.Checked and self._section_meta.get(i, {}).get("page_number") is not None
        }
        if hasattr(self, "preview_widget"):
            self.preview_widget.set_scope_range(self.spin_p_start.value(), val, included_pages=checked_pages)
            self.preview_widget.jump_to_page(val)
        self._update_kpi()

    def _filter_sections_by_pages(self, start_p: int, end_p: int) -> None:
        """Coche ou décoche automatiquement les fragments selon leur appartenance à la plage de pages sélectionnée sans écraser les exclusions manuelles."""
        if not self.is_paginated or self._syncing_selection:
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
                    item.setCheckState(Qt.CheckState.Checked if should_check else Qt.CheckState.Unchecked)
                    w = self.sections_list.itemWidget(item)
                    if isinstance(w, SectionRowWidget):
                        w.set_checked(should_check)
            self.sections_list.blockSignals(False)
        finally:
            self._syncing_selection = False

    def _on_section_checked_changed(self, item: QListWidgetItem, is_checked: bool) -> None:
        """Synchronisation dynamique unifiée section -> slider et mémorisation des exclusions manuelles avec navigation immédiate."""
        row = self.sections_list.row(item)
        meta = self._section_meta.get(row, {})
        title = str(meta.get("title") or "").lower().strip()
        orig_title = str(meta.get("title") or "")
        p_num = meta.get("page_number")

        # 1. Navigation immédiate vers la section concernée dans l'aperçu
        if hasattr(self, "preview_widget"):
            self.preview_widget.jump_to_heading(orig_title, p_num)

        # 2. Mémorisation des exclusions manuelles
        if not is_checked:
            if title:
                self._manual_exclusions.add(title)
        else:
            if title:
                self._manual_exclusions.discard(title)

        if not self.is_paginated or self._syncing_selection:
            self._update_kpi()
            return

        # 3. Recalcul unifié des bornes réelles depuis l'ensemble des sections cochées
        checked_pages = [
            self._section_meta[i]["page_number"]
            for i in range(self.sections_list.count())
            if self.sections_list.item(i).checkState() == Qt.CheckState.Checked and self._section_meta.get(i, {}).get("page_number") is not None
        ]

        if checked_pages:
            min_p = min(checked_pages)
            max_p = max(checked_pages)
        else:
            min_p = self.spin_p_start.value()
            max_p = self.spin_p_end.value()

        self._syncing_selection = True
        try:
            self.spin_p_start.setValue(min_p)
            self.spin_p_end.setValue(max_p)
            self.slider_p_start.setValue(min_p)
            self.slider_p_end.setValue(max_p)
            if hasattr(self, "range_bar"):
                self.range_bar.set_range(min_p, max_p, self._max_page)
        finally:
            self._syncing_selection = False

        # 4. Actualisation immédiate du statut de la visionneuse
        if hasattr(self, "preview_widget"):
            self.preview_widget.set_scope_range(min_p, max_p, included_pages=set(checked_pages))

        self._update_kpi()

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
        """Remplit la liste avec les sections sémantiques en affichant volume, cartes créées et avis d'utilité."""
        self.sections_list.blockSignals(True)
        self.sections_list.clear()
        self._section_meta.clear()

        chunks_to_display = self._all_chunks
        if not chunks_to_display:
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

        for idx, c_data in enumerate(chunks_to_display):
            title_str = c_data.get("heading_path") or (f"Page {c_data.get('page_number')}" if c_data.get("page_number") else f"Section #{c_data.get('index', 0) + 1}")
            page_num = c_data.get("page_number")
            chunk_idx = c_data.get("index", idx)
            content = str(c_data.get("content") or "")
            word_count = len(content.split()) if content else 0
            c_hash = c_data.get("content_hash")

            # Nombre de cartes associées : recherche prioritaire par hash de contenu ou (heading_path, page_num)
            cards_count = 0
            if c_hash and c_hash in self._hash_cards:
                cards_count = self._hash_cards[c_hash]
            elif (c_data.get("heading_path"), page_num) in self._heading_page_cards:
                cards_count = self._heading_page_cards[(c_data.get("heading_path"), page_num)]
            elif (title_str, page_num) in self._heading_page_cards:
                cards_count = self._heading_page_cards[(title_str, page_num)]
            elif chunk_idx in self._chunk_cards:
                cards_count = self._chunk_cards[chunk_idx]
            elif page_num is not None:
                cards_count = self._page_cards.get(page_num, 0)

            low_title = title_str.lower()
            is_noise = False

            self._section_meta[idx] = {
                "title": title_str,
                "page_number": page_num,
                "word_count": word_count,
                "cards_count": cards_count,
                "is_noise": is_noise,
            }

            item = QListWidgetItem()
            # Si des exclusions manuelles sont mémorisées, on les respecte fidèlement
            # Si le document est paginé, on respecte également la plage de pages active [start_p, end_p]
            in_range = True
            if self.is_paginated and page_num is not None and hasattr(self, "spin_p_start") and hasattr(self, "spin_p_end"):
                in_range = self.spin_p_start.value() <= page_num <= self.spin_p_end.value()
            is_checked = in_range and (low_title not in self._manual_exclusions)

            item.setCheckState(Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, title_str)

            row_widget = SectionRowWidget(
                item=item,
                list_widget=self.sections_list,
                title=title_str,
                is_checked=is_checked,
                page_number=page_num,
                word_count=word_count,
                cards_count=cards_count,
                is_noise=is_noise,
                show_page=self.is_paginated,
            )
            row_widget.checked_changed.connect(lambda chk, it=item: self._on_section_checked_changed(it, chk))
            item.setSizeHint(QSize(0, 36))

            # Tooltip riche
            rec_text = "À conserver impérativement (Cartes déjà créées)" if cards_count > 0 else ("Section courte / à vérifier" if word_count < 25 else "Contenu de cours standard")
            preview = content[:220].replace("\n", " ").strip()
            if len(content) > 220:
                preview += "..."
            p_str = f" (Page {page_num})" if (self.is_paginated and page_num) else ""
            item.setToolTip(f'<b>{title_str}</b>{p_str}<br>• Volume : {word_count} mots<br>• Cartes créées : {cards_count} carte(s)<br>• Diagnostic : <b>{rec_text}</b><hr><i>"{preview}"</i>')

            self.sections_list.addItem(item)
            self.sections_list.setItemWidget(item, row_widget)

        self.sections_list.blockSignals(False)

    def _update_kpi(self) -> None:
        """Met à jour l'indicateur de sections retenues et exclues ainsi que l'alerte d'impact de pagination."""
        total = self.sections_list.count()
        checked_count = 0
        excluded_count = 0
        checked_words = 0
        excluded_words = 0
        checked_cards = 0
        excluded_cards = 0

        for i in range(total):
            item = self.sections_list.item(i)
            meta = self._section_meta.get(i, {})
            w_cnt = int(meta.get("word_count", 0))
            c_cnt = int(meta.get("cards_count", 0))

            if item.checkState() == Qt.CheckState.Checked:
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
            self.lbl_selection_kpi.setText(f"✅ {checked_count} retenues ({pct_words}% mots) • ⚠️ 🚫 {excluded_count} exclues (dont {excluded_cards} carte{'s' if excluded_cards > 1 else ''} !)")
            self.lbl_selection_kpi.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        else:
            self.lbl_selection_kpi.setText(f"✅ {checked_count} retenues ({pct_words}% mots • {checked_cards} cartes) • 🚫 {excluded_count} exclues ({100 - pct_words}%)")
            self.lbl_selection_kpi.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; font-size: 11px; font-weight: bold; border: none; background: transparent;")

        # Impact sur la pagination (uniquement si le document est un PDF / paginé)
        if self.is_paginated:
            self.lbl_page_impact.show()
            start_p = self.spin_p_start.value()
            end_p = self.spin_p_end.value()
            excluded_pages = [p for p in self._page_cards if p < start_p or p > end_p]
            excluded_page_cards = sum(self._page_cards[p] for p in excluded_pages)

            if excluded_page_cards > 0:
                p_str = ", ".join(f"p.{p}" for p in sorted(excluded_pages))
                self.lbl_page_impact.setText(f"⚠️ {excluded_page_cards} carte(s) existante(s) dans les pages exclues ({p_str}) — la délimitation restreindra leur couverture.")
                self.lbl_page_impact.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; font-weight: 500; border: none; background: transparent;")
            else:
                self.lbl_page_impact.setText("✅ Aucune carte n'est impactée par les bornes de pagination choisies.")
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

        if self.is_paginated:
            checked_pages = [
                self._section_meta[i]["page_number"]
                for i in range(self.sections_list.count())
                if self.sections_list.item(i).checkState() == Qt.CheckState.Checked and self._section_meta.get(i, {}).get("page_number") is not None
            ]
            if checked:
                min_p = 1
                max_p = self._max_page
            elif checked_pages:
                min_p = min(checked_pages)
                max_p = max(checked_pages)
            else:
                min_p = self.spin_p_start.value()
                max_p = self.spin_p_end.value()

            self._syncing_selection = True
            try:
                self.spin_p_start.setValue(min_p)
                self.spin_p_end.setValue(max_p)
                self.slider_p_start.setValue(min_p)
                self.slider_p_end.setValue(max_p)
                if hasattr(self, "range_bar"):
                    self.range_bar.set_range(min_p, max_p, self._max_page)
            finally:
                self._syncing_selection = False

            if hasattr(self, "preview_widget"):
                self.preview_widget.set_scope_range(min_p, max_p, included_pages=set(checked_pages))

        self._update_kpi()

    def _on_apply(self) -> None:
        if self.is_paginated:
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
        for i in range(self.sections_list.count()):
            item = self.sections_list.item(i)
            val = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
            if item.checkState() == Qt.CheckState.Unchecked and val:
                effective_exclusions.add(val)
                effective_exclusions.add(val.lower())
        for ex in self._manual_exclusions:
            if ex:
                effective_exclusions.add(ex)

        retained_chunks = []
        low_exclusions = {e.lower().strip() for e in effective_exclusions}
        for chunk in self._all_chunks:
            if self.is_paginated and page_start is not None and page_end is not None:
                page_number = chunk.get("page_number")
                if page_number is not None and not (page_start <= page_number <= page_end):
                    continue
            h_path = (chunk.get("heading_path") or "").strip()
            title_str = h_path or (f"Page {chunk.get('page_number')}" if chunk.get("page_number") else f"Section #{chunk.get('index', 0) + 1}")
            low_title = title_str.lower().strip()
            low_h_path = h_path.lower()
            if low_title in low_exclusions or (low_h_path and any(ex in low_h_path for ex in low_exclusions)):
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

        # 3. Réindexation RAG si demandée
        if self.chk_revectorize.isChecked():
            try:
                rag = RAGService()
                rag.create_index(self.doc.id)
            except Exception as e:
                logger.warning("Erreur réindexation FAISS : %s", e)

        self.accept()
