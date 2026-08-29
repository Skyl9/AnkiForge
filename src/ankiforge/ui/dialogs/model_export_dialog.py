"""
Dialogue d'Exportation de Modèle de Carte (.afmodel / .json).
Permet de configurer les métadonnées de partage (auteur, version, description, cartes démos).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.services.cards.card_model_io import BUNDLE_EXTENSION, CardModelIO
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.components.inputs import StyledLineEdit
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ModelExportDialog(QDialog):
    """Boîte de dialogue modale pour l'exportation de modèles au format .afmodel ou .json."""

    def __init__(self, model: NoteTypeModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.exported_file_path: Path | None = None

        self.setWindowTitle(f"Exporter le Modèle — {self.model.name}")
        self.setMinimumSize(580, 520)
        self.resize(620, 560)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QFrame.section-box {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 12px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # ── En-tête ────────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.package", color=DesignTokens.ACCENT_PRIMARY).pixmap(26, 26))
        header.addWidget(icon_lbl)

        title_box = QVBoxLayout()
        title_lbl = QLabel(f"Exporter le Modèle : {self.model.name}")
        title_lbl.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        subtitle_lbl = QLabel("Créez un paquet autonome .afmodel partageable avec styles et cartes d'exemple.")
        subtitle_lbl.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED};")
        title_box.addWidget(title_lbl)
        title_box.addWidget(subtitle_lbl)
        header.addLayout(title_box, 1)

        layout.addLayout(header)

        # ── 1. Format d'Export ────────────────────────────────────────────────
        format_frame = QFrame()
        format_frame.setProperty("class", "section-box")
        fmt_layout = QVBoxLayout(format_frame)
        fmt_layout.setContentsMargins(12, 12, 12, 12)
        fmt_layout.setSpacing(8)

        lbl_fmt = QLabel("FORMAT DU PAQUET :")
        lbl_fmt.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {DesignTokens.TEXT_MUTED}; letter-spacing: 0.5px;")
        fmt_layout.addWidget(lbl_fmt)

        self.radio_bundle = QRadioButton("📦 Paquet Complet .afmodel (Templates + Styles + Démos + Métadonnées)")
        self.radio_bundle.setChecked(True)
        self.radio_bundle.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")

        self.radio_json = QRadioButton("📄 Fichier Léger .json (Format standard sérialisé)")
        self.radio_json.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;")

        self.format_group = QButtonGroup(self)
        self.format_group.addButton(self.radio_bundle)
        self.format_group.addButton(self.radio_json)
        self.radio_bundle.toggled.connect(self._on_format_toggled)

        fmt_layout.addWidget(self.radio_bundle)
        fmt_layout.addWidget(self.radio_json)
        layout.addWidget(format_frame)

        # ── 2. Métadonnées de Partage ──────────────────────────────────────────
        meta_frame = QFrame()
        meta_frame.setProperty("class", "section-box")
        meta_layout = QVBoxLayout(meta_frame)
        meta_layout.setContentsMargins(12, 12, 12, 12)
        meta_layout.setSpacing(10)

        lbl_meta = QLabel("MÉTADONNÉES DE PUBLICATION :")
        lbl_meta.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {DesignTokens.TEXT_MUTED}; letter-spacing: 0.5px;")
        meta_layout.addWidget(lbl_meta)

        # Auteur & Version
        row_author_ver = QHBoxLayout()
        row_author_ver.setSpacing(10)

        box_author = QVBoxLayout()
        lbl_a = QLabel("Auteur :")
        lbl_a.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY};")
        self.input_author = StyledLineEdit()
        self.input_author.setText("AnkiForge User")
        box_author.addWidget(lbl_a)
        box_author.addWidget(self.input_author)
        row_author_ver.addLayout(box_author, 2)

        box_ver = QVBoxLayout()
        lbl_v = QLabel("Version :")
        lbl_v.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY};")
        self.input_version = StyledLineEdit()
        self.input_version.setText("1.0.0")
        box_ver.addWidget(lbl_v)
        box_ver.addWidget(self.input_version)
        row_author_ver.addLayout(box_ver, 1)

        meta_layout.addLayout(row_author_ver)

        # Description
        lbl_d = QLabel("Description du style / Cas d'usage :")
        lbl_d.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY};")
        self.input_desc = StyledLineEdit()
        self.input_desc.setPlaceholderText("ex: Modèle avec badges contrastés et KaTeX pour concours...")
        meta_layout.addWidget(lbl_d)
        meta_layout.addWidget(self.input_desc)

        # Tags
        lbl_t = QLabel("Tags (séparés par des virgules) :")
        lbl_t.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY};")
        self.input_tags = StyledLineEdit()
        self.input_tags.setText("ankiforge, card-model")
        meta_layout.addWidget(lbl_t)
        meta_layout.addWidget(self.input_tags)

        # Cartes témoins
        self.chk_include_demos = QCheckBox("Inclure des cartes réelles anonymisées comme cartes témoins")
        self.chk_include_demos.setChecked(True)
        self.chk_include_demos.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; margin-top: 4px;")
        meta_layout.addWidget(self.chk_include_demos)

        layout.addWidget(meta_frame)

        # ── 3. Destination du Fichier ──────────────────────────────────────────
        dest_frame = QFrame()
        dest_frame.setProperty("class", "section-box")
        dest_layout = QVBoxLayout(dest_frame)
        dest_layout.setContentsMargins(12, 12, 12, 12)
        dest_layout.setSpacing(6)

        lbl_dest = QLabel("EMPLACEMENT DE SAUVEGARDE :")
        lbl_dest.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {DesignTokens.TEXT_MUTED}; letter-spacing: 0.5px;")
        dest_layout.addWidget(lbl_dest)

        dest_row = QHBoxLayout()
        self.dest_input = StyledLineEdit()
        default_filename = f"{self.model.name.replace(' ', '_').lower()}_model{BUNDLE_EXTENSION}"
        default_path = Path.home() / default_filename
        self.dest_input.setText(str(default_path))

        btn_browse = SecondaryButton("Parcourir...")
        btn_browse.clicked.connect(self._on_browse_destination)

        dest_row.addWidget(self.dest_input, 1)
        dest_row.addWidget(btn_browse)
        dest_layout.addLayout(dest_row)

        layout.addWidget(dest_frame)

        # ── Boutons d'Action ───────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.clicked.connect(self.reject)

        self.btn_export = PrimaryButton("Exporter le Modèle")
        self.btn_export.setIcon(load_phosphor_icon("ph.export", color="white"))
        self.btn_export.clicked.connect(self._on_confirm_export)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self.btn_export)
        layout.addLayout(btn_row)

    def _on_format_toggled(self) -> None:
        curr_path = Path(self.dest_input.text().strip())
        if self.radio_bundle.isChecked():
            self.dest_input.setText(str(curr_path.with_suffix(BUNDLE_EXTENSION)))
        else:
            self.dest_input.setText(str(curr_path.with_suffix(".json")))

    def _on_browse_destination(self) -> None:
        is_bundle = self.radio_bundle.isChecked()
        filter_str = "Paquet Modèle AnkiForge (*.afmodel)" if is_bundle else "Fichier Modèle JSON (*.json)"
        ext = BUNDLE_EXTENSION if is_bundle else ".json"
        default_name = f"{self.model.name.replace(' ', '_').lower()}_model{ext}"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Sélectionner l'emplacement d'exportation",
            str(Path.home() / default_name),
            filter_str,
        )
        if file_path:
            self.dest_input.setText(file_path)

    def _collect_demo_cards(self) -> list[dict[str, str]]:
        """Extrait 1 à 3 cartes réelles associées à ce modèle depuis la BDD SQLite."""
        if not self.chk_include_demos.isChecked():
            return []

        demo_cards: list[dict[str, str]] = []
        try:
            # Récupérer les notes associées
            notes = NoteModel.select().where(NoteModel.note_type == self.model).order_by(NoteModel.id.desc()).limit(3)
            for note in notes:
                active_v = NoteVersionModel.get_or_none(NoteVersionModel.note == note, NoteVersionModel.is_active)
                if active_v and active_v.content:
                    try:
                        content_dict = json.loads(active_v.content)
                        if isinstance(content_dict, dict):
                            demo_cards.append(content_dict)
                    except (json.JSONDecodeError, TypeError) as err:
                        logger.debug(f"Impossible de parser la version de démonstration : {err}")
        except Exception as e:
            logger.debug(f"Erreur lors de la collecte des cartes démos : {e}")

        if not demo_cards:
            # Cartes de démo génériques
            fields = ["Front", "Back"]
            try:
                if self.model.fields_schema:
                    fields = json.loads(self.model.fields_schema)
            except (json.JSONDecodeError, TypeError) as err:
                logger.debug(f"Utilisation des champs par défaut pour démo : {err}")
            demo_cards = [{f: f"Exemple pour {f}" for f in fields}]

        return demo_cards

    def _on_confirm_export(self) -> None:
        dest_str = self.dest_input.text().strip()
        if not dest_str:
            show_toast(self, "Veuillez choisir un chemin de destination.", is_error=True)
            return

        out_path = Path(dest_str)
        author = self.input_author.text().strip() or "AnkiForge User"
        version = self.input_version.text().strip() or "1.0.0"
        desc = self.input_desc.text().strip()
        tags = [t.strip() for t in self.input_tags.text().split(",") if t.strip()]
        demos = self._collect_demo_cards()

        try:
            if self.radio_bundle.isChecked():
                saved_path = CardModelIO.export_to_bundle(
                    model=self.model,
                    output_path=out_path,
                    author=author,
                    version=version,
                    description=desc,
                    tags=tags,
                    demo_cards=demos,
                )
            else:
                json_str = CardModelIO.export_to_json(
                    model=self.model,
                    author=author,
                    version=version,
                    description=desc,
                    tags=tags,
                    demo_cards=demos,
                )
                if out_path.suffix.lower() != ".json":
                    out_path = out_path.with_suffix(".json")
                out_path.write_text(json_str, encoding="utf-8")
                saved_path = out_path

            self.exported_file_path = saved_path
            show_toast(self, f"Modèle exporté avec succès dans '{saved_path.name}' !")
            self.accept()
        except Exception as e:
            show_toast(self, f"Échec de l'exportation : {str(e)}", is_error=True)
