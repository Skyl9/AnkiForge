"""
Dialogue de Prévisualisation et d'Importation de Modèle de Carte (.afmodel / .json).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteTypeModel
from ankiforge.services.cards.card_model_io import CardModelIO
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.components.inputs import StyledLineEdit
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.utils.icon_loader import load_phosphor_icon


class ModelImportDialog(QDialog):
    """Dialogue de validation et d'aperçu en direct avant enregistrement en base."""

    def __init__(self, model_data: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.model_data = model_data
        self.imported_model: Optional[NoteTypeModel] = None

        self.setWindowTitle("Importer un Modèle de Carte")
        self.setMinimumSize(850, 580)
        self.resize(920, 620)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # ── En-tête ────────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.download-simple", color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        icon_lbl.setStyleSheet("border: none; background: transparent;")

        title_box = QVBoxLayout()
        title_lbl = QLabel("Prévisualisation du Modèle à Importer")
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 16px; font-weight: bold; border: none;")
        subtitle_lbl = QLabel("Vérifiez le rendu en direct et configurez les options de fusion avant l'import.")
        subtitle_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(subtitle_lbl)

        header.addWidget(icon_lbl)
        header.addLayout(title_box, 1)
        layout.addLayout(header)

        # ── Corps principal ────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Panneau Gauche : Paramètres & Métadonnées
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 10, 0)
        left_layout.setSpacing(12)

        # 1. Nom du modèle
        lbl_name = QLabel("NOM DU MODÈLE :")
        lbl_name.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        left_layout.addWidget(lbl_name)

        self.name_input = StyledLineEdit()
        self.name_input.setText(self.model_data.get("name", "Modèle Importé"))
        left_layout.addWidget(self.name_input)

        # 2. Métadonnées
        meta = self.model_data.get("metadata", {})
        author = meta.get("author", "Inconnu")
        version = meta.get("version", "1.0.0")
        desc = meta.get("description", "")
        tags = meta.get("tags", [])

        meta_frame = QFrame()
        meta_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 10px;
            }}
        """)
        meta_layout = QVBoxLayout(meta_frame)
        meta_layout.setContentsMargins(8, 8, 8, 8)
        meta_layout.setSpacing(5)

        lbl_meta_author = QLabel(f"<b>Auteur :</b> {author} | <b>Version :</b> v{version}")
        lbl_meta_author.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; border: none;")
        meta_layout.addWidget(lbl_meta_author)

        if desc:
            lbl_desc = QLabel(f"<em>{desc}</em>")
            lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none;")
            lbl_desc.setWordWrap(True)
            meta_layout.addWidget(lbl_desc)

        fields_list = self.model_data.get("fields_schema", [])
        lbl_meta_fields = QLabel(f"<b>Champs ({len(fields_list)}) :</b> {', '.join(fields_list)}")
        lbl_meta_fields.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; border: none;")
        lbl_meta_fields.setWordWrap(True)
        meta_layout.addWidget(lbl_meta_fields)

        templates_list = self.model_data.get("templates", [])
        lbl_meta_tmpls = QLabel(f"<b>Cartes / Faces ({len(templates_list)}) :</b> {', '.join(t.get('name', 'Carte') for t in templates_list)}")
        lbl_meta_tmpls.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; border: none;")
        meta_layout.addWidget(lbl_meta_tmpls)

        if tags:
            lbl_meta_tags = QLabel(f"<b>Tags :</b> {', '.join(tags)}")
            lbl_meta_tags.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none;")
            meta_layout.addWidget(lbl_meta_tags)

        left_layout.addWidget(meta_frame)

        # 3. Détection de collision de nom
        self.collision_frame = QFrame()
        self.collision_frame.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(245, 158, 11, 0.10);
                border: 1px solid {DesignTokens.COLOR_YELLOW};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 10px;
            }}
        """)
        col_layout = QVBoxLayout(self.collision_frame)
        col_layout.setContentsMargins(8, 8, 8, 8)
        col_layout.setSpacing(6)

        lbl_col_title = QLabel("⚠️ Un modèle porte déjà ce nom :")
        lbl_col_title.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; font-weight: bold; border: none;")
        col_layout.addWidget(lbl_col_title)

        self.radio_rename = QRadioButton("Créer une copie (Nom incrémenté)")
        self.radio_rename.setChecked(True)
        self.radio_rename.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; border: none;")

        self.radio_overwrite = QRadioButton("Écraser le modèle existant")
        self.radio_overwrite.setStyleSheet(f"color: {DesignTokens.COLOR_RED}; font-size: 11px; border: none;")

        self.btn_group = QButtonGroup(self)
        self.btn_group.addButton(self.radio_rename)
        self.btn_group.addButton(self.radio_overwrite)

        col_layout.addWidget(self.radio_rename)
        col_layout.addWidget(self.radio_overwrite)

        left_layout.addWidget(self.collision_frame)
        self._check_name_collision()
        self.name_input.textChanged.connect(self._check_name_collision)

        left_layout.addStretch()
        splitter.addWidget(left_widget)

        # Panneau Droit : Aperçu WebEngine Live
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)
        right_layout.setSpacing(6)

        lbl_preview_title = QLabel("APERÇU DU RENDU EN DIRECT :")
        lbl_preview_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        right_layout.addWidget(lbl_preview_title)

        self.preview_widget = CardPreviewWidget()
        right_layout.addWidget(self.preview_widget, 1)

        splitter.addWidget(right_widget)
        splitter.setSizes([360, 480])
        layout.addWidget(splitter, 1)

        # ── Barre d'actions inférieure ─────────────────────────────────────────
        bot_row = QHBoxLayout()
        bot_row.setSpacing(10)

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.clicked.connect(self.reject)

        self.btn_import = PrimaryButton("Importer dans la Forge")
        self.btn_import.setIcon(load_phosphor_icon("ph.check", color="white"))
        self.btn_import.clicked.connect(self._on_confirm_import)

        bot_row.addStretch()
        bot_row.addWidget(btn_cancel)
        bot_row.addWidget(self.btn_import)
        layout.addLayout(bot_row)

        self._render_preview()

    def _check_name_collision(self) -> None:
        target_name = self.name_input.text().strip()
        exists = NoteTypeModel.get_or_none(NoteTypeModel.name == target_name) is not None
        self.collision_frame.setVisible(exists)

    def _render_preview(self) -> None:
        # Vérifier si des cartes témoins réelles sont incluses dans le paquet
        demos: List[Dict[str, str]] = self.model_data.get("demo_cards", [])
        if demos and isinstance(demos, list) and isinstance(demos[0], dict):
            preview_fields = dict(demos[0])
        else:
            fields_list = self.model_data.get("fields_schema", ["Front", "Back"])
            preview_fields = {f: f"Exemple de contenu pour {f}" for f in fields_list}
            if "Front" in preview_fields:
                preview_fields["Front"] = "Qu'est-ce que le modèle AnkiForge ?"
            if "Back" in preview_fields:
                preview_fields["Back"] = "Un gabarit riche avec CSS modulaire et snippets interactifs."
            if "Texte" in preview_fields:
                preview_fields["Texte"] = "La capitale de la France est {{c1::Paris}}."
            if "Extra" in preview_fields:
                preview_fields["Extra"] = "Paris est la ville la plus peuplée de France."

        templates = self.model_data.get("templates", [])
        css = self.model_data.get("css_style", "")

        self.preview_widget.update_preview(
            note_type=None,
            fields_dict=preview_fields,
            override_templates=templates,
            override_css=css,
        )

    def _on_confirm_import(self) -> None:
        target_name = self.name_input.text().strip()
        if not target_name:
            return

        overwrite = self.collision_frame.isVisible() and self.radio_overwrite.isChecked()

        model_inst, _ = CardModelIO.save_model_to_db(
            model_data=self.model_data,
            overwrite_existing=overwrite,
            new_name=target_name,
        )
        self.imported_model = model_inst
        self.accept()
