"""
Composant Tiroir / Bibliothèque de Snippets Modulaires pour l'Atelier de Modèles.
Permet d'explorer, inspecter les codes HTML/CSS, modifier en place, et créer de nouveaux snippets
sans modale (navigation Master-Detail & In-Place Form intégrée avec relief tactile, onglets de code compacts et affordance visuelle).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.cards.snippet_library import SnippetItem, SnippetLibrary
from ankiforge.ui.components.buttons import DangerButton, IconButton, PrimaryButton, SecondaryButton
from ankiforge.ui.components.code_editor import CodeEditorWithGutter
from ankiforge.ui.components.flow_layout import FlowWidget
from ankiforge.ui.components.inputs import GlowLineEdit, StyledLineEdit
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon


class SnippetCardWidget(QFrame):
    """Carte individuelle compacte et aérée représentant un snippet modulaire."""

    insert_requested = Signal(SnippetItem)
    edit_requested = Signal(SnippetItem)

    def __init__(self, snippet: SnippetItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.snippet = snippet
        self.setObjectName("snippetCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.setStyleSheet(f"""
            QFrame#snippetCard {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 2px;
            }}
            QFrame#snippetCard:hover {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Ligne 1 : Icône pastille + Titre + Actions (Insérer + Inspecter)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon(snippet.icon_name, color=DesignTokens.ACCENT_PRIMARY).pixmap(15, 15))
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        header_layout.addWidget(icon_lbl)

        title_lbl = QLabel(snippet.name)
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        header_layout.addWidget(title_lbl, 1)

        self.btn_insert = IconButton("ph.plus", tooltip="Insérer dans le code au curseur", size=18)
        self.btn_insert.clicked.connect(lambda: self.insert_requested.emit(self.snippet))
        header_layout.addWidget(self.btn_insert)

        btn_edit = IconButton("ph.caret-right", tooltip="Inspecter et modifier le snippet", size=18)
        btn_edit.clicked.connect(lambda: self.edit_requested.emit(self.snippet))
        header_layout.addWidget(btn_edit)
        layout.addLayout(header_layout)

        # Ligne 2 : Description courte
        if snippet.description:
            desc_lbl = QLabel(snippet.description)
            desc_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; border: none; background: transparent;")
            desc_lbl.setWordWrap(True)
            layout.addWidget(desc_lbl)

    def mousePressEvent(self, event) -> None:
        """Le clic sur la carte bascule vers la vue d'édition/détail du snippet."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.edit_requested.emit(self.snippet)
        super().mousePressEvent(event)


class SnippetLibraryDrawer(QWidget):
    """
    Explorateur complet des snippets modulaires avec navigation intégrée Master-Detail
    et création de composants in-place sans modale bloquante.
    """

    snippet_selected = Signal(SnippetItem)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_category = "Tous"
        self._all_snippets = SnippetLibrary.get_all_snippets()
        self._selected_snippet_for_detail: SnippetItem | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(0)

        # Stack de vues : 0=Liste des snippets, 1=Détail/Édition, 2=Création in-place
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        self._init_list_view()
        self._init_detail_view()
        self._init_create_view()

        self.stack.setCurrentIndex(0)

    # =========================================================================
    # 1. VUE 0 : LISTE & EXPLORATION (Master View)
    # =========================================================================
    def _init_list_view(self) -> None:
        list_widget = QWidget()
        layout = QVBoxLayout(list_widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # Barre supérieure : Titre + Bouton Nouveau Snippet
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)

        lbl_title = QLabel("BIBLIOTHÈQUE")
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        top_row.addWidget(lbl_title)
        top_row.addStretch()

        btn_new = PrimaryButton("Nouveau")
        btn_new.setIcon(load_phosphor_icon("ph.plus", color="white"))
        btn_new.setFixedHeight(26)
        btn_new.setToolTip("Créer un nouveau snippet personnalisé")
        btn_new.clicked.connect(self._open_create_view)
        top_row.addWidget(btn_new)

        layout.addLayout(top_row)

        # Barre de recherche avec loupe intégrée, animation et contour focus
        self.search_input = GlowLineEdit(placeholder="Rechercher un snippet...")
        self.search_input.setObjectName("snippetSearchInput")
        self.search_input.setProperty("role", "search")
        self.search_input.textChanged.connect(self._filter_snippets)
        layout.addWidget(self.search_input)

        # Filtres de catégories fluides (FlowWidget)
        self.category_container = FlowWidget(margin=0, h_spacing=4, v_spacing=4)
        self.category_container.setObjectName("categoryContainer")
        self.category_container.setStyleSheet("QWidget#categoryContainer { background: transparent; border: none; }")
        self.category_layout = self.category_container.flow_layout
        self._rebuild_category_buttons()
        layout.addWidget(self.category_container)

        # Zone scrollable des cartes de snippets
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)

        scroll_area.setWidget(self.cards_container)
        layout.addWidget(scroll_area, 1)

        self.stack.addWidget(list_widget)
        self._populate_cards(self._all_snippets)

    def _rebuild_category_buttons(self) -> None:
        self.category_container.clear()

        categories = ["Tous"] + SnippetLibrary.get_categories()
        self.category_buttons: list[SecondaryButton] = []

        for cat in categories:
            btn = SecondaryButton(cat)
            btn.setFixedHeight(22)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            if cat == self._current_category:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {DesignTokens.BG_ACTIVE};
                        border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                        color: {DesignTokens.TEXT_PRIMARY};
                        font-size: 10px;
                        font-weight: bold;
                        padding: 1px 8px;
                        border-radius: {DesignTokens.RADIUS_SM}px;
                    }}
                    QPushButton:pressed {{
                        padding-top: 2px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {DesignTokens.BG_INPUT};
                        border: 1px solid {DesignTokens.BORDER_COLOR};
                        color: {DesignTokens.TEXT_MUTED};
                        font-size: 10px;
                        padding: 1px 8px;
                        border-radius: {DesignTokens.RADIUS_SM}px;
                    }}
                    QPushButton:hover {{
                        background-color: {DesignTokens.BG_HOVER};
                        border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                        color: {DesignTokens.TEXT_PRIMARY};
                    }}
                    QPushButton:pressed {{
                        background-color: {DesignTokens.BG_ACTIVE};
                        padding-top: 2px;
                    }}
                """)
            btn.clicked.connect(lambda _, c=cat, b=btn: self._select_category(c, b))
            self.category_buttons.append(btn)
            self.category_layout.addWidget(btn)

    def _select_category(self, category: str, clicked_btn: SecondaryButton) -> None:
        self._current_category = category
        for btn in self.category_buttons:
            if btn == clicked_btn:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {DesignTokens.BG_ACTIVE};
                        border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                        color: {DesignTokens.TEXT_PRIMARY};
                        font-size: 10px;
                        font-weight: bold;
                        padding: 1px 8px;
                        border-radius: {DesignTokens.RADIUS_SM}px;
                    }}
                    QPushButton:pressed {{
                        padding-top: 2px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {DesignTokens.BG_INPUT};
                        border: 1px solid {DesignTokens.BORDER_COLOR};
                        color: {DesignTokens.TEXT_MUTED};
                        font-size: 10px;
                        padding: 1px 8px;
                        border-radius: {DesignTokens.RADIUS_SM}px;
                    }}
                    QPushButton:hover {{
                        background-color: {DesignTokens.BG_HOVER};
                        border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                        color: {DesignTokens.TEXT_PRIMARY};
                    }}
                    QPushButton:pressed {{
                        background-color: {DesignTokens.BG_ACTIVE};
                        padding-top: 2px;
                    }}
                """)
        self._filter_snippets()

    def _filter_snippets(self) -> None:
        query = self.search_input.text().lower().strip()
        filtered = []
        for s in self._all_snippets:
            if self._current_category != "Tous" and s.category != self._current_category:
                continue
            if query:
                text_match = query in s.name.lower() or query in s.description.lower() or any(query in t.lower() for t in s.tags)
                if not text_match:
                    continue
            filtered.append(s)
        self._populate_cards(filtered)

    def _populate_cards(self, snippets: list[SnippetItem]) -> None:
        while self.cards_layout.count():
            child = self.cards_layout.takeAt(0)
            if child:
                w = child.widget()
                if w:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()

        if not snippets:
            empty_lbl = QLabel("Aucun snippet correspondant.")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; padding: 20px;")
            self.cards_layout.addWidget(empty_lbl)
        else:
            for s in snippets:
                card = SnippetCardWidget(s)
                card.insert_requested.connect(self.snippet_selected.emit)
                card.edit_requested.connect(self._open_detail_view)
                self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()

    # =========================================================================
    # 2. VUE 1 : DÉTAIL & ÉDITION (Detail Zoom View)
    # =========================================================================
    def _init_detail_view(self) -> None:
        detail_widget = QWidget()
        layout = QVBoxLayout(detail_widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # Barre supérieure : Bouton Retour + Titre + Bouton Supprimer
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(6)

        btn_back = SecondaryButton("Retour")
        btn_back.setIcon(load_phosphor_icon("ph.arrow-left", color=DesignTokens.TEXT_PRIMARY))
        btn_back.setFixedHeight(28)
        btn_back.clicked.connect(self._return_to_list)
        top_bar.addWidget(btn_back)

        lbl_detail_title = QLabel("DÉTAIL DU SNIPPET")
        lbl_detail_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: bold;")
        top_bar.addWidget(lbl_detail_title)
        top_bar.addStretch()

        self.btn_detail_delete = DangerButton("Supprimer", ghost=True)
        self.btn_detail_delete.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))
        self.btn_detail_delete.setFixedHeight(28)
        self.btn_detail_delete.clicked.connect(self._delete_current_detail_snippet)
        top_bar.addWidget(self.btn_detail_delete)

        layout.addLayout(top_bar)

        # Formulaire scrollable structuré en cartes
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(10)

        # --- Section 1 : Métadonnées du Snippet ---
        meta_card = QFrame()
        meta_card.setObjectName("detailMetaCard")
        meta_card.setStyleSheet(f"""
            QFrame#detailMetaCard {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-top: 1px solid {DesignTokens.BORDER_LIGHT};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        meta_layout = QVBoxLayout(meta_card)
        meta_layout.setContentsMargins(10, 10, 10, 10)
        meta_layout.setSpacing(6)

        lbl_meta_hdr = QLabel("INFORMATIONS GÉNÉRALES")
        lbl_meta_hdr.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px; border: none;")
        meta_layout.addWidget(lbl_meta_hdr)

        lbl_name = QLabel("Nom du snippet :")
        lbl_name.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; border: none;")
        meta_layout.addWidget(lbl_name)
        self.detail_name_input = StyledLineEdit(icon_name="ph.text-t", placeholder="Nom du composant")
        meta_layout.addWidget(self.detail_name_input)

        lbl_cat = QLabel("Catégorie :")
        lbl_cat.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; border: none;")
        meta_layout.addWidget(lbl_cat)
        self.detail_cat_input = StyledLineEdit(icon_name="ph.folder", placeholder="Catégorie")
        meta_layout.addWidget(self.detail_cat_input)

        lbl_desc = QLabel("Description :")
        lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; border: none;")
        meta_layout.addWidget(lbl_desc)
        self.detail_desc_input = StyledLineEdit(icon_name="ph.chat-centered-text", placeholder="Description")
        meta_layout.addWidget(self.detail_desc_input)

        # Icône avec preview dynamique
        lbl_icon = QLabel("Icône Phosphor :")
        lbl_icon.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; border: none;")
        meta_layout.addWidget(lbl_icon)

        icon_row = QHBoxLayout()
        icon_row.setSpacing(6)
        self.detail_icon_input = StyledLineEdit(icon_name="ph.sparkle", placeholder="ex: ph.info, ph.code")
        self.detail_icon_input.textChanged.connect(self._update_detail_icon_preview)
        icon_row.addWidget(self.detail_icon_input, 1)

        self.detail_icon_preview = QLabel()
        self.detail_icon_preview.setFixedSize(30, 30)
        self.detail_icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_icon_preview.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.BG_ACTIVE};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
            }}
        """)
        icon_row.addWidget(self.detail_icon_preview)
        meta_layout.addLayout(icon_row)

        form_layout.addWidget(meta_card)

        # --- Section 2 : Éditeur de Code Compact avec Sous-Onglets (HTML / CSS) ---
        code_card = QFrame()
        code_card.setObjectName("detailCodeCard")
        code_card.setStyleSheet(f"""
            QFrame#detailCodeCard {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-top: 1px solid {DesignTokens.BORDER_LIGHT};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        code_layout = QVBoxLayout(code_card)
        code_layout.setContentsMargins(10, 10, 10, 10)
        code_layout.setSpacing(6)

        # En-tête avec switcher HTML / CSS
        code_tab_row = QHBoxLayout()
        code_tab_row.setSpacing(6)

        self.btn_detail_tab_html = SecondaryButton("Template HTML")
        self.btn_detail_tab_html.setIcon(load_phosphor_icon("ph.file-html", color=DesignTokens.TEXT_PRIMARY))
        self.btn_detail_tab_html.setFixedHeight(24)

        self.btn_detail_tab_css = SecondaryButton("Style CSS")
        self.btn_detail_tab_css.setIcon(load_phosphor_icon("ph.file-css", color=DesignTokens.TEXT_PRIMARY))
        self.btn_detail_tab_css.setFixedHeight(24)

        self.btn_detail_tab_html.clicked.connect(lambda: self._switch_detail_code_tab(0))
        self.btn_detail_tab_css.clicked.connect(lambda: self._switch_detail_code_tab(1))

        code_tab_row.addWidget(self.btn_detail_tab_html, 1)
        code_tab_row.addWidget(self.btn_detail_tab_css, 1)
        code_layout.addLayout(code_tab_row)

        self.detail_code_stack = QStackedWidget()

        self.detail_html_editor = CodeEditorWithGutter(
            placeholder='<div class="custom-card">\n  {{Champ}}\n</div>',
            mode="html",
        )
        self.detail_html_editor.setFixedHeight(140)
        self.detail_code_stack.addWidget(self.detail_html_editor)

        self.detail_css_editor = CodeEditorWithGutter(
            placeholder=".custom-card {\n  margin: 10px 0;\n  padding: 12px;\n}",
            mode="css",
        )
        self.detail_css_editor.setFixedHeight(140)
        self.detail_code_stack.addWidget(self.detail_css_editor)

        code_layout.addWidget(self.detail_code_stack)
        form_layout.addWidget(code_card)

        scroll_area.setWidget(form_container)
        layout.addWidget(scroll_area, 1)

        # Barre d'actions inférieure avec relief
        btn_actions_layout = QVBoxLayout()
        btn_actions_layout.setSpacing(6)

        btn_save = PrimaryButton("Enregistrer les modifications")
        btn_save.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        btn_save.setFixedHeight(30)
        btn_save.clicked.connect(self._save_detail_snippet)
        btn_actions_layout.addWidget(btn_save)

        self.btn_insert_detail = SecondaryButton("Insérer au curseur")
        self.btn_insert_detail.setIcon(load_phosphor_icon("ph.cursor-click", color=DesignTokens.TEXT_PRIMARY))
        self.btn_insert_detail.setFixedHeight(28)
        self.btn_insert_detail.setToolTip("Insérer ce snippet à la position actuelle du curseur dans l'éditeur actif.")
        self.btn_insert_detail.clicked.connect(self._insert_current_detail_snippet)
        btn_actions_layout.addWidget(self.btn_insert_detail)

        layout.addLayout(btn_actions_layout)

        self.stack.addWidget(detail_widget)
        self._switch_detail_code_tab(0)

    def _switch_detail_code_tab(self, index: int) -> None:
        self.detail_code_stack.setCurrentIndex(index)
        if index == 0:
            self.btn_detail_tab_html.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    color: {DesignTokens.TEXT_PRIMARY};
                    font-weight: bold;
                    font-size: 10px;
                }}
            """)
            self.btn_detail_tab_css.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    color: {DesignTokens.TEXT_MUTED};
                    font-size: 10px;
                }}
                QPushButton:hover {{
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    background-color: {DesignTokens.BG_HOVER};
                }}
            """)
        else:
            self.btn_detail_tab_css.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    color: {DesignTokens.TEXT_PRIMARY};
                    font-weight: bold;
                    font-size: 10px;
                }}
            """)
            self.btn_detail_tab_html.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    color: {DesignTokens.TEXT_MUTED};
                    font-size: 10px;
                }}
                QPushButton:hover {{
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    background-color: {DesignTokens.BG_HOVER};
                }}
            """)

    def _update_detail_icon_preview(self, icon_name: str) -> None:
        icon_clean = icon_name.strip() or "ph.sparkle"
        pixmap = load_phosphor_icon(icon_clean, color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16)
        self.detail_icon_preview.setPixmap(pixmap)

    # =========================================================================
    # 3. VUE 2 : CRÉATION IN-PLACE (Creation Form View)
    # =========================================================================
    def _init_create_view(self) -> None:
        create_widget = QWidget()
        layout = QVBoxLayout(create_widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # Barre supérieure : Annuler + Titre
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(6)

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.setIcon(load_phosphor_icon("ph.arrow-left", color=DesignTokens.TEXT_PRIMARY))
        btn_cancel.setFixedHeight(28)
        btn_cancel.clicked.connect(self._return_to_list)
        top_bar.addWidget(btn_cancel)

        lbl_create_title = QLabel("NOUVEAU SNIPPET")
        lbl_create_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: bold;")
        top_bar.addWidget(lbl_create_title)
        top_bar.addStretch()

        layout.addLayout(top_bar)

        # Formulaire scrollable structuré en cartes
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(10)

        # --- Section 1 : Métadonnées ---
        meta_card = QFrame()
        meta_card.setObjectName("createMetaCard")
        meta_card.setStyleSheet(f"""
            QFrame#createMetaCard {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-top: 1px solid {DesignTokens.BORDER_LIGHT};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        meta_layout = QVBoxLayout(meta_card)
        meta_layout.setContentsMargins(10, 10, 10, 10)
        meta_layout.setSpacing(6)

        lbl_meta_hdr = QLabel("INFORMATIONS GÉNÉRALES")
        lbl_meta_hdr.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px; border: none;")
        meta_layout.addWidget(lbl_meta_hdr)

        lbl_name = QLabel("Nom du snippet :")
        lbl_name.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; border: none;")
        meta_layout.addWidget(lbl_name)
        self.create_name_input = StyledLineEdit(icon_name="ph.text-t", placeholder="ex: Encadré Définition")
        meta_layout.addWidget(self.create_name_input)

        lbl_cat = QLabel("Catégorie :")
        lbl_cat.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; border: none;")
        meta_layout.addWidget(lbl_cat)
        self.create_cat_input = StyledLineEdit(icon_name="ph.folder", placeholder="ex: Callouts & Remarques")
        self.create_cat_input.setText("Personnalisé")
        meta_layout.addWidget(self.create_cat_input)

        lbl_desc = QLabel("Description :")
        lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; border: none;")
        meta_layout.addWidget(lbl_desc)
        self.create_desc_input = StyledLineEdit(icon_name="ph.chat-centered-text", placeholder="Courte description de l'usage")
        meta_layout.addWidget(self.create_desc_input)

        # Icône avec preview dynamique
        lbl_icon = QLabel("Icône Phosphor :")
        lbl_icon.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; border: none;")
        meta_layout.addWidget(lbl_icon)

        icon_row = QHBoxLayout()
        icon_row.setSpacing(6)
        self.create_icon_input = StyledLineEdit(icon_name="ph.sparkle", placeholder="ph.sparkle")
        self.create_icon_input.setText("ph.sparkle")
        self.create_icon_input.textChanged.connect(self._update_create_icon_preview)
        icon_row.addWidget(self.create_icon_input, 1)

        self.create_icon_preview = QLabel()
        self.create_icon_preview.setFixedSize(30, 30)
        self.create_icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.create_icon_preview.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.BG_ACTIVE};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
            }}
        """)
        icon_row.addWidget(self.create_icon_preview)
        meta_layout.addLayout(icon_row)

        form_layout.addWidget(meta_card)

        # --- Section 2 : Éditeur de Code Compact avec Sous-Onglets (HTML / CSS) ---
        code_card = QFrame()
        code_card.setObjectName("createCodeCard")
        code_card.setStyleSheet(f"""
            QFrame#createCodeCard {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-top: 1px solid {DesignTokens.BORDER_LIGHT};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        code_layout = QVBoxLayout(code_card)
        code_layout.setContentsMargins(10, 10, 10, 10)
        code_layout.setSpacing(6)

        # En-tête switcher
        code_tab_row = QHBoxLayout()
        code_tab_row.setSpacing(6)

        self.btn_create_tab_html = SecondaryButton("Template HTML")
        self.btn_create_tab_html.setIcon(load_phosphor_icon("ph.file-html", color=DesignTokens.TEXT_PRIMARY))
        self.btn_create_tab_html.setFixedHeight(24)

        self.btn_create_tab_css = SecondaryButton("Style CSS")
        self.btn_create_tab_css.setIcon(load_phosphor_icon("ph.file-css", color=DesignTokens.TEXT_PRIMARY))
        self.btn_create_tab_css.setFixedHeight(24)

        self.btn_create_tab_html.clicked.connect(lambda: self._switch_create_code_tab(0))
        self.btn_create_tab_css.clicked.connect(lambda: self._switch_create_code_tab(1))

        code_tab_row.addWidget(self.btn_create_tab_html, 1)
        code_tab_row.addWidget(self.btn_create_tab_css, 1)
        code_layout.addLayout(code_tab_row)

        self.create_code_stack = QStackedWidget()

        self.create_html_editor = CodeEditorWithGutter(
            placeholder='<div class="af-custom-box">\n  <div class="af-custom-title">Titre</div>\n  <div class="af-custom-body">{{Contenu}}</div>\n</div>',
            mode="html",
        )
        self.create_html_editor.setFixedHeight(140)
        self.create_code_stack.addWidget(self.create_html_editor)

        self.create_css_editor = CodeEditorWithGutter(
            placeholder=".af-custom-box {\n  margin: 12px 0;\n  padding: 10px;\n  border-radius: 8px;\n  background: rgba(99, 102, 241, 0.1);\n}",
            mode="css",
        )
        self.create_css_editor.setFixedHeight(140)
        self.create_code_stack.addWidget(self.create_css_editor)

        code_layout.addWidget(self.create_code_stack)
        form_layout.addWidget(code_card)

        scroll_area.setWidget(form_container)
        layout.addWidget(scroll_area, 1)

        # Bouton Créer avec relief et glow
        btn_submit = PrimaryButton("Créer et Ajouter à la Bibliothèque")
        btn_submit.setIcon(load_phosphor_icon("ph.plus", color="white"))
        btn_submit.setFixedHeight(30)
        btn_submit.clicked.connect(self._submit_create_snippet)
        layout.addWidget(btn_submit)

        self.stack.addWidget(create_widget)
        self._switch_create_code_tab(0)
        self._update_create_icon_preview("ph.sparkle")

    def _switch_create_code_tab(self, index: int) -> None:
        self.create_code_stack.setCurrentIndex(index)
        if index == 0:
            self.btn_create_tab_html.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    color: {DesignTokens.TEXT_PRIMARY};
                    font-weight: bold;
                    font-size: 10px;
                }}
            """)
            self.btn_create_tab_css.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    color: {DesignTokens.TEXT_MUTED};
                    font-size: 10px;
                }}
                QPushButton:hover {{
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    background-color: {DesignTokens.BG_HOVER};
                }}
            """)
        else:
            self.btn_create_tab_css.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    color: {DesignTokens.TEXT_PRIMARY};
                    font-weight: bold;
                    font-size: 10px;
                }}
            """)
            self.btn_create_tab_html.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    color: {DesignTokens.TEXT_MUTED};
                    font-size: 10px;
                }}
                QPushButton:hover {{
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    background-color: {DesignTokens.BG_HOVER};
                }}
            """)

    def _update_create_icon_preview(self, icon_name: str) -> None:
        icon_clean = icon_name.strip() or "ph.sparkle"
        pixmap = load_phosphor_icon(icon_clean, color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16)
        self.create_icon_preview.setPixmap(pixmap)

    # =========================================================================
    # ACTIONS & SLOTS
    # =========================================================================
    @Slot()
    def _return_to_list(self) -> None:
        self.stack.setCurrentIndex(0)

    @Slot()
    def _open_create_view(self) -> None:
        self.create_name_input.clear()
        self.create_cat_input.setText("Personnalisé")
        self.create_desc_input.clear()
        self.create_icon_input.setText("ph.sparkle")
        self.create_html_editor.clear()
        self.create_css_editor.clear()
        self._update_create_icon_preview("ph.sparkle")
        self._switch_create_code_tab(0)
        self.stack.setCurrentIndex(2)

    @Slot(SnippetItem)
    def _open_detail_view(self, snippet: SnippetItem) -> None:
        self._selected_snippet_for_detail = snippet
        self.detail_name_input.setText(snippet.name)
        self.detail_cat_input.setText(snippet.category)
        self.detail_desc_input.setText(snippet.description)
        self.detail_icon_input.setText(snippet.icon_name)
        self._update_detail_icon_preview(snippet.icon_name)
        self.detail_html_editor.setPlainText(snippet.html_template)
        self.detail_css_editor.setPlainText(snippet.css_style)
        self._switch_detail_code_tab(0)

        # Le bouton supprimer est actif pour tous les snippets modifiables
        self.btn_detail_delete.setVisible(snippet.is_custom)
        self.stack.setCurrentIndex(1)

    @Slot()
    def _save_detail_snippet(self) -> None:
        if not self._selected_snippet_for_detail:
            return

        name = self.detail_name_input.text().strip()
        if not name:
            show_toast(self, "Le nom du snippet ne peut pas être vide.", is_error=True)
            return

        self._selected_snippet_for_detail.name = name
        self._selected_snippet_for_detail.category = self.detail_cat_input.text().strip() or "Personnalisé"
        self._selected_snippet_for_detail.description = self.detail_desc_input.text().strip()
        self._selected_snippet_for_detail.icon_name = self.detail_icon_input.text().strip() or "ph.sparkle"
        self._selected_snippet_for_detail.html_template = self.detail_html_editor.toPlainText()
        self._selected_snippet_for_detail.css_style = self.detail_css_editor.toPlainText()

        SnippetLibrary.save_snippet(self._selected_snippet_for_detail)
        self.refresh_snippets()
        show_toast(self, f"Snippet « {name} » mis à jour avec succès.")
        self.stack.setCurrentIndex(0)

    @Slot()
    def _delete_current_detail_snippet(self) -> None:
        if not self._selected_snippet_for_detail:
            return

        res = QMessageBox.question(
            self,
            "Supprimer le Snippet",
            f"Voulez-vous vraiment supprimer le snippet « {self._selected_snippet_for_detail.name} » ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            SnippetLibrary.delete_snippet(self._selected_snippet_for_detail.id)
            self.refresh_snippets()
            show_toast(self, "Snippet supprimé de la bibliothèque.")
            self.stack.setCurrentIndex(0)

    @Slot()
    def _insert_current_detail_snippet(self) -> None:
        if self._selected_snippet_for_detail:
            self.snippet_selected.emit(self._selected_snippet_for_detail)

    @Slot()
    def _submit_create_snippet(self) -> None:
        name = self.create_name_input.text().strip()
        if not name:
            show_toast(self, "Veuillez saisir un nom pour le snippet.", is_error=True)
            return

        cat = self.create_cat_input.text().strip() or "Personnalisé"
        desc = self.create_desc_input.text().strip()
        icon = self.create_icon_input.text().strip() or "ph.sparkle"
        html = self.create_html_editor.toPlainText().strip()
        css = self.create_css_editor.toPlainText().strip()

        if not html:
            html = f'<div class="af-{name.lower().replace(" ", "-")}">\n  {{{{Champ}}}}\n</div>'

        created = SnippetLibrary.create_custom_snippet(
            name=name,
            category=cat,
            description=desc,
            icon_name=icon,
            html_template=html,
            css_style=css,
        )

        self.refresh_snippets()
        show_toast(self, f"Snippet « {created.name} » créé avec succès.")
        self.stack.setCurrentIndex(0)

    def refresh_snippets(self) -> None:
        """Recharge l'ensemble des snippets et reconstruit l'affichage."""
        self._all_snippets = SnippetLibrary.get_all_snippets()
        self._rebuild_category_buttons()
        self._filter_snippets()

    def refresh_theme(self, profile: Any) -> None:
        """Rafraîchit dynamiquement les styles de tous les sous-composants."""
        self.refresh_snippets()
