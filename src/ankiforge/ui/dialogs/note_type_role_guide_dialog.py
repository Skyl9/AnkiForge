"""
Dialogue modal unifié présentant le guide sémantique et le générateur de tableaux des rôles IA pour les types de note.
"""

from __future__ import annotations

import markdown
from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtWidgets import (
    QCompleter,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.cards.note_type_roles import (
    NoteTypeRoleArchetype,
    create_table_rows_for_archetype,
    generate_markdown_table,
    get_standard_role_archetypes,
    is_markdown_table,
    parse_markdown_table,
)
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton, apply_compact_style
from ankiforge.ui.components.tables import StyledTableWidget
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon


class TargetFieldsItemDelegate(QStyledItemDelegate):
    """Délégué d'édition pour la colonne Champs cibles offrant l'autocomplétion sur les champs réels."""

    def __init__(self, model_fields: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model_fields = model_fields

    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QWidget:
        editor = QLineEdit(parent)
        if self._model_fields:
            completer = QCompleter(self._model_fields, editor)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            editor.setCompleter(completer)
        return editor


class NoteTypeRoleGuideDialog(QDialog):
    """
    Dialogue modal unifié permettant de consulter le catalogue des rôles IA,
    de choisir un archétype pré-mappé sur les champs réels du modèle,
    ou de personnaliser son tableau Markdown avec prévisualisation en temps réel.
    """

    def __init__(
        self,
        current_text: str = "",
        model_fields: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Guide sémantique et prompt IA pour types de note"))
        self.resize(820, 520)
        self.setMinimumSize(720, 440)
        self.setModal(True)

        self._current_text = current_text.strip() if current_text else ""
        self._model_fields: list[str] = list(model_fields) if model_fields else []
        self._archetypes: list[NoteTypeRoleArchetype] = get_standard_role_archetypes()

        self.selected_directive: str | None = None
        self.selected_archetype: NoteTypeRoleArchetype | None = None
        self.selected_archetype_name: str | None = None
        self.archetype_chips: list[QPushButton] = []

        self._is_updating: bool = False

        self._setup_ui()
        self._init_data()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 14, 16, 14)
        root_layout.setSpacing(10)

        # 1. En-tête descriptif compact
        header_frame = QFrame()
        header_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 6px;
            }}
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 6, 10, 6)
        header_layout.setSpacing(12)

        icon_label = QLabel()
        icon_label.setPixmap(load_phosphor_icon("ph.table", color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        icon_label.setStyleSheet("border: none; background: transparent;")
        header_layout.addWidget(icon_label)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)

        title_lbl = QLabel(self.tr("Guide sémantique et prompt IA pour types de note"))
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: bold; border: none; background: transparent;")
        title_vbox.addWidget(title_lbl)

        subtitle_lbl = QLabel(self.tr("Définissez les directives et le tableau de rôles injectés dans la balise {{ available_card_models }} pour orienter l'IA."))
        subtitle_lbl.setWordWrap(True)
        subtitle_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        title_vbox.addWidget(subtitle_lbl)

        header_layout.addLayout(title_vbox, 1)
        root_layout.addWidget(header_frame)

        # 2. Bandeau conditionnel si directive textuelle libre existante
        self.plain_text_banner = QFrame()
        self.plain_text_banner.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px;
            }}
        """)
        banner_layout = QHBoxLayout(self.plain_text_banner)
        banner_layout.setContentsMargins(8, 4, 8, 4)
        banner_layout.setSpacing(8)

        self.lbl_plain_text = QLabel()
        self.lbl_plain_text.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        banner_layout.addWidget(self.lbl_plain_text, 1)

        self.btn_convert_plain_text = SecondaryButton(self.tr("Convertir en règle"))
        apply_compact_style(self.btn_convert_plain_text, height=24)
        self.btn_convert_plain_text.clicked.connect(self._on_convert_plain_text)
        banner_layout.addWidget(self.btn_convert_plain_text)

        self.btn_replace_plain_text = SecondaryButton(self.tr("Remplacer par un archétype"))
        apply_compact_style(self.btn_replace_plain_text, height=24)
        self.btn_replace_plain_text.clicked.connect(self._on_replace_plain_text)
        banner_layout.addWidget(self.btn_replace_plain_text)

        root_layout.addWidget(self.plain_text_banner)

        # 3. Ruban supérieur des archétypes prédéfinis
        archetypes_row = QHBoxLayout()
        archetypes_row.setSpacing(6)

        lbl_arch = QLabel(self.tr("Archétypes :"))
        lbl_arch.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: bold;")
        archetypes_row.addWidget(lbl_arch)

        chips_scroll = QScrollArea()
        chips_scroll.setWidgetResizable(True)
        chips_scroll.setFixedHeight(34)
        chips_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        chips_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        chips_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        chips_container = QWidget()
        chips_layout = QHBoxLayout(chips_container)
        chips_layout.setContentsMargins(0, 0, 0, 0)
        chips_layout.setSpacing(6)

        self.archetype_chips = []
        for arch in self._archetypes:
            chip_btn = SecondaryButton(arch.name)
            apply_compact_style(chip_btn, height=26)
            chip_btn.setToolTip(tr("%1\n\nChamps suggérés : %2", arch.use_case, ", ".join(arch.suggested_fields)))
            chip_btn.clicked.connect(lambda _checked=False, a=arch: self.load_archetype(a))
            chips_layout.addWidget(chip_btn)
            self.archetype_chips.append(chip_btn)

        chips_layout.addStretch()
        chips_scroll.setWidget(chips_container)
        archetypes_row.addWidget(chips_scroll, 1)
        root_layout.addLayout(archetypes_row)

        # 4. Pastilles des champs réels du modèle (si disponibles)
        if self._model_fields:
            fields_row = QHBoxLayout()
            fields_row.setSpacing(6)

            lbl_model_fields = QLabel(self.tr("Champs du type de note :"))
            lbl_model_fields.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
            fields_row.addWidget(lbl_model_fields)

            for f_name in self._model_fields:
                field_btn = SecondaryButton(f_name)
                apply_compact_style(field_btn, height=22)
                field_btn.setToolTip(tr("Insérer « %1 » dans la règle sélectionnée", f_name))
                field_btn.clicked.connect(lambda _checked=False, fn=f_name: self._insert_field_into_selected_row(fn))
                fields_row.addWidget(field_btn)

            fields_row.addStretch()
            root_layout.addLayout(fields_row)

        # 5. Grille interactive (3 colonnes)
        columns = [
            self.tr("Concept / Cas d'usage"),
            self.tr("Directive sémantique pour l'IA"),
            self.tr("Champs cibles"),
        ]
        self.grid_table = StyledTableWidget(columns=columns, parent=self)
        self.grid_table.setWordWrap(True)
        self.grid_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.grid_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.grid_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.grid_table.setColumnWidth(0, 190)
        self.grid_table.setColumnWidth(2, 180)
        self.grid_table.setItemDelegateForColumn(2, TargetFieldsItemDelegate(self._model_fields, self.grid_table))
        self.grid_table.itemChanged.connect(self._on_grid_item_changed)
        root_layout.addWidget(self.grid_table, 1)

        # Barre d'actions sous la grille
        grid_actions_row = QHBoxLayout()
        grid_actions_row.setSpacing(6)

        btn_add = SecondaryButton(self.tr("+ Ajouter une règle"))
        apply_compact_style(btn_add, height=26)
        btn_add.clicked.connect(self._add_blank_row)
        grid_actions_row.addWidget(btn_add)

        btn_remove = SecondaryButton(self.tr("Supprimer la règle"))
        apply_compact_style(btn_remove, height=26)
        btn_remove.clicked.connect(self._remove_selected_row)
        grid_actions_row.addWidget(btn_remove)

        btn_clear = SecondaryButton(self.tr("Tout effacer"))
        apply_compact_style(btn_clear, height=26)
        btn_clear.clicked.connect(self._clear_rows)
        grid_actions_row.addWidget(btn_clear)

        grid_actions_row.addStretch()
        root_layout.addLayout(grid_actions_row)

        # 6. Aperçu Markdown en direct
        preview_frame = QFrame()
        preview_frame.setFixedHeight(95)
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

        lbl_prev_title = QLabel(self.tr("Aperçu en direct du tableau Markdown généré :"))
        lbl_prev_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        preview_vbox.addWidget(lbl_prev_title)

        self.preview_browser = QTextBrowser()
        self.preview_browser.setStyleSheet("border: none; background: transparent;")
        preview_vbox.addWidget(self.preview_browser, 1)

        root_layout.addWidget(preview_frame)

        # 7. Pied de dialogue
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        caption_lbl = QLabel(self.tr("Astuce : L'application remplace la valeur du champ « Rôle IA » du type de note actif."))
        caption_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        bottom_layout.addWidget(caption_lbl, 1)

        btn_cancel = SecondaryButton(self.tr("Annuler"))
        apply_compact_style(btn_cancel, height=30)
        btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(btn_cancel)

        self.btn_apply = PrimaryButton(self.tr("Appliquer au type de note"))
        apply_compact_style(self.btn_apply, height=30)
        self.btn_apply.clicked.connect(self._on_apply)
        bottom_layout.addWidget(self.btn_apply)

        root_layout.addLayout(bottom_layout)

    def _get_default_fields(self) -> str:
        """Retourne la liste par défaut des champs pour une nouvelle règle."""
        return ", ".join(self._model_fields[:2]) if self._model_fields else "Front, Back"

    def _init_data(self) -> None:
        """Initialise la table selon le texte courant ou charge l'archétype par défaut."""
        if self._current_text:
            if is_markdown_table(self._current_text):
                self.plain_text_banner.setVisible(False)
                self._load_markdown_into_grid(self._current_text)
                return
            else:
                self.plain_text_banner.setVisible(True)
                self.lbl_plain_text.setText(tr("Directive textuelle actuelle : « %1 »", self._current_text))
                self._populate_grid_from_rows([])
                return
        else:
            self.plain_text_banner.setVisible(False)

        # Par défaut (texte vide), charger l'archétype Basique
        if self._archetypes:
            self.load_archetype(self._archetypes[0])

    def load_archetype(self, archetype: NoteTypeRoleArchetype) -> None:
        """Charge un archétype dans la grille interactive avec mapping sur les champs réels."""
        self.plain_text_banner.setVisible(False)
        self.selected_archetype = archetype
        self.selected_archetype_name = archetype.name

        rows = create_table_rows_for_archetype(archetype, self._model_fields)
        self._populate_grid_from_rows(rows)

    def _populate_grid_from_rows(self, rows: list[dict[str, str]]) -> None:
        """Remplit la grille avec la liste de dictionnaires fournie."""
        self._is_updating = True
        self.grid_table.setRowCount(len(rows))

        for row_idx, row in enumerate(rows):
            item_concept = QTableWidgetItem(row.get("concept", ""))
            item_directive = QTableWidgetItem(row.get("directive", ""))
            item_fields = QTableWidgetItem(row.get("fields", ""))

            self.grid_table.setItem(row_idx, 0, item_concept)
            self.grid_table.setItem(row_idx, 1, item_directive)
            self.grid_table.setItem(row_idx, 2, item_fields)

        self._is_updating = False
        self._update_preview()

    def _load_markdown_into_grid(self, md_text: str) -> None:
        """Parse un tableau Markdown existant et le charge dans la grille."""
        _, rows = parse_markdown_table(md_text)
        if rows:
            self._populate_grid_from_rows(rows)
        else:
            self._populate_grid_from_rows([])

    def _add_blank_row(self) -> None:
        """Ajoute une ligne vierge à la grille."""
        self._is_updating = True
        row = self.grid_table.rowCount()
        self.grid_table.insertRow(row)

        self.grid_table.setItem(row, 0, QTableWidgetItem(self.tr("Nouveau concept")))
        self.grid_table.setItem(row, 1, QTableWidgetItem(self.tr("Directive sémantique pour l'IA")))
        self.grid_table.setItem(row, 2, QTableWidgetItem(self._get_default_fields()))

        self._is_updating = False
        self._update_preview()

    def _remove_selected_row(self) -> None:
        """Supprime la ligne actuellement sélectionnée."""
        row = self.grid_table.currentRow()
        if row >= 0:
            self.grid_table.removeRow(row)
            self._update_preview()

    def _clear_rows(self) -> None:
        """Vide l'ensemble des règles de la grille."""
        self.grid_table.setRowCount(0)
        self._update_preview()

    def _insert_field_into_selected_row(self, field_name: str) -> None:
        """Insère ou ajoute le champ spécifié dans la cellule Champs cibles de la ligne active."""
        row = self.grid_table.currentRow()
        if row < 0:
            if self.grid_table.rowCount() > 0:
                row = self.grid_table.rowCount() - 1
            else:
                self._add_blank_row()
                row = 0

        item = self.grid_table.item(row, 2)
        if not item:
            item = QTableWidgetItem()
            self.grid_table.setItem(row, 2, item)

        current_val = item.text().strip()
        if not current_val:
            item.setText(field_name)
        else:
            existing = [f.strip() for f in current_val.split(",") if f.strip()]
            if field_name not in existing:
                existing.append(field_name)
                item.setText(", ".join(existing))

        self._update_preview()

    def _on_convert_plain_text(self) -> None:
        """Convertit la directive textuelle libre existante en première règle de la grille."""
        if not self._current_text:
            return

        rows = [
            {
                "concept": self.tr("Directive personnalisée"),
                "directive": self._current_text,
                "fields": self._get_default_fields(),
            }
        ]
        self._populate_grid_from_rows(rows)
        self.plain_text_banner.setVisible(False)

    def _on_replace_plain_text(self) -> None:
        """Masque le bandeau de texte libre et charge l'archétype par défaut."""
        if self._archetypes:
            self.load_archetype(self._archetypes[0])

    def _on_grid_item_changed(self, _item: QTableWidgetItem) -> None:
        """Régénère l'aperçu à chaque modification d'une cellule."""
        if not self._is_updating:
            self._update_preview()

    def _get_current_rows_data(self) -> list[dict[str, str]]:
        """Extrait les données de la grille sous forme de liste de dictionnaires."""
        rows: list[dict[str, str]] = []
        for r in range(self.grid_table.rowCount()):
            c_item = self.grid_table.item(r, 0)
            d_item = self.grid_table.item(r, 1)
            f_item = self.grid_table.item(r, 2)

            rows.append(
                {
                    "concept": c_item.text().strip() if c_item else "",
                    "directive": d_item.text().strip() if d_item else "",
                    "fields": f_item.text().strip() if f_item else "",
                }
            )
        return rows

    def _update_preview(self) -> None:
        """Actualise l'aperçu Markdown / HTML du tableau généré."""
        rows = self._get_current_rows_data()
        if not rows:
            self.preview_browser.setHtml(f"<p style='color: {DesignTokens.TEXT_MUTED}; font-size: 11px;'><i>{self.tr('Aucune règle définie.')}</i></p>")
            return

        md_text = generate_markdown_table(rows)
        html_rendered = markdown.markdown(md_text, extensions=["tables"])
        styled_html = f"""
        <style>
            table {{ border-collapse: collapse; width: 100%; font-size: 11px; }}
            th, td {{ border: 1px solid {DesignTokens.BORDER_COLOR}; padding: 3px 6px; text-align: left; }}
            th {{ background-color: {DesignTokens.BG_PANEL}; color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; }}
            td {{ color: {DesignTokens.TEXT_SECONDARY}; }}
        </style>
        {html_rendered}
        """
        self.preview_browser.setHtml(styled_html)

    def _on_apply(self) -> None:
        """Valide et enregistre le tableau Markdown généré."""
        rows = self._get_current_rows_data()
        if not rows:
            self.selected_directive = ""
        else:
            self.selected_directive = generate_markdown_table(rows)

        self.accept()
