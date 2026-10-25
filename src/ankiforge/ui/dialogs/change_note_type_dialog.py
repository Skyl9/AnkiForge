"""Dialogue interactif de changement de type de note pour AnkiForge (ADR 0045).

Permet à l'utilisateur de :
- Sélectionner un type de note cible pour une ou plusieurs notes.
- Configurer la correspondance détaillée des champs (Field Mapping) avec suggestions automatiques.
- Configurer la réassignation des gabarits et cartes physiques existantes (SRS préservé).
- Prévisualiser en direct Avant / Après le contenu remappé sur une note témoin.
- Nettoyer optionnellement les balises d'occlusion (Cloze) lors d'un passage vers Standard.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.services.cards.note_type_service import NoteTypeService
from ankiforge.ui.components.badges import Badge
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ChangeNoteTypeDialog(QDialog):
    """Dialogue modal de migration interactive de type de note."""

    IGNORE_FIELD_LABEL: str = "(Ignorer / Supprimer)"
    DELETE_CARD_LABEL: str = "(Supprimer la carte)"

    @property
    def ignore_field_label(self) -> str:
        return self.tr("(Ignorer / Supprimer)")

    @property
    def delete_card_label(self) -> str:
        return self.tr("(Supprimer la carte)")

    def __init__(self, note_ids: list[int], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.note_ids = list(note_ids)
        self.migrated_count: int = 0
        self.target_model_name: str = ""
        self.combo_sample_note: QComboBox | None = None

        # Chargement des notes et des types de notes disponibles
        self._notes: list[NoteModel] = list(NoteModel.select().where(NoteModel.id.in_(self.note_ids)))
        self._models: list[NoteTypeModel] = list(NoteTypeModel.select().order_by(NoteTypeModel.name.asc()))

        self._selected_target_model: NoteTypeModel | None = None
        self._field_combos: list[QComboBox] = []
        self._template_combos: list[QComboBox] = []
        self._source_fields_list: list[str] = []
        self._target_fields_list: list[str] = []
        self._source_templates_list: list[dict[str, Any]] = []
        self._target_templates_list: list[dict[str, Any]] = []

        self._is_populating: bool = False
        self._selected_sample_index: int = 0

        self.setWindowTitle(self.tr("Changer le type de note"))
        self.resize(780, 680)
        self.setMinimumSize(680, 560)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        self._setup_ui()
        self._init_target_model_selection()

    # -------------------------------------------------------------------------
    # Construction de l'interface
    # -------------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # 1. En-tête
        layout.addWidget(self._create_header_widget())

        # 2. Onglets de configuration (Champs & Gabarits)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                background-color: {DesignTokens.BG_PANEL};
            }}
            QTabBar::tab {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_SECONDARY};
                padding: 7px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 3px;
                font-size: 11px;
                font-weight: 500;
            }}
            QTabBar::tab:selected {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.ACCENT_PRIMARY};
                font-weight: bold;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-bottom: none;
            }}
        """)

        self.tab_fields = QWidget()
        self._setup_tab_fields()
        self.tabs.addTab(self.tab_fields, self.tr("1. Correspondance des champs"))

        self.tab_templates = QWidget()
        self._setup_tab_templates()
        self.tabs.addTab(self.tab_templates, self.tr("2. Correspondance des cartes"))

        layout.addWidget(self.tabs, stretch=1)

        # 3. Option Nettoyage Cloze
        self.chk_clean_cloze = QCheckBox(self.tr("Nettoyer les balises de trous {{c1::...}} si le modèle de destination est Standard"))
        self.chk_clean_cloze.setChecked(True)
        self.chk_clean_cloze.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        self.chk_clean_cloze.toggled.connect(self._on_field_or_cloze_changed)
        layout.addWidget(self.chk_clean_cloze)

        # 4. Zone d'aperçu en direct
        layout.addWidget(self._create_live_preview_widget(), stretch=1)

        # 5. Barre de boutons inférieure
        layout.addWidget(self._create_actions_widget())

    def _create_header_widget(self) -> QWidget:
        header_frame = QFrame()
        header_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        vbox = QVBoxLayout(header_frame)
        vbox.setContentsMargins(6, 6, 6, 6)
        vbox.setSpacing(8)

        # Titre et résumé du lot
        top_row = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("arrows-clockwise", color=DesignTokens.ACCENT_PRIMARY).pixmap(20, 20))
        top_row.addWidget(icon_lbl)

        count = len(self.note_ids)
        title_text = tr("Migration de la note #%1", self.note_ids[0]) if count == 1 else tr("Migration de %1 note(s) sélectionnée(s)", count)
        self.lbl_header_title = QLabel(title_text)
        self.lbl_header_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        top_row.addWidget(self.lbl_header_title)
        top_row.addStretch()

        vbox.addLayout(top_row)

        # Sélecteur de modèle cible
        target_row = QHBoxLayout()
        lbl_target = QLabel(self.tr("Nouveau type de note :"))
        lbl_target.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px; font-weight: 500;")
        target_row.addWidget(lbl_target)

        self.combo_target_model = QComboBox()
        self.combo_target_model.setMinimumWidth(260)
        self.combo_target_model.setStyleSheet(f"""
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 10px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
        """)
        for m in self._models:
            self.combo_target_model.addItem(m.name, userData=m.id)
        self.combo_target_model.currentIndexChanged.connect(self._on_target_model_changed)
        target_row.addWidget(self.combo_target_model)
        target_row.addStretch()

        vbox.addLayout(target_row)
        return header_frame

    def _setup_tab_fields(self) -> None:
        vbox = QVBoxLayout(self.tab_fields)
        vbox.setContentsMargins(10, 10, 10, 10)
        vbox.setSpacing(8)

        # Tableau des champs
        self.table_fields = QTableWidget(0, 3)
        self.table_fields.setHorizontalHeaderLabels([self.tr("Champ source"), "", self.tr("Champ de destination")])
        self.table_fields.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_fields.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table_fields.horizontalHeader().resizeSection(1, 40)
        self.table_fields.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_fields.verticalHeader().setVisible(False)
        self.table_fields.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_fields.setStyleSheet(f"""
            QTableWidget {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                border: none;
                gridline-color: {DesignTokens.BORDER_COLOR};
            }}
            QHeaderView::section {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_SECONDARY};
                font-size: 11px;
                font-weight: bold;
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                padding: 4px;
            }}
        """)
        vbox.addWidget(self.table_fields)

        # Alerte si perte de données
        self.lbl_fields_warning = QLabel()
        self.lbl_fields_warning.setWordWrap(True)
        self.lbl_fields_warning.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.COLOR_YELLOW_BG};
                color: {DesignTokens.COLOR_YELLOW_TEXT};
                border: 1px solid {DesignTokens.COLOR_YELLOW_BORDER};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px 10px;
                font-size: 11px;
            }}
        """)
        self.lbl_fields_warning.setVisible(False)
        vbox.addWidget(self.lbl_fields_warning)

    def _setup_tab_templates(self) -> None:
        vbox = QVBoxLayout(self.tab_templates)
        vbox.setContentsMargins(10, 10, 10, 10)
        vbox.setSpacing(8)

        self.table_templates = QTableWidget(0, 3)
        self.table_templates.setHorizontalHeaderLabels([self.tr("Carte / Gabarit source"), "", self.tr("Gabarit de destination")])
        self.table_templates.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_templates.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table_templates.horizontalHeader().resizeSection(1, 40)
        self.table_templates.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_templates.verticalHeader().setVisible(False)
        self.table_templates.setStyleSheet(f"""
            QTableWidget {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                border: none;
                gridline-color: {DesignTokens.BORDER_COLOR};
            }}
            QHeaderView::section {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_SECONDARY};
                font-size: 11px;
                font-weight: bold;
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                padding: 4px;
            }}
        """)
        vbox.addWidget(self.table_templates)

        self.lbl_cards_metrics = QLabel()
        self.lbl_cards_metrics.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.COLOR_BLUE_BG};
                color: {DesignTokens.COLOR_BLUE_TEXT};
                border: 1px solid {DesignTokens.COLOR_BLUE_BORDER};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px 10px;
                font-size: 11px;
            }}
        """)
        vbox.addWidget(self.lbl_cards_metrics)

    def _create_live_preview_widget(self) -> QWidget:
        preview_frame = QFrame()
        preview_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        vbox = QVBoxLayout(preview_frame)
        vbox.setContentsMargins(10, 10, 10, 10)
        vbox.setSpacing(6)

        # Ligne de contrôle de l'aperçu
        header_row = QHBoxLayout()
        lbl_p_title = QLabel(self.tr("Prévisualisation en direct :"))
        lbl_p_title.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {DesignTokens.TEXT_SECONDARY};")
        header_row.addWidget(lbl_p_title)

        self.combo_sample_note = None
        if len(self.note_ids) > 1:
            self.combo_sample_note = QComboBox()
            self.combo_sample_note.setStyleSheet(f"""
                QComboBox {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-size: 11px;
                    color: {DesignTokens.TEXT_PRIMARY};
                }}
            """)
            for idx, n in enumerate(self._notes):
                self.combo_sample_note.addItem(tr("Note #%1 (%2/%3)", n.id, idx + 1, len(self._notes)), userData=idx)
            self.combo_sample_note.currentIndexChanged.connect(self._on_sample_note_changed)
            header_row.addWidget(self.combo_sample_note)

        header_row.addStretch()
        vbox.addLayout(header_row)

        # Deux panneaux Avant / Après
        panels_row = QHBoxLayout()
        panels_row.setSpacing(10)

        # Panneau Avant
        vbox_before = QVBoxLayout()
        vbox_before.setSpacing(2)
        lbl_before = QLabel(self.tr("Avant (Modèle actuel)"))
        lbl_before.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {DesignTokens.TEXT_MUTED}; text-transform: uppercase;")
        vbox_before.addWidget(lbl_before)

        self.preview_before = QTextEdit()
        self.preview_before.setReadOnly(True)
        self.preview_before.setFont(QFont(DesignTokens.FONT_CODE, 10))
        self.preview_before.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        vbox_before.addWidget(self.preview_before)
        panels_row.addLayout(vbox_before)

        # Panneau Après
        vbox_after = QVBoxLayout()
        vbox_after.setSpacing(2)
        lbl_after = QLabel(self.tr("Après (Modèle migré)"))
        lbl_after.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {DesignTokens.ACCENT_PRIMARY}; text-transform: uppercase;")
        vbox_after.addWidget(lbl_after)

        self.preview_after = QTextEdit()
        self.preview_after.setReadOnly(True)
        self.preview_after.setFont(QFont(DesignTokens.FONT_CODE, 10))
        self.preview_after.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        vbox_after.addWidget(self.preview_after)
        panels_row.addLayout(vbox_after)

        vbox.addLayout(panels_row)
        return preview_frame

    def _create_actions_widget(self) -> QWidget:
        row = QHBoxLayout()
        row.setContentsMargins(0, 4, 0, 0)
        row.setSpacing(10)
        row.addStretch()

        btn_cancel = SecondaryButton(tr("Annuler"))
        btn_cancel.clicked.connect(self.reject)
        row.addWidget(btn_cancel)

        self.btn_apply = PrimaryButton(self.tr("Appliquer la migration"))
        self.btn_apply.setIcon(load_phosphor_icon("check", color=DesignTokens.TEXT_ON_ACCENT))
        self.btn_apply.clicked.connect(self._on_apply_migration)
        row.addWidget(self.btn_apply)

        widget = QWidget()
        widget.setLayout(row)
        return widget

    # -------------------------------------------------------------------------
    # Initialisation & Synchronisation des données
    # -------------------------------------------------------------------------

    def _init_target_model_selection(self) -> None:
        """Sélectionne initialement un modèle cible pertinent."""
        if not self._models:
            return

        current_model_id = None
        if self._notes and self._notes[0].note_type:
            current_model_id = self._notes[0].note_type.id

        target_index = 0
        for i in range(self.combo_target_model.count()):
            mid = self.combo_target_model.itemData(i)
            if mid != current_model_id:
                target_index = i
                break

        self.combo_target_model.setCurrentIndex(target_index)
        self._on_target_model_changed(target_index)

    @Slot(int)
    def _on_target_model_changed(self, index: int) -> None:
        """Déclenché lors du choix d'un nouveau modèle cible."""
        if index < 0 or index >= self.combo_target_model.count():
            return

        target_id = self.combo_target_model.itemData(index)
        self._selected_target_model = NoteTypeModel.get_or_none(NoteTypeModel.id == target_id)
        if not self._selected_target_model:
            return

        # Extraction des champs et gabarits sources
        source_fields_set: list[str] = []
        source_tmpls_list: list[dict[str, Any]] = []
        for n in self._notes:
            if n.note_type and n.note_type.fields_schema:
                try:
                    f_list = json.loads(str(n.note_type.fields_schema))
                    if isinstance(f_list, list):
                        for f in f_list:
                            f_str = str(f)
                            if f_str not in source_fields_set:
                                source_fields_set.append(f_str)
                except Exception:
                    pass
            if n.note_type and n.note_type.templates and not source_tmpls_list:
                try:
                    t_list = json.loads(str(n.note_type.templates))
                    if isinstance(t_list, list):
                        source_tmpls_list = [t for t in t_list if isinstance(t, dict)]
                except Exception:
                    pass

        self._source_fields_list = source_fields_set
        self._source_templates_list = source_tmpls_list

        # Extraction des champs cibles
        target_fields: list[str] = ["Front", "Back"]
        if self._selected_target_model.fields_schema:
            try:
                t_fields = json.loads(str(self._selected_target_model.fields_schema))
                if isinstance(t_fields, list) and t_fields:
                    target_fields = [str(f) for f in t_fields]
            except Exception:
                target_fields = ["Front", "Back"]
        self._target_fields_list = target_fields

        # Extraction des gabarits cibles
        target_tmpls: list[dict[str, Any]] = []
        if self._selected_target_model.templates:
            try:
                t_loaded = json.loads(str(self._selected_target_model.templates))
                if isinstance(t_loaded, list):
                    target_tmpls = [t for t in t_loaded if isinstance(t, dict)]
            except Exception:
                target_tmpls = []
        self._target_templates_list = target_tmpls

        # Ajuster visibilité / coche de clean_cloze
        is_src_cloze = any(NoteTypeService.is_cloze_model(n.note_type) for n in self._notes if n.note_type)
        is_tgt_cloze = NoteTypeService.is_cloze_model(self._selected_target_model)
        self.chk_clean_cloze.setVisible(is_src_cloze and not is_tgt_cloze)

        # Calculer le mapping suggéré automatique
        suggested = NoteTypeService.suggest_field_mapping(self._source_fields_list, self._target_fields_list)

        self._populate_fields_table(suggested)
        self._populate_templates_table()
        self._update_live_preview()

    def _populate_fields_table(self, suggested_mapping: dict[str, str]) -> None:
        """Peuple le tableau de correspondance des champs."""
        self._is_populating = True
        try:
            self.table_fields.setRowCount(len(self._source_fields_list))
            self._field_combos.clear()

            # Examiner quels champs sources ont des données non vides
            active_fields = set()
            for n in self._notes:
                active_v = n.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                if active_v and active_v.content:
                    try:
                        c_dict = json.loads(active_v.content)
                        if isinstance(c_dict, dict):
                            for k, val in c_dict.items():
                                if val is not None and str(val).strip():
                                    active_fields.add(k)
                    except Exception:
                        pass

            for row, src_f in enumerate(self._source_fields_list):
                # Colonne 0 : Nom du champ source + indicateur visuel
                has_content = src_f in active_fields
                col0_widget = QWidget()
                col0_layout = QHBoxLayout(col0_widget)
                col0_layout.setContentsMargins(6, 2, 6, 2)
                col0_layout.setSpacing(6)

                lbl_name = QLabel(src_f)
                lbl_name.setStyleSheet(f"font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
                col0_layout.addWidget(lbl_name)

                if has_content:
                    badge = Badge(self.tr("Contenu"), variant="success")
                    col0_layout.addWidget(badge)
                col0_layout.addStretch()
                self.table_fields.setCellWidget(row, 0, col0_widget)

                # Colonne 1 : Flèche
                arrow_lbl = QLabel(tr("➔"))
                arrow_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                arrow_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 13px;")
                self.table_fields.setCellWidget(row, 1, arrow_lbl)

                # Colonne 2 : ComboBox champ cible
                combo = QComboBox()
                combo.setStyleSheet(f"""
                    QComboBox {{
                        background-color: {DesignTokens.BG_INPUT};
                        border: 1px solid {DesignTokens.BORDER_COLOR};
                        border-radius: {DesignTokens.RADIUS_SM}px;
                        padding: 3px 8px;
                        color: {DesignTokens.TEXT_PRIMARY};
                        font-size: 11px;
                    }}
                """)
                combo.addItem(self.ignore_field_label, userData="")
                for tf in self._target_fields_list:
                    combo.addItem(tf, userData=tf)

                # Pré-sélection
                default_target = suggested_mapping.get(src_f, "")
                if default_target:
                    found_idx = combo.findText(default_target)
                    if found_idx >= 0:
                        combo.setCurrentIndex(found_idx)
                else:
                    combo.setCurrentIndex(0)

                combo.currentIndexChanged.connect(self._on_field_or_cloze_changed)
                self.table_fields.setCellWidget(row, 2, combo)
                self._field_combos.append(combo)

        finally:
            self._is_populating = False

        self._check_fields_warning()

    def _populate_templates_table(self) -> None:
        """Peuple le tableau de correspondance des gabarits."""
        self.table_templates.setRowCount(0)
        self._template_combos.clear()

        # Identifier le nombre maximal de cartes ou gabarits sources
        source_count = max(len(self._source_templates_list), max((len(n.cards) for n in self._notes), default=1))
        self.table_templates.setRowCount(source_count)

        target_count = len(self._target_templates_list)

        for row in range(source_count):
            src_name = tr("Carte %1", row + 1)
            if row < len(self._source_templates_list):
                tmpl_name = str(self._source_templates_list[row].get("name", ""))
                src_name = tr("%1 : %2", src_name, tmpl_name)

            col0_lbl = QLabel(src_name)
            col0_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; padding-left: 6px;")
            self.table_templates.setCellWidget(row, 0, col0_lbl)

            arrow_lbl = QLabel(tr("➔"))
            arrow_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            arrow_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 13px;")
            self.table_templates.setCellWidget(row, 1, arrow_lbl)

            combo = QComboBox()
            combo.setStyleSheet(f"""
                QComboBox {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 3px 8px;
                    color: {DesignTokens.TEXT_PRIMARY};
                    font-size: 11px;
                }}
            """)
            combo.addItem(self.delete_card_label, userData=None)
            for t_idx, tmpl in enumerate(self._target_templates_list):
                t_label = tr("Gabarit %1 : %2", t_idx + 1, tmpl.get("name", f"Carte {t_idx + 1}"))
                combo.addItem(t_label, userData=t_idx)

            # Assignation positionnelle par défaut
            if row < target_count:
                combo.setCurrentIndex(row + 1)  # +1 à cause de DELETE_CARD_LABEL
            else:
                combo.setCurrentIndex(0)  # Supprimer

            combo.currentIndexChanged.connect(self._on_template_mapping_changed)
            self.table_templates.setCellWidget(row, 2, combo)
            self._template_combos.append(combo)

        self._update_cards_metrics_banner()

    def get_field_target_combo(self, row: int) -> QComboBox | None:
        """Accesseur d'aide pour tests et interactions."""
        if 0 <= row < len(self._field_combos):
            return self._field_combos[row]
        return None

    def get_template_target_combo(self, row: int) -> QComboBox | None:
        """Accesseur d'aide pour tests et interactions."""
        if 0 <= row < len(self._template_combos):
            return self._template_combos[row]
        return None

    # -------------------------------------------------------------------------
    # Réactivité & Avertissements
    # -------------------------------------------------------------------------

    def _build_current_field_mapping(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for row, sf in enumerate(self._source_fields_list):
            if row < len(self._field_combos):
                cb = self._field_combos[row]
                val = cb.currentData()
                mapping[sf] = str(val) if val else ""
        return mapping

    def _build_current_template_mapping(self) -> dict[int, int | None]:
        mapping: dict[int, int | None] = {}
        for row in range(len(self._template_combos)):
            cb = self._template_combos[row]
            mapping[row] = cb.currentData()
        return mapping

    def _on_field_or_cloze_changed(self, *_args: Any) -> None:
        if self._is_populating:
            return
        self._check_fields_warning()
        self._update_live_preview()

    def _on_template_mapping_changed(self, *_args: Any) -> None:
        if self._is_populating:
            return
        self._update_cards_metrics_banner()

    @Slot(int)
    def _on_sample_note_changed(self, index: int) -> None:
        self._selected_sample_index = index
        self._update_live_preview()

    def _check_fields_warning(self) -> None:
        mapping = self._build_current_field_mapping()
        is_valid, err_msg, _ = NoteTypeService.validate_field_mapping(
            source_fields=self._source_fields_list,
            target_fields=self._target_fields_list,
            mapping_champs=mapping,
            sample_notes=self._notes,
        )
        if not is_valid and err_msg:
            self.lbl_fields_warning.setText(tr("⚠️ Avertissement : %1", err_msg))
            self.lbl_fields_warning.setVisible(True)
        else:
            self.lbl_fields_warning.setVisible(False)

    def _update_cards_metrics_banner(self) -> None:
        tmpl_mapping = self._build_current_template_mapping()
        target_tmpls_count = len(self._target_templates_list)

        total_preserved = 0
        total_created = 0
        total_deleted = 0

        for n in self._notes:
            existing_cards = list(n.cards)
            for c in existing_cards:
                mapped_target = tmpl_mapping.get(c.template_index)
                if mapped_target is not None and mapped_target < target_tmpls_count:
                    total_preserved += 1
                else:
                    total_deleted += 1

            if target_tmpls_count > len(existing_cards):
                total_created += target_tmpls_count - len(existing_cards)

        self.lbl_cards_metrics.setText(
            tr(
                "Bilan prévisionnel des cartes : %1 carte(s) conservée(s) avec historique SRS, %2 créée(s), %3 supprimée(s).",
                total_preserved,
                total_created,
                total_deleted,
            )
        )

    def _update_live_preview(self) -> None:
        if not self._notes:
            return

        sample_idx = min(self._selected_sample_index, len(self._notes) - 1)
        note = self._notes[sample_idx]

        active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
        before_dict: dict[str, Any] = {}
        if active_v and active_v.content:
            try:
                parsed = json.loads(active_v.content)
                if isinstance(parsed, dict):
                    before_dict = parsed
            except Exception:
                before_dict = {"Front": active_v.content}

        self.preview_before.setPlainText(json.dumps(before_dict, ensure_ascii=False, indent=2))

        # Calculer le contenu remappé
        mapping = self._build_current_field_mapping()
        after_dict = NoteTypeService.remap_fields(before_dict, self._target_fields_list, mapping_champs=mapping)

        # Nettoyage Cloze prévisionnel
        if self.chk_clean_cloze.isChecked() and not NoteTypeService.is_cloze_model(self._selected_target_model) and note.note_type and NoteTypeService.is_cloze_model(note.note_type):
            after_dict = {k: NoteTypeService.clean_cloze_markers(str(v)) if isinstance(v, str) else v for k, v in after_dict.items()}

        self.preview_after.setPlainText(json.dumps(after_dict, ensure_ascii=False, indent=2))

    # -------------------------------------------------------------------------
    # Application de la migration
    # -------------------------------------------------------------------------

    @Slot()
    def _on_apply_migration(self) -> None:
        if not self._selected_target_model:
            QMessageBox.warning(self, self.tr("Erreur"), self.tr("Veuillez sélectionner un type de note de destination."))
            return

        mapping_champs = self._build_current_field_mapping()
        tmpl_mapping = self._build_current_template_mapping()
        clean_cloze = self.chk_clean_cloze.isChecked()

        # Validation préalable
        is_valid, err_msg, _ = NoteTypeService.validate_field_mapping(
            source_fields=self._source_fields_list,
            target_fields=self._target_fields_list,
            mapping_champs=mapping_champs,
            sample_notes=self._notes,
        )

        if not is_valid:
            confirm = QMessageBox.question(
                self,
                self.tr("Avertissement de perte de données"),
                tr(
                    "%1\n\nSouhaitez-vous tout de même appliquer la migration vers '%2' ?",
                    err_msg,
                    self._selected_target_model.name,
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

        try:
            res = NoteTypeService.change_note_type(
                note_ids=self.note_ids,
                target_model=self._selected_target_model,
                mapping_champs=mapping_champs,
                template_mapping=tmpl_mapping,
                clean_cloze=clean_cloze,
            )
            self.migrated_count = res.get("migrated_count", len(self.note_ids))
            self.target_model_name = res.get("target_model_name", self._selected_target_model.name)
            self.accept()
        except Exception as e:
            logger.error("Erreur lors de l'application de la migration : %s", e)
            QMessageBox.critical(self, self.tr("Échec de la migration"), tr("Une erreur est survenue lors de la migration : %1", str(e)))
