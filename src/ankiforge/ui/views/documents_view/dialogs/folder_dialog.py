from __future__ import annotations

import logging

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import FolderModel
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.ui.components import (
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.hierarchy import join_hierarchy
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon

logger = logging.getLogger(__name__)


class FolderCreateDialog(QDialog):
    """
    Boîte de dialogue permettant de créer un nouveau dossier ou sous-dossier de documents.
    Permet de sélectionner le dossier parent et gère la hiérarchie '::'.
    """

    def __init__(self, parent_folder_id: int | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nouveau dossier")
        self.setMinimumWidth(440)
        self.resize(480, 320)
        self._parent_folder_id = parent_folder_id
        self._created_folder: FolderModel | None = None

        self._setup_ui()
        self._load_parents()
        self._update_preview()

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

        # En-tête
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.folder-plus", color=DesignTokens.COLOR_BLUE).pixmap(26, 26))
        header_layout.addWidget(icon_lbl)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        title_lbl = QLabel("Créer un dossier de documents")
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 15px; font-weight: bold;")
        desc_lbl = QLabel("Organisez vos cours et documents en dossiers et sous-dossiers.")
        desc_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(desc_lbl)

        header_layout.addLayout(title_vbox)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Formulaire
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

        # Sélecteur du parent
        lbl_parent = QLabel("Dossier parent :")
        lbl_parent.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        form_layout.addWidget(lbl_parent)

        self.combo_parent = StyledComboBox()
        self.combo_parent.currentIndexChanged.connect(self._on_inputs_changed)
        form_layout.addWidget(self.combo_parent)

        # Nom du dossier / chemin
        lbl_name = QLabel("Nom du sous-dossier :")
        lbl_name.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        form_layout.addWidget(lbl_name)

        self.input_name = StyledLineEdit(icon_name="ph.folder", placeholder="ex: Semestre 1 ou UE1::Biochimie")
        self.input_name.textChanged.connect(self._on_inputs_changed)
        self.input_name.returnPressed.connect(self._on_create)
        form_layout.addWidget(self.input_name)

        # Aperçu dynamique du chemin
        self.lbl_preview = QLabel()
        self.lbl_preview.setWordWrap(True)
        self.lbl_preview.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; padding: 4px 0px;")
        form_layout.addWidget(self.lbl_preview)

        layout.addWidget(form_card)

        # Astuce
        hint_lbl = QLabel("💡 Astuce : Utilisez '::' pour créer plusieurs niveaux d'arborescence d'un coup.")
        hint_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-style: italic;")
        layout.addWidget(hint_lbl)

        layout.addStretch()

        # Boutons d'action
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = SecondaryButton("Annuler")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_create = PrimaryButton("Créer")
        self.btn_create.setIcon(load_on_accent_icon("ph.check"))
        self.btn_create.clicked.connect(self._on_create)
        self.btn_create.setEnabled(False)
        btn_layout.addWidget(self.btn_create)

        layout.addLayout(btn_layout)

    def _load_parents(self) -> None:
        """Remplit la liste déroulante des dossiers parents."""
        self.combo_parent.blockSignals(True)
        self.combo_parent.clear()
        self.combo_parent.addItem("📁 Racine (aucun parent)", None)

        try:
            folders = list(FolderModel.select().order_by(FolderModel.name))
            selected_idx = 0
            for i, f in enumerate(folders, start=1):
                self.combo_parent.addItem(f"📁 {f.name}", f.id)
                if self._parent_folder_id is not None and f.id == self._parent_folder_id:
                    selected_idx = i
            self.combo_parent.setCurrentIndex(selected_idx)
        except Exception as e:
            logger.warning("Erreur chargement dossiers parents: %s", e)
        finally:
            self.combo_parent.blockSignals(False)

    @Slot()
    def _on_inputs_changed(self) -> None:
        self._update_preview()
        has_text = bool(self.input_name.text().strip())
        self.btn_create.setEnabled(has_text)

    def get_full_path(self) -> str:
        """Calcule le chemin hiérarchique complet du dossier à créer."""
        typed_name = self.input_name.text().strip()
        if not typed_name:
            return ""

        # Obtenir le nom du parent si sélectionné
        parent_id = self.combo_parent.currentData()
        if parent_id is not None:
            folder = FolderModel.get_or_none(FolderModel.id == parent_id)
            if folder:
                return join_hierarchy((folder.name, typed_name))

        return typed_name

    def _update_preview(self) -> None:
        path = self.get_full_path()
        if path:
            self.lbl_preview.setText(f"Chemin complet : <b style='color: {DesignTokens.TEXT_PRIMARY};'>{path}</b>")
        else:
            self.lbl_preview.setText("Chemin complet : <i>(Saisissez un nom)</i>")

    @Slot()
    def _on_create(self) -> None:
        path = self.get_full_path()
        if not path:
            return

        try:
            repo = DocumentRepository()
            self._created_folder = repo.ensure_folder_hierarchy(path)
            self.accept()
        except Exception as e:
            logger.error("Erreur création dossier '%s': %s", path, e)
            show_toast(self, f"Erreur lors de la création : {e}", is_error=True)

    def get_created_folder(self) -> FolderModel | None:
        return self._created_folder
