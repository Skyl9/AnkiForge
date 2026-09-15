from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import FolderModel
from ankiforge.services.cards.album_service import AlbumService
from ankiforge.ui.components import (
    IconButton,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class AlbumImportDialog(QDialog):
    """
    Boîte de dialogue modale permettant d'importer un lot de clichés/scans photographiques
    pour créer un nouvel album de cours avec tri naturel ou chronologique EXIF.
    """

    album_created = Signal(int)  # document_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Créer un Album d'Images")
        self.setMinimumSize(540, 520)
        self.resize(580, 560)
        self._image_paths: list[str] = []
        self._album_service = AlbumService()

        self._setup_ui()
        self._load_folders()
        self._refresh_list_view()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # ── En-tête ──────────────────────────────────────────────────────────
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.images", color=DesignTokens.COLOR_PURPLE).pixmap(28, 28))
        header_layout.addWidget(icon_lbl)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        title_lbl = QLabel("Nouvel Album d'Images")
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 16px; font-weight: bold;")
        desc_lbl = QLabel("Rassemblez vos polycopiés, fiches manuscrites et cours photographiés page par page.")
        desc_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(desc_lbl)

        header_layout.addLayout(title_vbox)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # ── Formulaire de configuration ──────────────────────────────────────
        form_card = QFrame()
        form_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(14, 14, 14, 14)
        form_layout.setSpacing(12)

        # 1. Titre de l'album
        lbl_title = QLabel("Titre de l'album :")
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        form_layout.addWidget(lbl_title)

        self.input_title = StyledLineEdit()
        self.input_title.setPlaceholderText("ex: Biochimie - Chapitre 3 : Les Lipides")
        form_layout.addWidget(self.input_title)

        # 2. Dossier parent & Mode de tri
        row_opts = QHBoxLayout()
        row_opts.setSpacing(12)

        # Dossier
        vbox_folder = QVBoxLayout()
        vbox_folder.setSpacing(4)
        lbl_folder = QLabel("Dossier de classement :")
        lbl_folder.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        self.combo_folder = StyledComboBox()
        vbox_folder.addWidget(lbl_folder)
        vbox_folder.addWidget(self.combo_folder)
        row_opts.addLayout(vbox_folder, 1)

        # Mode de tri
        vbox_sort = QVBoxLayout()
        vbox_sort.setSpacing(4)
        lbl_sort = QLabel("Ordre de tri initial :")
        lbl_sort.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        self.combo_sort = StyledComboBox()
        self.combo_sort.addItem("Tri alphanumérique naturel (page_1, page_2...)", "natural")
        self.combo_sort.addItem("Date de prise de vue EXIF (appareil)", "exif")
        self.combo_sort.addItem("Ordre d'importation brut", "none")
        self.combo_sort.currentIndexChanged.connect(self._re_sort_paths)
        vbox_sort.addWidget(lbl_sort)
        vbox_sort.addWidget(self.combo_sort)
        row_opts.addLayout(vbox_sort, 1)

        form_layout.addLayout(row_opts)
        layout.addWidget(form_card)

        # ── Section Fichiers / Planche de sélection ───────────────────────────
        files_header = QHBoxLayout()
        self.lbl_files_count = QLabel("Images sélectionnées : 0")
        self.lbl_files_count.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        files_header.addWidget(self.lbl_files_count)
        files_header.addStretch()

        self.btn_browse = SecondaryButton("Parcourir les images...")
        self.btn_browse.setIcon(load_phosphor_icon("ph.folder-simple-plus", color=DesignTokens.TEXT_PRIMARY))
        self.btn_browse.setFixedHeight(28)
        self.btn_browse.setStyleSheet(f"font-size: 11px; padding: 3px 10px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_browse.clicked.connect(self._on_browse_images)
        files_header.addWidget(self.btn_browse)

        self.btn_clear = IconButton("ph.trash", tooltip="Vider la sélection", size=24)
        self.btn_clear.clicked.connect(self._on_clear_images)
        files_header.addWidget(self.btn_clear)

        layout.addLayout(files_header)

        # Liste des fichiers
        self.files_list = QListWidget()
        self.files_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                font-size: 11px;
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        layout.addWidget(self.files_list, 1)

        # ── Boutons d'action (Bas) ───────────────────────────────────────────
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        self.btn_cancel = SecondaryButton("Annuler")
        self.btn_cancel.clicked.connect(self.reject)
        buttons_layout.addWidget(self.btn_cancel)

        self.btn_create = PrimaryButton("Créer l'Album")
        self.btn_create.setIcon(load_phosphor_icon("ph.check", color="white"))
        self.btn_create.clicked.connect(self._on_create_album)
        buttons_layout.addWidget(self.btn_create)

        layout.addLayout(buttons_layout)

    def _load_folders(self) -> None:
        """Charge les dossiers existants dans la liste déroulante."""
        self.combo_folder.clear()
        self.combo_folder.addItem("📁 Racine (Aucun dossier)", None)
        try:
            folders = list(FolderModel.select().order_by(FolderModel.name))
            for f in folders:
                self.combo_folder.addItem(f"📁 {f.name}", f.id)
        except Exception as e:
            logger.warning("Erreur chargement dossiers: %s", e)

    def set_initial_files(self, paths: list[str]) -> None:
        """Permet de pré-remplir la sélection de fichiers (ex: glisser-déposer)."""
        self._image_paths = [p for p in paths if Path(p).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp")]
        if self._image_paths and not self.input_title.text().strip():
            # Titre suggéré basé sur le nom du dossier parent
            folder_name = Path(self._image_paths[0]).parent.name
            self.input_title.setText(f"Album {folder_name}" if folder_name else "Nouvel Album")
        self._re_sort_paths()

    @Slot()
    def _on_browse_images(self) -> None:
        """Ouvre un sélecteur de fichiers multiples."""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Sélectionner les photographies du cours",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if paths:
            self._image_paths.extend(paths)
            if not self.input_title.text().strip():
                folder_name = Path(paths[0]).parent.name
                self.input_title.setText(f"Album {folder_name}" if folder_name else "Nouvel Album")
            self._re_sort_paths()

    @Slot()
    def _on_clear_images(self) -> None:
        """Vide la liste des images."""
        self._image_paths.clear()
        self._refresh_list_view()

    @Slot()
    def _re_sort_paths(self) -> None:
        """Trie la liste selon le mode sélectionné."""
        if not self._image_paths:
            self._refresh_list_view()
            return

        sort_mode = self.combo_sort.currentData() or "natural"
        self._image_paths = [str(p) for p in self._album_service.sort_images(self._image_paths, mode=sort_mode)]
        self._refresh_list_view()

    def _refresh_list_view(self) -> None:
        """Met à jour l'affichage de la liste des fichiers."""
        self.files_list.clear()
        for idx, p in enumerate(self._image_paths, 1):
            name = Path(p).name
            item = QListWidgetItem(f"Page {idx:02d} : {name}")
            item.setIcon(load_phosphor_icon("ph.image", color=DesignTokens.TEXT_MUTED))
            self.files_list.addItem(item)

        total = len(self._image_paths)
        self.lbl_files_count.setText(f"Images sélectionnées : {total}")
        self.btn_create.setEnabled(total > 0)

    @Slot()
    def _on_create_album(self) -> None:
        """Valide et déclenche la création atomique de l'album en base."""
        title = self.input_title.text().strip()
        if not title:
            show_toast(self, "Veuillez renseigner un titre pour l'album.", is_error=True)
            self.input_title.setFocus()
            return

        if not self._image_paths:
            show_toast(self, "Veuillez sélectionner au moins une image.", is_error=True)
            return

        folder_id = self.combo_folder.currentData()
        sort_mode = self.combo_sort.currentData() or "natural"

        try:
            doc = self._album_service.create_album_from_images(
                title=title,
                image_paths=self._image_paths,
                folder_id=folder_id,
                sort_mode=sort_mode,
            )
            show_toast(self, f"Album '{doc.title}' créé avec succès ({len(self._image_paths)} pages).")
            self.album_created.emit(doc.id)
            self.accept()
        except Exception as e:
            logger.exception("Erreur lors de la création de l'album: %s", e)
            QMessageBox.critical(self, "Erreur de création", f"Impossible de créer l'album : {e}")
