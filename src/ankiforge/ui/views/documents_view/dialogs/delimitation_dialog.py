import json
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

from ankiforge.database.models import DocumentChunkModel, DocumentModel, DocumentPageModel
from ankiforge.services.ai.rag_service import RAGService
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.components import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.paths import get_resource_path

logger = logging.getLogger(__name__)


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

        self.setWindowTitle(f"Délimiter les pages et sections — {doc.title}")
        self.resize(720, 710)
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
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

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
        layout.addWidget(header_card)

        # 2. Plage de pages
        pages_card = QFrame()
        pages_card.setObjectName("pagesCard")
        pages_card_layout = QVBoxLayout(pages_card)
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
        layout.addWidget(pages_card)

        # 3. Liste des sections et chapitres cochables
        sections_card = QFrame()
        sections_card.setObjectName("sectionsCard")
        sections_layout = QVBoxLayout(sections_card)
        sections_layout.setContentsMargins(12, 10, 12, 10)
        sections_layout.setSpacing(8)

        sec_header = QHBoxLayout()
        lbl_sec2 = QLabel("2. SECTIONS & TITRES DÉTECTÉS")
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
                padding: 6px 8px;
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
                width: 16px;
                height: 16px;
                border: 1px solid {DesignTokens.TEXT_MUTED};
                border-radius: 4px;
                background-color: {DesignTokens.BG_INPUT};
            }}
            QListWidget::indicator:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QListWidget::indicator:checked {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                image: url({check_icon_path});
            }}
        """)
        self.sections_list.setMinimumHeight(240)
        self.sections_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.sections_list.itemChanged.connect(lambda _: self._update_kpi())
        sections_layout.addWidget(self.sections_list, 1)
        layout.addWidget(sections_card, 1)

        self._populate_sections()
        self.setFocus()

        # Connecteurs réactifs pour les spinboxes
        self.spin_p_start.valueChanged.connect(lambda _: self._update_kpi())
        self.spin_p_end.valueChanged.connect(lambda _: self._update_kpi())

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

    def _populate_sections(self) -> None:
        """Remplit la liste avec les sections sémantiques en appliquant les exclusions mémorisées ou le filtre anti-bruit."""
        self.sections_list.blockSignals(True)
        self.sections_list.clear()

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

        for c_data in chunks_to_display:
            title_str = c_data.get("heading_path") or (f"Page {c_data.get('page_number')}" if c_data.get("page_number") else f"Section #{c_data.get('index', 0) + 1}")
            item = QListWidgetItem(title_str)
            item.setIcon(load_phosphor_icon("ph.article", color=DesignTokens.TEXT_SECONDARY))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)

            # Si des exclusions sont sauvegardées, on respecte fidèlement les choix précédents
            # Sinon, on applique le filtre anti-bruit par défaut
            low_title = title_str.lower()
            is_checked = (low_title not in excluded_list) if excluded_list else not any(k in low_title for k in noise_keywords)

            item.setCheckState(Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, title_str)
            self.sections_list.addItem(item)

        self.sections_list.blockSignals(False)

    def _update_kpi(self) -> None:
        """Met à jour l'indicateur de sections retenues et exclues."""
        total = self.sections_list.count()
        checked = sum(1 for i in range(total) if self.sections_list.item(i).checkState() == Qt.CheckState.Checked)
        excluded = total - checked
        self.lbl_selection_kpi.setText(f"✅ {checked} retenues • 🚫 {excluded} exclues")

    def _set_all_checked(self, checked: bool) -> None:
        self.sections_list.blockSignals(True)
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.sections_list.count()):
            self.sections_list.item(i).setCheckState(state)
        self.sections_list.blockSignals(False)
        self._update_kpi()

    def _apply_smart_filter(self, notify: bool = True) -> None:
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
        self.sections_list.blockSignals(True)
        for i in range(self.sections_list.count()):
            item = self.sections_list.item(i)
            txt = item.text().lower()
            if any(k in txt for k in noise_keywords):
                item.setCheckState(Qt.CheckState.Unchecked)
            else:
                item.setCheckState(Qt.CheckState.Checked)
        self.sections_list.blockSignals(False)
        self._update_kpi()
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
            page_number = chunk.get("page_number")
            if page_number is not None and not page_start <= page_number <= page_end:
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
