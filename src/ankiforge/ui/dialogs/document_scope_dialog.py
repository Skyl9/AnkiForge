"""
Dialogue modal de sélection de la portée de génération documentaire (DocumentScopeDialog).
Offre une interface visuelle similaire à la délimitation, mais restreinte exclusivement
aux parties utiles/filtrées du document (bornes start_page/end_page, exclusions respectées)
pour sélectionner la portée de génération (pages, sections, segments) sans altérer la base de données.
"""

from __future__ import annotations

import html
import json
import logging
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DocumentChunkModel, DocumentModel, DocumentPageModel
from ankiforge.services.ai.context_compactor import ContextCompactor
from ankiforge.services.parsing.chunking_service import ChunkingService, HeadingTreeNode
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.components import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import (
    ChapterCardWidget,
    DocumentPreviewWidget,
    DocumentStructureTreeWidget,
    ScopeRangeBarWidget,
    SectionRowWidget,
    SectionTreeWidgetItem,
    has_structured_heading_nodes,
)
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.paths import get_resource_path

logger = logging.getLogger(__name__)


def _safe_int(val: Any, default: int = 1) -> int:
    """Convertit une valeur en entier de manière sécurisée en ignorant les Mocks."""
    if val is None:
        return default
    if hasattr(val, "_mock_name") or hasattr(val, "_mock_return_value") or type(val).__name__ in ("MagicMock", "Mock"):
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


