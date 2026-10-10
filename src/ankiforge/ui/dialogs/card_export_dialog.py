"""
Dialogue d'exportation rapide des cartes en texte ou JSON (analyse rapide, contrôle qualité, scripts).
Permet de sélectionner la portée (sélection courante, filtre actif ou ensemble de la collection),
le format cible (JSON, JSONL, Texte, Markdown) et les options de structure.
"""

from __future__ import annotations

import logging
from pathlib import Path

import peewee
from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import CardModel, NoteModel
from ankiforge.services.cards.card_export_service import CardExportService
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.components.inputs import StyledLineEdit
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon

logger = logging.getLogger(__name__)


class CardExportDialog(QDialog):
    """
    Dialogue modal permettant d'exporter les cartes sélectionnées ou filtrées en texte brut ou JSON.
    """

    export_finished = Signal(str, int)  # file_path, card_count

    def __init__(
        self,
        selected_note_ids: list[int] | None = None,
        filtered_query: peewee.Query | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.export_service = CardExportService()
        self.selected_note_ids: list[int] = list(selected_note_ids or [])
        self.filtered_query: peewee.Query | None = filtered_query

        self.setWindowTitle(self.tr("Exporter en Texte ou JSON (Analyse rapide)"))
        self.resize(620, 560)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        # ── En-tête ──
        header = QHBoxLayout()
        header.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("file-text", color=DesignTokens.ACCENT_PRIMARY).pixmap(28, 28))
        icon_lbl.setStyleSheet("border: none; background: transparent;")

        title_vbox = QVBoxLayout()
        title_lbl = QLabel(self.tr("Exportation Rapide des Cartes (Texte / JSON)"))
        title_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 15, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none;")

        sub_lbl = QLabel(self.tr("Export léger pour audit qualité, détection de doublons, comptage ou scripts externes"))
        sub_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none;")

        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(sub_lbl)

        header.addWidget(icon_lbl)
        header.addLayout(title_vbox, 1)
        layout.addLayout(header)

        # ── 1. Cadre Portée (Scope) ──
        scope_frame = QFrame()
        scope_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        scope_layout = QVBoxLayout(scope_frame)
        scope_layout.setContentsMargins(8, 8, 8, 8)
        scope_layout.setSpacing(8)

        lbl_scope = QLabel(self.tr("PORTÉE DE L'EXPORT :"))
        lbl_scope.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        scope_layout.addWidget(lbl_scope)

        self.scope_group = QButtonGroup(self)

        sel_count = len(self.selected_note_ids)
        self.radio_selection = QRadioButton(tr("Sélection active (%1 cartes)", sel_count))
        self.radio_selection.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        self.radio_selection.setEnabled(sel_count > 0)
        self.scope_group.addButton(self.radio_selection)
        scope_layout.addWidget(self.radio_selection)

        # Filtre de la table si disponible
        filter_count = 0
        if self.filtered_query is not None:
            try:
                filter_count = self.filtered_query.count()
            except Exception as e:
                logger.debug("Erreur calcul count sur filtered_query: %s", e)
                filter_count = 0

        self.radio_filter = QRadioButton(tr("Filtre actif dans l'Éditeur (%1 cartes)", filter_count))
        self.radio_filter.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        self.radio_filter.setEnabled(filter_count > 0)
        self.scope_group.addButton(self.radio_filter)
        scope_layout.addWidget(self.radio_filter)

        total_collection_count = 0
        try:
            total_collection_count = NoteModel.select().count()
        except Exception as e:
            logger.debug("Erreur calcul count total notes: %s", e)

        self.radio_all = QRadioButton(tr("Toute la collection (%1 cartes)", total_collection_count))
        self.radio_all.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        self.scope_group.addButton(self.radio_all)
        scope_layout.addWidget(self.radio_all)

        # Sélection par défaut
        if sel_count > 0:
            self.radio_selection.setChecked(True)
        elif filter_count > 0:
            self.radio_filter.setChecked(True)
        else:
            self.radio_all.setChecked(True)

        layout.addWidget(scope_frame)

        # ── 2. Cadre Format & Structure ──
        format_frame = QFrame()
        format_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        format_layout = QVBoxLayout(format_frame)
        format_layout.setContentsMargins(8, 8, 8, 8)
        format_layout.setSpacing(8)

        lbl_format = QLabel(self.tr("FORMAT DE SORTIE :"))
        lbl_format.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        format_layout.addWidget(lbl_format)

        self.format_group = QButtonGroup(self)

        self.radio_json = QRadioButton(self.tr("JSON structuré (*.json — tableau d'objets, indenté et lisible)"))
        self.radio_json.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        self.radio_json.setChecked(True)
        self.format_group.addButton(self.radio_json)
        format_layout.addWidget(self.radio_json)

        self.radio_jsonl = QRadioButton(self.tr("JSON Lines (*.jsonl — une ligne JSON par carte, idéal scripts/stream)"))
        self.radio_jsonl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        self.format_group.addButton(self.radio_jsonl)
        format_layout.addWidget(self.radio_jsonl)

        self.radio_text = QRadioButton(self.tr("Texte lisible (*.txt — une carte par bloc avec en-têtes et délimiteurs)"))
        self.radio_text.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        self.format_group.addButton(self.radio_text)
        format_layout.addWidget(self.radio_text)

        self.radio_markdown = QRadioButton(self.tr("Markdown (*.md — titres, citations et blocs de champs)"))
        self.radio_markdown.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        self.format_group.addButton(self.radio_markdown)
        format_layout.addWidget(self.radio_markdown)

        # Options complémentaires
        self.chk_include_ids = QCheckBox(self.tr("Inclure les identifiants techniques (id, guid, chunk_id)"))
        self.chk_include_ids.setChecked(True)
        self.chk_include_ids.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; margin-top: 4px;")
        format_layout.addWidget(self.chk_include_ids)

        self.chk_single_file = QCheckBox(self.tr("Exporter dans un fichier unique (décocher pour un dossier avec 1 fichier par carte)"))
        self.chk_single_file.setChecked(True)
        self.chk_single_file.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        format_layout.addWidget(self.chk_single_file)

        self.radio_json.toggled.connect(self._on_format_changed)
        self.radio_jsonl.toggled.connect(self._on_format_changed)
        self.radio_text.toggled.connect(self._on_format_changed)
        self.radio_markdown.toggled.connect(self._on_format_changed)
        self.chk_single_file.toggled.connect(self._on_single_file_toggled)

        layout.addWidget(format_frame)

        # ── 3. Fichier de Destination ──
        dest_row = QHBoxLayout()
        dest_row.setSpacing(8)

        self.dest_input = StyledLineEdit()
        self._update_default_dest_filename()
        dest_row.addWidget(self.dest_input, 1)

        self.btn_browse_dest = SecondaryButton(self.tr("Choisir..."))
        self.btn_browse_dest.setIcon(load_phosphor_icon("folder-open", color=DesignTokens.TEXT_PRIMARY))
        self.btn_browse_dest.clicked.connect(self._browse_destination)
        dest_row.addWidget(self.btn_browse_dest)

        layout.addLayout(dest_row)

        # Progression & statut
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        layout.addWidget(self.lbl_status)

        layout.addStretch()

        # ── Boutons d'Action ──
        footer = QHBoxLayout()
        footer.setSpacing(10)

        btn_cancel = SecondaryButton(self.tr("Annuler"))
        btn_cancel.setAutoDefault(False)
        btn_cancel.clicked.connect(self.reject)
        footer.addWidget(btn_cancel)

        footer.addStretch()

        self.btn_export = PrimaryButton(self.tr("Exporter les cartes"))
        self.btn_export.setDefault(True)
        self.btn_export.setIcon(load_on_accent_icon("arrow-square-out"))
        self.btn_export.clicked.connect(self._start_export)
        footer.addWidget(self.btn_export)

        layout.addLayout(footer)

    def _get_active_extension(self) -> str:
        if self.radio_jsonl.isChecked():
            return ".jsonl"
        if self.radio_text.isChecked():
            return ".txt"
        if self.radio_markdown.isChecked():
            return ".md"
        return ".json"

    def _get_active_format_type(self) -> str:
        if self.radio_jsonl.isChecked():
            return "jsonl"
        if self.radio_text.isChecked():
            return "text"
        if self.radio_markdown.isChecked():
            return "markdown"
        return "json"

    def _update_default_dest_filename(self) -> None:
        ext = self._get_active_extension()
        default_path = (Path.home() / "Desktop" / f"export_cartes{ext}") if self.chk_single_file.isChecked() else (Path.home() / "Desktop" / "export_cartes")
        self.dest_input.setText(str(default_path))

    @Slot()
    def _on_format_changed(self) -> None:
        curr_text = self.dest_input.text().strip()
        if curr_text and self.chk_single_file.isChecked():
            p = Path(curr_text)
            new_ext = self._get_active_extension()
            self.dest_input.setText(str(p.with_suffix(new_ext)))

    @Slot(bool)
    def _on_single_file_toggled(self, is_single: bool) -> None:
        curr_text = self.dest_input.text().strip()
        if not curr_text:
            self._update_default_dest_filename()
            return

        p = Path(curr_text)
        if is_single:
            if not p.suffix:
                self.dest_input.setText(str(p.with_suffix(self._get_active_extension())))
        else:
            # Mode dossier
            if p.suffix:
                self.dest_input.setText(str(p.parent / p.stem))

    def _browse_destination(self) -> None:
        current_dest = self.dest_input.text().strip()
        if not self.chk_single_file.isChecked():
            # Sélection de dossier
            dir_path = QFileDialog.getExistingDirectory(
                self,
                self.tr("Sélectionner le dossier de destination"),
                current_dest or str(Path.home() / "Desktop"),
            )
            if dir_path:
                self.dest_input.setText(dir_path)
        else:
            # Sélection de fichier unique via getSaveFileName
            ext = self._get_active_extension()
            filter_map = {
                ".json": "Fichiers JSON (*.json);;Tous les fichiers (*.*)",
                ".jsonl": "JSON Lines (*.jsonl);;Tous les fichiers (*.*)",
                ".txt": "Fichiers Texte (*.txt);;Tous les fichiers (*.*)",
                ".md": "Fichiers Markdown (*.md);;Tous les fichiers (*.*)",
            }
            filter_str = filter_map.get(ext, "Tous les fichiers (*.*)")

            file_path, _ = QFileDialog.getSaveFileName(
                self,
                self.tr("Enregistrer l'export des cartes"),
                current_dest or str(Path.home() / "Desktop" / f"export_cartes{ext}"),
                filter_str,
            )
            if file_path:
                p = Path(file_path)
                if not p.suffix:
                    file_path = str(p.with_suffix(ext))
                self.dest_input.setText(file_path)

        self.raise_()
        self.activateWindow()

    def _resolve_notes_to_export(self) -> list[NoteModel]:
        """Résout la liste des instances NoteModel selon la portée choisie."""
        if self.radio_selection.isChecked() and self.selected_note_ids:
            return list(NoteModel.select().where(NoteModel.id.in_(self.selected_note_ids)))

        if self.radio_filter.isChecked() and self.filtered_query is not None:
            try:
                # Si filtered_query est sur CardModel, on extrait les notes distinctes
                model = getattr(self.filtered_query, "model", None)
                if model == CardModel:
                    note_ids = [c.note_id for c in self.filtered_query.select(CardModel.note).distinct()]
                    return list(NoteModel.select().where(NoteModel.id.in_(note_ids)))
                return list(self.filtered_query)
            except Exception as e:
                logger.warning("Erreur résolution notes depuis filtered_query: %s", e)

        # Repli : toute la collection
        return list(NoteModel.select())

    @Slot()
    def _start_export(self) -> None:
        dest_path = self.dest_input.text().strip()
        if not dest_path:
            QMessageBox.warning(self, self.tr("Destination manquante"), self.tr("Veuillez choisir un chemin de destination pour l'exportation."))
            return

        is_single = self.chk_single_file.isChecked()
        p = Path(dest_path)
        fmt = self._get_active_format_type()
        include_ids = self.chk_include_ids.isChecked()

        if is_single and not p.suffix:
            dest_path = str(p.with_suffix(self._get_active_extension()))
            self.dest_input.setText(dest_path)

        notes = self._resolve_notes_to_export()
        if not notes:
            QMessageBox.warning(self, self.tr("Aucune carte à exporter"), self.tr("Aucune carte ne correspond à la sélection actuelle."))
            return

        self.btn_export.setEnabled(False)
        self.progress_bar.show()
        self.lbl_status.setText(self.tr("Exportation en cours..."))

        try:
            if is_single:
                count = self.export_service.export_to_file(
                    notes=notes,
                    output_path=dest_path,
                    format_type=fmt,
                    include_ids=include_ids,
                )
            else:
                count = self.export_service.export_to_directory(
                    notes=notes,
                    output_dir=dest_path,
                    format_type=fmt,
                    include_ids=include_ids,
                )

            self.progress_bar.hide()
            self.btn_export.setEnabled(True)

            parent_window = self.parentWidget() or self
            show_toast(parent_window, tr("✅ %1 cartes exportées avec succès !", count), level="success")
            QMessageBox.information(
                self,
                self.tr("Exportation Réussie"),
                tr("Les cartes ont été exportées avec succès :\n\n%1\n\n• %2 carte(s) exportée(s)\n• Format : %3", dest_path, count, fmt.upper()),
            )
            self.export_finished.emit(dest_path, count)
            self.accept()

        except Exception as e:
            logger.error("Erreur durant l'exportation rapide des cartes : %s", e, exc_info=True)
            self.progress_bar.hide()
            self.btn_export.setEnabled(True)
            self.lbl_status.setText(self.tr("Erreur d'exportation."))
            QMessageBox.critical(self, self.tr("Erreur d'Exportation"), tr("Impossible d'exporter les cartes :\n%1", str(e)))
