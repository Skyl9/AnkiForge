"""
Dialogue d'Importation de Paquets et Collections Anki (.apkg, .colpkg, .txt).
Gère l'analyse préliminaire, le déclenchement du Smart Merge si conflits de contenu,
et l'écriture finale en base avec rapport de synthèse.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFont
from PySide6.QtWidgets import (
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

from ankiforge.services.cards.import_manager import ImportAnalysisResult, ImportManager
from ankiforge.services.workers.import_cards_worker import ImportCardsWorker
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.components.deck_select_window import DeckSelectWindow
from ankiforge.ui.components.inputs import StyledLineEdit
from ankiforge.ui.dialogs.smart_merge_dialog import SmartMergeDialog
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ImportDropZone(QFrame):
    """Zone de glisser-déposer pour fichiers .apkg, .colpkg et .txt."""

    file_dropped = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setStyleSheet(f"""
            ImportDropZone {{
                background-color: {DesignTokens.BG_INPUT};
                border: 2px dashed {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 16px;
            }}
            ImportDropZone:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        self.icon_lbl = QLabel()
        self.icon_lbl.setPixmap(load_phosphor_icon("upload-simple", color=DesignTokens.ACCENT_PRIMARY).pixmap(32, 32))
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setStyleSheet("border: none; background: transparent;")

        self.lbl_title = QLabel("Glissez-déposez votre archive Anki ici")
        self.lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_sub = QLabel("Formats supportés : .apkg (Paquet), .colpkg (Collection), .txt (Export texte)")
        self.lbl_sub.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        self.lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.icon_lbl)
        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_sub)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = url.toLocalFile()
                if p.lower().endswith((".apkg", ".colpkg", ".txt")):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = url.toLocalFile()
                if p.lower().endswith((".apkg", ".colpkg", ".txt")):
                    self.file_dropped.emit(p)
                    event.acceptProposedAction()
                    return