class DocumentScopeDialog(QDialog):
    """
    Modale de sélection de la portée de génération pour CreationView et BatchView.
    - Donne accès uniquement aux parties filtrées/utiles du document.
    - Le slider de portée n'est affiché qu'en mode 'Plage personnalisée' sur documents paginés.
    - Non destructif pour la BDD (ne modifie pas DocumentModel ni DocumentChunkModel).
    """

    def __init__(
        self,
        doc: DocumentModel,
        initial_scope_str: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if getattr(doc, "id", None):
            try:
                doc = DocumentModel.get_by_id(doc.id)
            except Exception:
                pass
        self.doc = doc
        self.initial_scope_str = initial_scope_str.strip()

        file_type = (getattr(self.doc, "file_type", "") or "").lower()
        if not file_type and getattr(self.doc, "title", "").lower().endswith(".pdf"):
            file_type = "pdf"
        self.is_paginated = file_type in ("pdf", "album", "pptx")
        self.selection_mode = "pages" if self.is_paginated else "chapters"

        # 1. Calcul des bornes utiles globales issues de la délimitation
        max_chunk_page = 1
        if getattr(self.doc, "id", None):
            chunk_pages = [c.page_number for c in DocumentChunkModel.select(DocumentChunkModel.page_number).where(DocumentChunkModel.document == self.doc) if c.page_number is not None]
            if chunk_pages:
                max_chunk_page = max(chunk_pages)
            page_records = [p.page_number for p in DocumentPageModel.select(DocumentPageModel.page_number).where(DocumentPageModel.document == self.doc) if p.page_number is not None]
            if page_records:
                max_chunk_page = max(max_chunk_page, max(page_records))

        self._doc_total_pages = max(_safe_int(getattr(self.doc, "total_pages", None), default=1), max_chunk_page)
        self._delimited_start_page = _safe_int(getattr(self.doc, "start_page", None), default=1)
        self._delimited_end_page = _safe_int(getattr(self.doc, "end_page", None), default=self._doc_total_pages)
        if self._delimited_end_page < self._delimited_start_page:
            self._delimited_end_page = max(self._delimited_start_page, self._doc_total_pages)

        # 2. Chargement des exclusions sémantiques mémorisées
        self._excluded_headings: list[str] = []
        raw_excl = getattr(self.doc, "excluded_headings", None)
        if raw_excl:
            try:
                parsed = json.loads(raw_excl)
                if isinstance(parsed, list):
                    self._excluded_headings = [str(x).lower().strip() for x in parsed]
            except Exception:
                self._excluded_headings = []

        # 3. Extraction des fragments utiles (filtrés par délimitation)
        self._useful_chunks: list[dict[str, Any]] = self._load_filtered_chunks()

        # Si paginé, s'assurer que les bornes délimitées englobent bien les chunks chargés
        if self.is_paginated and self._useful_chunks:
            chunk_pages_useful = [u["page_number"] for u in self._useful_chunks if u.get("page_number") is not None]
            if chunk_pages_useful:
                if getattr(self.doc, "start_page", None) is None:
                    self._delimited_start_page = min(chunk_pages_useful)
                if getattr(self.doc, "end_page", None) is None:
                    self._delimited_end_page = max(chunk_pages_useful)
                self._doc_total_pages = max(self._doc_total_pages, max(chunk_pages_useful))

        self._section_meta: dict[int, dict[str, Any]] = {}
        self._syncing_selection: bool = False
        self._manually_deselected_indices: set[int] = set()
        self._context_limit = self._read_context_limit()
        self._chapter_cards: list[ChapterCardWidget] = []
        self._tree_nodes: list[HeadingTreeNode] = []

        # 4. Résultat sélectionné en sortie
        self._result: dict[str, Any] = {
            "chunks": [],
            "scope_title": "Portée : Tout le document utile",
            "scope_stats": "0 mot • 0 carte estimée",
            "range_str": f"{self._delimited_start_page}-{self._delimited_end_page}",
            "start_page": self._delimited_start_page,
            "end_page": self._delimited_end_page,
            "selection_mode": self.selection_mode,
        }

        self._setup_window()
        self._build_ui()
        self._apply_initial_scope()
        self._update_kpi()

    def _setup_window(self) -> None:
        title_prefix = "Portée de génération (Pages & Segments)" if self.is_paginated else "Portée de génération (Sections)"
        self.setWindowTitle(f"{title_prefix} — {self.doc.title}")
        self.resize(1240, 750)
        self.setMinimumSize(940, 580)

        check_icon_path = str(get_resource_path("src", "ressources", "icons", "check_white.svg")).replace("\\", "/")
        dash_icon_path = str(get_resource_path("src", "ressources", "icons", "dash_white.svg")).replace("\\", "/")
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QFrame#scopeHeaderCard, QFrame#scopePagesCard, QFrame#scopeSectionsCard, QFrame#scopeAllCard, QFrame#scopeChaptersCard {{
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
            QCheckBox::indicator:indeterminate {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-color: {DesignTokens.ACCENT_PRIMARY};
                image: url({dash_icon_path});
            }}
        """)

    def _load_filtered_chunks(self) -> list[dict[str, Any]]:
        """Charge uniquement les fragments faisant partie du périmètre utile délimité."""
        useful: list[dict[str, Any]] = []

        # Tenter de charger les chunks persistés en base de données (déjà filtrés par délimitation)
        db_chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == self.doc).order_by(DocumentChunkModel.chunk_index))

        has_start = getattr(self.doc, "start_page", None) is not None
        has_end = getattr(self.doc, "end_page", None) is not None

        if db_chunks:
            for _idx, c in enumerate(db_chunks):
                p_num = c.page_number
                # Filtrage strict de pagination si des bornes explicites sont définies
                if self.is_paginated and p_num is not None:
                    if has_start and p_num < self._delimited_start_page:
                        continue
                    if has_end and p_num > self._delimited_end_page:
                        continue

                # Filtrage des titres exclus
                h_path = (c.heading_path or "").lower().strip()
                if self._excluded_headings and any(ex in h_path or h_path == ex for ex in self._excluded_headings):
                    continue

                content = str(c.content or "")
                tokens = ContextCompactor.estimate_tokens(content)
                useful_idx = len(useful)
                useful.append(
                    {
                        "index": useful_idx,
                        "title": c.heading_path or (f"Page {p_num}" if p_num else f"Segment #{useful_idx + 1}"),
                        "heading_path": c.heading_path,
                        "page_number": p_num,
                        "content": content,
                        "tokens": tokens,
                    }
                )
        else:
            # Repli sur les pages ou l'extraction sémantique du texte brut
            pages_query = list(DocumentPageModel.select().where(DocumentPageModel.document == self.doc).order_by(DocumentPageModel.page_number))
            if self.doc.file_type == "album" or pages_query:
                for p in pages_query:
                    p_num = int(p.page_number)
                    if p_num < self._delimited_start_page or p_num > self._delimited_end_page:
                        continue
                    text = p.ocr_text or f"Planche {p_num}"
                    useful_idx = len(useful)
                    useful.append(
                        {
                            "index": useful_idx,
                            "title": f"Planche {p_num}",
                            "heading_path": f"Planche {p_num}",
                            "page_number": p_num,
                            "content": text,
                            "tokens": ContextCompactor.estimate_tokens(text),
                        }
                    )
            else:
                raw_chunks = ChunkingService.extract_chunks(self.doc.content or "", file_type=self.doc.file_type or "md")
                for c in raw_chunks:
                    p_num = c.get("page_number")
                    if self.is_paginated and p_num is not None and (p_num < self._delimited_start_page or p_num > self._delimited_end_page):
                        continue
                    h_path = str(c.get("heading_path") or "").lower()
                    if any(ex in h_path for ex in self._excluded_headings):
                        continue
                    content = str(c.get("content") or "")
                    useful_idx = len(useful)
                    useful.append(
                        {
                            "index": useful_idx,
                            "title": c.get("heading_path") or (f"Page {p_num}" if p_num else f"Section #{useful_idx + 1}"),
                            "heading_path": c.get("heading_path"),
                            "page_number": p_num,
                            "content": content,
                            "tokens": ContextCompactor.estimate_tokens(content),
                        }
                    )

        return useful

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Conteneur gauche : contrôles de portée & sélection des fragments
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # 1. En-tête descriptif
        header_card = QFrame()
        header_card.setObjectName("scopeHeaderCard")
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(10, 8, 10, 8)
        h_layout.setSpacing(4)

        header_top = QHBoxLayout()
        header_top.setSpacing(8)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.sliders", color=DesignTokens.ACCENT_PRIMARY).pixmap(20, 20))
        title_lbl = QLabel(f"Portée de génération : <b>{html.escape(self.doc.title)}</b>")
        title_lbl.setTextFormat(Qt.TextFormat.RichText)
        title_lbl.setStyleSheet(f"font-size: 14px; color: {DesignTokens.TEXT_PRIMARY}; border: none;")
        title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        badge_lbl = QLabel("PORTÉE DE GÉNÉRATION (NON DESTRUCTIF)")
        badge_lbl.setStyleSheet(
            "background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold;"
        )
        header_top.addWidget(icon_lbl)
        header_top.addWidget(title_lbl, 1)
        header_top.addWidget(badge_lbl)
        h_layout.addLayout(header_top)

        scope_desc = (
            f"Délimitation active : pages {self._delimited_start_page} à {self._delimited_end_page}. "
            "Sélectionnez les pages ou segments spécifiques à soumettre au prompt IA ou au lot batch. "
            "<i>(Sélection temporaire de session, ne modifie pas la structure du document)</i>"
            if self.is_paginated
            else "Sélectionnez les sections utiles à soumettre au prompt IA ou au lot batch. <i>(Sélection temporaire de session, ne modifie pas la structure du document)</i>"
        )
        desc_lbl = QLabel(scope_desc)
        desc_lbl.setTextFormat(Qt.TextFormat.RichText)
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

        useful_page_count = self._delimited_end_page - self._delimited_start_page + 1
        self.btn_mode_all = QPushButton("Tout le document utile")
        self.btn_mode_all.setToolTip(f"Tout le document utile ({useful_page_count} pages)")
        self.btn_mode_all.setIcon(load_phosphor_icon("ph.files", color=DesignTokens.TEXT_PRIMARY))
        self.btn_mode_all.setCheckable(True)
        self.btn_mode_all.setChecked(True)
        self.btn_mode_all.setStyleSheet(mode_btn_style)

        self.btn_mode_range = QPushButton("Plage de pages")
        self.btn_mode_range.setIcon(load_phosphor_icon("ph.frame-corners", color=DesignTokens.TEXT_PRIMARY))
        self.btn_mode_range.setCheckable(True)
        self.btn_mode_range.setStyleSheet(mode_btn_style)

        self.btn_mode_structure = QPushButton("Par Chapitres")
        self.btn_mode_structure.setIcon(load_phosphor_icon("ph.tree-structure", color=DesignTokens.TEXT_PRIMARY))
        self.btn_mode_structure.setCheckable(True)
        self.btn_mode_structure.setStyleSheet(mode_btn_style)

        self.btn_mode_sections = QPushButton("Par Sections")
        self.btn_mode_sections.setIcon(load_phosphor_icon("ph.list-dashes", color=DesignTokens.TEXT_PRIMARY))
        self.btn_mode_sections.setCheckable(True)
        self.btn_mode_sections.setStyleSheet(mode_btn_style)

        self.scope_mode_group = QButtonGroup(self)
        self.scope_mode_group.addButton(self.btn_mode_all)
        self.scope_mode_group.addButton(self.btn_mode_range)
        self.scope_mode_group.addButton(self.btn_mode_structure)
        self.scope_mode_group.addButton(self.btn_mode_sections)
        self.btn_mode_all.clicked.connect(self._on_mode_all_clicked)
        self.btn_mode_range.clicked.connect(self._on_mode_range_clicked)
        self.btn_mode_structure.clicked.connect(self._on_mode_structure_clicked)
        self.btn_mode_sections.clicked.connect(self._on_mode_sections_clicked)

        mode_row.addWidget(self.btn_mode_all)
        mode_row.addWidget(self.btn_mode_range)
        mode_row.addWidget(self.btn_mode_structure)
        mode_row.addWidget(self.btn_mode_sections)
        mode_row.addStretch()
        self.mode_card = QFrame()
        self.mode_card.setObjectName("scopePagesCard")
        mode_card_layout = QVBoxLayout(self.mode_card)
        mode_card_layout.setContentsMargins(10, 8, 10, 8)
        mode_card_layout.setSpacing(0)
        mode_card_layout.addLayout(mode_row)
        left_layout.addWidget(self.mode_card)

        # 2. Carte de portée de pagination (affichée uniquement pour documents paginés)
        self.pages_card = QFrame()
        self.pages_card.setObjectName("scopePagesCard")
        pages_card_layout = QVBoxLayout(self.pages_card)
        pages_card_layout.setContentsMargins(12, 10, 12, 10)
        pages_card_layout.setSpacing(8)

        lbl_sec1 = QLabel("1. PORTÉE DE PAGES DANS LE PÉRIMÈTRE UTILE")
        lbl_sec1.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: bold; font-size: 10px; letter-spacing: 0.5px; border: none;")
        pages_card_layout.addWidget(lbl_sec1)

        self.range_bar = ScopeRangeBarWidget(self)
        self.range_bar.set_range(self._delimited_start_page, self._delimited_end_page, self._doc_total_pages)
        pages_card_layout.addWidget(self.range_bar)

        # Conteneur des curseurs (slider) et spinboxes — Visible UNIQUEMENT en mode Plage personnalisée
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

        # Ligne début : SpinBox + Slider début (restreints au périmètre utile [start, end])
        start_row = QHBoxLayout()
        start_row.setContentsMargins(0, 0, 0, 0)
        start_row.setSpacing(8)
        lbl_p_start = QLabel("Début :")
        lbl_p_start.setFixedWidth(44)
        lbl_p_start.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; border: none;")
        self.spin_p_start = QSpinBox()
        self.spin_p_start.setRange(self._delimited_start_page, self._delimited_end_page)
        self.spin_p_start.setValue(self._delimited_start_page)
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
        self.slider_p_start.setRange(self._delimited_start_page, self._delimited_end_page)
        self.slider_p_start.setValue(self._delimited_start_page)
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
        self.spin_p_end.setRange(self._delimited_start_page, self._delimited_end_page)
        self.spin_p_end.setValue(self._delimited_end_page)
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
        self.slider_p_end.setRange(self._delimited_start_page, self._delimited_end_page)
        self.slider_p_end.setValue(self._delimited_end_page)
        self.slider_p_end.setStyleSheet(slider_style)
        self.slider_p_end.valueChanged.connect(self._on_slider_end_changed)

        end_row.addWidget(lbl_p_end)
        end_row.addWidget(self.spin_p_end)
        end_row.addWidget(self.slider_p_end, 1)
        slider_scope_layout.addLayout(end_row)

        pages_card_layout.addWidget(self.slider_scope_container)
        self.slider_scope_container.hide()

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
        btn_preset_all.clicked.connect(lambda: self._apply_page_preset(self._delimited_start_page, self._delimited_end_page))
        del_span = self._delimited_end_page - self._delimited_start_page + 1
        btn_preset_h1 = QPushButton("1ère moitié")
        btn_preset_h1.setStyleSheet(preset_btn_style)
        btn_preset_h1.clicked.connect(lambda: self._apply_page_preset(self._delimited_start_page, max(self._delimited_start_page, self._delimited_start_page + del_span // 2 - 1)))
        btn_preset_h2 = QPushButton("2ème moitié")
        btn_preset_h2.setStyleSheet(preset_btn_style)
        btn_preset_h2.clicked.connect(lambda: self._apply_page_preset(min(self._delimited_end_page, self._delimited_start_page + del_span // 2), self._delimited_end_page))
        btn_preset_10 = QPushButton("10 premières p.")
        btn_preset_10.setStyleSheet(preset_btn_style)
        btn_preset_10.clicked.connect(lambda: self._apply_page_preset(self._delimited_start_page, min(self._delimited_start_page + 9, self._delimited_end_page)))

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
                border-radius: {DesignTokens.RADIUS_SM}px;
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

        # 3. Mode All: Carte récapitulative complète
        self.all_card = QFrame()
        self.all_card.setObjectName("scopeAllCard")
        all_layout = QVBoxLayout(self.all_card)
        all_layout.setContentsMargins(14, 14, 14, 14)
        all_layout.setSpacing(12)

        hero_banner = QFrame()
        hero_banner.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(34, 197, 94, 0.08);
                border: 1px solid rgba(34, 197, 94, 0.25);
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        hero_layout = QHBoxLayout(hero_banner)
        hero_layout.setContentsMargins(10, 8, 10, 8)
        hero_layout.setSpacing(10)
        hero_icon = QLabel()
        hero_icon.setPixmap(load_phosphor_icon("ph.check-circle", color="#22c55e").pixmap(24, 24))
        hero_layout.addWidget(hero_icon)
        hero_text_col = QVBoxLayout()
        hero_text_col.setSpacing(2)
        hero_title = QLabel("Portée intégrale du périmètre utile")
        hero_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        hero_subtitle = QLabel("Toutes les sections utiles et pages délimitées sont incluses pour la génération.")
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
                    border-radius: {DesignTokens.RADIUS_SM}px;
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

        box_pages, self.lbl_all_kpi_pages = _make_kpi_box("Pages utiles", f"{useful_page_count} p.", "100% du périmètre")
        box_chapters, self.lbl_all_kpi_chapters = _make_kpi_box("Chapitres", "—", "Structure globale")
        box_sections, self.lbl_all_kpi_sections = _make_kpi_box("Sections", "—", "Fragments utiles")
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
                border-radius: {DesignTokens.RADIUS_SM}px;
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
        self.chapters_card.setObjectName("scopeChaptersCard")
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
                border-radius: {DesignTokens.RADIUS_SM}px;
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

        # 3. Liste des sections et segments utiles
        sections_card = QFrame()
        self.sections_card = sections_card
        sections_card.setObjectName("scopeSectionsCard")
        sections_layout = QVBoxLayout(sections_card)
        sections_layout.setContentsMargins(12, 10, 12, 10)
        sections_layout.setSpacing(8)

        sec_header = QHBoxLayout()
        sec_title = "2. SECTIONS & SEGMENTS UTILES" if self.is_paginated else "SECTIONS & SEGMENTS UTILES"
        lbl_sec2 = QLabel(sec_title)
        lbl_sec2.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: bold; font-size: 10px; letter-spacing: 0.5px; border: none;")
        sec_header.addWidget(lbl_sec2)
        sec_header.addStretch()

        self.lbl_selection_kpi = QLabel("")
        self.lbl_selection_kpi.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; font-size: 11px; font-weight: bold; border: none;")
        sec_header.addWidget(self.lbl_selection_kpi)
        sections_layout.addLayout(sec_header)

        # Boutons d'actions rapides
        self.section_actions = QWidget()
        quick_btns = QHBoxLayout(self.section_actions)
        btn_check_all = SecondaryButton("Tout cocher")
        btn_check_all.setFixedHeight(26)
        btn_check_all.setStyleSheet(f"font-size: 11px; padding: 2px 8px; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px;")
        btn_check_all.clicked.connect(lambda: self._set_all_checked(True))

        btn_uncheck_all = SecondaryButton("Tout décocher")
        btn_uncheck_all.setFixedHeight(26)
        btn_uncheck_all.setStyleSheet(f"font-size: 11px; padding: 2px 8px; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px;")
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
            f"border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 4px 8px; }}"
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
                border-radius: 6px;
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
        self.sections_list.setMinimumHeight(220)
        self.sections_list.setVerticalScrollMode(QTreeWidget.ScrollMode.ScrollPerPixel)
        self.sections_list.currentItemChanged.connect(lambda cur, prev: self._on_tree_current_item_changed(cur))
        self.sections_list.itemClicked.connect(lambda item, *args: self._on_tree_current_item_changed(item))
        tree_container_layout.addWidget(self.sections_list)
        sections_layout.addWidget(self.section_tree_container, 1)
        left_layout.addWidget(sections_card, 1)

        # 4. Splitter horizontal (Gauche = Contrôles de portée, Droite = Visionneuse & Vue finale assemblée)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(left_container)

        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # Barre de sélection de vue (Document source vs Vue finale assemblée)
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

        # Stack de visualisation
        self.preview_stack = QStackedWidget()

        # Page 0 : Visionneuse native / paginée
        self.preview_widget = DocumentPreviewWidget(self.doc)
        self.preview_stack.addWidget(self.preview_widget)

        # Page 1 : Vue finale assemblée (ce qui sera réellement soumis au LLM)
        self.final_preview_card = QFrame()
        self.final_preview_card.setObjectName("finalPreviewCard")
        self.final_preview_card.setStyleSheet(f"""
            QFrame#finalPreviewCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        final_layout = QVBoxLayout(self.final_preview_card)
        final_layout.setContentsMargins(12, 10, 12, 10)
        final_layout.setSpacing(8)

        self.lbl_final_preview_kpi = QLabel("")
        self.lbl_final_preview_kpi.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        final_layout.addWidget(self.lbl_final_preview_kpi)

        self.final_preview_browser = QTextBrowser()
        self.final_preview_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 12px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: {DesignTokens.FONT_MAIN};
                font-size: 12px;
            }}
        """)
        final_layout.addWidget(self.final_preview_browser, 1)

        self.preview_stack.addWidget(self.final_preview_card)
        right_layout.addWidget(self.preview_stack, 1)

        self.main_splitter.addWidget(right_container)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.setSizes([480, 760])
        layout.addWidget(self.main_splitter, 1)

        # Connecteurs réactifs pour les spinboxes
        if self.is_paginated:
            self.spin_p_start.valueChanged.connect(self._on_start_page_changed)
            self.spin_p_end.valueChanged.connect(self._on_end_page_changed)

        # 5. Pied de page & validation
        footer = QHBoxLayout()
        self.lbl_footer_summary = QLabel("")
        self.lbl_footer_summary.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        footer.addWidget(self.lbl_footer_summary)
        self.lbl_context_tokens = QLabel("")
        self.lbl_context_tokens.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px;")
        self.token_progress = QProgressBar()
        self.token_progress.setFixedHeight(8)
        self.token_progress.setTextVisible(False)
        self.token_progress.setMaximum(self._context_limit or 1)
        self.token_progress.setStyleSheet(
            f"QProgressBar {{ background-color: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; "
            f"border-radius: 4px; }} QProgressBar::chunk {{ background-color: {DesignTokens.ACCENT_PRIMARY}; border-radius: 4px; }}"
        )
        footer.addWidget(self.lbl_context_tokens)
        footer.addWidget(self.token_progress, 1)
        if self._context_limit is None:
            self.lbl_context_tokens.hide()
            self.token_progress.hide()
        footer.addStretch()

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        footer.addWidget(btn_cancel)

        btn_apply = PrimaryButton("Valider la sélection pour la génération")
        btn_apply.setIcon(load_phosphor_icon("ph.check-circle", color="white"))
        btn_apply.clicked.connect(self._on_apply)
        footer.addWidget(btn_apply)

        layout.addLayout(footer)

        self._populate_sections()

    @staticmethod
    def _read_context_limit() -> int | None:
        """Retourne la limite de contexte configurée, sans inventer de valeur par défaut."""
        raw_limit = SettingsService.get("ai/context_limit", default=None)
        if isinstance(raw_limit, bool) or not isinstance(raw_limit, str | int | float):
            return None
        try:
            context_limit = int(raw_limit)
        except (TypeError, ValueError):
            return None
        return context_limit if context_limit > 0 else None

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

    def _on_tree_current_item_changed(self, item: QTreeWidgetItem | None) -> None:
        if not item:
            return
        row = self.sections_list.row(item)
        if row >= 0:
            self._on_section_selected(row)

    def _populate_sections(self) -> None:
        """Remplit la liste des sections/segments utiles sous forme arborescente."""
        self.sections_list.blockSignals(True)
        self.sections_list.clear()
        self._section_meta.clear()

        # 1. Extraction arborescente depuis les fragments utiles
        tree_nodes = ChunkingService.build_tree_from_chunks(self._useful_chunks)
        has_headings = has_structured_heading_nodes(tree_nodes)

        # Remplissage des menus déroulants de chapitres
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
                self.btn_mode_structure.show()
                if not self.is_paginated:
                    self.structure_scope_container.show()
            else:
                self.btn_mode_structure.hide()
                if hasattr(self, "structure_scope_container"):
                    self.structure_scope_container.hide()
            self.combo_c_start.blockSignals(False)
            self.combo_c_end.blockSignals(False)

        self.btn_mode_sections.setVisible(has_headings)
        self.btn_mode_sections.setEnabled(has_headings)
        self.btn_mode_all.setEnabled(self.is_paginated)
        self.btn_mode_range.setEnabled(self.is_paginated)
        if has_headings:
            if self.is_paginated:
                self.selection_mode = "pages"
                self.btn_mode_all.setChecked(True)
                self.all_card.show()
                self.chapters_card.hide()
                self.pages_card.show()
                self.slider_scope_container.hide()
                self.range_presets_container.hide()
                self.range_info_card.hide()
                self.left_layout.setStretchFactor(self.pages_card, 0)
                self._set_section_controls_visible(False)
            else:
                self.selection_mode = "sections"
                self.btn_mode_sections.setChecked(True)
                self.all_card.hide()
                self.chapters_card.hide()
                if hasattr(self, "structure_scope_container"):
                    self.structure_scope_container.hide()
                self._set_section_controls_visible(True)
        else:
            self.selection_mode = "chapters" if self.combo_c_start.count() else "pages"
            if self.is_paginated:
                self.btn_mode_all.setChecked(True)
                self.all_card.show()
                self.chapters_card.hide()
                self.pages_card.show()
                self.slider_scope_container.hide()
                self.range_presets_container.hide()
                self.range_info_card.hide()
                self.left_layout.setStretchFactor(self.pages_card, 0)
                self._set_section_controls_visible(False)
            elif self.combo_c_start.count():
                self.btn_mode_structure.setChecked(True)
                self.all_card.hide()
                self.chapters_card.show()
                if hasattr(self, "structure_scope_container"):
                    self.structure_scope_container.show()
                self._set_section_controls_visible(False)
            else:
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
            p_num = node.start_page
            end_p = node.end_page
            title = node.title
            word_count = node.word_count
            token_count = node.token_count
            level = node.level

            # Association avec le fragment d'origine
            chunk_dict: dict[str, Any] | None = None
            if node.chunk_index is not None:
                chunk_dict = next((c for c in self._useful_chunks if c.get("index") == node.chunk_index), None)
            if chunk_dict is None and not node.children:
                chunk_dict = next((c for c in self._useful_chunks if c.get("heading_path") == node.heading_path or c.get("title") == title), None)

            if chunk_dict is None:
                chunk_dict = {
                    "index": flat_idx,
                    "title": title,
                    "heading_path": node.heading_path,
                    "page_number": p_num,
                    "content": f"# {title}\n",
                    "tokens": token_count,
                }

            self._section_meta[flat_idx] = {
                "chunk": chunk_dict,
                "title": title,
                "heading_path": node.heading_path,
                "page_number": p_num,
                "end_page": end_p,
                "level": level,
                "word_count": word_count,
                "tokens": token_count,
                "root_index": root_index,
                "is_leaf": not node.children,
                "item": item,
            }

            in_range = True
            if self.is_paginated and p_num is not None and hasattr(self, "spin_p_start") and hasattr(self, "spin_p_end"):
                in_range = self.spin_p_start.value() <= p_num <= self.spin_p_end.value()
            is_checked = in_range and (flat_idx not in self._manually_deselected_indices)

            item.setCheckState(0, Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
            item.setData(0, Qt.ItemDataRole.UserRole, flat_idx)

            row_widget = SectionRowWidget(
                item=item,
                tree_widget=self.sections_list,
                title=title,
                is_checked=is_checked,
                page_number=p_num,
                end_page=end_p,
                level=level,
                word_count=word_count,
                cards_count=0,
                is_noise=False,
                is_leaf=not node.children,
                show_page=self.is_paginated,
            )
            row_widget.state_changed.connect(lambda st, it=item: self._on_tree_item_state_changed(it, st))
            item.setSizeHint(0, QSize(0, 36))

            content_preview = str(chunk_dict.get("content") or "")[:200].replace("\n", " ").strip()
            if len(content_preview) == 200:
                content_preview += "..."
            p_str = f" (Pages {p_num}–{end_p})" if (self.is_paginated and p_num and end_p and end_p > p_num) else (f" (Page {p_num})" if (self.is_paginated and p_num) else "")
            item.setToolTip(0, f'<b>{title}</b>{p_str}<br>• Volume : ~{token_count} tokens (~{word_count} mots)<hr><i>"{content_preview}"</i>')

            self.sections_list.setItemWidget(item, 0, row_widget)

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

        def _gather_chapter_stats(n: Any) -> tuple[int, int]:
            sub_c = len(n.children)
            words = getattr(n, "word_count", 0)
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
                    border-radius: {DesignTokens.RADIUS_SM}px;
                }}
            """)
            or_layout = QHBoxLayout(outline_row)
            or_layout.setContentsMargins(8, 6, 8, 6)
            or_layout.setSpacing(8)

            ch_badge = QLabel(f"Ch. {idx + 1}")
            ch_badge.setStyleSheet(
                "background-color: rgba(99, 102, 241, 0.2); color: #a5b4fc; border: 1px solid rgba(99, 102, 241, 0.4); border-radius: 4px; padding: 2px 6px; font-weight: bold; font-size: 10px;"
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

    def _apply_page_preset(self, start_p: int, end_p: int) -> None:
        """Applique rapidement une plage prédéfinie de pages."""
        if not self.is_paginated:
            return
        start_p = max(self._delimited_start_page, min(start_p, self._delimited_end_page))
        end_p = max(start_p, min(end_p, self._delimited_end_page))
        self.spin_p_start.setValue(start_p)
        self.spin_p_end.setValue(end_p)
        self._on_mode_range_clicked()

    def _on_check_all_chapters(self) -> None:
        """Sélectionne tous les chapitres."""
        for card in self._chapter_cards:
            card.set_checked(True)
        if hasattr(self, "combo_c_start") and hasattr(self, "combo_c_end") and self._chapter_cards:
            self.combo_c_start.blockSignals(True)
            self.combo_c_end.blockSignals(True)
            self.combo_c_start.setCurrentIndex(0)
            self.combo_c_end.setCurrentIndex(len(self._chapter_cards) - 1)
            self.combo_c_start.blockSignals(False)
            self.combo_c_end.blockSignals(False)
        self._update_kpi()
        self._refresh_final_preview()

    def _on_uncheck_all_chapters(self) -> None:
        """Désélectionne tous les chapitres."""
        for card in self._chapter_cards:
            card.set_checked(False)
        self._update_kpi()
        self._refresh_final_preview()

    def _on_chapter_card_toggled(self, chapter_index: int, is_checked: bool) -> None:
        """Gestionnaire de bascule d'une carte chapitre individuelle."""
        checked_indices = [c.chapter_index for c in self._chapter_cards if c.is_checked()]
        if checked_indices and hasattr(self, "combo_c_start") and hasattr(self, "combo_c_end"):
            min_c = min(checked_indices)
            max_c = max(checked_indices)
            self.combo_c_start.blockSignals(True)
            self.combo_c_end.blockSignals(True)
            self.combo_c_start.setCurrentIndex(min_c)
            self.combo_c_end.setCurrentIndex(max_c)
            self.combo_c_start.blockSignals(False)
            self.combo_c_end.blockSignals(False)
        self._update_kpi()
        self._refresh_final_preview()

    def _apply_initial_scope(self) -> None:
        """Initialise la portée à partir de la chaîne passée (ex: '3-8')."""
        if not self.is_paginated or not self.initial_scope_str:
            return

        import re

        m = re.match(r"^(\d+)(?:\s*-\s*(\d+))?$", self.initial_scope_str)
        if m:
            start_p = int(m.group(1))
            end_p = int(m.group(2)) if m.group(2) else start_p

            # Borner aux limites utiles
            start_p = max(self._delimited_start_page, min(start_p, self._delimited_end_page))
            end_p = max(start_p, min(end_p, self._delimited_end_page))

            if start_p > self._delimited_start_page or end_p < self._delimited_end_page:
                self.btn_mode_range.setChecked(True)
                self.all_card.hide()
                self.chapters_card.hide()
                self.pages_card.show()
                self.slider_scope_container.show()
                self.range_presets_container.show()
                self.range_info_card.show()
                self.left_layout.setStretchFactor(self.pages_card, 1)
                if hasattr(self, "structure_scope_container"):
                    self.structure_scope_container.hide()
                self.spin_p_start.setValue(start_p)
                self.spin_p_end.setValue(end_p)
                self.slider_p_start.setValue(start_p)
                self.slider_p_end.setValue(end_p)
                self.range_bar.set_range(start_p, end_p, self._doc_total_pages)
                self._filter_sections_by_pages(start_p, end_p)
                checked_pages = {
                    self._section_meta[i]["page_number"]
                    for i in range(self.sections_list.count())
                    if self.sections_list.item(i).checkState(0) == Qt.CheckState.Checked and self._section_meta.get(i, {}).get("page_number") is not None
                }
                if hasattr(self, "preview_widget"):
                    self.preview_widget.set_scope_range(start_p, end_p, included_pages=checked_pages)

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
        self.spin_p_start.blockSignals(True)
        self.spin_p_end.blockSignals(True)
        self.slider_p_start.blockSignals(True)
        self.slider_p_end.blockSignals(True)

        self.spin_p_start.setValue(self._delimited_start_page)
        self.spin_p_end.setValue(self._delimited_end_page)
        self.slider_p_start.setValue(self._delimited_start_page)
        self.slider_p_end.setValue(self._delimited_end_page)

        self.spin_p_start.blockSignals(False)
        self.spin_p_end.blockSignals(False)
        self.slider_p_start.blockSignals(False)
        self.slider_p_end.blockSignals(False)

        self.range_bar.set_range(self._delimited_start_page, self._delimited_end_page, self._doc_total_pages)
        self._set_all_checked(True)
        for card in self._chapter_cards:
            card.set_checked(True)
        self._filter_sections_by_pages(self._delimited_start_page, self._delimited_end_page)
        checked_pages = {
            self._section_meta[i]["page_number"]
            for i in range(self.sections_list.count())
            if self.sections_list.item(i).checkState(0) == Qt.CheckState.Checked and self._section_meta.get(i, {}).get("page_number") is not None
        }
        if hasattr(self, "preview_widget"):
            self.preview_widget.set_scope_range(self._delimited_start_page, self._delimited_end_page, included_pages=checked_pages)
        self._update_kpi()
        self._refresh_final_preview()

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
        self.range_bar.set_range(sp, ep, self._doc_total_pages)
        self._filter_sections_by_pages(sp, ep)
        checked_pages = {
            self._section_meta[i]["page_number"]
            for i in range(self.sections_list.count())
            if self.sections_list.item(i).checkState(0) == Qt.CheckState.Checked and self._section_meta.get(i, {}).get("page_number") is not None
        }
        if hasattr(self, "preview_widget"):
            self.preview_widget.set_scope_range(sp, ep, included_pages=checked_pages)
        self._update_kpi()
        self._refresh_final_preview()

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
        self._refresh_final_preview()

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
        self._refresh_final_preview()

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
        if (val > self._delimited_start_page or self.spin_p_end.value() < self._delimited_end_page) and not self.btn_mode_range.isChecked():
            self.btn_mode_range.setChecked(True)
            self.all_card.hide()
            self.chapters_card.hide()
            self.pages_card.show()
            self.slider_scope_container.show()
            self.range_presets_container.show()
            self.range_info_card.show()
            self.left_layout.setStretchFactor(self.pages_card, 1)
            if hasattr(self, "structure_scope_container"):
                self.structure_scope_container.hide()

        self.slider_p_start.blockSignals(True)
        self.slider_p_start.setValue(val)
        self.slider_p_start.blockSignals(False)

        self.range_bar.set_range(val, self.spin_p_end.value(), self._doc_total_pages)
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
        self._refresh_final_preview()

    def _on_end_page_changed(self, val: int) -> None:
        if self._syncing_selection:
            return
        if self.selection_mode != "pages":
            return
        if (self.spin_p_start.value() > self._delimited_start_page or val < self._delimited_end_page) and not self.btn_mode_range.isChecked():
            self.btn_mode_range.setChecked(True)
            self.all_card.hide()
            self.chapters_card.hide()
            self.pages_card.show()
            self.slider_scope_container.show()
            self.range_presets_container.show()
            self.range_info_card.show()
            self.left_layout.setStretchFactor(self.pages_card, 1)
            if hasattr(self, "structure_scope_container"):
                self.structure_scope_container.hide()

        self.slider_p_end.blockSignals(True)
        self.slider_p_end.setValue(val)
        self.slider_p_end.blockSignals(False)

        self.range_bar.set_range(self.spin_p_start.value(), val, self._doc_total_pages)
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
        self._refresh_final_preview()

    def _filter_sections_by_pages(self, start_p: int, end_p: int) -> None:
        """Coche ou décoche automatiquement les fragments selon leur appartenance à la plage de pages sans écraser les désélections manuelles."""
        if not self.is_paginated or self.selection_mode != "pages" or self._syncing_selection:
            return

        self._syncing_selection = True
        try:
            self.sections_list.blockSignals(True)
            for i in range(self.sections_list.count()):
                item = self.sections_list.item(i)
                meta = self._section_meta.get(i, {})
                p_num = meta.get("page_number")
                if p_num is not None:
                    in_range = start_p <= p_num <= end_p
                    should_check = in_range and (i not in self._manually_deselected_indices)
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
        self._refresh_final_preview()

    def _on_tree_item_state_changed(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        """Synchronisation dynamique arborescence -> slider et prévisualisation directe avec cascade parent-enfant."""
        row = self.sections_list.row(item)
        meta = self._section_meta.get(row, {})
        title = str(meta.get("title") or "")
        p_num = meta.get("page_number")

        # 1. Navigation immédiate vers la section concernée dans l'aperçu
        if hasattr(self, "preview_widget"):
            self.preview_widget.jump_to_heading(title, p_num)

        # 2. Cascade parent/enfant
        if not self._syncing_selection:
            self._syncing_selection = True
            try:
                if state in (Qt.CheckState.Checked, Qt.CheckState.Unchecked):
                    self._cascade_down(item, state)
                self._cascade_up(item)

                if state == Qt.CheckState.Unchecked:
                    self._manually_deselected_indices.add(row)
                elif state == Qt.CheckState.Checked:
                    self._manually_deselected_indices.discard(row)
            finally:
                self._syncing_selection = False

        if self.selection_mode == "pages" or self._syncing_selection:
            self._update_kpi()
            self._refresh_final_preview()
            return

        self._update_kpi()
        self._refresh_final_preview()

    def _cascade_down(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            w = self.sections_list.itemWidget(child, 0)
            if isinstance(w, SectionRowWidget):
                w.set_check_state(state)
            child_row = self.sections_list.row(child)
            if state == Qt.CheckState.Unchecked:
                self._manually_deselected_indices.add(child_row)
            elif state == Qt.CheckState.Checked:
                self._manually_deselected_indices.discard(child_row)
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

    def _on_view_source_clicked(self) -> None:
        self.preview_stack.setCurrentIndex(0)

    def _on_view_final_clicked(self) -> None:
        self._refresh_final_preview()
        self.preview_stack.setCurrentIndex(1)

    def _selected_chunks_for_mode(self) -> list[dict[str, Any]]:
        """Retourne les fragments gouvernés par le mode actif, sans croiser pages et sections."""
        if self.selection_mode == "pages":
            start_page = self.spin_p_start.value()
            end_page = self.spin_p_end.value()
            return [chunk for chunk in self._useful_chunks if chunk.get("page_number") is None or start_page <= chunk.get("page_number", start_page) <= end_page]

        if self.selection_mode == "chapters":
            chapter_chunks: list[dict[str, Any]] = []
            if hasattr(self, "_chapter_cards") and self._chapter_cards:
                checked_chs = {c.chapter_index for c in self._chapter_cards if c.is_checked()}
                for i in range(self.sections_list.count()):
                    item = self.sections_list.item(i)
                    meta = self._section_meta.get(i, {})
                    if item and item.childCount() == 0 and meta.get("root_index", -1) in checked_chs:
                        chunk = meta.get("chunk")
                        if isinstance(chunk, dict):
                            chapter_chunks.append(chunk)
                return chapter_chunks
            else:
                start = self.combo_c_start.currentIndex()
                end = self.combo_c_end.currentIndex()
                if start < 0 or end < 0:
                    return []
                for i in range(self.sections_list.count()):
                    item = self.sections_list.item(i)
                    meta = self._section_meta.get(i, {})
                    if item.childCount() == 0 and start <= meta.get("root_index", -1) <= end:
                        chunk = meta.get("chunk")
                        if isinstance(chunk, dict):
                            chapter_chunks.append(chunk)
                return chapter_chunks

        selected: list[dict[str, Any]] = []
        for i in range(self.sections_list.count()):
            item = self.sections_list.item(i)
            if item.checkState(0) != Qt.CheckState.Checked or item.childCount() > 0:
                continue
            chunk = self._section_meta.get(i, {}).get("chunk")
            if isinstance(chunk, dict):
                selected.append(chunk)
        return selected

    def _refresh_final_preview(self) -> None:
        """Génère le texte assemblé des fragments actuellement cochés avec statistiques exactes."""
        if not hasattr(self, "final_preview_browser"):
            return

        selected_chunks = self._selected_chunks_for_mode()
        checked_items = [
            (
                next(
                    (meta for meta in self._section_meta.values() if meta.get("chunk") is chunk),
                    {"title": chunk.get("title", ""), "page_number": chunk.get("page_number"), "tokens": chunk.get("tokens", 0)},
                ),
                chunk,
            )
            for chunk in selected_chunks
        ]

        if not checked_items:
            self.lbl_final_preview_kpi.setText("Aucun fragment sélectionné pour la vue finale.")
            self.final_preview_browser.setHtml(
                f"<p style='color: {DesignTokens.TEXT_MUTED}; font-style: italic;'>Cochez au moins une section ou ajustez la plage de pages pour prévisualiser le contenu assemblé.</p>"
            )
            return

        total_words = sum(len(str(c.get("content", "")).split()) for _, c in checked_items)
        total_tokens = sum(int(m.get("tokens", 0)) for m, _ in checked_items)
        approx_cards = max(1, total_words // 180) if total_words > 0 else 0

        self.lbl_final_preview_kpi.setText(f"{len(checked_items)} fragment(s) assemblé(s) • ~{total_tokens:,} tokens • ~{total_words:,} mots • ~{approx_cards} cartes estimées".replace(",", " "))

        html_blocks: list[str] = []
        for meta, chunk in checked_items:
            title = html.escape(str(meta.get("title", "")))
            p_num = meta.get("page_number")
            p_info = f" <span style='color: {DesignTokens.TEXT_MUTED}; font-size: 11px;'>(Page {p_num})</span>" if p_num else ""
            raw_content = str(chunk.get("content", ""))
            escaped_content = html.escape(raw_content)

            block = (
                f'<div style="background-color: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; '
                f'border-radius: 6px; padding: 12px; margin-bottom: 12px;">'
                f'<div style="color: {DesignTokens.ACCENT_PRIMARY}; font-weight: bold; font-size: 13px; margin-bottom: 8px;">'
                f"{title}{p_info}"
                f"</div>"
                f'<div style="color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; line-height: 1.5; white-space: pre-wrap;">'
                f"{escaped_content}"
                f"</div>"
                f"</div>"
            )
            html_blocks.append(block)

        self.final_preview_browser.setHtml("".join(html_blocks))

    def _on_section_selected(self, row: int) -> None:
        if row < 0 or row not in self._section_meta:
            return
        meta = self._section_meta[row]
        title = str(meta.get("title") or "")
        page = meta.get("page_number")
        self.preview_widget.jump_to_heading(title, page)

    def _set_all_checked(self, checked: bool) -> None:
        self.sections_list.blockSignals(True)
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.sections_list.count()):
            item = self.sections_list.item(i)
            item.setCheckState(0, state)
            w = self.sections_list.itemWidget(item, 0)
            if isinstance(w, SectionRowWidget):
                w.set_check_state(state)
            if not checked:
                self._manually_deselected_indices.add(i)
            else:
                self._manually_deselected_indices.discard(i)
        self.sections_list.blockSignals(False)

        self._update_kpi()
        self._refresh_final_preview()

    def _update_kpi(self) -> None:
        total = self.sections_list.count()
        selected_chunks = self._selected_chunks_for_mode()
        selected_ids = {id(chunk) for chunk in selected_chunks}
        checked_count = sum(
            1
            for i in range(total)
            if self.sections_list.item(i).childCount() == 0
            and (
                id(self._section_meta.get(i, {}).get("chunk")) in selected_ids
                or self.selection_mode == "pages"
                and self._section_meta.get(i, {}).get("page_number") is not None
                and self.spin_p_start.value() <= self._section_meta.get(i, {}).get("page_number") <= self.spin_p_end.value()
            )
        )
        total_tokens = sum(ContextCompactor.estimate_tokens(str(chunk.get("content", ""))) for chunk in selected_chunks)
        total_words = sum(len(str(chunk.get("content", "")).split()) for chunk in selected_chunks)

        approx_cards = max(1, total_words // 180) if total_words > 0 else 0
        self.lbl_selection_kpi.setText(f"{checked_count}/{total} sélectionné(s)")
        self.lbl_footer_summary.setText(f"Portée : {checked_count} fragment(s) • ~{total_tokens:,} tokens • ~{total_words:,} mots • ~{approx_cards} cartes estimées".replace(",", " "))
        self._update_context_progress(total_tokens)

        # Mise à jour des KPIs du Mode All
        if hasattr(self, "lbl_all_kpi_pages"):
            pages_span = self._delimited_end_page - self._delimited_start_page + 1 if self.is_paginated else 1
            self.lbl_all_kpi_pages.setText(f"{pages_span} p.")
            self.lbl_all_kpi_chapters.setText(f"{len(self._chapter_cards)} chap.")
            self.lbl_all_kpi_sections.setText(f"{len(self._section_meta)} sec.")
            all_words = sum(len(str(c.get("content", "")).split()) for c in self._useful_chunks)
            self.lbl_all_kpi_words.setText(f"~{all_words:,} mots".replace(",", " "))

        # Mise à jour des informations du Mode Range
        if hasattr(self, "lbl_range_coverage_kpi") and hasattr(self, "spin_p_start") and hasattr(self, "spin_p_end"):
            sp = self.spin_p_start.value()
            ep = self.spin_p_end.value()
            p_cnt = ep - sp + 1
            delimited_pages = self._delimited_end_page - self._delimited_start_page + 1
            p_pct = (p_cnt / delimited_pages * 100) if delimited_pages > 0 else 100.0
            self.lbl_range_coverage_kpi.setText(f"Pages {sp} à {ep} ({p_cnt} / {delimited_pages} pages — {p_pct:.1f}%)")
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
            self.lbl_chapters_summary.setText(f"{len(checked_chs)} chapitre{ch_plural} actif{ch_plural} • {total_words:,} mots sélectionnés".replace(",", " "))

    def _update_context_progress(self, selected_tokens: int) -> None:
        """Actualise la jauge de contexte lorsque la limite active est valide."""
        if self._context_limit is None:
            return
        ratio = selected_tokens / self._context_limit
        if ratio < 0.5:
            chunk_color = DesignTokens.COLOR_GREEN
        elif ratio < 0.8:
            chunk_color = DesignTokens.COLOR_YELLOW
        else:
            chunk_color = DesignTokens.COLOR_RED
        self.token_progress.setValue(min(selected_tokens, self._context_limit))
        self.token_progress.setStyleSheet(
            f"QProgressBar {{ background-color: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; "
            f"border-radius: 4px; }} QProgressBar::chunk {{ background-color: {chunk_color}; border-radius: 4px; }}"
        )
        self.lbl_context_tokens.setText(f"Contexte : ~{selected_tokens:,} / {self._context_limit:,} tokens".replace(",", " "))

    def _on_apply(self) -> None:
        checked_chunks = self._selected_chunks_for_mode()

        if not checked_chunks:
            show_toast(self, "Veuillez sélectionner au moins un fragment ou une section.", is_error=True)
            return

        if self.selection_mode == "pages":
            sp = self.spin_p_start.value()
            ep = self.spin_p_end.value()
            is_all = sp == self._delimited_start_page and ep == self._delimited_end_page
            if is_all:
                scope_title = f"Portée : Tout le document utile ({ep - sp + 1} pages)"
                range_str = f"{sp}-{ep}"
            elif sp == ep:
                scope_title = f"Portée : Page {sp}"
                range_str = str(sp)
            else:
                scope_title = f"Portée : Pages {sp} à {ep}"
                range_str = f"{sp}-{ep}"
        else:
            sp = self._delimited_start_page
            ep = self._delimited_end_page
            scope_title = f"Portée : {len(checked_chunks)} section(s) utile(s)"
            range_str = "" if self.is_paginated else "1"

        total_words = sum(len(str(c.get("content", "")).split()) for c in checked_chunks)
        approx_cards = max(1, total_words // 180) if total_words > 0 else 0
        stats_str = f"~{total_words:,} mots • ~{approx_cards} cartes estimées".replace(",", " ")

        self._result = {
            "chunks": checked_chunks,
            "scope_title": scope_title,
            "scope_stats": stats_str,
            "range_str": range_str,
            "start_page": sp,
            "end_page": ep,
            "selection_mode": self.selection_mode,
        }

        self.accept()

    def get_result(self) -> dict[str, Any]:
        """Retourne la configuration de portée sélectionnée pour la génération."""
        return self._result
