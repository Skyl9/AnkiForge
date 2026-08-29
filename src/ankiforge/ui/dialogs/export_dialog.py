"""
Dialogue d'Exportation Sélective de Paquets et Collections Anki (.apkg, .colpkg).
Permet de choisir le paquet racine via DeckSelectWindow, filtrer par tags, sélectionner le statut et inclure les médias.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
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

from ankiforge.database.models import DeckModel
from ankiforge.services.cards.export_manager import ExportManager
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.components.deck_select_window import DeckSelectWindow
from ankiforge.ui.components.inputs import StyledLineEdit
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ExportDialog(QDialog):
    """
    Dialogue de configuration et d'exportation vers .apkg ou .colpkg s'appuyant sur DeckSelectWindow.
    """

    export_finished = Signal(str, int)  # file_path, count

    def __init__(self, default_deck_id: int | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.export_manager = ExportManager()
        self.selected_tags: list[str] = []
        self.selected_deck_id: int | None = default_deck_id
        self.selected_deck_name: str = "Tous les paquets (Collection entière)"
        self._deck_modal: DeckSelectWindow | None = None

        self.setWindowTitle("Exporter un Paquet Anki")
        self.resize(600, 520)

        self._setup_ui(default_deck_id)

    def _setup_ui(self, default_deck_id: int | None = None) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        # Header
        header = QHBoxLayout()
        header.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("upload-simple", color=DesignTokens.ACCENT_PRIMARY).pixmap(26, 26))
        icon_lbl.setStyleSheet("border: none; background: transparent;")

        title_vbox = QVBoxLayout()
        title_lbl = QLabel("Exportation Anki (.apkg / .colpkg)")
        title_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 15, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none;")

        sub_lbl = QLabel("Packaging zstandard avec inclusion automatique des médias")
        sub_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none;")

        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(sub_lbl)

        header.addWidget(icon_lbl)
        header.addLayout(title_vbox, 1)
        layout.addLayout(header)

        # 1. Sélection du Paquet via DeckSelectWindow
        deck_frame = QFrame()
        deck_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        deck_layout = QVBoxLayout(deck_frame)
        deck_layout.setContentsMargins(8, 8, 8, 8)
        deck_layout.setSpacing(6)

        lbl_deck = QLabel("PAQUET À EXPORTER :")
        lbl_deck.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        deck_layout.addWidget(lbl_deck)

        deck_picker_row = QHBoxLayout()
        deck_picker_row.setSpacing(8)

        # Nom du paquet initial
        if default_deck_id:
            d = DeckModel.get_or_none(DeckModel.id == default_deck_id)
            if d:
                self.selected_deck_name = d.name

        self.btn_select_deck = SecondaryButton(f"📁 {self.selected_deck_name} ▾")
        self.btn_select_deck.clicked.connect(self._open_deck_select_modal)
        deck_picker_row.addWidget(self.btn_select_deck, 1)

        deck_layout.addLayout(deck_picker_row)
        layout.addWidget(deck_frame)

        # 2. Portée et Filtres
        filters_frame = QFrame()
        filters_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        filters_layout = QVBoxLayout(filters_frame)
        filters_layout.setContentsMargins(8, 8, 8, 8)
        filters_layout.setSpacing(8)

        lbl_scope = QLabel("PORTÉE DE L'EXPORT :")
        lbl_scope.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        filters_layout.addWidget(lbl_scope)

        self.radio_all = QRadioButton("Toutes les cartes du paquet")
        self.radio_all.setChecked(True)
        self.radio_all.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")

        self.radio_new_only = QRadioButton("Nouvelles cartes uniquement (statut 'new')")
        self.radio_new_only.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")

        filters_layout.addWidget(self.radio_all)
        filters_layout.addWidget(self.radio_new_only)

        # Options Médias
        self.chk_include_media = QCheckBox("Inclure tous les médias associés (images et sons)")
        self.chk_include_media.setChecked(True)
        self.chk_include_media.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: bold;")
        filters_layout.addWidget(self.chk_include_media)

        layout.addWidget(filters_frame)

        # 3. Fichier de Destination
        dest_row = QHBoxLayout()
        dest_row.setSpacing(8)

        self.dest_input = StyledLineEdit()
        self._update_default_dest_filename()
        dest_row.addWidget(self.dest_input, 1)

        btn_browse_dest = SecondaryButton("Choisir...")
        btn_browse_dest.setIcon(load_phosphor_icon("folder-open", color=DesignTokens.TEXT_PRIMARY))
        btn_browse_dest.clicked.connect(self._browse_destination)
        dest_row.addWidget(btn_browse_dest)

        layout.addLayout(dest_row)

        # Progress bar
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

        # Footer Buttons
        footer = QHBoxLayout()
        footer.setSpacing(10)

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        footer.addWidget(btn_cancel)

        footer.addStretch()

        self.btn_export = PrimaryButton("Exporter le Paquet")
        self.btn_export.setIcon(load_phosphor_icon("arrow-square-out", color="white"))
        self.btn_export.clicked.connect(self._start_export)
        footer.addWidget(self.btn_export)

        layout.addLayout(footer)

    def _update_default_dest_filename(self) -> None:
        if self.selected_deck_id is None:
            filename = "export_collection.apkg"
        else:
            clean_name = self.selected_deck_name.replace("::", "_").replace(" ", "_")
            filename = f"export_{clean_name}.apkg"
        self.dest_input.setText(str(Path.home() / "Desktop" / filename))

    @Slot()
    def _open_deck_select_modal(self) -> None:
        try:
            if self._deck_modal and self._deck_modal.isVisible():
                self._deck_modal.raise_()
                self._deck_modal.activateWindow()
                return
        except RuntimeError:
            self._deck_modal = None

        self._deck_modal = DeckSelectWindow(title="Sélectionner un paquet à exporter", parent=self)
        self._deck_modal.deck_selected.connect(self._on_deck_selected_from_modal)
        self._deck_modal.show()
        self._deck_modal.raise_()
        self._deck_modal.activateWindow()

    @Slot(int, str)
    def _on_deck_selected_from_modal(self, deck_id: int, deck_name: str) -> None:
        if deck_id == -1:
            self.selected_deck_id = None
            self.selected_deck_name = "Tous les paquets (Collection entière)"
        else:
            self.selected_deck_id = deck_id
            self.selected_deck_name = deck_name

        self.btn_select_deck.setText(f"📁 {self.selected_deck_name} ▾")
        self._update_default_dest_filename()

    def _browse_destination(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Enregistrer le paquet Anki",
            self.dest_input.text(),
            "Archives Anki (*.apkg);;Collections Anki (*.colpkg);;Tous les fichiers (*.*)",
        )
        if file_path:
            self.dest_input.setText(file_path)

    def _start_export(self) -> None:
        dest_path = self.dest_input.text().strip()
        if not dest_path:
            QMessageBox.warning(self, "Destination manquante", "Veuillez choisir un chemin de destination pour l'exportation.")
            return

        status_filter = "new" if self.radio_new_only.isChecked() else "all"
        include_media = self.chk_include_media.isChecked()

        self.btn_export.setEnabled(False)
        self.progress_bar.show()
        self.lbl_status.setText("Génération du paquet Anki en cours...")

        try:
            count = self.export_manager.export_package(
                output_path=dest_path,
                deck_id=self.selected_deck_id,
                tags=self.selected_tags if self.selected_tags else None,
                status_filter=status_filter,
                include_media=include_media,
                progress_callback=self.lbl_status.setText,
            )
            self.progress_bar.hide()
            self.btn_export.setEnabled(True)

            show_toast(self, f"{count} cartes exportées avec succès !")
            QMessageBox.information(
                self,
                "Exportation Réussie",
                f"Le fichier a été exporté avec succès :\n\n{dest_path}\n\n• {count} carte(s) empaquetée(s)\n• Prêt à être importé dans Anki Desktop !",
            )
            self.export_finished.emit(dest_path, count)
            self.accept()

        except Exception as e:
            self.progress_bar.hide()
            self.btn_export.setEnabled(True)
            self.lbl_status.setText("Erreur d'exportation.")
            QMessageBox.critical(self, "Erreur d'Exportation", f"Impossible d'exporter le paquet :\n{str(e)}")
