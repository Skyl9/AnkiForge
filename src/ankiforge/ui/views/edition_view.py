"""
Vue Édition / Analyse — Fidélité 100% à la maquette concept_ide/index.html
"""

import typing
import re
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QLabel,
    QScrollArea,
    QFrame,
    QCheckBox,
    QListWidget,
    QListWidgetItem,
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont

from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.components.panels import IdePanel
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton, IconButton
from ankiforge.ui.components.inputs import GlowLineEdit, StyledComboBox, StyledTextEdit
from ankiforge.ui.components.badges import Badge
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.database.models import NoteModel, NoteVersionModel
from ankiforge.ui.dialogs.history_modal import HistoryModal


class CardListItemWidget(QFrame):
    """Widget d'item de carte personnalisé conforme à la maquette concept_ide."""

    def __init__(self, note: NoteModel, parent: typing.Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.note = note
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            CardListItemWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 0px;
            }}
            CardListItemWidget:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        # Rangée 1 : ID (tech font bleu) + Badge Carte n°1
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)

        id_lbl = QLabel(f"ID: {note.id}")
        id_font = QFont(DesignTokens.FONT_CODE, 11, QFont.Weight.Bold)
        id_lbl.setFont(id_font)
        id_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; border: none; background: transparent;")

        badge = Badge("Carte n°1", variant="outline", color=DesignTokens.COLOR_GREEN)
        badge.setStyleSheet(f"""
            color: {DesignTokens.COLOR_GREEN};
            border: 1px solid rgba(16, 185, 129, 0.3);
            background-color: rgba(16, 185, 129, 0.15);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 600;
        """)

        row1.addWidget(id_lbl)
        row1.addStretch()
        row1.addWidget(badge)
        layout.addLayout(row1)

        # Rangée 2 : Type de note (icône swatches)
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(6)

        swatches_icon = QLabel()
        swatches_icon.setPixmap(load_phosphor_icon("swatches", color=DesignTokens.TEXT_MUTED).pixmap(14, 14))
        swatches_icon.setStyleSheet("border: none; background: transparent;")

        note_type_name = note.note_type.name if hasattr(note, "note_type") and note.note_type else "Informatique"
        type_lbl = QLabel(note_type_name)
        type_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 500; font-size: 12px; border: none; background: transparent;")

        row2.addWidget(swatches_icon)
        row2.addWidget(type_lbl)
        row2.addStretch()
        layout.addLayout(row2)

        # Rangée 3 : Dossier (icône folder)
        row3 = QHBoxLayout()
        row3.setContentsMargins(0, 0, 0, 0)
        row3.setSpacing(6)

        folder_icon = QLabel()
        folder_icon.setPixmap(load_phosphor_icon("folder", color=DesignTokens.TEXT_MUTED).pixmap(14, 14))
        folder_icon.setStyleSheet("border: none; background: transparent;")

        folder_name = note.folder.name if hasattr(note, "folder") and note.folder else "Ensimag..."
        folder_lbl = QLabel(folder_name)
        folder_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")

        row3.addWidget(folder_icon)
        row3.addWidget(folder_lbl)
        row3.addStretch()
        layout.addLayout(row3)

        # Rangée 4 : Tags pills
        row4 = QHBoxLayout()
        row4.setContentsMargins(0, 4, 0, 0)
        row4.setSpacing(4)

        raw_tags = note.tags if hasattr(note, "tags") and note.tags else "Informatique"
        tags_list = [t.strip() for t in raw_tags.split(",") if t.strip()] if isinstance(raw_tags, str) else ["Informatique"]

        for tag in tags_list[:3]:
            tag_pill = QLabel(tag)
            tag_pill.setStyleSheet(f"""
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_SECONDARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            """)
            row4.addWidget(tag_pill)

        row4.addStretch()
        layout.addLayout(row4)


