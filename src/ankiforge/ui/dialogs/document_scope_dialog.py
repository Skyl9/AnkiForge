"""
Dialogue modal de sélection de la portée de génération documentaire (DocumentScopeDialog).
Offre une interface visuelle similaire à la délimitation, mais restreinte exclusivement
aux parties utiles/filtrées du document (bornes start_page/end_page, exclusions respectées)
pour sélectionner la portée de génération (pages, sections, segments) sans altérer la base de données.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DocumentChunkModel, DocumentModel, DocumentPageModel
from ankiforge.services.ai.context_compactor import ContextCompactor
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.ui.components import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import (
    DocumentPreviewWidget,
    ScopeRangeBarWidget,
    SectionRowWidget,
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
        self.doc = doc
        self.initial_scope_str = initial_scope_str.strip()

        file_type = (getattr(self.doc, "file_type", "") or "").lower()
        if not file_type and getattr(self.doc, "title", "").lower().endswith(".pdf"):
            file_type = "pdf"
        self.is_paginated = file_type in ("pdf", "album", "pptx")

        # 1. Calcul des bornes utiles globales issues de la délimitation
        self._doc_total_pages = _safe_int(getattr(doc, "total_pages", None), default=1)
        self._delimited_start_page = _safe_int(getattr(doc, "start_page", None), default=1)
        self._delimited_end_page = _safe_int(getattr(doc, "end_page", None), default=self._doc_total_pages)
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
        self._section_meta: dict[int, dict[str, Any]] = {}

        # 4. Résultat sélectionné en sortie
        self._result: dict[str, Any] = {
            "chunks": [],
            "scope_title": "Portée : Tout le document utile",
            "scope_stats": "0 mot • 0 carte estimée",
            "range_str": f"{self._delimited_start_page}-{self._delimited_end_page}",
            "start_page": self._delimited_start_page,
            "end_page": self._delimited_end_page,
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
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QFrame#scopeHeaderCard, QFrame#scopePagesCard, QFrame#scopeSectionsCard {{
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

    def _load_filtered_chunks(self) -> list[dict[str, Any]]:
        """Charge uniquement les fragments faisant partie du périmètre utile délimité."""
        useful: list[dict[str, Any]] = []

        # Tenter de charger les chunks persistés en base de données (déjà filtrés par délimitation)
        db_chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == self.doc).order_by(DocumentChunkModel.chunk_index))

        if db_chunks:
            for idx, c in enumerate(db_chunks):
                p_num = c.page_number
                # Filtrage strict de pagination
                if self.is_paginated and p_num is not None and (p_num < self._delimited_start_page or p_num > self._delimited_end_page):
                    continue

                # Filtrage des titres exclus
                h_path = (c.heading_path or "").lower()
                if any(ex in h_path for ex in self._excluded_headings):
                    continue

                content = str(c.content or "")
                tokens = ContextCompactor.estimate_tokens(content)
                useful.append(
                    {
                        "index": idx,
                        "title": c.heading_path or (f"Page {p_num}" if p_num else f"Segment #{idx + 1}"),
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
                    useful.append(
                        {
                            "index": p_num - 1,
                            "title": f"Planche {p_num}",
                            "heading_path": f"Planche {p_num}",
                            "page_number": p_num,
                            "content": text,
                            "tokens": ContextCompactor.estimate_tokens(text),
                        }
                    )
            else:
                raw_chunks = ChunkingService.extract_chunks(self.doc.content or "", file_type=self.doc.file_type or "md")
                for idx, c in enumerate(raw_chunks):
                    p_num = c.get("page_number")
                    if self.is_paginated and p_num is not None and (p_num < self._delimited_start_page or p_num > self._delimited_end_page):
                        continue
                    h_path = str(c.get("heading_path") or "").lower()
                    if any(ex in h_path for ex in self._excluded_headings):
                        continue
                    content = str(c.get("content") or "")
                    useful.append(
                        {
                            "index": idx,
                            "title": c.get("heading_path") or (f"Page {p_num}" if p_num else f"Section #{idx + 1}"),
                            "heading_path": c.get("heading_path"),
                            "page_number": p_num,
                            "content": content,
                            "tokens": ContextCompactor.estimate_tokens(content),
                        }
                    )

        return useful

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Conteneur gauche : contrôles de portée & sélection des fragments
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # 1. En-tête descriptif
        header_card = QFrame()
        header_card.setObjectName("scopeHeaderCard")
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(12, 10, 12, 10)
        h_layout.setSpacing(4)

        header_top = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.sliders", color=DesignTokens.ACCENT_PRIMARY).pixmap(20, 20))
        title_lbl = QLabel(f"Portée de génération : <b>{self.doc.title}</b>")
        title_lbl.setStyleSheet(f"font-size: 14px; color: {DesignTokens.TEXT_PRIMARY}; border: none;")
        header_top.addWidget(icon_lbl)
        header_top.addWidget(title_lbl, 1)
        h_layout.addLayout(header_top)

        scope_desc = (
            f"Délimitation active : pages {self._delimited_start_page} à {self._delimited_end_page}. Sélectionnez les pages ou segments spécifiques à soumettre au prompt IA ou au lot batch."
            if self.is_paginated
            else "Sélectionnez les sections utiles à soumettre au prompt IA ou au lot batch."
        )
        desc_lbl = QLabel(scope_desc)
        desc_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none;")
        desc_lbl.setWordWrap(True)
        h_layout.addWidget(desc_lbl)
        left_layout.addWidget(header_card)

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

        # Mode de portée : Tout le document utile vs Plage personnalisée
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
        self.btn_mode_all = QPushButton(f"Tout le document utile ({useful_page_count} p.)")
        self.btn_mode_all.setCheckable(True)
        self.btn_mode_all.setChecked(True)
        self.btn_mode_all.setStyleSheet(mode_btn_style)

        self.btn_mode_range = QPushButton("Plage de pages")
        self.btn_mode_range.setCheckable(True)
        self.btn_mode_range.setStyleSheet(mode_btn_style)

        self.scope_mode_group = QButtonGroup(self)
        self.scope_mode_group.addButton(self.btn_mode_all)
        self.scope_mode_group.addButton(self.btn_mode_range)
        self.btn_mode_all.clicked.connect(self._on_mode_all_clicked)
        self.btn_mode_range.clicked.connect(self._on_mode_range_clicked)

        mode_row.addWidget(self.btn_mode_all)
        mode_row.addWidget(self.btn_mode_range)
        mode_row.addStretch()
        pages_card_layout.addLayout(mode_row)

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
        self.slider_scope_container.hide()  # Masqué par défaut en mode 'Tout le document utile'

        if self.is_paginated:
            left_layout.addWidget(self.pages_card)
        else:
            self.pages_card.hide()

        # 3. Liste des sections et segments utiles
        sections_card = QFrame()
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
        quick_btns = QHBoxLayout()
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
        self.sections_list.setMinimumHeight(220)
        self.sections_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.sections_list.currentRowChanged.connect(self._on_section_selected)
        sections_layout.addWidget(self.sections_list, 1)
        left_layout.addWidget(sections_card, 1)

        # 4. Splitter horizontal (Gauche = Contrôles de portée, Droite = Visionneuse)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(left_container)
        self.preview_widget = DocumentPreviewWidget(self.doc)
        self.main_splitter.addWidget(self.preview_widget)
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
        footer.addStretch()

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        footer.addWidget(btn_cancel)

        btn_apply = PrimaryButton("Valider la portée")
        btn_apply.setIcon(load_phosphor_icon("ph.check-circle", color="white"))
        btn_apply.clicked.connect(self._on_apply)
        footer.addWidget(btn_apply)

        layout.addLayout(footer)

        self._populate_sections()

    def _populate_sections(self) -> None:
        """Remplit la liste des sections/segments utiles."""
        self.sections_list.blockSignals(True)
        self.sections_list.clear()
        self._section_meta.clear()

        for idx, chunk in enumerate(self._useful_chunks):
            title = chunk.get("title") or f"Segment #{idx + 1}"
            p_num = chunk.get("page_number")
            content = str(chunk.get("content") or "")
            word_count = len(content.split()) if content else 0
            token_count = int(chunk.get("tokens") or ContextCompactor.estimate_tokens(content))

            self._section_meta[idx] = {
                "chunk": chunk,
                "title": title,
                "page_number": p_num,
                "word_count": word_count,
                "tokens": token_count,
            }

            item = QListWidgetItem()
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, idx)

            row_widget = SectionRowWidget(
                item=item,
                list_widget=self.sections_list,
                title=title,
                is_checked=True,
                page_number=p_num,
                word_count=word_count,
                cards_count=0,
                is_noise=False,
                show_page=self.is_paginated,
            )
            row_widget.checked_changed.connect(lambda _: self._update_kpi())
            item.setSizeHint(QSize(0, 36))

            preview = content[:200].replace("\n", " ").strip()
            if len(content) > 200:
                preview += "..."
            p_str = f" (Page {p_num})" if (self.is_paginated and p_num) else ""
            item.setToolTip(f'<b>{title}</b>{p_str}<br>• Volume : ~{token_count} tokens (~{word_count} mots)<hr><i>"{preview}"</i>')

            self.sections_list.addItem(item)
            self.sections_list.setItemWidget(item, row_widget)

        self.sections_list.blockSignals(False)

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
                self.slider_scope_container.show()
                self.spin_p_start.setValue(start_p)
                self.spin_p_end.setValue(end_p)
                self.slider_p_start.setValue(start_p)
                self.slider_p_end.setValue(end_p)
                self.range_bar.set_range(start_p, end_p, self._doc_total_pages)
                self.preview_widget.set_scope_range(start_p, end_p)
                self._filter_sections_by_pages(start_p, end_p)

    def _on_mode_all_clicked(self) -> None:
        self.slider_scope_container.hide()
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
        self.preview_widget.set_scope_range(self._delimited_start_page, self._delimited_end_page)
        self._filter_sections_by_pages(self._delimited_start_page, self._delimited_end_page)
        self._update_kpi()

    def _on_mode_range_clicked(self) -> None:
        self.slider_scope_container.show()
        sp = self.spin_p_start.value()
        ep = self.spin_p_end.value()
        self.range_bar.set_range(sp, ep, self._doc_total_pages)
        self.preview_widget.set_scope_range(sp, ep)
        self._filter_sections_by_pages(sp, ep)
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
        if (val > self._delimited_start_page or self.spin_p_end.value() < self._delimited_end_page) and not self.btn_mode_range.isChecked():
            self.btn_mode_range.setChecked(True)
            self.slider_scope_container.show()

        self.slider_p_start.blockSignals(True)
        self.slider_p_start.setValue(val)
        self.slider_p_start.blockSignals(False)

        self.range_bar.set_range(val, self.spin_p_end.value(), self._doc_total_pages)
        self.preview_widget.set_scope_range(val, self.spin_p_end.value())
        self.preview_widget.jump_to_page(val)
        self._filter_sections_by_pages(val, self.spin_p_end.value())
        self._update_kpi()

    def _on_end_page_changed(self, val: int) -> None:
        if (self.spin_p_start.value() > self._delimited_start_page or val < self._delimited_end_page) and not self.btn_mode_range.isChecked():
            self.btn_mode_range.setChecked(True)
            self.slider_scope_container.show()

        self.slider_p_end.blockSignals(True)
        self.slider_p_end.setValue(val)
        self.slider_p_end.blockSignals(False)

        self.range_bar.set_range(self.spin_p_start.value(), val, self._doc_total_pages)
        self.preview_widget.set_scope_range(self.spin_p_start.value(), val)
        self.preview_widget.jump_to_page(val)
        self._filter_sections_by_pages(self.spin_p_start.value(), val)
        self._update_kpi()

    def _filter_sections_by_pages(self, start_p: int, end_p: int) -> None:
        """Coche ou décoche automatiquement les fragments selon leur appartenance à la plage de pages."""
        if not self.is_paginated:
            return

        self.sections_list.blockSignals(True)
        for i in range(self.sections_list.count()):
            item = self.sections_list.item(i)
            meta = self._section_meta.get(i, {})
            p_num = meta.get("page_number")
            if p_num is not None:
                in_range = start_p <= p_num <= end_p
                item.setCheckState(Qt.CheckState.Checked if in_range else Qt.CheckState.Unchecked)
                w = self.sections_list.itemWidget(item)
                if isinstance(w, SectionRowWidget):
                    w.set_checked(in_range)
        self.sections_list.blockSignals(False)

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
            item.setCheckState(state)
            w = self.sections_list.itemWidget(item)
            if isinstance(w, SectionRowWidget):
                w.set_checked(checked)
        self.sections_list.blockSignals(False)
        self._update_kpi()

    def _update_kpi(self) -> None:
        total = self.sections_list.count()
        checked_count = 0
        total_tokens = 0
        total_words = 0

        for i in range(total):
            item = self.sections_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                meta = self._section_meta.get(i, {})
                checked_count += 1
                total_tokens += int(meta.get("tokens", 0))
                total_words += int(meta.get("word_count", 0))

        approx_cards = max(1, total_words // 180) if total_words > 0 else 0
        self.lbl_selection_kpi.setText(f"{checked_count}/{total} sélectionné(s)")
        self.lbl_footer_summary.setText(f"Portée : {checked_count} fragment(s) • ~{total_tokens:,} tokens • ~{total_words:,} mots • ~{approx_cards} cartes estimées".replace(",", " "))

    def _on_apply(self) -> None:
        checked_chunks: list[dict[str, Any]] = []
        for i in range(self.sections_list.count()):
            item = self.sections_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                meta = self._section_meta.get(i, {})
                chunk = meta.get("chunk")
                if isinstance(chunk, dict):
                    checked_chunks.append(chunk)

        if not checked_chunks:
            show_toast(self, "Veuillez sélectionner au moins un fragment ou une section.", is_error=True)
            return

        if self.is_paginated:
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
            sp = 1
            ep = 1
            scope_title = f"Portée : {len(checked_chunks)} section(s) utile(s)"
            range_str = "1"

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
        }

        self.accept()

    def get_result(self) -> dict[str, Any]:
        """Retourne la configuration de portée sélectionnée pour la génération."""
        return self._result
