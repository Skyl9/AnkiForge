import logging
from typing import Optional, Union

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    NoteChunkLinkModel,
)
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.components.inputs import GlowLineEdit
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ClickableChunkWidget(QFrame):
    """Un paragraphe du document, cliquable, avec un indicateur visuel de couverture."""

    clicked = Signal(int)

    def __init__(self, chunk_id: int, text: str, status: str = "unprofiled", parent=None):
        super().__init__(parent)
        self.chunk_id = chunk_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        color_map = {
            "unprofiled": "transparent",
            "gap": DesignTokens.COLOR_YELLOW,
            "covered": DesignTokens.COLOR_GREEN,
            "hallucination": DesignTokens.COLOR_RED,
        }
        border_color = color_map.get(status, "transparent")

        self.setStyleSheet(f"""
            ClickableChunkWidget {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-left: 3px solid {border_color};
                border-radius: 4px;
                margin-bottom: 4px;
            }}
            ClickableChunkWidget:hover {{
                background-color: {DesignTokens.BG_HOVER};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        self.lbl_text = QLabel(text)
        self.lbl_text.setWordWrap(True)
        self.lbl_text.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; line-height: 1.4;")
        layout.addWidget(self.lbl_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.chunk_id)
        super().mousePressEvent(event)


class DocumentInspectorPanel(QWidget):
    """Panneau pour inspecter l'audit et la couverture détaillée d'un document."""

    back_requested = Signal()
    request_navigation = Signal(str, object)

    def __init__(self, doc_or_id: Union[int, DocumentModel], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        if isinstance(doc_or_id, DocumentModel):
            self.doc = doc_or_id
            self.doc_id = doc_or_id.id
        else:
            self.doc_id = doc_or_id
            self.doc = DocumentModel.get_or_none(DocumentModel.id == doc_or_id)

        if not self.doc:
            return

        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Header du Document
        header_frame = QFrame()
        header_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(12, 8, 12, 8)
        h_layout.setSpacing(10)

        btn_back = SecondaryButton("Retour")
        btn_back.setIcon(load_phosphor_icon("ph.arrow-left", color=DesignTokens.TEXT_PRIMARY))
        btn_back.clicked.connect(self.back_requested.emit)

        ico_doc = QLabel()
        ico_doc.setPixmap(load_phosphor_icon("ph.file-text", color=DesignTokens.COLOR_BLUE, weight="fill").pixmap(18, 18))
        ico_doc.setStyleSheet("border: none; background: transparent;")

        title_to_display = self.doc.original_media.original_name if self.doc.original_media else self.doc.title
        header_lbl = QLabel(title_to_display)
        header_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        header_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        header_lbl.setToolTip(title_to_display)

        self.lbl_doc_summary = QLabel("Couverture : 0%")
        self.lbl_doc_summary.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        self.lbl_doc_summary.setStyleSheet(
            f"background-color: rgba(16,185,129,0.15); color: {DesignTokens.COLOR_GREEN}; border: 1px solid rgba(16,185,129,0.3); border-radius: 9999px; padding: 4px 10px;"
        )

        self.btn_fill_orphans = PrimaryButton("Combler les trous")
        self.btn_fill_orphans.setIcon(load_phosphor_icon("ph.sparkle", color="white"))
        self.btn_fill_orphans.clicked.connect(self._on_fill_all_orphans)

        self.btn_reindex = SecondaryButton("Ré-indexer FAISS")
        self.btn_reindex.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_reindex.clicked.connect(self._on_reindex_faiss)

        h_layout.addWidget(btn_back)
        h_layout.addSpacing(4)
        h_layout.addWidget(ico_doc)
        h_layout.addWidget(header_lbl, 1)
        h_layout.addWidget(self.lbl_doc_summary)
        h_layout.addWidget(self.btn_fill_orphans)
        h_layout.addWidget(self.btn_reindex)

        layout.addWidget(header_frame)

        # 2. Splitter 2 Volets
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel = QFrame()
        left_panel.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; }}")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        lbl_toc = QLabel("Sommaire & Sections du Document")
        lbl_toc.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_toc.setStyleSheet(
            f"color: {DesignTokens.TEXT_PRIMARY}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; "
            f"border-top: none; border-left: none; border-right: none; background: transparent; padding-bottom: 6px;"
        )
        left_layout.addWidget(lbl_toc)

        self.chapters_list = QListWidget()
        self.chapters_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self.chapters_list.itemClicked.connect(self._on_chapter_item_clicked)
        left_layout.addWidget(self.chapters_list, 1)

        lbl_text_title = QLabel("Extrait de la Section Sélectionnée")
        lbl_text_title.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        lbl_text_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent; padding-top: 4px;")
        left_layout.addWidget(lbl_text_title)

        self.text_preview = QTextBrowser()
        self.text_preview.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 10px;
                font-size: 13px;
                line-height: 1.5;
            }}
        """)
        left_layout.addWidget(self.text_preview, 1)

        right_panel = QFrame()
        right_panel.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; }}")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(8)

        lbl_cards_title = QLabel("Cartes Anki Liées & Action de Forge")
        lbl_cards_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_cards_title.setStyleSheet(
            f"color: {DesignTokens.TEXT_PRIMARY}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; "
            f"border-top: none; border-left: none; border-right: none; background: transparent; padding-bottom: 6px;"
        )
        right_layout.addWidget(lbl_cards_title)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards_scroll.setStyleSheet("background: transparent;")

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.setSpacing(10)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.cards_scroll.setWidget(self.cards_container)
        right_layout.addWidget(self.cards_scroll, 1)

        self.splitter.addWidget(left_panel)
        self.splitter.addWidget(right_panel)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 5)
        layout.addWidget(self.splitter, 1)

        self.load_chunks()

    def load_chunks(self) -> None:
        self.chapters_list.clear()
        chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == self.doc).order_by(DocumentChunkModel.chunk_index))

        if not chunks:
            self.lbl_doc_summary.setText("Non indexé (0 section)")
            self.text_preview.setHtml("<p style='color: #9ca3af;'>Ce document n'a pas encore été fragmenté. Cliquez sur 'Ré-indexer FAISS'.</p>")
            return

        covered_count = 0
        for chunk in chunks:
            card_count = NoteChunkLinkModel.select().where(NoteChunkLinkModel.chunk == chunk).count()
            is_covered = card_count > 0
            if is_covered:
                covered_count += 1
                badge = "●"
                status_text = f"{card_count} carte(s)"
            else:
                badge = "○"
                status_text = "Trou (0 carte)"

            title_str = chunk.heading_path or (f"Page {chunk.page_number}" if chunk.page_number else f"Section #{chunk.chunk_index + 1}")
            item_text = f"{badge} {title_str}  ·  {status_text}"

            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, chunk.id)
            if is_covered:
                item.setForeground(QColor(DesignTokens.COLOR_GREEN))
            else:
                item.setForeground(QColor(DesignTokens.COLOR_YELLOW))
            self.chapters_list.addItem(item)

        total_chunks = len(chunks)
        percent = (covered_count / total_chunks * 100) if total_chunks > 0 else 0
        total_cards = NoteChunkLinkModel.select().join(DocumentChunkModel).where(DocumentChunkModel.document == self.doc).count()
        self.lbl_doc_summary.setText(f"Couverture : {percent:.0f}% ({covered_count}/{total_chunks} sections · {total_cards} cartes)")
        if percent >= 90:
            self.lbl_doc_summary.setStyleSheet(
                f"background-color: rgba(16,185,129,0.15); color: {DesignTokens.COLOR_GREEN}; border: 1px solid rgba(16,185,129,0.3); border-radius: 9999px; padding: 4px 10px;"
            )
        elif percent >= 50:
            self.lbl_doc_summary.setStyleSheet(
                f"background-color: rgba(245,158,11,0.15); color: {DesignTokens.COLOR_YELLOW}; border: 1px solid rgba(245,158,11,0.3); border-radius: 9999px; padding: 4px 10px;"
            )
        else:
            self.lbl_doc_summary.setStyleSheet(
                f"background-color: rgba(239,68,68,0.15); color: {DesignTokens.COLOR_RED}; border: 1px solid rgba(239,68,68,0.3); border-radius: 9999px; padding: 4px 10px;"
            )

        if self.chapters_list.count() > 0:
            self.chapters_list.setCurrentRow(0)
            first_id = self.chapters_list.item(0).data(Qt.ItemDataRole.UserRole)
            self.inspect_chunk(first_id)

    def _on_chapter_item_clicked(self, item: QListWidgetItem) -> None:
        chunk_id = item.data(Qt.ItemDataRole.UserRole)
        if chunk_id:
            self.inspect_chunk(chunk_id)

    def inspect_chunk(self, chunk_id: int) -> None:
        chunk = DocumentChunkModel.get_or_none(DocumentChunkModel.id == chunk_id)
        if not chunk:
            return

        header_title = chunk.heading_path or (f"Page {chunk.page_number}" if chunk.page_number else f"Section #{chunk.chunk_index + 1}")
        safe_content = chunk.content.replace("\n", "<br>")
        html_preview = (
            f"<h4 style='color: {DesignTokens.TEXT_PRIMARY}; margin-bottom: 6px;'>{header_title}</h4>"
            f"<hr style='border: 1px solid {DesignTokens.BORDER_COLOR};'/>"
            f"<p style='color: {DesignTokens.TEXT_SECONDARY}; line-height: 1.5;'>{safe_content}</p>"
        )
        self.text_preview.setHtml(html_preview)

        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        links = list(NoteChunkLinkModel.select().where(NoteChunkLinkModel.chunk == chunk))

        if not links:
            box = QFrame()
            box.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_INPUT}; border-radius: 6px; border: 1px dashed {DesignTokens.COLOR_YELLOW}; padding: 16px; }}")
            b_layout = QVBoxLayout(box)
            b_layout.setSpacing(10)

            lbl_warn = QLabel("Trou de cours détecté : Aucune flashcard n'a encore été générée pour cette section.")
            lbl_warn.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
            lbl_warn.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; border: none; background: transparent;")
            lbl_warn.setWordWrap(True)
            b_layout.addWidget(lbl_warn)

            lbl_desc = QLabel("Forgez des cartes ciblées pour combler ce manque et garantir la complétion de votre apprentissage.")
            lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
            lbl_desc.setWordWrap(True)
            b_layout.addWidget(lbl_desc)

            btn_gen = PrimaryButton("Forger cette section maintenant")
            btn_gen.setIcon(load_phosphor_icon("ph.sparkle", color="white"))
            btn_gen.clicked.connect(lambda: self._on_forge_chunk(chunk.id))
            b_layout.addWidget(btn_gen)

            self.cards_layout.addWidget(box)
        else:
            lbl_cnt = QLabel(f"{len(links)} carte(s) Anki forgée(s) depuis cette section :")
            lbl_cnt.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
            lbl_cnt.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; margin-bottom: 4px; border: none; background: transparent;")
            self.cards_layout.addWidget(lbl_cnt)

            for link in links:
                note = link.note
                card_box = QFrame()
                card_box.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_INPUT}; border-radius: 6px; border: 1px solid {DesignTokens.BORDER_COLOR}; padding: 10px; }}")
                c_layout = QVBoxLayout(card_box)
                c_layout.setContentsMargins(8, 8, 8, 8)
                c_layout.setSpacing(6)

                import json
                from ankiforge.database.models import CardModel, NoteVersionModel

                fields = {}
                if note:
                    active_ver = NoteVersionModel.get_or_none(
                        NoteVersionModel.note == note,
                        NoteVersionModel.is_active == True,  # noqa: E712
                    )
                    if active_ver and active_ver.content:
                        try:
                            fields = json.loads(active_ver.content)
                        except Exception as e:
                            logger.debug("Erreur parsing active_ver content: %s", e)

                    if not fields and hasattr(note, "fields_data") and getattr(note, "fields_data", None):
                        try:
                            fields = json.loads(note.fields_data)
                        except Exception as e:
                            logger.debug("Erreur parsing fields_data: %s", e)

                front = fields.get("Front") or fields.get("Recto") or fields.get("Question") or "Carte Anki"
                back = fields.get("Back") or fields.get("Verso") or fields.get("Answer") or ""

                deck_name = "Général"
                if note:
                    card = CardModel.get_or_none(CardModel.note == note)
                    if card and card.deck:
                        deck_name = card.deck.name
                    elif hasattr(note, "deck") and getattr(note, "deck", None):
                        deck_name = getattr(note.deck, "name", "Général")

                top_row = QHBoxLayout()
                lbl_deck = QLabel(f"Paquet : {deck_name}")
                lbl_deck.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; border: none; background: transparent;")
                top_row.addWidget(lbl_deck)
                top_row.addStretch()
                c_layout.addLayout(top_row)

                lbl_front = QLabel(f"Q : {front}")
                lbl_front.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px; border: none; background: transparent;")
                lbl_front.setWordWrap(True)
                c_layout.addWidget(lbl_front)

                if back:
                    lbl_back = QLabel(f"R : {back}")
                    lbl_back.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; border: none; background: transparent;")
                    lbl_back.setWordWrap(True)
                    c_layout.addWidget(lbl_back)

                if link.is_hallucinating:
                    lbl_bad = QLabel("Alerte : Incohérence sémantique détectée face au document source")
                    lbl_bad.setStyleSheet(f"color: {DesignTokens.COLOR_RED}; font-size: 10px; font-weight: bold;")
                    c_layout.addWidget(lbl_bad)

                self.cards_layout.addWidget(card_box)

            btn_more = SecondaryButton("+ Générer plus de cartes pour ce chapitre")
            btn_more.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))
            btn_more.clicked.connect(lambda: self._on_forge_chunk(chunk.id))
            self.cards_layout.addWidget(btn_more)

    def _on_forge_chunk(self, chunk_id: int) -> None:
        chunk = DocumentChunkModel.get_or_none(DocumentChunkModel.id == chunk_id)
        if not chunk:
            return
        doc_title = self.doc.title if self.doc else "Document"
        section_name = chunk.heading_path or (f"Page {chunk.page_number}" if chunk.page_number else f"Section #{chunk.chunk_index + 1}")
        self.request_navigation.emit(
            "creation",
            {
                "text_source": chunk.content,
                "source_title": f"{doc_title} - {section_name}",
                "chunk_id": chunk.id,
            },
        )

    def _on_fill_all_orphans(self) -> None:
        chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == self.doc).order_by(DocumentChunkModel.chunk_index))
        linked_chunk_ids = {link.chunk_id for link in NoteChunkLinkModel.select(NoteChunkLinkModel.chunk_id).join(DocumentChunkModel).where(DocumentChunkModel.document == self.doc)}

        orphan = next((c for c in chunks if c.id not in linked_chunk_ids), None)
        if orphan:
            self._on_forge_chunk(orphan.id)
        else:
            show_toast(self, "Toutes les sections de ce cours sont déjà couvertes !")

    def _on_reindex_faiss(self) -> None:
        from ankiforge.services.workers.coverage_worker import CoverageWorker

        show_toast(self, "Indexation FAISS et structuration en cours...")
        self._coverage_worker = CoverageWorker(self.doc.id)
        self._coverage_worker.finished_processing.connect(self._on_coverage_finished)
        self._coverage_worker.start()

    def _on_coverage_finished(self) -> None:
        show_toast(self, "Indexation FAISS terminée avec succès !")
        self.load_chunks()