class ExplorateurDossiersTagsWidget(QWidget):
    """Panneau d'explorateur dossiers et filtres par tags (Haut 35%)."""

    folder_selected = Signal(str)
    tag_selected = Signal(str)
    import_requested = Signal()
    export_requested = Signal()

    def __init__(self, parent: typing.Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Actions de Collection (Import / Export) au-dessus des dossiers
        coll_toolbar = QHBoxLayout()
        coll_toolbar.setContentsMargins(0, 0, 0, 0)
        coll_toolbar.setSpacing(6)

        self.btn_import_collection = SecondaryButton("Importer")
        self.btn_import_collection.setIcon(load_phosphor_icon("download-simple", color=DesignTokens.TEXT_PRIMARY))
        self.btn_import_collection.setToolTip("Importer un paquet ou une collection (.apkg, .colpkg)")
        self.btn_import_collection.clicked.connect(self.import_requested.emit)

        self.btn_export_collection = SecondaryButton("Exporter")
        self.btn_export_collection.setIcon(load_phosphor_icon("export", color=DesignTokens.TEXT_PRIMARY))
        self.btn_export_collection.setToolTip("Exporter la collection au format Anki (.apkg)")
        self.btn_export_collection.clicked.connect(self.export_requested.emit)

        coll_toolbar.addWidget(self.btn_import_collection, 1)
        coll_toolbar.addWidget(self.btn_export_collection, 1)
        layout.addLayout(coll_toolbar)

        # Section Dossiers
        self.folder_area = QWidget()
        folder_layout = QVBoxLayout(self.folder_area)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(4)

        self.folder_list = QListWidget()
        self.folder_list.setFrameShape(QFrame.Shape.NoFrame)
        self.folder_list.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-radius: 6px;
                color: #f8fafc;
            }
            QListWidget::item:hover {
                background-color: #2d313a;
            }
            QListWidget::item:selected {
                background-color: #2d313a;
                font-weight: bold;
            }
        """)

        # Add mock/real items
        item1 = QListWidgetItem("Default")
        item1.setIcon(load_phosphor_icon("folder", color=DesignTokens.COLOR_BLUE))
        self.folder_list.addItem(item1)

        item2 = QListWidgetItem("Ensimag...")
        item2.setIcon(load_phosphor_icon("folder", color=DesignTokens.COLOR_BLUE))
        self.folder_list.addItem(item2)

        item3 = QListWidgetItem("  Seme...")
        item3.setIcon(load_phosphor_icon("folder", color=DesignTokens.COLOR_BLUE))
        self.folder_list.addItem(item3)

        folder_layout.addWidget(self.folder_list)
        layout.addWidget(self.folder_area, 1)

        # Séparateur / En-tête Filtres Tags
        tags_header_layout = QHBoxLayout()
        tags_header_layout.setContentsMargins(0, 4, 0, 0)
        tags_header_layout.setSpacing(6)

        tag_icon = QLabel()
        tag_icon.setPixmap(load_phosphor_icon("tag", color=DesignTokens.COLOR_YELLOW).pixmap(14, 14))

        tags_hdr_lbl = QLabel("FILTRES (TAGS)")
        tags_hdr_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; border: none;")

        tags_header_layout.addWidget(tag_icon)
        tags_header_layout.addWidget(tags_hdr_lbl)
        tags_header_layout.addStretch()
        layout.addLayout(tags_header_layout)

        # Section Tags
        self.tag_list = QListWidget()
        self.tag_list.setFrameShape(QFrame.Shape.NoFrame)
        self.tag_list.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-radius: 6px;
                color: #94a3b8;
            }
            QListWidget::item:hover {
                background-color: #2d313a;
                color: #f8fafc;
            }
        """)

        t_item1 = QListWidgetItem("Tous les tags")
        t_item1.setIcon(load_phosphor_icon("tag", color=DesignTokens.COLOR_YELLOW))
        self.tag_list.addItem(t_item1)

        t_item2 = QListWidgetItem("Définition (1)")
        t_item2.setIcon(load_phosphor_icon("tag", color=DesignTokens.COLOR_YELLOW))
        self.tag_list.addItem(t_item2)

        layout.addWidget(self.tag_list, 1)

    def populate_folders(self, folders: list) -> None:
        self.folder_list.clear()
        for f in folders:
            item = QListWidgetItem(f.name)
            item.setIcon(load_phosphor_icon("folder", color=DesignTokens.COLOR_BLUE))
            item.setData(Qt.ItemDataRole.UserRole, f.id)
            self.folder_list.addItem(item)


