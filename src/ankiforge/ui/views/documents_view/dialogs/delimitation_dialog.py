import json
import logging
import re
from pathlib import Path
from typing import Any

import markdown
from peewee import fn
from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QPixmap
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
        elif is_noise:
            diag_badge = QLabel("🔇 Bruit (Non péda)")
            diag_badge.setStyleSheet(
                "background-color: rgba(234, 179, 8, 0.15); color: #facc15; border: 1px solid rgba(234, 179, 8, 0.3); border-radius: 4px; padding: 2px 6px; font-size: 10px; font-weight: bold;"
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

    def _update_page_label(self) -> None:
        if self._is_paginated and self._current_mode in ("pdf", "album"):
            self.lbl_page.show()
            self.btn_prev_page.show()
            self.btn_next_page.show()
            self.lbl_page.setText(f"Page {self._current_page} / {self._total_pages}")
            self.btn_prev_page.setEnabled(self._current_page > 1)
            self.btn_next_page.setEnabled(self._current_page < self._total_pages)
        else:
            self.lbl_page.hide()
            self.btn_prev_page.hide()
            self.btn_next_page.hide()

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
        self.doc = doc
        self._chunk_cards: dict[int, int] = {}
        self._page_cards: dict[int, int] = {}
        self._section_meta: dict[int, dict[str, Any]] = {}
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
            page_numbers = [int(chunk["page_number"]) for chunk in self._all_chunks if chunk.get("page_number") is not None]
            self._max_page = max(page_numbers, default=int(doc.total_pages or 1))
            if doc.total_pages and doc.total_pages > self._max_page:
                self._max_page = int(doc.total_pages)

        win_title = f"Délimiter les pages et sections — {doc.title}" if self.is_paginated else f"Délimiter les sections — {doc.title}"
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
        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.scissors", color=DesignTokens.ACCENT_PRIMARY).pixmap(20, 20))
        title_lbl = QLabel(f"Délimiter le périmètre utile : <b>{doc.title}</b>")
        title_lbl.setStyleSheet(f"font-size: 14px; color: {DesignTokens.TEXT_PRIMARY}; border: none;")
        header_top.addWidget(icon_lbl)
        header_top.addWidget(title_lbl, 1)
        h_layout.addLayout(header_top)

        desc_lbl = QLabel("Excluez les parties non pédagogiques (sommaires, préfaces, annexes) pour focaliser la couverture, l'éditeur et la recherche IA sur le contenu essentiel.")
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

        pages_inputs = QHBoxLayout()
        lbl_p_start = QLabel("Page de début :")
        lbl_p_start.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; border: none;")
        self.spin_p_start = QSpinBox()
        self.spin_p_start.setRange(1, self._max_page)
        start_val = doc.start_page if (doc.start_page and doc.start_page > 0) else 1
        self.spin_p_start.setValue(min(start_val, self._max_page))
        self.spin_p_start.setStyleSheet(f"""
            QSpinBox {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 4px 6px 4px 8px;
                min-width: 60px;
            }}
            QSpinBox:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        lbl_p_end = QLabel("Page de fin :")
        lbl_p_end.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; border: none;")
        self.spin_p_end = QSpinBox()
        self.spin_p_end.setRange(1, self._max_page)
        end_val = doc.end_page if (doc.end_page and doc.end_page >= start_val) else self._max_page
        self.spin_p_end.setValue(min(end_val, self._max_page))
        self.spin_p_end.setStyleSheet(f"""
            QSpinBox {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 4px 6px 4px 8px;
                min-width: 60px;
            }}
            QSpinBox:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        pages_inputs.addWidget(lbl_p_start)
        pages_inputs.addWidget(self.spin_p_start)
        pages_inputs.addSpacing(16)
        pages_inputs.addWidget(lbl_p_end)
        pages_inputs.addWidget(self.spin_p_end)
        pages_inputs.addSpacing(16)

        lbl_max_info = QLabel(f"(Total détecté : {self._max_page} pages)")
        lbl_max_info.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none;")
        pages_inputs.addWidget(lbl_max_info)
        pages_inputs.addStretch()

        pages_card_layout.addLayout(pages_inputs)

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

        btn_smart_filter = SecondaryButton("Filtre Anti-Bruit Automatique")
        btn_smart_filter.setIcon(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_YELLOW))
        btn_smart_filter.setFixedHeight(28)
        btn_smart_filter.setStyleSheet(f"font-size: 11px; padding: 4px 12px; color: {DesignTokens.COLOR_YELLOW}; border: 1px solid {DesignTokens.COLOR_YELLOW}; border-radius: 4px;")
        btn_smart_filter.clicked.connect(self._apply_smart_filter)

        quick_btns.addWidget(btn_check_all)
        quick_btns.addWidget(btn_uncheck_all)
        quick_btns.addStretch()
        quick_btns.addWidget(btn_smart_filter)
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

        btn_apply = PrimaryButton("Appliquer la sélection")
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

    def _on_start_page_changed(self, val: int) -> None:
        self._update_kpi()
        self.preview_widget.jump_to_page(val)

    def _on_end_page_changed(self, val: int) -> None:
        self._update_kpi()
        self.preview_widget.jump_to_page(val)

    def _load_document_stats(self) -> None:
        """Charge la distribution des cartes créées par fragment et par page."""
        self._chunk_cards = {}
        self._page_cards = {}

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
                    fn.COUNT(NoteChunkLinkModel.note).alias("cnt"),
                )
                .join(DocumentChunkModel)
                .where(DocumentChunkModel.document == self.doc)
                .group_by(DocumentChunkModel.chunk_index, DocumentChunkModel.page_number)
            )
            for row in links:
                c_idx = row.chunk.chunk_index
                p_num = row.chunk.page_number
                cnt = int(getattr(row, "cnt", 0))
                if c_idx is not None:
                    self._chunk_cards[c_idx] = self._chunk_cards.get(c_idx, 0) + cnt
                if p_num is not None:
                    self._page_cards[p_num] = self._page_cards.get(p_num, 0) + cnt
        except Exception as e:
            logger.debug("Erreur comptage des cartes par fragment: %s", e)

    def _populate_sections(self) -> None:
        """Remplit la liste avec les sections sémantiques en affichant volume, cartes créées et avis d'utilité."""
        self.sections_list.blockSignals(True)
        self.sections_list.clear()
        self._section_meta.clear()

        excluded_list: list[str] = []
        raw_excl = getattr(self.doc, "excluded_headings", None)
        if raw_excl:
            try:
                parsed = json.loads(raw_excl)
                if isinstance(parsed, list):
                    excluded_list = [str(x).lower() for x in parsed]
            except Exception:
                excluded_list = []

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

        noise_keywords = [
            "sommaire",
            "table des matières",
            "table of contents",
            "toc",
            "remerciements",
            "acknowledgments",
            "acknowledgements",
            "avant-propos",
            "préface",
            "foreword",
            "bibliographie",
            "references",
            "références",
            "annexe",
            "annexes",
            "appendix",
            "appendices",
            "index",
            "glossaire",
            "glossary",
            "copyright",
            "license",
            "mentions légales",
            "colophon",
        ]

        for idx, c_data in enumerate(chunks_to_display):
            title_str = c_data.get("heading_path") or (f"Page {c_data.get('page_number')}" if c_data.get("page_number") else f"Section #{c_data.get('index', 0) + 1}")
            page_num = c_data.get("page_number")
            chunk_idx = c_data.get("index", idx)
            content = str(c_data.get("content") or "")
            word_count = len(content.split()) if content else 0

            # Nombre de cartes associées
            cards_count = self._chunk_cards.get(chunk_idx, 0)
            if not cards_count and page_num is not None:
                cards_count = self._page_cards.get(page_num, 0)

            low_title = title_str.lower()
            is_noise = any(k in low_title for k in noise_keywords)

            self._section_meta[idx] = {
                "title": title_str,
                "page_number": page_num,
                "word_count": word_count,
                "cards_count": cards_count,
                "is_noise": is_noise,
            }

            item = QListWidgetItem()
            # Si des exclusions sont mémorisées, on les respecte fidèlement
            # Sinon, filtre automatique : on conserve le contenu utile ou toute section ayant des cartes créées
            is_checked = (low_title not in excluded_list) if excluded_list else (cards_count > 0 or not is_noise)

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
            row_widget.checked_changed.connect(lambda _: self._update_kpi())
            item.setSizeHint(QSize(0, 36))

            # Tooltip riche
            rec_text = (
                "À conserver impérativement (Cartes déjà créées)"
                if cards_count > 0
                else ("Bruit documentaire non pédagogique" if is_noise else ("Section courte / à vérifier" if word_count < 25 else "Contenu de cours standard"))
            )
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
        self.sections_list.blockSignals(False)
        self._update_kpi()

    def _apply_smart_filter(self, notify: bool = True) -> None:
        self.sections_list.blockSignals(True)
        for i in range(self.sections_list.count()):
            item = self.sections_list.item(i)
            meta = self._section_meta.get(i, {})
            is_noise = meta.get("is_noise", False)
            cards_cnt = int(meta.get("cards_count", 0))
            should_check = not (is_noise and cards_cnt == 0)
            item.setCheckState(Qt.CheckState.Checked if should_check else Qt.CheckState.Unchecked)
            widget = self.sections_list.itemWidget(item)
            if isinstance(widget, SectionRowWidget):
                widget.set_checked(should_check)
        self.sections_list.blockSignals(False)
        self._update_kpi()
        if notify:
            show_toast(self, "Filtre intelligent appliqué : bruit documentaire exclu.")

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
        else:
            page_start = None
            page_end = None

        selected_headings: list[str] = []
        excluded_headings: list[str] = []
        for i in range(self.sections_list.count()):
            item = self.sections_list.item(i)
            val = str(item.data(Qt.ItemDataRole.UserRole))
            if item.checkState() == Qt.CheckState.Checked:
                selected_headings.append(val)
            else:
                excluded_headings.append(val)

        retained_chunks = []
        for chunk in self._all_chunks:
            if self.is_paginated and page_start is not None and page_end is not None:
                page_number = chunk.get("page_number")
                if page_number is not None and not (page_start <= page_number <= page_end):
                    continue
            h_path = chunk.get("heading_path", "")
            if not selected_headings or any(sh in h_path for sh in selected_headings) or not h_path:
                retained_chunks.append(chunk)

        if not retained_chunks:
            show_toast(self, "Aucun contenu ne correspond à cette sélection.", is_error=True)
            return

        # 1. Persistance durable sur DocumentModel
        self.doc.start_page = page_start
        self.doc.end_page = page_end
        self.doc.excluded_headings = json.dumps(excluded_headings, ensure_ascii=False)
        self.doc.save()

        # 2. Mise à jour atomique des chunks actifs en base
        with DocumentChunkModel._meta.database.atomic():
            DocumentChunkModel.delete().where(DocumentChunkModel.document == self.doc).execute()
            for idx, c_data in enumerate(retained_chunks):
                DocumentChunkModel.create(
                    document=self.doc,
                    chunk_index=idx,
                    content=c_data["content"],
                    page_number=c_data.get("page_number"),
                    heading_path=c_data.get("heading_path"),
                    content_hash=c_data.get("content_hash") or ChunkingService.hash_content(c_data["content"]),
                )

        # 3. Réindexation RAG si demandée
        if self.chk_revectorize.isChecked():
            try:
                rag = RAGService()
                rag.create_index(self.doc.id)
            except Exception as e:
                logger.warning("Erreur réindexation FAISS : %s", e)

        self.accept()