class ImportDialog(QDialog):
    """
    Dialogue complet d'importation avec analyse, détection de conflits et confirmation.
    """

    import_finished = Signal(dict)

    def __init__(self, initial_path: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.import_manager = ImportManager()
        self.worker: ImportCardsWorker | None = None
        self.analysis_result: ImportAnalysisResult | None = None
        self._deck_modal: DeckSelectWindow | None = None

        self.setWindowTitle("Importer un Paquet ou une Collection Anki")
        self.resize(640, 520)

        self._setup_ui()

        if initial_path:
            self.path_input.setText(initial_path)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        # Header
        header = QHBoxLayout()
        header.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("download-simple", color=DesignTokens.ACCENT_PRIMARY).pixmap(26, 26))
        icon_lbl.setStyleSheet("border: none; background: transparent;")

        title_vbox = QVBoxLayout()
        title_lbl = QLabel("Importation & Synchronisation Anki")
        title_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 15, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none;")

        sub_lbl = QLabel("Analyse automatique et arbitrage des conflits (Règle 11)")
        sub_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none;")

        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(sub_lbl)

        header.addWidget(icon_lbl)
        header.addLayout(title_vbox, 1)
        layout.addLayout(header)

        # Drop Zone
        self.drop_zone = ImportDropZone(self)
        self.drop_zone.file_dropped.connect(self._on_file_selected)
        layout.addWidget(self.drop_zone)

        # File Chooser Row
        file_row = QHBoxLayout()
        file_row.setSpacing(8)

        self.path_input = StyledLineEdit()
        self.path_input.setPlaceholderText("Chemin du fichier .apkg, .colpkg ou .txt...")
        file_row.addWidget(self.path_input, 1)

        self.btn_browse = SecondaryButton("Parcourir...")
        self.btn_browse.setIcon(load_phosphor_icon("folder-open", color=DesignTokens.TEXT_PRIMARY))
        self.btn_browse.clicked.connect(self._browse_file)
        file_row.addWidget(self.btn_browse)

        layout.addLayout(file_row)

        # Options de destination
        options_frame = QFrame()
        options_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 8px;
            }}
        """)
        options_layout = QVBoxLayout(options_frame)
        options_layout.setContentsMargins(10, 10, 10, 10)
        options_layout.setSpacing(8)

        lbl_dest = QLabel("DESTINATION :")
        lbl_dest.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        options_layout.addWidget(lbl_dest)

        self.radio_keep_tree = QRadioButton("Conserver la hiérarchie d'origine des paquets")
        self.radio_keep_tree.setChecked(True)
        self.radio_keep_tree.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        options_layout.addWidget(self.radio_keep_tree)

        merge_row = QHBoxLayout()
        self.radio_merge_deck = QRadioButton("Fusionner dans le paquet :")
        self.radio_merge_deck.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        merge_row.addWidget(self.radio_merge_deck)

        self.target_deck_id: int | None = None
        self.btn_select_target_deck = SecondaryButton("📁 Choisir un paquet cible ▾")
        self.btn_select_target_deck.clicked.connect(self._open_target_deck_select_modal)
        merge_row.addWidget(self.btn_select_target_deck, 1)
        options_layout.addLayout(merge_row)

        layout.addWidget(options_frame)

        # Barre de progression et statut
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

        self.btn_import = PrimaryButton("Lancer l'Importation")
        self.btn_import.setIcon(load_phosphor_icon("arrow-circle-down", color="white"))
        self.btn_import.clicked.connect(self._start_import_analysis)
        footer.addWidget(self.btn_import)

        layout.addLayout(footer)

    @Slot()
    def _open_target_deck_select_modal(self) -> None:
        try:
            if hasattr(self, "_deck_modal") and self._deck_modal and self._deck_modal.isVisible():
                self._deck_modal.raise_()
                self._deck_modal.activateWindow()
                return
        except RuntimeError:
            self._deck_modal = None

        from ankiforge.ui.components.deck_select_window import DeckSelectWindow

        self._deck_modal = DeckSelectWindow(title="Sélectionner le paquet cible", parent=self)
        self._deck_modal.deck_selected.connect(self._on_target_deck_selected_from_modal)
        self._deck_modal.show()
        self._deck_modal.raise_()
        self._deck_modal.activateWindow()

    @Slot(int, str)
    def _on_target_deck_selected_from_modal(self, deck_id: int, deck_name: str) -> None:
        if deck_id == -1:
            self.target_deck_id = None
            self.btn_select_target_deck.setText("📁 Choisir un paquet cible ▾")
        else:
            self.target_deck_id = deck_id
            self.btn_select_target_deck.setText(f"📁 {deck_name} ▾")
            self.radio_merge_deck.setChecked(True)

    def _browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner un fichier Anki",
            "",
            "Archives Anki (*.apkg *.colpkg *.txt);;Tous les fichiers (*.*)",
        )
        if file_path:
            self._on_file_selected(file_path)

    def _on_file_selected(self, path: str) -> None:
        self.path_input.setText(path)

    def _start_import_analysis(self) -> None:
        file_path = self.path_input.text().strip()
        if not file_path or not Path(file_path).exists():
            QMessageBox.warning(self, "Fichier manquant", "Veuillez sélectionner un fichier .apkg, .colpkg ou .txt valide.")
            return

        self.btn_import.setEnabled(False)
        self.progress_bar.show()
        self.lbl_status.setText("Analyse du fichier en cours...")

        self.worker = ImportCardsWorker(path=file_path, mode="analyze", import_manager=self.import_manager, parent=self)
        self.worker.progress.connect(self.lbl_status.setText)
        self.worker.analysis_ready.connect(self._on_analysis_ready)
        self.worker.error_signal.connect(self._on_import_error)
        self.worker.start()

    def _on_analysis_ready(self, analysis: ImportAnalysisResult) -> None:
        self.analysis_result = analysis
        self.progress_bar.hide()

        conflicts_count = len(analysis.conflicts)
        new_count = len(analysis.new_notes)
        silent_count = len(analysis.silent_updates)

        logger.info(
            "Analyse terminée : %d nouvelles, %d silencieuses, %d conflits",
            new_count,
            silent_count,
            conflicts_count,
        )

        resolutions = {}

        # Si des conflits de contenu existent selon la règle 11 -> Ouverture du Smart Merge
        if conflicts_count > 0:
            merge_dialog = SmartMergeDialog(analysis.conflicts, parent=self)
            if merge_dialog.exec() == QDialog.DialogCode.Accepted:
                resolutions = merge_dialog.get_resolutions()
            else:
                self.btn_import.setEnabled(True)
                self.lbl_status.setText("Importation annulée par l'utilisateur.")
                return

        # Commit final
        target_id = self.target_deck_id if self.radio_merge_deck.isChecked() else None

        self.lbl_status.setText("Écriture en base de données...")
        self.progress_bar.show()

        try:
            summary = self.import_manager.commit_import(
                analysis=analysis,
                conflict_resolutions=resolutions,
                target_deck_id=target_id,
                progress_callback=self.lbl_status.setText,
            )
            self.progress_bar.hide()
            self.btn_import.setEnabled(True)

            msg = (
                f"Importation terminée avec succès !\n\n"
                f"• {summary['created']} nouvelle(s) carte(s) créée(s)\n"
                f"• {summary['updated']} mise(s) à jour silencieuse(s)\n"
                f"• {summary['merged']} conflit(s) de contenu fusionné(s)\n"
                f"• {summary['media']} fichier(s) média indexé(s)"
            )
            QMessageBox.information(self, "Importation Réussie", msg)
            show_toast(self, "Importation Anki terminée !")
            self.import_finished.emit(summary)
            self.accept()

        except Exception as e:
            self._on_import_error(str(e))

    def _on_import_error(self, err_msg: str) -> None:
        self.progress_bar.hide()
        self.btn_import.setEnabled(True)
        self.lbl_status.setText("Erreur d'importation.")
        QMessageBox.critical(self, "Erreur d'Importation", f"Impossible d'importer l'archive :\n{err_msg}")