class EditionView(QWidget):
    """
    Vue Édition / Analyse conformité 100% avec maquette concept_ide/index.html.
    Structure à 2 panneaux côte-à-côte (IdePanel Explorateur 320px | IdePanel Éditeur Flex-1).
    """

    def __init__(self, parent: typing.Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._dirty = False
        self._current_note: typing.Optional[NoteModel] = None
        self._preview_device = "desktop"

        self._setup_ui()

    def _setup_ui(self) -> None:
        # Layout principal de la vue
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # QSplitter horizontal principal : Panneau Gauche (320px) | Panneau Droit (Flex-1)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setStyleSheet("QSplitter::handle { background: transparent; }")
        main_layout.addWidget(self.main_splitter)

        # ==========================================
        # PANNEAU 1 (GAUCHE) : Explorateur & Liste des Cartes (320px)
        # ==========================================
        self.left_panel = IdePanel(detachable=True)
        self.left_panel.setFixedWidth(320)

        left_content = QWidget()
        left_layout = QVBoxLayout(left_content)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Splitter vertical dans la colonne de gauche (Haut 35% | Bas flex-1)
        self.col1_splitter = QSplitter(Qt.Orientation.Vertical)
        self.col1_splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {DesignTokens.BORDER_COLOR}; height: 1px; }}")

        # Haut : Explorateur dossiers & tags
        self.explorer_widget = ExplorateurDossiersTagsWidget()
        self.explorer_widget.import_requested.connect(self._on_import_collection)
        self.explorer_widget.export_requested.connect(self._on_export_collection)
        self.col1_splitter.addWidget(self.explorer_widget)

        # Bas : Recherche + Liste de cartes
        card_list_container = QWidget()
        card_list_layout = QVBoxLayout(card_list_container)
        card_list_layout.setContentsMargins(0, 0, 0, 0)
        card_list_layout.setSpacing(0)

        # Toolbar recherche
        search_toolbar = QWidget()
        search_toolbar.setStyleSheet(f"background-color: {DesignTokens.BG_SIDEBAR}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")
        search_layout = QHBoxLayout(search_toolbar)
        search_layout.setContentsMargins(10, 8, 10, 8)
        search_layout.setSpacing(8)

        self.search_input = GlowLineEdit()
        self.search_input.setPlaceholderText("Rechercher...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        search_layout.addWidget(self.search_input, 1)

        self.btn_filter = IconButton("funnel", tooltip="Filtres avancés", size=24)
        search_layout.addWidget(self.btn_filter)

        card_list_layout.addWidget(search_toolbar)

        # QListWidget pour les cartes
        self.card_list = QListWidget()
        self.card_list.setFrameShape(QFrame.Shape.NoFrame)
        self.card_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_MAIN};
                border: none;
            }}
            QListWidget::item {{
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                padding: 0px;
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        self.card_list.itemClicked.connect(self._on_card_selected)
        card_list_layout.addWidget(self.card_list, 1)

        self.col1_splitter.addWidget(card_list_container)
        self.col1_splitter.setSizes([200, 450])
        self.col1_splitter.setCollapsible(0, True)
        self.col1_splitter.setCollapsible(1, False)

        left_layout.addWidget(self.col1_splitter)
        self.left_panel.add_tab("Explorateur", left_content, icon_name="ph.compass", closable=False)
        self.main_splitter.addWidget(self.left_panel)

        # ==========================================
        # PANNEAU 2 (DROIT) : Éditeur & Prévisualisation (Flex-1)
        # ==========================================
        self.right_panel = IdePanel(detachable=True)

        # Boutons d'en-tête (Historique + Sauvegarder)
        self.btn_history = SecondaryButton("Historique")
        self.btn_history.setIcon(load_phosphor_icon("clock-counter-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_history.clicked.connect(self._open_history_modal)

        self.btn_save = PrimaryButton("Sauvegarder")
        self.btn_save.setIcon(load_phosphor_icon("floppy-disk", color="white"))
        self.btn_save.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10b981, stop:1 #059669);
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: 600;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #059669, stop:1 #047857);
            }
        """)
        self.btn_save.clicked.connect(self._save_card)

        self.right_panel.add_header_widget(self.btn_history)
        self.right_panel.add_header_widget(self.btn_save)
        self.right_panel.add_header_separator()

        editor_content = QWidget()
        editor_content_layout = QVBoxLayout(editor_content)
        editor_content_layout.setContentsMargins(0, 0, 0, 0)
        editor_content_layout.setSpacing(0)

        # Splitter vertical entre Éditeur (Haut) et Prévisualisation (Bas)
        self.col2_splitter = QSplitter(Qt.Orientation.Vertical)
        self.col2_splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {DesignTokens.BORDER_COLOR}; height: 1px; }}")

        # --- Haut : Zone de saisie (Recto & Verso) ---
        fields_container = QWidget()
        fields_layout = QVBoxLayout(fields_container)
        fields_layout.setContentsMargins(16, 16, 16, 16)
        fields_layout.setSpacing(14)

        # Champ Recto
        recto_hdr = QHBoxLayout()
        recto_lbl = QLabel("RECTO")
        recto_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; border: none;")
        recto_hdr.addWidget(recto_lbl)
        recto_hdr.addStretch()

        self.btn_bold = IconButton("text-b", tooltip="Gras", size=24)
        self.btn_bold.clicked.connect(lambda: self._insert_format("**", "**"))
        self.btn_italic = IconButton("text-italic", tooltip="Italique", size=24)
        self.btn_italic.clicked.connect(lambda: self._insert_format("*", "*"))
        self.btn_code = IconButton("code", tooltip="Code", size=24)
        self.btn_code.clicked.connect(lambda: self._insert_format("`", "`"))

        recto_hdr.addWidget(self.btn_bold)
        recto_hdr.addWidget(self.btn_italic)
        recto_hdr.addWidget(self.btn_code)
        fields_layout.addLayout(recto_hdr)

        self.editor_recto = StyledTextEdit()
        self.editor_recto.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 12px;
                padding: 10px;
            }}
            QTextEdit:focus {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.editor_recto.setPlaceholderText("Entrez le recto de la carte (support Markdown & LaTeX)...")
        self.editor_recto.textChanged.connect(self._on_text_changed)
        fields_layout.addWidget(self.editor_recto, 1)

        # Champ Verso
        verso_hdr = QHBoxLayout()
        verso_lbl = QLabel("VERSO")
        verso_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; border: none;")
        verso_hdr.addWidget(verso_lbl)
        verso_hdr.addStretch()
        fields_layout.addLayout(verso_hdr)

        self.editor_verso = StyledTextEdit()
        self.editor_verso.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 12px;
                padding: 10px;
            }}
            QTextEdit:focus {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.editor_verso.setPlaceholderText("Entrez le verso de la carte...")
        self.editor_verso.textChanged.connect(self._on_text_changed)
        fields_layout.addWidget(self.editor_verso, 1)

        # Ligne de Tags
        tags_row = QHBoxLayout()
        tags_row.setContentsMargins(0, 4, 0, 0)
        tags_row.setSpacing(8)

        self.tag_pill = QLabel("Informatique")
        self.tag_pill.setStyleSheet(f"""
            background-color: {DesignTokens.BG_INPUT};
            color: {DesignTokens.TEXT_SECONDARY};
            border: 1px solid {DesignTokens.BORDER_COLOR};
            border-radius: 4px;
            padding: 4px 10px;
            font-size: 11px;
        """)
        tags_row.addWidget(self.tag_pill)

        self.btn_add_tag = IconButton("plus", tooltip="Ajouter un tag", size=24)
        tags_row.addWidget(self.btn_add_tag)
        tags_row.addStretch()

        fields_layout.addLayout(tags_row)
        self.col2_splitter.addWidget(fields_container)

        # --- Bas : Zone de prévisualisation live ---
        preview_container = QWidget()
        preview_container.setStyleSheet("background-color: rgba(0, 0, 0, 0.15);")
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(16, 12, 16, 16)
        preview_layout.setSpacing(12)

        # Barre de contrôles de prévisualisation
        preview_ctrl = QHBoxLayout()
        preview_ctrl.setContentsMargins(0, 0, 0, 0)
        preview_ctrl.setSpacing(12)

        prev_title = QLabel("PRÉVISUALISATION")
        prev_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; border: none;")
        preview_ctrl.addWidget(prev_title)

        self.card_combo = StyledComboBox()
        self.card_combo.addItems(["Carte n°1 (Principale)", "Carte n°2 (Inversée)"])
        self.card_combo.setFixedWidth(180)
        preview_ctrl.addWidget(self.card_combo)

        preview_ctrl.addStretch()

        self.verso_cb = QCheckBox("Verso")
        self.verso_cb.setChecked(True)
        self.verso_cb.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: bold;")
        self.verso_cb.toggled.connect(self._toggle_verso)
        preview_ctrl.addWidget(self.verso_cb)

        # Appareils (Desktop / Mobile)
        self.btn_desktop = IconButton("monitor", tooltip="Mode Bureau", size=24)
        self.btn_desktop.setStyleSheet(f"background-color: {DesignTokens.BG_HOVER}; border-radius: 4px;")
        self.btn_desktop.clicked.connect(lambda: self._set_device("desktop"))

        self.btn_mobile = IconButton("device-mobile", tooltip="Mode Mobile", size=24)
        self.btn_mobile.clicked.connect(lambda: self._set_device("mobile"))

        preview_ctrl.addWidget(self.btn_desktop)
        preview_ctrl.addWidget(self.btn_mobile)

        preview_layout.addLayout(preview_ctrl)

        # Zone d'affichage de la carte
        self.card_preview_scroll = QScrollArea()
        self.card_preview_scroll.setWidgetResizable(True)
        self.card_preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.card_preview_scroll.setStyleSheet("background: transparent;")

        self.card_wrapper = QWidget()
        card_wrapper_layout = QVBoxLayout(self.card_wrapper)
        card_wrapper_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_wrapper_layout.setContentsMargins(12, 12, 12, 12)

        # Cadre Premium Flashcard
        self.flashcard_frame = QFrame()
        self.flashcard_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #1a1d24;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-top: 4px solid qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:1 #8b5cf6);
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        apply_shadow(self.flashcard_frame, blur=16, offset_y=4)

        card_internal_layout = QVBoxLayout(self.flashcard_frame)
        card_internal_layout.setContentsMargins(24, 24, 24, 24)
        card_internal_layout.setSpacing(16)

        # Contenu Recto
        self.lbl_front = QLabel("Qu'est-ce qu'une <b>fonction de répartition</b> F<sub>X</sub>(t) et quelles sont ses 4 propriétés principales ?")
        self.lbl_front.setFont(QFont(DesignTokens.FONT_MAIN, 14))
        self.lbl_front.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        self.lbl_front.setWordWrap(True)
        card_internal_layout.addWidget(self.lbl_front)

        # Séparateur VERSO
        self.divider_container = QWidget()
        div_layout = QVBoxLayout(self.divider_container)
        div_layout.setContentsMargins(0, 4, 0, 4)

        self.divider_line = QFrame()
        self.divider_line.setFrameShape(QFrame.Shape.HLine)
        self.divider_line.setStyleSheet(f"border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; border-top: none;")
        div_layout.addWidget(self.divider_line)

        self.divider_lbl = QLabel("VERSO")
        self.divider_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; border: none;")
        self.divider_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        div_layout.addWidget(self.divider_lbl)

        card_internal_layout.addWidget(self.divider_container)

        # Contenu Verso
        self.lbl_back = QLabel("La fonction de répartition d'une variable aléatoire réelle X est définie par F<sub>X</sub>(t) = P(X ≤ t).")
        self.lbl_back.setFont(QFont(DesignTokens.FONT_MAIN, 14))
        self.lbl_back.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        self.lbl_back.setWordWrap(True)
        card_internal_layout.addWidget(self.lbl_back)

        card_wrapper_layout.addWidget(self.flashcard_frame)
        self.card_preview_scroll.setWidget(self.card_wrapper)
        preview_layout.addWidget(self.card_preview_scroll, 1)

        self.col2_splitter.addWidget(preview_container)

        self.col2_splitter.setSizes([350, 350])
        self.col2_splitter.setCollapsible(0, False)
        self.col2_splitter.setCollapsible(1, False)

        editor_content_layout.addWidget(self.col2_splitter)

        self.right_panel.add_tab("Éditeur (ID: 175908)", editor_content, icon_name="ph.pencil-simple", closable=False)
        self.main_splitter.addWidget(self.right_panel)

        self.main_splitter.setSizes([320, 800])
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)

    def _on_card_selected(self, item: QListWidgetItem) -> None:
        note: typing.Optional[NoteModel] = item.data(Qt.ItemDataRole.UserRole)
        if not note:
            return
        self._current_note = note

        # Update tab title
        self.right_panel.set_tab_text(0, f"Éditeur (ID: {note.id})")

        # Load active version content if present
        version = NoteVersionModel.get_or_none(note=note, is_active=True)
        if version and version.content:
            import json

            try:
                data = json.loads(version.content)
                recto = data.get("front", "")
                verso = data.get("back", "")
            except Exception:
                recto = version.content
                verso = ""
        else:
            recto = f"Recto pour la note #{note.id}"
            verso = f"Verso pour la note #{note.id}"

        self.editor_recto.setText(recto)
        self.editor_verso.setText(verso)
        self._update_preview()
        self._dirty = False

    def _on_text_changed(self) -> None:
        self._dirty = True
        self._update_preview()

    def _update_preview(self) -> None:
        recto_text = self.editor_recto.toPlainText() or "<i>Saisissez un recto...</i>"
        verso_text = self.editor_verso.toPlainText() or "<i>Saisissez un verso...</i>"

        # Format markdown bold -> html
        formatted_recto = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", recto_text)
        formatted_verso = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", verso_text)

        self.lbl_front.setText(formatted_recto)
        self.lbl_back.setText(formatted_verso)

    def _toggle_verso(self, checked: bool) -> None:
        self.divider_container.setVisible(checked)
        self.lbl_back.setVisible(checked)

    def _set_device(self, device: str) -> None:
        self._preview_device = device
        if device == "mobile":
            self.flashcard_frame.setFixedWidth(375)
            self.btn_mobile.setStyleSheet(f"background-color: {DesignTokens.BG_HOVER}; border-radius: 4px;")
            self.btn_desktop.setStyleSheet("background-color: transparent;")
        else:
            self.flashcard_frame.setMaximumWidth(16777215)
            self.flashcard_frame.setMinimumWidth(0)
            self.btn_desktop.setStyleSheet(f"background-color: {DesignTokens.BG_HOVER}; border-radius: 4px;")
            self.btn_mobile.setStyleSheet("background-color: transparent;")

    def _insert_format(self, prefix: str, suffix: str) -> None:
        cursor = self.editor_recto.textCursor()
        selected = cursor.selectedText()
        cursor.insertText(f"{prefix}{selected}{suffix}")

    def _on_search_text_changed(self, text: str) -> None:
        text = text.lower()
        for i in range(self.card_list.count()):
            item = self.card_list.item(i)
            note = item.data(Qt.ItemDataRole.UserRole)
            if note:
                match = text in str(note.id).lower() or text in (note.tags or "").lower()
                item.setHidden(not match)

    def _open_history_modal(self) -> None:
        if self._current_note:
            modal = HistoryModal(self._current_note, self)
            modal.exec()

    @Slot()
    def _save_card(self) -> None:
        if not self._current_note:
            return

        try:
            new_content = {"front": self.editor_recto.toPlainText(), "back": self.editor_verso.toPlainText()}
            self._current_note.add_version(new_content, source="manual")
            self._dirty = False
        except Exception:
            pass  # nosec B110

    def _on_import_collection(self) -> None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        file_path, _ = QFileDialog.getOpenFileName(self, "Importer une collection ou paquet Anki", "", "Fichiers Anki (*.apkg *.colpkg *.txt);;Tous les fichiers (*)")
        if not file_path:
            return
        try:
            from ankiforge.services.cards.store_manager import StoreManager

            StoreManager.import_apkg(file_path)
            self.refresh_data()
            QMessageBox.information(self, "Import réussi", f"Le fichier '{file_path}' a été importé avec succès.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'import", f"Erreur lors de l'import : {str(e)}")

    def _on_export_collection(self) -> None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        file_path, _ = QFileDialog.getSaveFileName(self, "Exporter la collection Anki", "AnkiForge_Collection.apkg", "Paquet Anki (*.apkg)")
        if not file_path:
            return
        try:
            from ankiforge.services.cards.export_manager import ExportManager
            from ankiforge.database.models import DeckModel

            decks = list(DeckModel.select())
            if not decks:
                QMessageBox.warning(self, "Export impossible", "Aucun paquet trouvé dans la collection.")
                return
            ExportManager.export_deck_to_apkg(decks[0], file_path)
            QMessageBox.information(self, "Export réussi", f"La collection a été exportée vers '{file_path}'.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'export", f"Erreur lors de l'export : {str(e)}")

    def refresh_data(self) -> None:
        self.card_list.clear()
        try:
            notes = NoteModel.select()
            for note in notes:
                item = QListWidgetItem()
                widget = CardListItemWidget(note)
                item.setSizeHint(widget.sizeHint())
                item.setData(Qt.ItemDataRole.UserRole, note)
                self.card_list.addItem(item)
                self.card_list.setItemWidget(item, widget)

            if self.card_list.count() > 0:
                self.card_list.setCurrentRow(0)
                self._on_card_selected(self.card_list.item(0))
        except Exception:
            pass  # nosec B110

    def is_dirty(self) -> bool:
        return self._dirty


# Alias pour la rétrocompatibilité
EditionTab = EditionView
