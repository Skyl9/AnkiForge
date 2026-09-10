import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DocumentChunkModel, DocumentModel
from ankiforge.services.ai.rag_service import RAGService
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.ui.components import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class DocumentDelimitationDialog(QDialog):
    """
    Dialogue interactif de délimitation de documents :
    Permet de sélectionner des plages de pages utiles, de filtrer les sections
    et d'exclure les parties non pédagogiques (sommaires, remerciements, bibliographies).
    """

    def __init__(self, doc: DocumentModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.doc = doc
        self._all_chunks = ChunkingService.extract_chunks(doc.content or "", file_type=doc.file_type or "md")
        page_numbers = [chunk["page_number"] for chunk in self._all_chunks if chunk.get("page_number") is not None]
        self._max_page = max(page_numbers, default=1)
        self.setWindowTitle(f"Délimiter les pages et sections — {doc.title}")
        self.resize(640, 540)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 1. En-tête descriptif
        header_card = QFrame()
        header_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 4px;
            }}
        """)
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(12, 10, 12, 10)
        h_layout.setSpacing(4)

        header_top = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.scissors", color=DesignTokens.ACCENT_PRIMARY).pixmap(20, 20))
        title_lbl = QLabel(f"Délimiter les pages et sections : <b>{doc.title}</b>")
        title_lbl.setStyleSheet(f"font-size: 14px; color: {DesignTokens.TEXT_PRIMARY};")
        header_top.addWidget(icon_lbl)
        header_top.addWidget(title_lbl, 1)
        h_layout.addLayout(header_top)

        desc_lbl = QLabel("Sélectionnez une plage de pages et les sections pertinentes pour exclure le bruit documentaire avant la forge et le RAG.")
        desc_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        desc_lbl.setWordWrap(True)
        h_layout.addWidget(desc_lbl)
        layout.addWidget(header_card)

        # 2. Plage de pages
        pages_card = QFrame()
        pages_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        pages_card_layout = QVBoxLayout(pages_card)
        pages_card_layout.setContentsMargins(12, 10, 12, 10)
        pages_card_layout.setSpacing(8)

        lbl_sec1 = QLabel("1. BORNES DE PAGINATION")
        lbl_sec1.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: bold; font-size: 10px; letter-spacing: 0.5px;")
        pages_card_layout.addWidget(lbl_sec1)

        pages_inputs = QHBoxLayout()
        lbl_p_start = QLabel("Page de début :")
        lbl_p_start.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;")
        self.spin_p_start = QSpinBox()
        self.spin_p_start.setRange(1, self._max_page)
        self.spin_p_start.setValue(1)
        self.spin_p_start.setStyleSheet(f"""
            QSpinBox {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 4px 8px;
            }}
        """)

        lbl_p_end = QLabel("Page de fin :")
        lbl_p_end.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;")
        self.spin_p_end = QSpinBox()
        self.spin_p_end.setRange(1, self._max_page)
        self.spin_p_end.setValue(self._max_page)
        self.spin_p_end.setStyleSheet(f"""
            QSpinBox {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 4px 8px;
            }}
        """)

        pages_inputs.addWidget(lbl_p_start)
        pages_inputs.addWidget(self.spin_p_start)
        pages_inputs.addSpacing(16)
        pages_inputs.addWidget(lbl_p_end)
        pages_inputs.addWidget(self.spin_p_end)
        pages_inputs.addStretch()
        pages_card_layout.addLayout(pages_inputs)
        layout.addWidget(pages_card)

        # 3. Liste des sections et chapitres cochables
        sections_card = QFrame()
        sections_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        sections_layout = QVBoxLayout(sections_card)
        sections_layout.setContentsMargins(12, 10, 12, 10)
        sections_layout.setSpacing(8)

        lbl_sec2 = QLabel("2. SÉLECTION DES CHAPITRES & SECTIONS DÉTECTÉS")
        lbl_sec2.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: bold; font-size: 10px; letter-spacing: 0.5px;")
        sections_layout.addWidget(lbl_sec2)

        # Actions rapides
        quick_btns = QHBoxLayout()
        btn_check_all = SecondaryButton("Tout sélectionner")
        btn_check_all.setFixedHeight(28)
        btn_check_all.setStyleSheet(f"font-size: 11px; padding: 4px 8px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        btn_check_all.clicked.connect(lambda: self._set_all_checked(True))

        btn_uncheck_all = SecondaryButton("Tout désélectionner")
        btn_uncheck_all.setFixedHeight(28)
        btn_uncheck_all.setStyleSheet(f"font-size: 11px; padding: 4px 8px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        btn_uncheck_all.clicked.connect(lambda: self._set_all_checked(False))

        btn_smart_filter = SecondaryButton("Filtre Intelligent IA")
        btn_smart_filter.setIcon(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_YELLOW))
        btn_smart_filter.setFixedHeight(28)
        btn_smart_filter.setStyleSheet(f"font-size: 11px; padding: 4px 10px; color: {DesignTokens.COLOR_YELLOW}; border: 1px solid {DesignTokens.COLOR_YELLOW};")
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
                padding: 6px 8px;
                border-radius: 4px;
                margin-bottom: 2px;
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        sections_layout.addWidget(self.sections_list, 1)
        layout.addWidget(sections_card, 1)

        self._populate_sections()
        self._apply_smart_filter(notify=False)

        # 4. Pied de page & validation
        footer = QHBoxLayout()
        self.chk_revectorize = QCheckBox("Re-vectoriser automatiquement dans FAISS après délimitation")
        self.chk_revectorize.setChecked(True)
        self.chk_revectorize.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
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

    def _populate_sections(self) -> None:
        """Remplit la liste avec les sections sémantiques déjà indexées ou déduites."""
        chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == self.doc).order_by(DocumentChunkModel.chunk_index))
        if chunks:
            for c in chunks:
                title_str = c.heading_path or (f"Page {c.page_number}" if c.page_number else f"Section #{c.chunk_index + 1}")
                item = QListWidgetItem(title_str)
                item.setIcon(load_phosphor_icon("ph.article", color=DesignTokens.TEXT_SECONDARY))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                item.setData(Qt.ItemDataRole.UserRole, title_str)
                self.sections_list.addItem(item)
        else:
            for c_data in self._all_chunks:
                title_str = c_data.get("heading_path") or (f"Page {c_data.get('page_number')}" if c_data.get("page_number") else f"Section #{c_data.get('index', 0) + 1}")
                item = QListWidgetItem(title_str)
                item.setIcon(load_phosphor_icon("ph.article", color=DesignTokens.TEXT_SECONDARY))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                item.setData(Qt.ItemDataRole.UserRole, title_str)
                self.sections_list.addItem(item)

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.sections_list.count()):
            self.sections_list.item(i).setCheckState(state)

    def _apply_smart_filter(self, notify: bool = True) -> None:
        noise_keywords = ["sommaire", "table des matières", "remerciements", "avant-propos", "préface", "bibliographie", "références", "annexes", "index", "glossaire", "copyright"]
        for i in range(self.sections_list.count()):
            item = self.sections_list.item(i)
            txt = item.text().lower()
            if any(k in txt for k in noise_keywords):
                item.setCheckState(Qt.CheckState.Unchecked)
            else:
                item.setCheckState(Qt.CheckState.Checked)
        if notify:
            show_toast(self, "Filtre intelligent appliqué : bruit documentaire exclu.")

    def _on_apply(self) -> None:
        page_start = self.spin_p_start.value()
        page_end = self.spin_p_end.value()
        if page_start > page_end:
            show_toast(self, "La page de début doit être inférieure ou égale à la page de fin.", is_error=True)
            return
        if page_end > self._max_page:
            show_toast(self, f"La page de fin ne peut pas dépasser la dernière page détectée ({self._max_page}).", is_error=True)
            return

        selected_headings = []
        for i in range(self.sections_list.count()):
            item = self.sections_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_headings.append(item.data(Qt.ItemDataRole.UserRole))

        retained_chunks = []
        for chunk in self._all_chunks:
            page_number = chunk.get("page_number")
            if page_number is not None and not page_start <= page_number <= page_end:
                continue
            h_path = chunk.get("heading_path", "")
            if not selected_headings or any(sh in h_path for sh in selected_headings) or not h_path:
                retained_chunks.append(chunk)

        if not retained_chunks:
            show_toast(self, "Aucun contenu ne correspond à cette sélection.", is_error=True)
            return

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

        if self.chk_revectorize.isChecked():
            try:
                rag = RAGService()
                rag.create_index(self.doc.id)
            except Exception as e:
                logger.warning("Erreur re-vectorisation FAISS : %s", e)

        self.accept()
