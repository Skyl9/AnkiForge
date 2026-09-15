"""
Boîte de dialogue modale pour le Masquage d'Images Intelligent (Image Occlusion IA).
Permet de charger une image depuis le disque, le presse-papier ou une vue,
et d'interagir avec l'éditeur visuel d'occlusion.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteModel
from ankiforge.ui.components import IconButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.image_occlusion_editor import ImageOcclusionEditor
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ImageOcclusionDialog(QDialog):
    """Dialogue modal plein écran pour l'édition et la création de cartes Image Occlusion."""

    notes_generated = Signal(list)  # list[NoteModel]

    def __init__(
        self,
        image_path: str | Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Masquage d'Images Intelligent & Vision (Image Occlusion)")
        self.resize(1100, 750)
        self.setMinimumSize(850, 600)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        self.created_notes: list[NoteModel] = []
        self._temp_files: list[Path] = []

        self._setup_ui(image_path)

    def _setup_ui(self, initial_image: str | Path | None) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── En-tête supérieur du dialogue ────────────────────────────────────
        header_bar = QWidget()
        header_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.bounding-box", color=DesignTokens.ACCENT_PRIMARY).pixmap(22, 22))
        header_layout.addWidget(icon_lbl)

        title_lbl = QLabel("Masquage d'Images Intelligent (Image Occlusion IA)")
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 15px;")
        header_layout.addWidget(title_lbl)

        header_layout.addStretch()

        # Bouton Ouvrir une autre image
        btn_open = SecondaryButton("Changer d'image...")
        btn_open.setIcon(load_phosphor_icon("ph.folder-open", color=DesignTokens.TEXT_PRIMARY))
        btn_open.clicked.connect(self._browse_image)
        header_layout.addWidget(btn_open)

        # Bouton Coller depuis le presse-papier
        btn_paste = SecondaryButton("Coller l'image")
        btn_paste.setIcon(load_phosphor_icon("ph.clipboard", color=DesignTokens.TEXT_PRIMARY))
        btn_paste.clicked.connect(self._paste_image_from_clipboard)
        header_layout.addWidget(btn_paste)

        # Bouton Fermer
        btn_close = IconButton("ph.x", tooltip="Fermer le dialogue", size=24)
        btn_close.clicked.connect(self.accept)
        header_layout.addWidget(btn_close)

        layout.addWidget(header_bar)

        # ── Éditeur d'occlusion ──────────────────────────────────────────────
        self.editor = ImageOcclusionEditor(image_path=initial_image, parent=self)
        self.editor.notes_created.connect(self._on_notes_created)
        layout.addWidget(self.editor)

    def _browse_image(self) -> None:
        """Ouvre un sélecteur de fichier pour charger une nouvelle image."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner un schéma ou diagramme",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.svg)",
        )
        if file_path:
            self.editor.load_image(file_path)

    def _paste_image_from_clipboard(self) -> None:
        """Récupère et charge une image depuis le presse-papier système."""
        clipboard = QGuiApplication.clipboard()
        image = clipboard.image()
        if image.isNull():
            show_toast(self, "Aucune image trouvée dans le presse-papier.", is_error=False)
            return

        # Sauvegarde temporaire pour traitement
        temp_dir = Path(tempfile.gettempdir())
        temp_path = temp_dir / f"pasted_occlusion_{len(self._temp_files)}.png"
        image.save(str(temp_path), "PNG")
        self._temp_files.append(temp_path)

        self.editor.load_image(temp_path)
        show_toast(self, "Image collée depuis le presse-papier avec succès !", is_error=False)

    def _on_notes_created(self, notes: list[NoteModel]) -> None:
        """Gère la confirmation de génération des cartes."""
        self.created_notes.extend(notes)
        self.notes_generated.emit(notes)

    def get_created_notes(self) -> list[NoteModel]:
        """Retourne la liste des notes créées lors de cette session."""
        return self.created_notes

    def closeEvent(self, event: Any) -> None:
        """Nettoie les éventuels fichiers temporaires collés."""
        for p in self._temp_files:
            try:
                if p.exists():
                    p.unlink()
            except OSError:
                pass
        super().closeEvent(event)