class AISourcesDiagnosticTab(QWidget):
    """Onglet de diagnostic et santé des documents : synthèse globale et inspection détaillée."""

    request_navigation = Signal(str, object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # PAGE 0 : Grille des Documents
        self.page_grid = QWidget()
        grid_page_layout = QVBoxLayout(self.page_grid)
        grid_page_layout.setContentsMargins(12, 12, 12, 12)
        grid_page_layout.setSpacing(10)
        self.stack.addWidget(self.page_grid)

        # PAGE 1 : Inspecteur de Document
        self.page_inspector = QWidget()
        inspector_layout = QVBoxLayout(self.page_inspector)
        inspector_layout.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.page_inspector)

        # 1. Barre de KPIs globaux de la Forge
        kpi_header = QFrame()
        kpi_header.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        kpi_layout = QHBoxLayout(kpi_header)
        kpi_layout.setContentsMargins(12, 8, 12, 8)
        kpi_layout.setSpacing(12)

        def _make_kpi_chip(icon_name: str, icon_color: str, title: str):
            chip = QFrame()
            chip.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_MAIN};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                }}
            """)
            c_lay = QHBoxLayout(chip)
            c_lay.setContentsMargins(10, 5, 10, 5)
            c_lay.setSpacing(8)
            ico = QLabel()
            ico.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(16, 16))
            ico.setStyleSheet("border: none; background: transparent;")
            lbl_t = QLabel(title)
            lbl_t.setFont(QFont(DesignTokens.FONT_MAIN, 10))
            lbl_t.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
            lbl_v = QLabel("--")
            lbl_v.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
            lbl_v.setStyleSheet(f"color: {icon_color}; border: none; background: transparent;")
            c_lay.addWidget(ico)
            c_lay.addWidget(lbl_t)
            c_lay.addWidget(lbl_v)
            return chip, lbl_v

        chip_docs, self.lbl_kpi_docs_val = _make_kpi_chip("ph.files", DesignTokens.COLOR_BLUE, "Documents")
        chip_cov, self.lbl_kpi_coverage_val = _make_kpi_chip("ph.target", DesignTokens.COLOR_GREEN, "Couverture")
        chip_orphans, self.lbl_kpi_orphans_val = _make_kpi_chip("ph.warning-circle", DesignTokens.COLOR_YELLOW, "Sections orphelines")
        chip_cards, self.lbl_kpi_cards_val = _make_kpi_chip("ph.lightning", DesignTokens.COLOR_PURPLE, "Cartes forgées")

        kpi_layout.addWidget(chip_docs)
        kpi_layout.addWidget(chip_cov)
        kpi_layout.addWidget(chip_orphans)
        kpi_layout.addWidget(chip_cards)
        kpi_layout.addStretch()

        grid_page_layout.addWidget(kpi_header)

        # 2. Barre de Filtres et Recherche
        filter_bar = QFrame()
        filter_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        f_outer = QVBoxLayout(filter_bar)
        f_outer.setContentsMargins(12, 8, 12, 8)
        f_outer.setSpacing(6)

        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self.search_input = GlowLineEdit()
        self.search_input.setPlaceholderText("Rechercher un document ou cours...")
        self.search_input.setMinimumWidth(220)
        self.search_input.textChanged.connect(self.refresh_data)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["Tous les statuts", "Couverts à 100%", "Trous à forger (<100%)", "Non indexés"])
        self.status_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 8px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self.status_combo.currentIndexChanged.connect(self.refresh_data)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(
            [
                "Taux de couverture ↓",
                "Taux de couverture ↑",
                "Nombre de cartes ↓",
                "Sections orphelines ↓",
                "Nom du fichier (A-Z)",
                "Date d'importation ↓",
            ]
        )
        self.sort_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 8px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self.sort_combo.currentIndexChanged.connect(self.refresh_data)

        self.btn_refresh = SecondaryButton("Actualiser")
        self.btn_refresh.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_refresh.clicked.connect(self.refresh_data)

        row1.addWidget(self.search_input, 1)
        row1.addWidget(self.status_combo)
        row1.addWidget(self.sort_combo)
        row1.addWidget(self.btn_refresh)
        f_outer.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(6)

        lbl_filter = QLabel("Formats :")
        lbl_filter.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        lbl_filter.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        row2.addWidget(lbl_filter)

        self.btn_filter_all = SecondaryButton("Tous")
        self.btn_filter_pdf = SecondaryButton("PDF")
        self.btn_filter_md = SecondaryButton("Markdown")
        self.btn_filter_web = SecondaryButton("Web & Vidéo")
        self.current_format_filter = "all"

        self.format_buttons = {
            "all": self.btn_filter_all,
            "pdf": self.btn_filter_pdf,
            "md": self.btn_filter_md,
            "web": self.btn_filter_web,
        }

        for fmt, b in self.format_buttons.items():
            b.setFixedHeight(26)
            b.clicked.connect(lambda _, f=fmt: self._set_format_filter(f))
            row2.addWidget(b)

        row2.addStretch()
        f_outer.addLayout(row2)

        grid_page_layout.addWidget(filter_bar)

        # 3. Grille des Cartes de Documents (2 colonnes)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent;")

        self.grid_content = QWidget()
        self.grid_content.setStyleSheet("background: transparent;")
        self.grid_layout = QGridLayout(self.grid_content)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(12)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.grid_content)
        grid_page_layout.addWidget(self.scroll_area, 1)

        self.refresh_data()

    def _set_format_filter(self, fmt: str) -> None:
        self.current_format_filter = fmt
        self.refresh_data()

    def refresh_data(self) -> None:
        from ankiforge.ui.components.linter_widgets import SourceDiagnosticCardWidget

        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        docs = list(DocumentModel.select())
        search_text = self.search_input.text().strip().lower()

        docs_data = []
        total_forge_chunks = 0
        total_forge_covered = 0
        total_forge_orphans = 0
        total_forge_cards = 0

        for doc in docs:
            ext = (doc.file_type or "md").lower()
            title = doc.original_media.original_name if doc.original_media else doc.title

            chunks = list(doc.chunks)
            total_chunks = len(chunks)
            linked_chunk_ids = {link.chunk_id for link in NoteChunkLinkModel.select(NoteChunkLinkModel.chunk_id).join(DocumentChunkModel).where(DocumentChunkModel.document == doc)}
            covered_chunks = len(linked_chunk_ids)
            orphan_chunks = max(0, total_chunks - covered_chunks)
            total_cards = NoteChunkLinkModel.select().join(DocumentChunkModel).where(DocumentChunkModel.document == doc).count()
            coverage_pct = (covered_chunks / total_chunks * 100) if total_chunks > 0 else 0.0
            density = (total_cards / total_chunks) if total_chunks > 0 else 0.0
            is_indexed = total_chunks > 0
            word_count = getattr(doc, "word_count", None) or (len(doc.content.split()) if doc.content else 0)

            total_forge_chunks += total_chunks
            total_forge_covered += covered_chunks
            total_forge_orphans += orphan_chunks
            total_forge_cards += total_cards

            if self.current_format_filter != "all":
                if self.current_format_filter == "pdf" and ext != "pdf":
                    continue
                if self.current_format_filter == "md" and ext not in ("md", "markdown"):
                    continue
                if self.current_format_filter == "web" and ext not in ("web", "yt", "youtube"):
                    continue

            if search_text and search_text not in title.lower():
                continue

            status_idx = self.status_combo.currentIndex()
            if status_idx == 1 and (not is_indexed or coverage_pct < 100):
                continue
            elif status_idx == 2 and (not is_indexed or orphan_chunks == 0):
                continue
            elif status_idx == 3 and is_indexed:
                continue

            docs_data.append(
                {
                    "doc_id": doc.id,
                    "extension": ext,
                    "title": title,
                    "coverage_pct": coverage_pct,
                    "is_indexed": is_indexed,
                    "total_chunks": total_chunks,
                    "covered_chunks": covered_chunks,
                    "orphan_chunks": orphan_chunks,
                    "total_cards": total_cards,
                    "density": density,
                    "word_count": word_count,
                    "created_at": getattr(doc, "created_at", None),
                }
            )

        self.lbl_kpi_docs_val.setText(f"{len(docs)}")
        avg_cov = (total_forge_covered / total_forge_chunks * 100) if total_forge_chunks > 0 else 0.0
        self.lbl_kpi_coverage_val.setText(f"{avg_cov:.0f}%")
        self.lbl_kpi_orphans_val.setText(f"{total_forge_orphans}")
        self.lbl_kpi_cards_val.setText(f"{total_forge_cards}")

        sort_idx = self.sort_combo.currentIndex()
        if sort_idx == 0:
            docs_data.sort(key=lambda d: d["coverage_pct"], reverse=True)
        elif sort_idx == 1:
            docs_data.sort(key=lambda d: d["coverage_pct"])
        elif sort_idx == 2:
            docs_data.sort(key=lambda d: d["total_cards"], reverse=True)
        elif sort_idx == 3:
            docs_data.sort(key=lambda d: d["orphan_chunks"], reverse=True)
        elif sort_idx == 4:
            docs_data.sort(key=lambda d: d["title"].lower())
        elif sort_idx == 5:
            docs_data.sort(key=lambda d: str(d["created_at"]), reverse=True)

        row = 0
        col = 0
        for data in docs_data:
            card = SourceDiagnosticCardWidget(data)
            card.inspect_requested.connect(self.show_inspector)
            self.grid_layout.addWidget(card, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1

    def _on_card_forge_orphan_requested(self, doc_id: int) -> None:
        doc = DocumentModel.get_or_none(DocumentModel.id == doc_id)
        if not doc:
            return

        chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc).order_by(DocumentChunkModel.chunk_index))
        linked_chunk_ids = {link.chunk_id for link in NoteChunkLinkModel.select(NoteChunkLinkModel.chunk_id).join(DocumentChunkModel).where(DocumentChunkModel.document == doc)}

        orphan = next((c for c in chunks if c.id not in linked_chunk_ids), None)
        if orphan:
            section_name = orphan.heading_path or (f"Page {orphan.page_number}" if orphan.page_number else f"Section #{orphan.chunk_index + 1}")
            self.request_navigation.emit(
                "creation",
                {
                    "text_source": orphan.content,
                    "source_title": f"{doc.title} - {section_name}",
                    "chunk_id": orphan.id,
                },
            )
        else:
            show_toast(self, "Toutes les sections de ce cours sont déjà couvertes !")

    def _on_card_reindex_requested(self, doc_id: int) -> None:
        from ankiforge.services.workers.coverage_worker import CoverageWorker

        show_toast(self, "Indexation FAISS en cours...")
        self._coverage_worker = CoverageWorker(doc_id)
        self._coverage_worker.finished_processing.connect(self.refresh_data)
        self._coverage_worker.start()

    def show_inspector(self, doc_id: int) -> None:
        while self.page_inspector.layout().count():
            item = self.page_inspector.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        panel = DocumentInspectorPanel(doc_id, self)
        panel.back_requested.connect(lambda: self.stack.setCurrentIndex(0))
        panel.request_navigation.connect(self.request_navigation)
        self.page_inspector.layout().addWidget(panel)
        self.stack.setCurrentIndex(1)
