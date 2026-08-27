"""
Vue Library (Hub Documentaire & RAG Local) — Conforme au Design System & Maquette AnkiForge.

- Explorateur d'arborescence à gauche avec recherche dynamique et gestion de dossiers récursifs.
- Éditeur & Lecteur central détachable (PDF natif, Markdown KaTeX en direct, Terminal de logs).
- Barre d'actions responsive compacte et épurée :
  * ✂️ Délimiter / Chapitres : Dialogue interactif de sélection de plages de pages et filtrage de sections.
  * 🔮 Marker OCR : Extraction Deep Learning PDF vers Markdown KaTeX.
  * 📊 Vectoriser (RAG FAISS) : Statut en capsule et indexation vectorielle locale.
  * 💾 Sauvegarder & Compteur de mots live.
- Volet Droit à 2 onglets :
  * 📑 Onglet 1 : Sommaire & Couverture SRS (Jauge de couverture de cours, liste des sections et bouton ⚡ Forger).
  * 🔍 Onglet 2 : Recherche & Sandbox RAG (Banc de test sémantique vectoriel FAISS en temps réel).
"""

import logging
import pathlib
import shutil
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    FolderModel,
    NoteChunkLinkModel,
)
from ankiforge.services.ai.rag_service import RAGService
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.services.workers.coverage_worker import CoverageWorker
from ankiforge.services.workers.document_worker import DocumentWorker
from ankiforge.ui.components import (
    Badge,
    GlowLineEdit,
    IconButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


def apply_pill_style(badge: QLabel, color_hex: str) -> None:
    """Applique un style de capsule/pill parfaitement arrondie avec fond translucide et bordure assortie."""
    hex_c = color_hex.lstrip("#")
    if len(hex_c) == 6:
        r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    else:
        r, g, b = 100, 116, 139
    badge.setStyleSheet(f"""
        QLabel {{
            background-color: rgba({r}, {g}, {b}, 0.15) !important;
            color: {color_hex};
            border: 1px solid rgba({r}, {g}, {b}, 0.35);
            border-radius: 9999px;
            padding: 3px 10px;
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 0.5px;
        }}
    """)


# =====================================================================
# MODALE DE DÉLIMITATION DE DOCUMENT (DOCUMENTDELIMITATIONDIALOG)
# =====================================================================


class DocumentDelimitationDialog(QDialog):
    """
    Dialogue interactif de délimitation de documents :
    Permet de sélectionner des plages de pages utiles, de filtrer les sections
    et d'exclure les parties non pédagogiques (sommaires, remerciements, bibliographies).
    """

    def __init__(self, doc: DocumentModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.setWindowTitle(f"Délimitation du Document — {doc.title}")
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
        title_lbl = QLabel(f"Délimitation : <b>{doc.title}</b>")
        title_lbl.setStyleSheet(f"font-size: 14px; color: {DesignTokens.TEXT_PRIMARY};")
        header_top.addWidget(icon_lbl)
        header_top.addWidget(title_lbl, 1)
        h_layout.addLayout(header_top)

        desc_lbl = QLabel("Sélectionnez les chapitres et plages de pages pertinents pour exclure le bruit documentaire avant la forge et le RAG.")
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
        lbl_p_start = QLabel("Page Début :")
        lbl_p_start.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;")
        self.spin_p_start = QSpinBox()
        self.spin_p_start.setRange(1, 9999)
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

        lbl_p_end = QLabel("Page Fin :")
        lbl_p_end.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;")
        self.spin_p_end = QSpinBox()
        self.spin_p_end.setRange(1, 9999)
        self.spin_p_end.setValue(100)
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

        btn_apply = PrimaryButton("Appliquer la délimitation")
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
            raw_content = self.doc.content or ""
            extracted = ChunkingService.extract_chunks(raw_content, file_type=self.doc.file_type or "md")
            for c_data in extracted:
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
        """Décoche automatiquement les sections de métadonnées et bruit documentaire."""
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
        """Applique la délimitation et régénère les DocumentChunkModel."""
        selected_headings = []
        for i in range(self.sections_list.count()):
            item = self.sections_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_headings.append(item.data(Qt.ItemDataRole.UserRole))

        raw_content = self.doc.content or ""
        all_chunks = ChunkingService.extract_chunks(raw_content, file_type=self.doc.file_type or "md")

        retained_chunks = []
        for chunk in all_chunks:
            h_path = chunk.get("heading_path", "")
            if not selected_headings or any(sh in h_path for sh in selected_headings) or not h_path:
                retained_chunks.append(chunk)

        if not retained_chunks:
            retained_chunks = all_chunks

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


# =====================================================================
# MODALE DE TEST SÉMANTIQUE RAG (RAGTESTDIALOG)
# =====================================================================


class RAGTestDialog(QDialog):
    """Permet de tester instantanément la recherche RAG Hybride (FAISS + BM25 avec RRF) sur le document."""

    def __init__(self, doc: DocumentModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.setWindowTitle(f"Recherche RAG Hybride — {doc.title}")
        self.resize(680, 540)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header_top = QHBoxLayout()
        ico = QLabel()
        ico.setPixmap(load_phosphor_icon("ph.database", color=DesignTokens.COLOR_GREEN).pixmap(20, 20))
        title_lbl = QLabel(f"Interroger l'index RAG : <b>{doc.title}</b>")
        title_lbl.setStyleSheet(f"font-size: 13px; color: {DesignTokens.TEXT_PRIMARY};")
        header_top.addWidget(ico)
        header_top.addWidget(title_lbl, 1)
        layout.addLayout(header_top)

        # Ligne de configuration de mode
        mode_row = QHBoxLayout()
        lbl_mode = QLabel("Canal de recherche :")
        lbl_mode.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: bold;")
        self.mode_cb = QComboBox()
        self.mode_cb.setFixedHeight(28)
        self.mode_cb.addItem("🧬 RAG Hybride (FAISS Dense + BM25 Sparse avec RRF)", "hybrid")
        self.mode_cb.addItem("🌌 Sémantique Dense Pure (FAISS L2)", "dense")
        self.mode_cb.addItem("🔤 Lexicale Exacte Pure (BM25 Okapi)", "sparse")
        self.mode_cb.setStyleSheet(f"""
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 2px 8px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 11px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 18px;
            }}
        """)
        mode_row.addWidget(lbl_mode)
        mode_row.addWidget(self.mode_cb, 1)
        layout.addLayout(mode_row)

        # Barre de recherche
        search_row = QHBoxLayout()
        self.search_input = GlowLineEdit()
        self.search_input.setPlaceholderText("Posez une question ou entrez des mots-clés techniques...")
        self.search_input.returnPressed.connect(self._on_search)

        btn_search = PrimaryButton("Rechercher")
        btn_search.setIcon(load_phosphor_icon("ph.magnifying-glass", color="white"))
        btn_search.clicked.connect(self._on_search)

        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(btn_search)
        layout.addLayout(search_row)

        self.results_list = QListWidget()
        self.results_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 6px;
            }}
            QListWidget::item {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                margin-bottom: 6px;
                padding: 8px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QListWidget::item:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        layout.addWidget(self.results_list, 1)

    def _on_search(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            return

        self.results_list.clear()
        try:
            mode = self.mode_cb.currentData() or "hybrid"
            rag = RAGService()
            results = rag.search(self.doc.id, query, top_k=4, mode=mode)
            if not results:
                self.results_list.addItem(QListWidgetItem("Aucun fragment pertinent trouvé pour cette requête."))
                return

            for r in results:
                loc = r.get("heading_path") or (f"Page {r.get('page_number')}" if r.get("page_number") else f"Section #{r.get('chunk_index', 0) + 1}")
                channel = r.get("channel", "hybrid")
                rel_pct = r.get("relevance_pct", 0)

                if channel == "hybrid":
                    badge_info = f"🧬 RRF: {r.get('rrf_score', 0.0):.5f} • FAISS: #{r.get('dense_rank', '-')} • BM25: #{r.get('sparse_rank', '-')}"
                elif channel == "dense_only":
                    badge_info = f"🌌 FAISS: #{r.get('dense_rank', '-')} (score: {r.get('dense_score', 0.0)})"
                elif channel == "sparse_only":
                    badge_info = f"🔤 BM25: #{r.get('sparse_rank', '-')} (score: {r.get('sparse_score', 0.0)})"
                else:
                    badge_info = "📄 BDD Directe"

                content_snippet = r.get("content", "")[:180] + "..." if len(r.get("content", "")) > 180 else r.get("content", "")
                item_txt = f"📍 {loc}  (Pertinence : {rel_pct}%)  [{badge_info}]\n{content_snippet}"
                item = QListWidgetItem(item_txt)
                item.setData(Qt.ItemDataRole.UserRole, r)
                self.results_list.addItem(item)

        except Exception as e:
            self.results_list.addItem(QListWidgetItem(f"Erreur recherche RAG : {e}"))


# =====================================================================
# WIDGET D'ARBRE DE DOCUMENTS AVEC DRAG & DROP & FILTRAGE DYNAMIQUE
# =====================================================================


class DocumentTreeWidget(QTreeWidget):
    """QTreeWidget customisé pour supporter le Drag & Drop, l'arborescence et le filtrage rapide."""

    itemMoved = Signal(object, object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def dropEvent(self, event: QDropEvent) -> None:
        source_item = self.currentItem()
        if not source_item:
            event.ignore()
            return

        source_data = source_item.data(0, Qt.ItemDataRole.UserRole)
        target_item = self.itemAt(event.position().toPoint())
        target_data = target_item.data(0, Qt.ItemDataRole.UserRole) if target_item else None

        event.ignore()
        if source_item == target_item:
            return

        if source_data:
            self.itemMoved.emit(source_data, target_data)

    def filter_text(self, query: str) -> None:
        """Filtre récursivement les documents et dossiers affichés."""
        query = query.strip().lower()

        def _filter_item(item: QTreeWidgetItem) -> bool:
            match = query in item.text(0).lower()
            child_match = False
            for i in range(item.childCount()):
                child = item.child(i)
                if _filter_item(child):
                    child_match = True
            is_visible = match or child_match or not query
            item.setHidden(not is_visible)
            if child_match and query:
                item.setExpanded(True)
            return is_visible

        for i in range(self.topLevelItemCount()):
            _filter_item(self.topLevelItem(i))


# =====================================================================
# CLASSE PRINCIPALE : DOCUMENTSVIEW (HUB DOCUMENTAIRE & RAG)
# =====================================================================


class DocumentsView(QWidget):
    """
    Vue My Documents / Library — 100% Conforme au Design System AnkiForge.
    """

    request_navigation = Signal(str, object)

    def __init__(self, ai_manager: Optional[Any] = None, profile_name: Optional[str] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.profile_name = profile_name
        self._current_doc_id: Optional[int] = None
        self._dirty = False
        self.worker: Optional[DocumentWorker] = None
        self._coverage_worker: Optional[CoverageWorker] = None

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # ── 1. Panneau Gauche : Explorateur de Documents ──────────────────────
        self.explorer_panel = IdePanel(detachable=True)
        self.explorer_panel.setMinimumWidth(220)
        self.explorer_panel.setMaximumWidth(280)

        explorer_content = QWidget()
        explorer_layout = QVBoxLayout(explorer_content)
        explorer_layout.setContentsMargins(8, 8, 8, 8)
        explorer_layout.setSpacing(8)

        # Barre d'outils supérieure (Importer, URL, Nouveau dossier, Supprimer)
        explorer_toolbar = QHBoxLayout()
        explorer_toolbar.setSpacing(6)

        self.btn_import = SecondaryButton("Importer")
        self.btn_import.setIcon(load_phosphor_icon("ph.upload-simple", color=DesignTokens.TEXT_PRIMARY))
        self.btn_import.clicked.connect(self._on_import_file)

        self.btn_import_url = IconButton("ph.link", tooltip="Importer depuis le Web / YouTube", size=24)
        self.btn_import_url.clicked.connect(self._on_import_url)

        self.btn_new_folder = IconButton("ph.folder-plus", tooltip="Nouveau dossier", size=24)
        self.btn_new_folder.clicked.connect(self._on_new_folder)

        self.btn_delete = IconButton("ph.trash", tooltip="Supprimer", size=24)
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._on_delete_item)

        explorer_toolbar.addWidget(self.btn_import, 1)
        explorer_toolbar.addWidget(self.btn_import_url)
        explorer_toolbar.addWidget(self.btn_new_folder)
        explorer_toolbar.addWidget(self.btn_delete)
        explorer_layout.addLayout(explorer_toolbar)

        # Champ de recherche dynamique
        self.doc_search_input = GlowLineEdit()
        self.doc_search_input.setPlaceholderText("Rechercher un document...")
        self.doc_search_input.textChanged.connect(self._on_search_filter_changed)
        explorer_layout.addWidget(self.doc_search_input)

        # Tree Widget
        self.tree_explorer = DocumentTreeWidget()
        self.tree_explorer.setHeaderHidden(True)
        self.tree_explorer.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 4px;
            }}
            QTreeWidget::item {{
                padding: 6px;
                border-radius: 4px;
            }}
            QTreeWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QTreeWidget::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        explorer_layout.addWidget(self.tree_explorer, 1)

        self.explorer_panel.add_tab("Documents", explorer_content, "ph.files", closable=False)
        self.main_splitter.addWidget(self.explorer_panel)

        # ── 2. Panneau Central : Éditeur & Lecteur de Document ────────────────
        self.editor_panel = IdePanel(detachable=True)
        self.editor_stack = QStackedWidget()

        # PAGE 0 : État vide
        empty_page = QWidget()
        empty_layout = QVBoxLayout(empty_page)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(12)

        empty_icon = QLabel()
        empty_icon.setPixmap(load_phosphor_icon("ph.files", color=DesignTokens.TEXT_MUTED).pixmap(56, 56))
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_title = QLabel("Aucun document sélectionné")
        empty_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 16px; font-weight: bold;")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_subtitle = QLabel("Choisissez un document dans l'explorateur à gauche ou importez un nouveau support de cours (PDF, Markdown, Word, Page Web).")
        empty_subtitle.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px;")
        empty_subtitle.setWordWrap(True)
        empty_subtitle.setMaximumWidth(440)
        empty_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_layout.addWidget(empty_icon)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_subtitle)

        empty_actions = QHBoxLayout()
        empty_actions.setSpacing(10)
        btn_quick_import = PrimaryButton("Importer un fichier")
        btn_quick_import.setIcon(load_phosphor_icon("ph.upload-simple", color="white"))
        btn_quick_import.clicked.connect(self._on_import_file)

        btn_quick_url = SecondaryButton("Importer depuis le Web")
        btn_quick_url.setIcon(load_phosphor_icon("ph.link", color=DesignTokens.TEXT_PRIMARY))
        btn_quick_url.clicked.connect(self._on_import_url)

        empty_actions.addWidget(btn_quick_import)
        empty_actions.addWidget(btn_quick_url)
        empty_layout.addLayout(empty_actions)

        self.editor_stack.addWidget(empty_page)

        # PAGE 1 : Conteneur Éditeur
        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        # Toolbar du document (2 rangées aérées et responsives)
        doc_header_card = QFrame()
        doc_header_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        header_main_layout = QVBoxLayout(doc_header_card)
        header_main_layout.setContentsMargins(10, 8, 10, 8)
        header_main_layout.setSpacing(6)

        # Rangée 1 : Titre + Métriques + Sauvegarde
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(8)

        self.doc_title_lbl = QLabel("Sélectionnez un document")
        self.doc_title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 15px; font-weight: bold;")
        row1.addWidget(self.doc_title_lbl, 1)

        self.lbl_word_count = QLabel("0 mots")
        self.lbl_word_count.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px;")
        row1.addWidget(self.lbl_word_count)

        self.rag_status_pill = Badge("Non indexé", variant="status")
        apply_pill_style(self.rag_status_pill, "#94a3b8")
        row1.addWidget(self.rag_status_pill)

        self.btn_save = PrimaryButton("Sauvegarder")
        self.btn_save.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        self.btn_save.setFixedHeight(28)
        self.btn_save.setStyleSheet("font-size: 11px; padding: 4px 10px;")
        self.btn_save.clicked.connect(self._on_save_document)
        row1.addWidget(self.btn_save)

        header_main_layout.addLayout(row1)

        # Rangée 2 : Sélecteur de Mode + Outils IA
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(6)

        # Basculeur de mode (PDF / Markdown / Terminal)
        self.view_toggle_frame = QFrame()
        self.view_toggle_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 12px;
            }}
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {DesignTokens.TEXT_MUTED};
                font-weight: 600;
                border-radius: 10px;
                padding: 3px 8px;
                font-size: 11px;
            }}
            QPushButton:checked {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                color: white;
            }}
        """)
        toggle_layout = QHBoxLayout(self.view_toggle_frame)
        toggle_layout.setContentsMargins(2, 2, 2, 2)
        toggle_layout.setSpacing(1)

        self.btn_view_pdf = QPushButton("PDF")
        self.btn_view_pdf.setIcon(load_phosphor_icon("ph.file-pdf", color=DesignTokens.COLOR_RED))
        self.btn_view_pdf.setCheckable(True)
        self.btn_view_pdf.setChecked(True)

        self.btn_view_md = QPushButton("MD")
        self.btn_view_md.setIcon(load_phosphor_icon("ph.markdown-logo", color=DesignTokens.COLOR_YELLOW))
        self.btn_view_md.setCheckable(True)

        self.btn_view_term = QPushButton("Logs")
        self.btn_view_term.setIcon(load_phosphor_icon("ph.terminal-window", color=DesignTokens.COLOR_BLUE))
        self.btn_view_term.setCheckable(True)

        toggle_layout.addWidget(self.btn_view_pdf)
        toggle_layout.addWidget(self.btn_view_md)
        toggle_layout.addWidget(self.btn_view_term)

        self.btn_view_pdf.clicked.connect(lambda: self._on_view_toggled("pdf"))
        self.btn_view_md.clicked.connect(lambda: self._on_view_toggled("md"))
        self.btn_view_term.clicked.connect(lambda: self._on_view_toggled("term"))

        row2.addWidget(self.view_toggle_frame)
        row2.addStretch()

        # Outils IA & Actions
        self.btn_delimit = SecondaryButton("Délimiter")
        self.btn_delimit.setIcon(load_phosphor_icon("ph.scissors", color="#38bdf8"))
        self.btn_delimit.setToolTip("Délimiter les plages de pages et chapitres utiles")
        self.btn_delimit.setFixedHeight(26)
        self.btn_delimit.setStyleSheet(f"font-size: 11px; padding: 2px 8px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_delimit.clicked.connect(self._on_open_delimitation_dialog)
        row2.addWidget(self.btn_delimit)

        self.btn_marker = SecondaryButton("Marker OCR")
        self.btn_marker.setIcon(load_phosphor_icon("ph.magic-wand", color=DesignTokens.COLOR_PURPLE))
        self.btn_marker.setToolTip("Extraction Deep Learning PDF vers Markdown KaTeX via Marker")
        self.btn_marker.setFixedHeight(26)
        self.btn_marker.setStyleSheet(f"font-size: 11px; padding: 2px 8px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_marker.clicked.connect(self._on_run_marker_analysis)
        row2.addWidget(self.btn_marker)

        self.btn_rag = SecondaryButton("Vectoriser")
        self.btn_rag.setIcon(load_phosphor_icon("ph.database", color="#10b981"))
        self.btn_rag.setToolTip("Indexer ce document dans la base vectorielle locale FAISS")
        self.btn_rag.setFixedHeight(26)
        self.btn_rag.setStyleSheet(f"font-size: 11px; padding: 2px 8px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_rag.clicked.connect(self._on_vectorize_rag)
        row2.addWidget(self.btn_rag)

        self.btn_test_rag = IconButton("ph.magnifying-glass", tooltip="Recherche sémantique instantanée", size=22)
        self.btn_test_rag.clicked.connect(self._on_open_rag_test_dialog)
        row2.addWidget(self.btn_test_rag)

        header_main_layout.addLayout(row2)
        editor_layout.addWidget(doc_header_card)

        self.inner_editor_stack = QStackedWidget()

        from PySide6.QtPdf import QPdfDocument
        from PySide6.QtPdfWidgets import QPdfView

        self.pdf_document = QPdfDocument(self)
        self.pdf_viewer = QPdfView()
        self.pdf_viewer.setDocument(self.pdf_document)
        self.pdf_viewer.setPageMode(QPdfView.PageMode.MultiPage)
        self.inner_editor_stack.addWidget(self.pdf_viewer)

        # Éditeur Markdown pleine hauteur
        from ankiforge.ui.widgets.katex_editor import KaTeXEditor

        self.text_editor = KaTeXEditor()
        self.text_editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if hasattr(self.text_editor, "editor"):
            self.text_editor.editor.setReadOnly(False)
        self.inner_editor_stack.addWidget(self.text_editor)

        # Terminal view
        from PySide6.QtWidgets import QTextBrowser

        self.terminal_view = QTextBrowser()
        self.terminal_view.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.ACCENT_PRIMARY};
                font-family: '{DesignTokens.FONT_CODE}', Courier, monospace;
                padding: 12px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        self.inner_editor_stack.addWidget(self.terminal_view)
        editor_layout.addWidget(self.inner_editor_stack, 1)

        self.editor_stack.addWidget(editor_container)
        self.editor_panel.add_tab("Éditeur", self.editor_stack, "ph.file-text", closable=False)
        self.main_splitter.addWidget(self.editor_panel)

        # ── 3. Panneau Droit : Sommaire, Couverture & Sandbox RAG ──────────────
        self.coverage_panel = IdePanel(detachable=True)
        self.coverage_panel.setMinimumWidth(250)
        self.coverage_panel.setMaximumWidth(320)

        # --- TAB 1: Sommaire & Couverture SRS ---
        coverage_content = QWidget()
        cov_layout = QVBoxLayout(coverage_content)
        cov_layout.setContentsMargins(10, 10, 10, 10)
        cov_layout.setSpacing(10)

        # Carte de synthèse de couverture
        self.coverage_card = QFrame()
        self.coverage_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        cov_card_layout = QVBoxLayout(self.coverage_card)
        cov_card_layout.setContentsMargins(12, 10, 12, 10)
        cov_card_layout.setSpacing(6)

        self.lbl_coverage_summary = QLabel("📊 Couverture : 0%")
        self.lbl_coverage_summary.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 13px;")
        cov_card_layout.addWidget(self.lbl_coverage_summary)

        self.coverage_bar = QProgressBar()
        self.coverage_bar.setRange(0, 100)
        self.coverage_bar.setValue(0)
        self.coverage_bar.setTextVisible(False)
        self.coverage_bar.setFixedHeight(8)
        self.coverage_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {DesignTokens.COLOR_GREEN};
                border-radius: 3px;
            }}
        """)
        cov_card_layout.addWidget(self.coverage_bar)

        self.lbl_coverage_details = QLabel("0 sections analysées • 0 cartes liées")
        self.lbl_coverage_details.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px;")
        cov_card_layout.addWidget(self.lbl_coverage_details)

        cov_layout.addWidget(self.coverage_card)

        # Liste des chapitres
        self.chapters_list = QListWidget()
        self.chapters_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                font-size: 11px;
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        cov_layout.addWidget(self.chapters_list, 1)

        self.btn_forge_chapter = PrimaryButton("⚡ Forger la section")
        self.btn_forge_chapter.clicked.connect(self._on_forge_selected_chapter)
        cov_layout.addWidget(self.btn_forge_chapter)

        self.coverage_panel.add_tab("Sommaire", coverage_content, "ph.list-checks", closable=False)

        # --- TAB 2: Bac à Sable RAG (RAG Test Sandbox) ---
        rag_sandbox_content = QWidget()
        rag_layout = QVBoxLayout(rag_sandbox_content)
        rag_layout.setContentsMargins(10, 10, 10, 10)
        rag_layout.setSpacing(8)

        lbl_rag_desc = QLabel("Recherche Sémantique FAISS")
        lbl_rag_desc.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: bold; font-size: 11px; letter-spacing: 0.5px;")
        rag_layout.addWidget(lbl_rag_desc)

        rag_search_row = QHBoxLayout()
        self.rag_sandbox_input = GlowLineEdit()
        self.rag_sandbox_input.setPlaceholderText("Poser une question au document...")
        self.rag_sandbox_input.returnPressed.connect(self._on_sandbox_search)

        self.btn_sandbox_search = PrimaryButton("")
        self.btn_sandbox_search.setIcon(load_phosphor_icon("ph.magnifying-glass", color="white"))
        self.btn_sandbox_search.setFixedWidth(36)
        self.btn_sandbox_search.clicked.connect(self._on_sandbox_search)

        rag_search_row.addWidget(self.rag_sandbox_input, 1)
        rag_search_row.addWidget(self.btn_sandbox_search)
        rag_layout.addLayout(rag_search_row)

        self.rag_sandbox_results = QListWidget()
        self.rag_sandbox_results.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QListWidget::item {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                margin-bottom: 6px;
                padding: 8px;
                font-size: 11px;
            }}
            QListWidget::item:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        rag_layout.addWidget(self.rag_sandbox_results, 1)

        self.btn_forge_rag_result = SecondaryButton("⚡ Forger ce fragment")
        self.btn_forge_rag_result.setIcon(load_phosphor_icon("ph.lightning", color=DesignTokens.COLOR_YELLOW))
        self.btn_forge_rag_result.clicked.connect(self._on_forge_sandbox_result)
        rag_layout.addWidget(self.btn_forge_rag_result)

        self.coverage_panel.add_tab("RAG", rag_sandbox_content, "ph.database", closable=False)

        self.main_splitter.addWidget(self.coverage_panel)

        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.setCollapsible(2, False)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        self.main_splitter.setSizes([230, 600, 270])
        self.editor_stack.setCurrentIndex(0)

    def _connect_signals(self) -> None:
        self.tree_explorer.itemSelectionChanged.connect(self._on_document_selected)
        self.tree_explorer.itemMoved.connect(self._on_item_moved)
        self.text_editor.content_changed.connect(self._on_document_text_changed)

    def _on_search_filter_changed(self, text: str) -> None:
        """Filtre instantanément l'explorateur de documents."""
        self.tree_explorer.filter_text(text)

    def _on_item_moved(self, source_data: dict, target_data: Optional[dict]) -> None:
        """Gère le déplacement (drag and drop) d'un document ou d'un dossier."""
        if not source_data:
            return

        source_type = source_data.get("type")
        source_id = source_data.get("id")
        target_type = target_data.get("type") if target_data else None
        target_id = target_data.get("id") if target_data else None

        if target_type == "doc":
            doc = DocumentModel.get_or_none(DocumentModel.id == target_id)
            if doc and doc.folder:
                target_id = doc.folder.id
            else:
                target_id = None

        if source_type == "doc":
            doc = DocumentModel.get_or_none(DocumentModel.id == source_id)
            if doc:
                current_folder_id = doc.folder.id if doc.folder else None
                if current_folder_id == target_id:
                    return
                doc.folder = target_id
                doc.save()
                self.refresh_data()

        elif source_type == "folder":
            folder = FolderModel.get_or_none(FolderModel.id == source_id)
            if not folder:
                return

            target_folder = FolderModel.get_or_none(FolderModel.id == target_id) if target_id else None
            old_name = folder.name
            base_name = old_name.split("::")[-1]
            new_name = (target_folder.name + "::" + base_name) if target_folder else base_name

            if new_name == old_name:
                return

            if target_folder and (target_folder.name == old_name or target_folder.name.startswith(old_name + "::")):
                show_toast(self, "Vous ne pouvez pas déplacer un dossier dans lui-même.", is_error=True)
                return

            try:
                with FolderModel._meta.database.atomic():
                    folders_to_update = FolderModel.select().where((FolderModel.name == old_name) | (FolderModel.name.startswith(old_name + "::")))
                    for f in folders_to_update:
                        if f.name == old_name:
                            f.name = new_name
                        else:
                            suffix = f.name[len(old_name) :]
                            f.name = new_name + suffix
                        f.save()
                self.refresh_data()
            except Exception as e:
                logger.error("Erreur déplacement dossier : %s", e)
                show_toast(self, "Un dossier avec ce nom existe déjà à cet emplacement.", is_error=True)

    def refresh_data(self) -> None:
        """Recharge l'arborescence des dossiers et documents depuis Peewee."""
        try:
            self.tree_explorer.blockSignals(True)
            self.tree_explorer.clear()

            folder_items: Dict[int, QTreeWidgetItem] = {}
            path_items: Dict[str, QTreeWidgetItem] = {}
            folders = list(FolderModel.select())
            sorted_folders = sorted(folders, key=lambda f: f.name)

            for folder in sorted_folders:
                parts = folder.name.split("::")
                parent_item = None
                for i in range(1, len(parts)):
                    parent_path = "::".join(parts[:i])
                    if parent_path in path_items:
                        parent_item = path_items[parent_path]
                    else:
                        new_item = QTreeWidgetItem(parent_item or self.tree_explorer, [parts[i - 1]])
                        new_item.setIcon(0, load_phosphor_icon("ph.folder", weight="fill", color=DesignTokens.COLOR_BLUE))
                        path_items[parent_path] = new_item
                        parent_item = new_item

                node_name = parts[-1]
                item = QTreeWidgetItem(parent_item or self.tree_explorer, [node_name])
                item.setIcon(0, load_phosphor_icon("ph.folder", weight="fill", color=DesignTokens.COLOR_BLUE))
                item.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": folder.id})
                folder_items[folder.id] = item
                path_items[folder.name] = item

            documents = list(DocumentModel.select())
            for doc in documents:
                parent_item = folder_items[doc.folder_id] if hasattr(doc, "folder_id") and doc.folder_id and doc.folder_id in folder_items else self.tree_explorer
                title_to_display = doc.original_media.original_name if doc.original_media else doc.title
                item = QTreeWidgetItem(parent_item, [title_to_display])
                item.setData(0, Qt.ItemDataRole.UserRole, {"type": "doc", "id": doc.id})

                title_lower = doc.title.lower()
                is_pdf = getattr(doc, "file_type", "") == "pdf"
                has_content = bool(doc.content and doc.content.strip())

                if is_pdf:
                    if has_content:
                        item.setIcon(0, load_phosphor_icon("ph.file-pdf", color=DesignTokens.COLOR_RED))
                    else:
                        item.setIcon(0, load_phosphor_icon("ph.file-pdf", color=DesignTokens.TEXT_MUTED))
                        item.setText(0, f"{title_to_display} (Non extrait)")
                        item.setForeground(0, QColor(DesignTokens.TEXT_MUTED))
                elif getattr(doc, "file_type", "") == "txt" or title_lower.endswith(".txt"):
                    item.setIcon(0, load_phosphor_icon("ph.file-text", color=DesignTokens.COLOR_BLUE))
                elif getattr(doc, "file_type", "") == "md" or title_lower.endswith(".md"):
                    item.setIcon(0, load_phosphor_icon("ph.file-code", color="#eab308"))
                elif getattr(doc, "file_type", "") == "web":
                    item.setIcon(0, load_phosphor_icon("ph.globe", color=DesignTokens.ACCENT_PRIMARY))
                elif getattr(doc, "file_type", "") == "youtube":
                    item.setIcon(0, load_phosphor_icon("ph.youtube-logo", color=DesignTokens.COLOR_RED))
                else:
                    item.setIcon(0, load_phosphor_icon("ph.file-text", color=DesignTokens.COLOR_BLUE))

            self.tree_explorer.expandAll()
            self.tree_explorer.blockSignals(False)

            if not self._current_doc_id:
                self.editor_stack.setCurrentIndex(0)

        except Exception as e:
            logger.warning("Erreur refresh_data documents_view: %s", e)

    def is_dirty(self) -> bool:
        return self._dirty

    @Slot()
    def _on_document_selected(self) -> None:
        items = self.tree_explorer.selectedItems()
        if not items:
            self.btn_delete.setEnabled(False)
            self._current_doc_id = None
            self.editor_stack.setCurrentIndex(0)
            return

        self.btn_delete.setEnabled(True)
        item = items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("type") == "doc":
            doc = DocumentModel.get_or_none(DocumentModel.id == data["id"])
            if doc:
                self._current_doc_id = doc.id
                title_to_display = doc.original_media.original_name if doc.original_media else doc.title
                self.doc_title_lbl.setText(title_to_display)
                self.text_editor.blockSignals(True)
                self.text_editor.set_content(doc.content if hasattr(doc, "content") else "")
                self.text_editor.blockSignals(False)
                self._dirty = False
                self._update_word_count()
                self._update_rag_status_pill()

                # Show PDF if available
                if doc.file_type == "pdf" and doc.original_media:
                    from ankiforge.utils.paths import get_app_data_dir

                    pdf_path = get_app_data_dir() / "media" / doc.original_media.filename
                    if pdf_path.exists():
                        self.pdf_document.load(str(pdf_path))
                        self.view_toggle_frame.show()
                        self._on_view_toggled("pdf")
                    else:
                        self.view_toggle_frame.hide()
                        self._on_view_toggled("md")
                else:
                    self.view_toggle_frame.hide()
                    self._on_view_toggled("md")

                self.editor_stack.setCurrentIndex(1)
                self._refresh_chapters_list()
        else:
            self._current_doc_id = None
            self.editor_stack.setCurrentIndex(0)
            self._refresh_chapters_list()

    def _update_rag_status_pill(self) -> None:
        """Met à jour le badge pill de vectorisation FAISS."""
        if not self._current_doc_id:
            self.rag_status_pill.setText("Non indexé")
            apply_pill_style(self.rag_status_pill, "#94a3b8")
            return

        chunk_count = DocumentChunkModel.select().where(DocumentChunkModel.document_id == self._current_doc_id).count()
        if chunk_count > 0:
            self.rag_status_pill.setText(f"Indexé ({chunk_count} chunks)")
            apply_pill_style(self.rag_status_pill, "#10b981")
        else:
            self.rag_status_pill.setText("Non indexé")
            apply_pill_style(self.rag_status_pill, "#eab308")

    @Slot()
    def _on_document_text_changed(self) -> None:
        self._dirty = True
        self.btn_save.setEnabled(True)
        self._update_word_count()

    def _update_word_count(self) -> None:
        text = self.text_editor.get_content()
        words = len(text.split())
        self.lbl_word_count.setText(f"{words:,} mots")

    @Slot()
    def _on_import_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Importer un document",
            "",
            "Documents (*.pdf *.txt *.md *.docx *.pptx);;Tous les fichiers (*.*)",
        )
        if file_path:
            ext = pathlib.Path(file_path).suffix.lower()
            if ext == ".pdf":
                self._import_pdf_directly(file_path)
            else:
                self._start_document_worker(file_path)

    @Slot()
    def _on_import_url(self) -> None:
        url, ok = QInputDialog.getText(self, "Importer depuis le Web", "Entrez l'URL de la page web ou de la vidéo YouTube :")
        if ok and url.strip():
            self._start_document_worker(url.strip())

    @Slot(str)
    def _on_view_toggled(self, mode: str) -> None:
        self.btn_view_pdf.setChecked(mode == "pdf")
        self.btn_view_md.setChecked(mode == "md")
        self.btn_view_term.setChecked(mode == "term")

        if mode == "pdf":
            self.inner_editor_stack.setCurrentIndex(0)
        elif mode == "md":
            self.inner_editor_stack.setCurrentIndex(1)
        else:
            self.inner_editor_stack.setCurrentIndex(2)

    def _import_pdf_directly(self, file_path: str) -> None:
        from ankiforge.services.cards.media_manager import MediaManager

        media_manager = MediaManager()
        media = media_manager.store_document_source(file_path)
        if not media:
            show_toast(self, "Erreur lors de l'import du PDF.", is_error=True)
            return

        file_path_obj = pathlib.Path(file_path)
        doc = DocumentModel.create(
            title=file_path_obj.stem,
            content="",
            original_media_id=media.id,
            file_type="pdf",
            source_url=None,
        )

        self.refresh_data()
        self._current_doc_id = doc.id
        title_to_display = media.original_name
        self.doc_title_lbl.setText(title_to_display)
        self.text_editor.set_content("Cliquer sur 'Marker OCR' pour extraire le texte et les formules en KaTeX...")
        self.editor_stack.setCurrentIndex(1)

        from ankiforge.utils.paths import get_app_data_dir

        pdf_path = get_app_data_dir() / "media" / media.filename
        if pdf_path.exists():
            self.pdf_document.load(str(pdf_path))
            self.view_toggle_frame.show()
            self._on_view_toggled("pdf")
        else:
            self.view_toggle_frame.hide()
            self._on_view_toggled("md")

        show_toast(self, f"PDF '{title_to_display}' importé. Démarrage de l'analyse Marker OCR...")
        if pdf_path.exists():
            self._start_document_worker(str(pdf_path), doc_id=doc.id)

    def _start_document_worker(self, path_or_url: str, doc_id: Optional[int] = None) -> None:
        self.btn_import.setEnabled(False)
        self.btn_import_url.setEnabled(False)
        show_toast(self, "Extraction et analyse du document en cours...")

        self.worker = DocumentWorker(path_or_url)
        self.worker.doc_id_to_update = doc_id
        self.worker.finished_signal.connect(self._on_worker_finished)
        self.worker.error_signal.connect(self._on_worker_error)
        self.worker.log_signal.connect(self._on_worker_log)

        self._on_view_toggled("term")
        self.terminal_view.clear()
        self.terminal_view.append("--- Démarrage de l'extraction documentaire ---")
        self.worker.start()

    @Slot(str)
    def _on_worker_log(self, msg: str) -> None:
        if hasattr(self, "terminal_view"):
            self.terminal_view.append(msg)

    @Slot(str, str)
    def _on_worker_finished(self, title: str, content: str) -> None:
        if hasattr(self, "terminal_view"):
            self.terminal_view.append("--- Extraction terminée avec succès ! ---")

        self._on_view_toggled("md")
        self.btn_import.setEnabled(True)
        self.btn_import_url.setEnabled(True)

        try:
            doc_id_to_update = getattr(self.worker, "doc_id_to_update", None)
            file_type = "md"

            if doc_id_to_update:
                doc = DocumentModel.get_by_id(doc_id_to_update)
                doc.content = content
                doc.save()
                file_type = doc.file_type or "md"
            else:
                from ankiforge.services.cards.media_manager import MediaManager

                original_media_id = None
                source_url = None

                if self.worker and self.worker.file_path:
                    path_or_url = self.worker.file_path
                    if path_or_url.startswith("http"):
                        source_url = path_or_url
                        file_type = "web"
                    else:
                        media_manager = MediaManager()
                        media = media_manager.store_document_source(path_or_url)
                        if media:
                            original_media_id = media.id
                        file_type = pathlib.Path(path_or_url).suffix.replace(".", "") or "txt"

                doc = DocumentModel.create(
                    title=title,
                    content=content,
                    original_media_id=original_media_id,
                    file_type=file_type,
                    source_url=source_url,
                )

            extracted_chunks = ChunkingService.extract_chunks(content, file_type=file_type)
            with DocumentChunkModel._meta.database.atomic():
                DocumentChunkModel.delete().where(DocumentChunkModel.document == doc).execute()
                for idx, chunk_data in enumerate(extracted_chunks):
                    DocumentChunkModel.create(
                        document=doc,
                        chunk_index=idx,
                        content=chunk_data["content"],
                        page_number=chunk_data.get("page_number"),
                        heading_path=chunk_data.get("heading_path"),
                        content_hash=chunk_data.get("content_hash") or ChunkingService.hash_content(chunk_data["content"]),
                    )

            self.refresh_data()
            self._current_doc_id = doc.id
            title_to_display = doc.original_media.original_name if doc.original_media else doc.title
            self.doc_title_lbl.setText(title_to_display)
            self.text_editor.set_content(content)
            self.editor_stack.setCurrentIndex(1)
            self._update_rag_status_pill()

            show_toast(self, f"Document '{title_to_display}' importé avec succès !")
        except Exception as e:
            logger.exception("Erreur enregistrement document : %s", e)
            QMessageBox.critical(self, "Erreur", f"Échec de l'enregistrement du document : {e}")

    @Slot(str)
    def _on_worker_error(self, error: str) -> None:
        self.btn_import.setEnabled(True)
        self.btn_import_url.setEnabled(True)
        QMessageBox.critical(self, "Erreur d'importation", f"Impossible d'extraire le document :\n{error}")

    @Slot()
    def _on_new_folder(self) -> None:
        folder_name, ok = QInputDialog.getText(self, "Nouveau dossier", "Nom du dossier :")
        if ok and folder_name.strip():
            target_name = folder_name.strip()
            items = self.tree_explorer.selectedItems()
            if items:
                data = items[0].data(0, Qt.ItemDataRole.UserRole)
                if data:
                    item_type = data.get("type")
                    item_id = data.get("id")
                    target_folder_id = item_id if item_type == "folder" else (DocumentModel.get_by_id(item_id).folder.id if DocumentModel.get_by_id(item_id).folder else None)
                    if target_folder_id:
                        folder = FolderModel.get_or_none(FolderModel.id == target_folder_id)
                        if folder:
                            target_name = f"{folder.name}::{target_name}"

            try:
                FolderModel.create(name=target_name)
                self.refresh_data()
                show_toast(self, f"Dossier '{target_name}' créé.")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de créer le dossier : {e}")

    @Slot()
    def _on_delete_item(self) -> None:
        items = self.tree_explorer.selectedItems()
        if not items:
            return

        item = items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type = data.get("type")
        item_id = data.get("id")

        if item_type == "doc":
            doc = DocumentModel.get_or_none(DocumentModel.id == item_id)
            if doc:
                reply = QMessageBox.question(
                    self,
                    "Confirmer la suppression",
                    f"Voulez-vous vraiment supprimer le document '{doc.title}' ?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    doc.delete_instance()
                    self.refresh_data()
                    self.editor_stack.setCurrentIndex(0)
                    show_toast(self, "Document supprimé.")
        elif item_type == "folder":
            folder = FolderModel.get_or_none(FolderModel.id == item_id)
            if folder:
                reply = QMessageBox.question(
                    self,
                    "Confirmer la suppression",
                    f"Voulez-vous vraiment supprimer le dossier '{folder.name}' et son contenu ?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    with FolderModel._meta.database.atomic():
                        folders_to_delete = FolderModel.select().where((FolderModel.name == folder.name) | (FolderModel.name.startswith(folder.name + "::")))
                        for f in folders_to_delete:
                            f.delete_instance()
                    self.refresh_data()
                    self.editor_stack.setCurrentIndex(0)
                    show_toast(self, "Dossier supprimé.")

    @Slot()
    def _on_open_delimitation_dialog(self) -> None:
        """Ouvre la boîte de dialogue de délimitation de pages et chapitres utiles."""
        if not self._current_doc_id:
            show_toast(self, "Veuillez sélectionner un document.", is_error=True)
            return

        doc = DocumentModel.get_by_id(self._current_doc_id)
        dlg = DocumentDelimitationDialog(doc, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            show_toast(self, "Délimitation et sections appliquées avec succès !")
            self._refresh_chapters_list()
            self._update_rag_status_pill()

    @Slot()
    def _on_open_rag_test_dialog(self) -> None:
        """Ouvre la boîte de dialogue de test de recherche sémantique RAG."""
        if not self._current_doc_id:
            show_toast(self, "Veuillez sélectionner un document.", is_error=True)
            return

        doc = DocumentModel.get_by_id(self._current_doc_id)
        dlg = RAGTestDialog(doc, parent=self)
        dlg.exec()

    @Slot()
    def _on_run_marker_analysis(self) -> None:
        """Lance l'extraction Deep Learning Marker OCR pour les PDF avec vérification du Lazy Loading."""
        if not self._current_doc_id:
            show_toast(self, "Veuillez d'abord sélectionner un document.", is_error=True)
            return

        doc = DocumentModel.get_by_id(self._current_doc_id)

        marker_exec = shutil.which("marker_single")
        if not marker_exec:
            reply = QMessageBox.information(
                self,
                "Marker OCR (Lazy Loading)",
                "Le moteur Marker OCR (Deep Learning) n'est pas encore installé sur votre environnement local.\n\n"
                "Souhaitez-vous continuer avec l'extraction standard immédiate (PyPDF/Texte) ?\n"
                "(Pour installer Marker à la volée : 'uv pip install marker-pdf')",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        if doc.file_type == "pdf" and doc.original_media:
            from ankiforge.utils.paths import get_app_data_dir

            pdf_path = get_app_data_dir() / "media" / doc.original_media.filename
            if pdf_path.exists():
                self._start_document_worker(str(pdf_path), doc_id=doc.id)
                return

        show_toast(self, "Analyse Marker : Document déjà textuel.")

    @Slot()
    def _on_save_document(self) -> None:
        if not self._current_doc_id:
            show_toast(self, "Aucun document sélectionné à sauvegarder.", is_error=True)
            return

        try:
            doc = DocumentModel.get_or_none(DocumentModel.id == self._current_doc_id)
            if doc:
                doc.title = self.doc_title_lbl.text()
                content = self.text_editor.get_content()
                doc.content = content
                doc.word_count = len(content.split())
                doc.save()
                self._dirty = False
                self.btn_save.setStyleSheet("")
                show_toast(self, f"Document '{doc.title}' enregistré avec succès !")
        except Exception as e:
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Impossible d'enregistrer le document : {e}")

    def _refresh_chapters_list(self) -> None:
        """Met à jour le sommaire des chapitres et les indicateurs de couverture du document actif."""
        self.chapters_list.clear()
        if not self._current_doc_id:
            self.lbl_coverage_summary.setText("📊 Couverture : 0%")
            self.coverage_bar.setValue(0)
            self.lbl_coverage_details.setText("0 sections analysées • 0 cartes liées")
            return

        chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document_id == self._current_doc_id).order_by(DocumentChunkModel.chunk_index))
        if not chunks:
            item = QListWidgetItem("Aucun fragment indexé (cliquez sur 'Vectoriser')")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.chapters_list.addItem(item)
            self.lbl_coverage_summary.setText("📊 Couverture : 0%")
            self.coverage_bar.setValue(0)
            self.lbl_coverage_details.setText("0 sections analysées • 0 cartes liées")
            return

        linked_chunk_ids = {link.chunk_id for link in NoteChunkLinkModel.select(NoteChunkLinkModel.chunk_id).join(DocumentChunkModel).where(DocumentChunkModel.document_id == self._current_doc_id)}

        covered_count = 0
        for chunk in chunks:
            is_covered = chunk.id in linked_chunk_ids
            if is_covered:
                covered_count += 1
                badge = "🟢"
                status_text = "Couvert"
            else:
                badge = "⚠️"
                status_text = "Non couvert"

            title_str = chunk.heading_path or (f"Page {chunk.page_number}" if chunk.page_number else f"Section #{chunk.chunk_index + 1}")
            item_text = f"{badge} {title_str} ({status_text})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, chunk.id)
            self.chapters_list.addItem(item)

        total_chunks = len(chunks)
        percent = int(covered_count / total_chunks * 100) if total_chunks > 0 else 0
        self.lbl_coverage_summary.setText(f"📊 Couverture : {percent}% ({covered_count}/{total_chunks} sections)")
        self.coverage_bar.setValue(percent)
        self.lbl_coverage_details.setText(f"{total_chunks} sections • {covered_count} couvertes • {len(linked_chunk_ids)} liens")

    @Slot()
    def _on_forge_selected_chapter(self) -> None:
        """Bascule sur l'Usine de Création en préchargeant la section sélectionnée."""
        items = self.chapters_list.selectedItems()
        if not items:
            show_toast(self, "Veuillez sélectionner un chapitre dans le sommaire.", is_error=True)
            return

        chunk_id = items[0].data(Qt.ItemDataRole.UserRole)
        if not chunk_id:
            return

        chunk = DocumentChunkModel.get_or_none(DocumentChunkModel.id == chunk_id)
        if not chunk:
            return

        doc = DocumentModel.get_or_none(DocumentModel.id == self._current_doc_id)
        doc_title = doc.title if doc else "Document"
        section_name = chunk.heading_path or (f"Page {chunk.page_number}" if chunk.page_number else f"Section #{chunk.chunk_index + 1}")

        self.request_navigation.emit(
            "creation",
            {
                "text_source": chunk.content,
                "source_title": f"{doc_title} - {section_name}",
                "chunk_id": chunk.id,
            },
        )

    @Slot()
    def _on_vectorize_rag(self) -> None:
        if not self._current_doc_id:
            show_toast(self, "Veuillez sélectionner un document à vectoriser.", is_error=True)
            return

        self.btn_rag.setEnabled(False)
        self.btn_rag.setText("Vectorisation FAISS...")

        self._coverage_worker = CoverageWorker(document_id=self._current_doc_id, parent=self)
        self._coverage_worker.finished_processing.connect(self._on_vectorization_success)
        self._coverage_worker.error_occurred.connect(self._on_vectorization_error)
        self._coverage_worker.finished.connect(self._coverage_worker.deleteLater)
        self._coverage_worker.start()

    @Slot()
    def _on_vectorization_success(self) -> None:
        self.btn_rag.setEnabled(True)
        self.btn_rag.setText("Vectoriser (RAG)")
        show_toast(self, "Document indexé avec succès dans FAISS !")
        self._refresh_chapters_list()
        self._update_rag_status_pill()

    @Slot(str)
    def _on_vectorization_error(self, err: str) -> None:
        self.btn_rag.setEnabled(True)
        self.btn_rag.setText("Vectoriser (RAG)")
        show_toast(self, f"Échec de la vectorisation : {err}", is_error=True)

    @Slot()
    def _on_sandbox_search(self) -> None:
        """Exécute la recherche sémantique dans l'onglet Sandbox RAG."""
        if not self._current_doc_id:
            show_toast(self, "Veuillez d'abord sélectionner un document.", is_error=True)
            return

        query = self.rag_sandbox_input.text().strip()
        if not query:
            return

        self.rag_sandbox_results.clear()
        try:
            rag = RAGService()
            results = rag.search(self._current_doc_id, query, top_k=4)
            if not results:
                self.rag_sandbox_results.addItem(QListWidgetItem("Aucun fragment pertinent trouvé."))
                return

            for r in results:
                loc = r.get("heading_path") or (f"Page {r.get('page_number')}" if r.get("page_number") else f"Section #{r.get('chunk_index', 0) + 1}")
                rel_pct = r.get("relevance_pct", 0)
                if rel_pct == 0:
                    score_val = r.get("score", 1.0)
                    rel_pct = max(0, min(100, int((1.0 - min(score_val, 1.0)) * 100))) if score_val <= 1.0 else int(100 / (1.0 + score_val))

                content_snippet = r.get("content", "")[:160] + "..." if len(r.get("content", "")) > 160 else r.get("content", "")
                item_txt = f"📍 {loc} (Pertinence: {rel_pct}%)\n{content_snippet}"
                item = QListWidgetItem(item_txt)
                item.setData(Qt.ItemDataRole.UserRole, r)
                self.rag_sandbox_results.addItem(item)

        except Exception as e:
            self.rag_sandbox_results.addItem(QListWidgetItem(f"Erreur recherche RAG : {e}"))

    @Slot()
    def _on_forge_sandbox_result(self) -> None:
        """Bascule sur la Forge avec le fragment sélectionné dans la Sandbox RAG."""
        items = self.rag_sandbox_results.selectedItems()
        if not items:
            show_toast(self, "Veuillez sélectionner un fragment dans la liste des résultats.", is_error=True)
            return

        data = items[0].data(Qt.ItemDataRole.UserRole)
        if not data or not isinstance(data, dict):
            return

        doc = DocumentModel.get_or_none(DocumentModel.id == self._current_doc_id)
        doc_title = doc.title if doc else "Document"
        section_name = data.get("heading_path") or (f"Page {data.get('page_number')}" if data.get("page_number") else "Section RAG")

        self.request_navigation.emit(
            "creation",
            {
                "text_source": data.get("content", ""),
                "source_title": f"{doc_title} - {section_name}",
                "chunk_id": data.get("chunk_id"),
            },
        )

    def refresh_theme(self, profile: Any) -> None:
        """Rafraîchit dynamiquement les styles de la vue lors d'un changement de thème."""
        if hasattr(self, "tree_explorer"):
            self.tree_explorer.setStyleSheet(f"""
                QTreeWidget {{
                    background-color: {profile.bg_panel};
                    border: 1px solid {profile.border_color};
                    border-radius: {profile.radius_sm}px;
                    color: {profile.text_primary};
                    padding: 4px;
                }}
                QTreeWidget::item {{
                    padding: 6px;
                    border-radius: 4px;
                }}
                QTreeWidget::item:hover {{
                    background-color: {profile.bg_hover};
                }}
                QTreeWidget::item:selected {{
                    background-color: {profile.bg_hover};
                    color: {profile.text_primary};
                }}
            """)

        if hasattr(self, "doc_page_frame"):
            self.doc_page_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {profile.bg_panel};
                    border: 1px solid {profile.border_color};
                    border-radius: {profile.radius_md}px;
                }}
            """)

        if hasattr(self, "doc_title_lbl"):
            self.doc_title_lbl.setStyleSheet(f"color: {profile.text_primary}; font-size: 18px; font-weight: bold; border-bottom: 1px solid {profile.border_color}; padding-bottom: 8px;")

        if hasattr(self, "coverage_card"):
            self.coverage_card.setStyleSheet(f"""
                QFrame {{
                    background-color: {profile.bg_panel};
                    border: 1px solid {profile.border_color};
                    border-radius: {profile.radius_md}px;
                }}
            """)

        if hasattr(self, "lbl_coverage_summary"):
            self.lbl_coverage_summary.setStyleSheet(f"color: {profile.text_primary}; font-weight: bold; font-size: 13px;")

        if hasattr(self, "coverage_bar"):
            self.coverage_bar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: {profile.bg_input};
                    border: 1px solid {profile.border_color};
                    border-radius: 4px;
                }}
                QProgressBar::chunk {{
                    background-color: {profile.color_green};
                    border-radius: 3px;
                }}
            """)

        if hasattr(self, "chapters_list"):
            self.chapters_list.setStyleSheet(f"""
                QListWidget {{
                    background-color: {profile.bg_panel};
                    border: 1px solid {profile.border_color};
                    border-radius: {profile.radius_sm}px;
                    color: {profile.text_primary};
                    padding: 4px;
                }}
                QListWidget::item {{
                    padding: 8px;
                    border-bottom: 1px solid {profile.border_color};
                    border-radius: 4px;
                    font-size: 11px;
                }}
                QListWidget::item:hover {{
                    background-color: {profile.bg_hover};
                }}
                QListWidget::item:selected {{
                    background-color: {profile.bg_hover};
                    color: {profile.text_primary};
                }}
            """)

        if hasattr(self, "rag_sandbox_results"):
            self.rag_sandbox_results.setStyleSheet(f"""
                QListWidget {{
                    background-color: {profile.bg_input};
                    border: 1px solid {profile.border_color};
                    border-radius: {profile.radius_sm}px;
                    padding: 4px;
                    color: {profile.text_primary};
                }}
                QListWidget::item {{
                    background-color: {profile.bg_panel};
                    border: 1px solid {profile.border_color};
                    border-radius: 6px;
                    margin-bottom: 6px;
                    padding: 8px;
                    font-size: 11px;
                }}
                QListWidget::item:hover {{
                    border-color: {profile.accent_primary};
                }}
            """)


DocumentsTab = DocumentsView
