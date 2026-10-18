from __future__ import annotations

import json
import logging

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteModel, NoteTypeModel
from ankiforge.services.cards.group_edit_service import (
    GroupEditOptions,
    GroupEditResult,
    GroupEditService,
)
from ankiforge.ui.components import ActionButton, PrimaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon

logger = logging.getLogger(__name__)


class GroupEditDialog(QDialog):
    """Boîte de dialogue modale permettant l'édition groupée de cartes/notes sélectionnées."""

    def __init__(self, note_ids: list[int], parent: QWidget | None = None, initial_mode: str | None = None) -> None:
        super().__init__(parent)
        self.note_ids = list(note_ids)
        self.result_data: GroupEditResult | None = None

        self.setWindowTitle(tr("Édition groupée (%1 cartes)", len(self.note_ids)))
        self.setMinimumWidth(560)
        self.setStyleSheet(f"QDialog {{ background-color: {DesignTokens.BG_PANEL}; }}")

        self._available_fields = self._collect_available_fields()
        self._init_ui()

        if initial_mode == "find_replace":
            self.cb_enable_field_edit.setChecked(True)
            idx = self.combo_action.findData("find_replace")
            if idx >= 0:
                self.combo_action.setCurrentIndex(idx)
            self.input_find.setFocus()

    def _collect_available_fields(self) -> list[str]:
        """Extrait l'ensemble des champs distincts partagés par les modèles des notes sélectionnées."""
        fields_set: list[str] = []
        try:
            notes = list(NoteModel.select(NoteModel.note_type).where(NoteModel.id.in_(self.note_ids)).distinct())
            type_ids = {n.note_type_id for n in notes if n.note_type_id}
            note_types = list(NoteTypeModel.select().where(NoteTypeModel.id.in_(type_ids)))

            for nt in note_types:
                if nt.fields_schema:
                    try:
                        parsed = json.loads(nt.fields_schema)
                        if isinstance(parsed, list):
                            for f_name in parsed:
                                if isinstance(f_name, str) and f_name not in fields_set:
                                    fields_set.append(f_name)
                    except Exception as e:
                        logger.warning("Erreur décodage fields_schema pour NoteType %s: %s", nt.id, e)
        except Exception as e:
            logger.warning("Erreur collecte des champs des notes sélectionnées: %s", e)

        if not fields_set:
            fields_set = ["Front", "Back"]
        return fields_set

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # 1. En-tête informatif
        header_card = QFrame(self)
        header_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_SIDEBAR};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(6, 6, 6, 6)
        header_layout.setSpacing(12)

        icon_lbl = QLabel(header_card)
        icon_lbl.setPixmap(load_phosphor_icon("cards", color=DesignTokens.ACCENT_PRIMARY).pixmap(28, 28))
        header_layout.addWidget(icon_lbl)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        title_lbl = QLabel(tr("Édition groupée — %1 carte(s) sélectionnée(s)", len(self.note_ids)), header_card)
        title_lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; border: none;")
        info_layout.addWidget(title_lbl)

        sub_lbl = QLabel(
            tr("Les modifications ci-dessous s'appliqueront à toutes les cartes sélectionnées dans une seule transaction atomique."),
            header_card,
        )
        sub_lbl.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED}; border: none;")
        sub_lbl.setWordWrap(True)
        info_layout.addWidget(sub_lbl)

        header_layout.addLayout(info_layout, stretch=1)
        layout.addWidget(header_card)

        # 2. Section Tags
        tags_group = QGroupBox(self.tr("🏷️ Étiquettes (Tags)"), self)
        tags_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold;
                font-size: 11px;
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                margin-top: 6px;
                padding-top: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }}
        """)
        tags_layout = QVBoxLayout(tags_group)
        tags_layout.setSpacing(8)

        # Ajout de tags
        lbl_add = QLabel(self.tr("Ajouter des tags (séparés par virgules ou espaces) :"), tags_group)
        lbl_add.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        tags_layout.addWidget(lbl_add)

        self.input_tags_add = QLineEdit(tags_group)
        self.input_tags_add.setPlaceholderText(self.tr("Ex: vocabulaire, examen-2026, chap-1"))
        self.input_tags_add.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px 10px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        tags_layout.addWidget(self.input_tags_add)

        # Retrait de tags
        lbl_remove = QLabel(self.tr("Retirer des tags (séparés par virgules ou espaces) :"), tags_group)
        lbl_remove.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        tags_layout.addWidget(lbl_remove)

        self.input_tags_remove = QLineEdit(tags_group)
        self.input_tags_remove.setPlaceholderText(self.tr("Ex: brouillon, a_revoir"))
        self.input_tags_remove.setStyleSheet(self.input_tags_add.styleSheet())
        tags_layout.addWidget(self.input_tags_remove)

        tags_note = QLabel(
            self.tr("<i>Remarque : les tags de provenance documentaire (doc:, source:, page:, section:) sont préservés pour garantir la traçabilité.</i>"),
            tags_group,
        )
        tags_note.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px;")
        tags_note.setWordWrap(True)
        tags_layout.addWidget(tags_note)

        layout.addWidget(tags_group)

        # 3. Section Champs de Contenu
        field_group = QGroupBox(self.tr("📝 Modification d'un champ de contenu"), self)
        field_group.setStyleSheet(tags_group.styleSheet())
        field_layout = QVBoxLayout(field_group)
        field_layout.setSpacing(8)

        self.cb_enable_field_edit = QCheckBox(self.tr("Activer la modification d'un champ pour tout le groupe"), field_group)
        self.cb_enable_field_edit.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: bold;")
        self.cb_enable_field_edit.toggled.connect(self._on_field_edit_toggled)
        field_layout.addWidget(self.cb_enable_field_edit)

        # Conteneur des options de champ
        self.field_options_widget = QWidget(field_group)
        f_opts_layout = QVBoxLayout(self.field_options_widget)
        f_opts_layout.setContentsMargins(0, 4, 0, 0)
        f_opts_layout.setSpacing(8)

        # Sélecteur de champ et action
        selectors_layout = QHBoxLayout()
        selectors_layout.setSpacing(8)

        # Champ cible
        vbox_field = QVBoxLayout()
        vbox_field.setSpacing(2)
        lbl_f_target = QLabel(self.tr("Champ cible :"), self.field_options_widget)
        lbl_f_target.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        vbox_field.addWidget(lbl_f_target)

        self.combo_field = QComboBox(self.field_options_widget)
        for f_name in self._available_fields:
            self.combo_field.addItem(f_name)
        vbox_field.addWidget(self.combo_field)
        selectors_layout.addLayout(vbox_field, stretch=1)

        # Action à effectuer
        vbox_action = QVBoxLayout()
        vbox_action.setSpacing(2)
        lbl_f_action = QLabel(self.tr("Opération :"), self.field_options_widget)
        lbl_f_action.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        vbox_action.addWidget(lbl_f_action)

        self.combo_action = QComboBox(self.field_options_widget)
        self.combo_action.addItem(self.tr("Remplacer par"), "replace")
        self.combo_action.addItem(self.tr("Ajouter à la fin (suffixer)"), "append")
        self.combo_action.addItem(self.tr("Ajouter au début (préfixer)"), "prepend")
        self.combo_action.addItem(self.tr("Rechercher et remplacer"), "find_replace")
        self.combo_action.currentIndexChanged.connect(self._on_action_changed)
        vbox_action.addWidget(self.combo_action)
        selectors_layout.addLayout(vbox_action, stretch=1)

        f_opts_layout.addLayout(selectors_layout)

        # Ligne "Rechercher" (uniquement pour find_replace)
        self.find_container = QWidget(self.field_options_widget)
        find_layout = QVBoxLayout(self.find_container)
        find_layout.setContentsMargins(0, 0, 0, 0)
        find_layout.setSpacing(2)

        lbl_find = QLabel(self.tr("Texte à rechercher :"), self.find_container)
        lbl_find.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        find_layout.addWidget(lbl_find)

        self.input_find = QLineEdit(self.find_container)
        self.input_find.setPlaceholderText(self.tr("Sous-chaîne exacte à remplacer..."))
        self.input_find.setStyleSheet(self.input_tags_add.styleSheet())
        find_layout.addWidget(self.input_find)
        self.find_container.setVisible(False)
        f_opts_layout.addWidget(self.find_container)

        # Zone de texte de la nouvelle valeur
        self.lbl_val = QLabel(self.tr("Texte de remplacement / Valeur :"), self.field_options_widget)
        self.lbl_val.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        f_opts_layout.addWidget(self.lbl_val)

        self.text_field_value = QTextEdit(self.field_options_widget)
        self.text_field_value.setPlaceholderText(self.tr("Saisissez la valeur ou le complément..."))
        self.text_field_value.setMaximumHeight(80)
        self.text_field_value.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
            }}
            QTextEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        f_opts_layout.addWidget(self.text_field_value)

        field_layout.addWidget(self.field_options_widget)
        self.field_options_widget.setEnabled(False)
        layout.addWidget(field_group)

        # 4. Boutons d'action
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_cancel = ActionButton("x", self.tr("Annuler"), parent=self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        btn_layout.addStretch()

        self.btn_apply = PrimaryButton(self.tr("Appliquer au groupe"), parent=self)
        self.btn_apply.setIcon(load_on_accent_icon("check"))
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        btn_layout.addWidget(self.btn_apply)

        layout.addLayout(btn_layout)

    @Slot(bool)
    def _on_field_edit_toggled(self, checked: bool) -> None:
        self.field_options_widget.setEnabled(checked)

    @Slot(int)
    def _on_action_changed(self, index: int) -> None:
        action_key = str(self.combo_action.currentData())
        is_find_replace = action_key == "find_replace"
        self.find_container.setVisible(is_find_replace)
        if is_find_replace:
            self.lbl_val.setText(self.tr("Remplacer par :"))
        elif action_key == "append":
            self.lbl_val.setText(self.tr("Texte à ajouter à la fin :"))
        elif action_key == "prepend":
            self.lbl_val.setText(self.tr("Texte à ajouter au début :"))
        else:
            self.lbl_val.setText(self.tr("Nouvelle valeur du champ :"))

    @Slot()
    def _on_apply_clicked(self) -> None:
        raw_add = self.input_tags_add.text().strip()
        raw_remove = self.input_tags_remove.text().strip()

        tags_to_add = [t.strip() for t in raw_add.replace(",", " ").split() if t.strip()]
        tags_to_remove = [t.strip() for t in raw_remove.replace(",", " ").split() if t.strip()]

        field_name: str | None = None
        field_action: str | None = None
        field_value: str = ""
        find_text: str = ""

        if self.cb_enable_field_edit.isChecked():
            field_name = str(self.combo_field.currentText()).strip()
            field_action = str(self.combo_action.currentData())
            field_value = self.text_field_value.toPlainText().strip()
            find_text = self.input_find.text().strip()

            if not field_name:
                QMessageBox.warning(self, self.tr("Champ manquant"), self.tr("Veuillez sélectionner un champ cible."))
                return

            if field_action == "find_replace" and not find_text:
                QMessageBox.warning(self, self.tr("Texte manquant"), self.tr("Veuillez préciser le texte à rechercher."))
                return

        if not tags_to_add and not tags_to_remove and not field_name:
            QMessageBox.information(
                self,
                self.tr("Aucune modification"),
                self.tr("Veuillez renseigner au moins une action (tags à ajouter/retirer ou modification de champ)."),
            )
            return

        options = GroupEditOptions(
            tags_to_add=tags_to_add,
            tags_to_remove=tags_to_remove,
            field_name=field_name,
            field_action=field_action,
            field_value=field_value,
            find_text=find_text,
        )

        result = GroupEditService.apply_group_edit(self.note_ids, options)
        if not result.success:
            QMessageBox.critical(
                self,
                self.tr("Échec de l'édition groupée"),
                tr("La modification a échoué et la transaction a été annulée :\n%1", result.error_message or "Erreur inconnue"),
            )
            return

        self.result_data = result
        self.accept()
