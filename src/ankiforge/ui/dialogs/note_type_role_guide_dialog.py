"""
Dialogue modal présentant le guide sémantique et le créateur de tableaux des rôles IA pour les types de note.
"""

from __future__ import annotations

import markdown
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.cards.note_type_roles import (
    NoteTypeRoleArchetype,
    generate_markdown_table,
    get_standard_role_archetypes,
    get_table_creation_templates,
)
from ankiforge.ui.components.badges import Badge
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton, apply_compact_style
from ankiforge.ui.components.inputs import StyledLineEdit
from ankiforge.ui.components.tables import StyledTableWidget
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class NoteTypeRoleGuideDialog(QDialog):
    """
    Dialogue modal permettant de consulter le catalogue sémantique des rôles IA,
    de choisir un archétype prédéfini, ou de concevoir son propre tableau Markdown sur-mesure.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Guide des rôles IA pour les types de note"))
        self.resize(1000, 640)
        self.setMinimumSize(860, 520)
        self.setModal(True)

        self._archetypes: list[NoteTypeRoleArchetype] = get_standard_role_archetypes()
        self._builder_templates: list[dict[str, str]] = get_table_creation_templates()
        self.selected_directive: str | None = None
        self.selected_archetype: NoteTypeRoleArchetype | None = None
        self.selected_archetype_name: str | None = None

        self._setup_ui()
        self._populate_archetypes_table()
        self._init_builder_with_default()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(12)

        # 1. En-tête descriptif
        header_frame = QFrame()
        header_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(14)

        icon_label = QLabel()
        icon_label.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.ACCENT_PRIMARY).pixmap(28, 28))
        icon_label.setStyleSheet("border: none; background: transparent;")
        header_layout.addWidget(icon_label)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(3)

        title_lbl = QLabel(self.tr("Guide sémantique et créateur de rôles IA"))
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 15px; font-weight: bold; border: none; background: transparent;")
        title_vbox.addWidget(title_lbl)

        subtitle_lbl = QLabel(
            self.tr("Le « Rôle IA » est une directive ou un tableau Markdown injecté dans la balise {{ available_card_models }} pour orienter l'IA sur le gabarit de carte à privilégier.")
        )
        subtitle_lbl.setWordWrap(True)
        subtitle_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        title_vbox.addWidget(subtitle_lbl)

        header_layout.addLayout(title_vbox, 1)
        root_layout.addWidget(header_frame)

        # 2. Système d'onglets : Modèles types vs Créateur sur-mesure
        self.tab_widget = QTabWidget()

        # Onglet 1 : Modèles types prédéfinis
        tab_archetypes = QWidget()
        tab_archetypes_layout = QVBoxLayout(tab_archetypes)
        tab_archetypes_layout.setContentsMargins(6, 10, 6, 6)
        tab_archetypes_layout.setSpacing(10)

        # Barre d'outils / filtre
        tools_layout = QHBoxLayout()
        tools_layout.setSpacing(10)

        lbl_search = QLabel(self.tr("Rechercher :"))
        lbl_search.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px; font-weight: bold;")
        tools_layout.addWidget(lbl_search)

        self.search_input = StyledLineEdit()
        self.search_input.setFixedHeight(28)
        self.search_input.setPlaceholderText(self.tr("Filtrer par mot-clé, cas d'usage ou nom de champ..."))
        self.search_input.textChanged.connect(self._on_search_changed)
        tools_layout.addWidget(self.search_input, 1)

        tab_archetypes_layout.addLayout(tools_layout)

        # Tableau des archétypes
        columns = [
            self.tr("Archétype"),
            self.tr("Quand le choisir ?"),
            self.tr("Champs suggérés"),
            self.tr("Directive transmise à l'IA"),
            self.tr("Action"),
        ]
        self.table = StyledTableWidget(columns=columns, parent=self)
        self.table.setWordWrap(True)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 170)
        self.table.setColumnWidth(1, 190)
        self.table.setColumnWidth(2, 160)
        self.table.setColumnWidth(4, 210)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(72)

        tab_archetypes_layout.addWidget(self.table, 1)
        self.tab_widget.addTab(tab_archetypes, self.tr("Modèles types prédéfinis"))

        # Onglet 2 : Créateur de tableau sur-mesure
        tab_builder = QWidget()
        tab_builder_layout = QVBoxLayout(tab_builder)
        tab_builder_layout.setContentsMargins(6, 10, 6, 6)
        tab_builder_layout.setSpacing(10)

        # Barre d'aide à la création (briques rapides)
        assistant_frame = QFrame()
        assistant_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px dashed {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px;
            }}
        """)
        asst_layout = QVBoxLayout(assistant_frame)
        asst_layout.setContentsMargins(8, 6, 8, 6)
        asst_layout.setSpacing(6)

        asst_title_row = QHBoxLayout()
        asst_title_row.setSpacing(6)
        lbl_asst = QLabel(self.tr("Aide à la création — Ajouter une règle type au tableau :"))
        lbl_asst.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: bold;")
        asst_title_row.addWidget(lbl_asst)
        asst_title_row.addStretch()
        asst_layout.addLayout(asst_title_row)

        chips_scroll = QScrollArea()
        chips_scroll.setWidgetResizable(True)
        chips_scroll.setFixedHeight(38)
        chips_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        chips_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        chips_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        chips_widget = QWidget()
        chips_layout = QHBoxLayout(chips_widget)
        chips_layout.setContentsMargins(0, 0, 0, 0)
        chips_layout.setSpacing(6)

        for tmpl in self._builder_templates:
            chip_btn = SecondaryButton(f"+ {tmpl['concept'].split('&')[0].strip()}")
            apply_compact_style(chip_btn, height=26)
            chip_btn.setToolTip(f"{tmpl['concept']} : {tmpl['directive']}")
            chip_btn.clicked.connect(lambda _checked=False, t=tmpl: self._add_builder_row_from_template(t))
            chips_layout.addWidget(chip_btn)

        chips_layout.addStretch()
        chips_scroll.setWidget(chips_widget)
        asst_layout.addWidget(chips_scroll)

        tab_builder_layout.addWidget(assistant_frame)

        # Grille interactive du tableau personnalisé
        builder_cols = [
            self.tr("Concept / Cas d'usage"),
            self.tr("Directive sémantique pour l'IA"),
            self.tr("Champs cibles"),
        ]
        self.builder_table = StyledTableWidget(columns=builder_cols, parent=self)
        self.builder_table.setWordWrap(True)
        self.builder_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.builder_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.builder_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.builder_table.setColumnWidth(0, 220)
        self.builder_table.setColumnWidth(2, 200)
        self.builder_table.itemChanged.connect(self._on_builder_item_changed)
        tab_builder_layout.addWidget(self.builder_table, 1)

        # Barre d'actions de la grille
        grid_actions_row = QHBoxLayout()
        grid_actions_row.setSpacing(8)

        btn_add_blank = SecondaryButton(self.tr("+ Ajouter une règle"))
        apply_compact_style(btn_add_blank, height=28)
        btn_add_blank.clicked.connect(self._add_blank_builder_row)
        grid_actions_row.addWidget(btn_add_blank)

        btn_remove_row = SecondaryButton(self.tr("Supprimer la règle sélectionnée"))
        apply_compact_style(btn_remove_row, height=28)
        btn_remove_row.clicked.connect(self._remove_selected_builder_row)
        grid_actions_row.addWidget(btn_remove_row)

        btn_clear_rows = SecondaryButton(self.tr("Tout effacer"))
        apply_compact_style(btn_clear_rows, height=28)
        btn_clear_rows.clicked.connect(self._clear_builder_rows)
        grid_actions_row.addWidget(btn_clear_rows)

        grid_actions_row.addStretch()

        self.btn_apply_builder = PrimaryButton(self.tr("Appliquer ce tableau au type de note"))
        apply_compact_style(self.btn_apply_builder, height=30)
        self.btn_apply_builder.clicked.connect(self._apply_builder_table)
        grid_actions_row.addWidget(self.btn_apply_builder)

        tab_builder_layout.addLayout(grid_actions_row)

        # Aperçu rendu en direct
        preview_frame = QFrame()
        preview_frame.setFixedHeight(120)
        preview_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        preview_vbox = QVBoxLayout(preview_frame)
        preview_vbox.setContentsMargins(6, 4, 6, 4)
        preview_vbox.setSpacing(2)

        lbl_prev_title = QLabel(self.tr("Aperçu en direct du tableau Markdown pour l'IA :"))
        lbl_prev_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        preview_vbox.addWidget(lbl_prev_title)

        self.builder_preview = QTextBrowser()
        self.builder_preview.setStyleSheet("border: none; background: transparent;")
        preview_vbox.addWidget(self.builder_preview, 1)

        tab_builder_layout.addWidget(preview_frame)
        self.tab_widget.addTab(tab_builder, self.tr("Créateur de tableau sur-mesure"))

        root_layout.addWidget(self.tab_widget, 1)

        # 3. Pied de dialogue avec bouton Fermer
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        caption_lbl = QLabel(self.tr("Astuce : L'application remplace la valeur du champ « Rôle IA » du type de note actif."))
        caption_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        bottom_layout.addWidget(caption_lbl, 1)

        btn_close = SecondaryButton(self.tr("Fermer"))
        apply_compact_style(btn_close, height=32)
        btn_close.clicked.connect(self.reject)
        bottom_layout.addWidget(btn_close)

        root_layout.addLayout(bottom_layout)

    def _populate_archetypes_table(self) -> None:
        """Remplit les lignes de l'onglet 1 avec les archétypes canoniques."""
        self.table.setRowCount(len(self._archetypes))

        for row, arch in enumerate(self._archetypes):
            # Colonne 0 : Nom + Badge catégorie
            name_cell = QWidget()
            name_layout = QVBoxLayout(name_cell)
            name_layout.setContentsMargins(8, 6, 8, 6)
            name_layout.setSpacing(4)

            name_lbl = QLabel(arch.name)
            name_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 12px; background: transparent;")
            name_layout.addWidget(name_lbl)

            badge = Badge(arch.category, variant="neutral")
            badge.setFixedHeight(18)
            name_layout.addWidget(badge)
            name_layout.addStretch()

            self.table.setCellWidget(row, 0, name_cell)

            # Colonne 1 : Cas d'usage
            use_case_item = QTableWidgetItem(arch.use_case)
            use_case_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 1, use_case_item)

            # Colonne 2 : Champs suggérés
            fields_str = ", ".join(arch.suggested_fields)
            fields_item = QTableWidgetItem(fields_str)
            fields_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, fields_item)

            # Colonne 3 : Directive IA
            directive_item = QTableWidgetItem(arch.ai_heuristic_directive)
            directive_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, directive_item)

            # Colonne 4 : Boutons Appliquer + Personnaliser
            actions_cell = QWidget()
            actions_layout = QHBoxLayout(actions_cell)
            actions_layout.setContentsMargins(6, 6, 6, 6)
            actions_layout.setSpacing(6)
            actions_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            apply_btn = PrimaryButton(self.tr("Appliquer"))
            apply_compact_style(apply_btn, height=28)
            apply_btn.clicked.connect(lambda _checked=False, a=arch: self._apply_archetype(a))
            actions_layout.addWidget(apply_btn)

            custom_btn = SecondaryButton(self.tr("Personnaliser"))
            apply_compact_style(custom_btn, height=28)
            custom_btn.setToolTip(self.tr("Charger cet archétype dans le créateur de tableau sur-mesure"))
            custom_btn.clicked.connect(lambda _checked=False, a=arch: self.load_archetype_into_builder(a))
            actions_layout.addWidget(custom_btn)

            self.table.setCellWidget(row, 4, actions_cell)

    def _init_builder_with_default(self) -> None:
        """Initialise le créateur avec la première suggestion type."""
        if self._builder_templates:
            self._add_builder_row_from_template(self._builder_templates[0])

    def _add_builder_row_from_template(self, tmpl: dict[str, str]) -> None:
        """Ajoute une ligne dans le créateur à partir d'un template."""
        row = self.builder_table.rowCount()
        self.builder_table.insertRow(row)
        self.builder_table.setItem(row, 0, QTableWidgetItem(tmpl.get("concept", "")))
        self.builder_table.setItem(row, 1, QTableWidgetItem(tmpl.get("directive", "")))
        self.builder_table.setItem(row, 2, QTableWidgetItem(tmpl.get("fields", "")))
        self._update_builder_preview()

    def _add_blank_builder_row(self) -> None:
        """Ajoute une ligne vierge dans le créateur de tableau."""
        row = self.builder_table.rowCount()
        self.builder_table.insertRow(row)
        self.builder_table.setItem(row, 0, QTableWidgetItem(self.tr("Nouveau cas d'usage")))
        self.builder_table.setItem(row, 1, QTableWidgetItem(self.tr("Consigne spécifique pour l'IA")))
        self.builder_table.setItem(row, 2, QTableWidgetItem("Front, Back"))
        self._update_builder_preview()

    def _remove_selected_builder_row(self) -> None:
        """Supprime la ligne actuellement sélectionnée dans le créateur."""
        current_row = self.builder_table.currentRow()
        if current_row >= 0:
            self.builder_table.removeRow(current_row)
            self._update_builder_preview()

    def _clear_builder_rows(self) -> None:
        """Vide l'ensemble des lignes du créateur."""
        self.builder_table.setRowCount(0)
        self._update_builder_preview()

    def _on_builder_item_changed(self) -> None:
        """Régénère l'aperçu en direct au fur et à mesure des modifications de cellules."""
        self._update_builder_preview()

    def _collect_builder_rows(self) -> list[dict[str, str]]:
        """Collecte les données saisies dans les cellules du créateur."""
        rows: list[dict[str, str]] = []
        for r in range(self.builder_table.rowCount()):
            c_item = self.builder_table.item(r, 0)
            d_item = self.builder_table.item(r, 1)
            f_item = self.builder_table.item(r, 2)
            concept = c_item.text().strip() if c_item else ""
            directive = d_item.text().strip() if d_item else ""
            fields = f_item.text().strip() if f_item else ""
            if concept or directive:
                rows.append({"concept": concept, "directive": directive, "fields": fields})
        return rows

    def _update_builder_preview(self) -> None:
        """Met à jour le rendu HTML du tableau Markdown généré dans le volet d'aperçu."""
        rows = self._collect_builder_rows()
        if not rows:
            self.builder_preview.setHtml(f"<p style='color: {DesignTokens.TEXT_MUTED}; font-style: italic; font-size: 11px;'>{self.tr('Le tableau est vide. Ajoutez une règle type ci-dessus.')}</p>")
            return

        md_table = generate_markdown_table(rows)
        rendered_html = markdown.markdown(md_table, extensions=["tables"])
        css = f"""
        <style>
            table {{ width: 100%; border-collapse: collapse; font-size: 11px; color: {DesignTokens.TEXT_PRIMARY}; }}
            th {{ background-color: {DesignTokens.BG_PANEL}; padding: 4px 8px; border: 1px solid {DesignTokens.BORDER_COLOR}; text-align: left; font-weight: bold; }}
            td {{ padding: 4px 8px; border: 1px solid {DesignTokens.BORDER_COLOR}; vertical-align: top; }}
        </style>
        """
        self.builder_preview.setHtml(f"{css}<div>{rendered_html}</div>")

    def _apply_builder_table(self) -> None:
        """Compile le tableau en Markdown et valide la modale."""
        rows = self._collect_builder_rows()
        if not rows:
            return

        md_table = generate_markdown_table(rows)
        self.selected_directive = md_table
        self.selected_archetype = None
        self.selected_archetype_name = self.tr("Tableau Markdown personnalisé")
        self.accept()

    def load_archetype_into_builder(self, archetype: NoteTypeRoleArchetype) -> None:
        """Charge un archétype existant dans le créateur sur-mesure et bascule sur l'onglet Créateur."""
        self.builder_table.setRowCount(0)
        row = self.builder_table.rowCount()
        self.builder_table.insertRow(row)
        self.builder_table.setItem(row, 0, QTableWidgetItem(archetype.name))
        self.builder_table.setItem(row, 1, QTableWidgetItem(archetype.ai_heuristic_directive))
        self.builder_table.setItem(row, 2, QTableWidgetItem(", ".join(archetype.suggested_fields)))
        self._update_builder_preview()
        self.tab_widget.setCurrentIndex(1)

    def _apply_archetype(self, archetype: NoteTypeRoleArchetype) -> None:
        """Sélectionne l'archétype prédéfini et valide la modale."""
        self.selected_directive = archetype.ai_heuristic_directive
        self.selected_archetype = archetype
        self.selected_archetype_name = archetype.name
        self.accept()

    def get_apply_button_at_row(self, row: int) -> QPushButton | None:
        """Retourne le bouton Appliquer pour une ligne donnée de l'onglet 1."""
        widget = self.table.cellWidget(row, 4)
        if isinstance(widget, QPushButton):
            return widget
        if widget is not None:
            return widget.findChild(QPushButton)
        return None

    def _on_search_changed(self, text: str) -> None:
        """Filtre les lignes du tableau selon le terme recherché."""
        filter_term = text.strip().lower()

        for row, arch in enumerate(self._archetypes):
            if not filter_term:
                self.table.setRowHidden(row, False)
                continue

            searchable_text = f"{arch.name} {arch.category} {arch.use_case} {' '.join(arch.suggested_fields)} {arch.ai_heuristic_directive}".lower()
            matches = filter_term in searchable_text
            self.table.setRowHidden(row, not matches)

    def get_archetype_at_row(self, row: int) -> NoteTypeRoleArchetype | None:
        """Retourne l'archétype situé à l'indice de ligne donné."""
        if 0 <= row < len(self._archetypes):
            return self._archetypes[row]
        return None
