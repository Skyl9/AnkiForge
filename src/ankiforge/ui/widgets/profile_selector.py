import re
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.profile_manager import ProfileManager
from ankiforge.ui.components.buttons import DangerButton, PrimaryButton, SecondaryButton
from ankiforge.ui.components.inputs import GlowLineEdit, StyledLineEdit
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.utils.icon_loader import load_logo_icon


class ProfileSelectorDialog(QDialog):
    """
    Dialogue de gestion et de bascule des espaces de travail / profils AnkiForge.
    Permet de sélectionner un profil existant, d'en créer un nouveau ou de supprimer un profil inutilisé.
    """

    def __init__(self, profiles: list[str], current_profile: str = "default", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gestion des Espaces de Travail - AnkiForge")
        self.setFixedSize(480, 560)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        self.pm = ProfileManager()
        self.current_profile = current_profile
        self.profiles: list[str] = profiles if profiles else [current_profile or "default"]
        self.selected_profile: str = current_profile or (self.profiles[0] if self.profiles else "default")

        self._setup_ui()
        self._populate_profiles()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # 1. En-tête avec Logo et description
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(14)

        logo_lbl = QLabel()
        logo_lbl.setPixmap(load_logo_icon(DesignTokens.ACCENT_PRIMARY).pixmap(40, 40))
        logo_lbl.setStyleSheet("border: none; background: transparent;")
        header_layout.addWidget(logo_lbl)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        title = QLabel("Espaces de Travail & Profils")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; border: none;")
        subtitle = QLabel("Chaque profil possède sa propre base SQLite et ses médias isolés.")
        subtitle.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED}; border: none;")
        subtitle.setWordWrap(True)
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        header_layout.addLayout(title_layout, 1)

        layout.addWidget(header_widget)

        # 2. Barre de recherche
        self.search_input = GlowLineEdit(placeholder="Filtrer les espaces de travail...")
        self.search_input.textChanged.connect(self._filter_profiles)
        layout.addWidget(self.search_input)

        # 3. Liste des profils
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 6px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 10px 12px;
                border-radius: {DesignTokens.RADIUS_SM}px;
                margin-bottom: 4px;
                font-size: 13px;
                font-weight: 500;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
                border: 1.5px solid {DesignTokens.ACCENT_PRIMARY};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        apply_shadow(self.list_widget, blur=10, offset_y=2, color="rgba(0,0,0,0.15)")
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self.list_widget, 1)

        # 4. Formulaire de création rapide & suppression
        actions_frame = QFrame()
        actions_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px;
            }}
        """)
        actions_layout = QVBoxLayout(actions_frame)
        actions_layout.setContentsMargins(8, 8, 8, 8)
        actions_layout.setSpacing(8)

        new_box = QHBoxLayout()
        new_box.setSpacing(8)
        self.new_profile_input = StyledLineEdit(icon_name="folder-plus", placeholder="Nom du nouvel espace (ex: droit, medecine)...")
        self.new_profile_input.returnPressed.connect(self._on_create_profile)
        self.btn_create = SecondaryButton("+ Créer")
        self.btn_create.setFixedHeight(34)
        self.btn_create.clicked.connect(self._on_create_profile)
        new_box.addWidget(self.new_profile_input, 1)
        new_box.addWidget(self.btn_create)
        actions_layout.addLayout(new_box)

        sub_actions_box = QHBoxLayout()
        sub_actions_box.setSpacing(8)
        self.delete_btn = DangerButton("Supprimer cet espace")
        self.delete_btn.setFixedHeight(30)
        self.delete_btn.clicked.connect(self._on_delete_profile)
        self.delete_btn.setEnabled(False)
        sub_actions_box.addStretch()
        sub_actions_box.addWidget(self.delete_btn)
        actions_layout.addLayout(sub_actions_box)

        layout.addWidget(actions_frame)

        # 5. Boutons de bascule / validation en bas
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        self.btn_cancel = SecondaryButton("Annuler")
        self.btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_cancel)

        self.btn_select = PrimaryButton("Basculer vers cet Espace")
        self.btn_select.clicked.connect(self.accept)
        bottom_layout.addWidget(self.btn_select, 1)

        layout.addLayout(bottom_layout)

    def _populate_profiles(self) -> None:
        """Remplit le widget de liste avec tous les profils disponibles."""
        self.list_widget.clear()
        target_row = 0

        for idx, p in enumerate(self.profiles):
            display_text = f"  📁  {p}"
            if p == self.current_profile:
                display_text = f"  ✨  {p}  [ ACTIF ]"

            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, p)
            if p == self.current_profile:
                item.setForeground(Qt.GlobalColor.green)

            self.list_widget.addItem(item)
            if p == self.selected_profile:
                target_row = idx

        if self.profiles:
            self.list_widget.setCurrentRow(target_row)

    def _filter_profiles(self, query: str) -> None:
        """Filtre les éléments de la liste selon la requête textuelle."""
        q = query.strip().lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            raw_name = item.data(Qt.ItemDataRole.UserRole) or ""
            item.setHidden(q != "" and q not in raw_name.lower())

    def _on_selection_changed(self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]) -> None:
        if not current:
            self.delete_btn.setEnabled(False)
            return

        raw_name = current.data(Qt.ItemDataRole.UserRole)
        if raw_name:
            self.selected_profile = raw_name
            # La suppression est interdite sur le profil actif courant et s'il ne reste qu'1 seul profil
            can_delete = (raw_name != self.current_profile) and (len(self.profiles) > 1)
            self.delete_btn.setEnabled(can_delete)

    def _on_create_profile(self) -> None:
        raw_name = self.new_profile_input.text().strip()
        if not raw_name:
            return

        # Sanitize profile name
        clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", raw_name)
        if clean_name in self.profiles:
            QMessageBox.warning(self, "Profil existant", f"L'espace de travail « {clean_name} » existe déjà.")
            return

        try:
            self.pm.create_profile(clean_name)
            self.profiles = self.pm.list_profiles()
            self.selected_profile = clean_name
            self.new_profile_input.clear()
            self._populate_profiles()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de créer le profil : {e}")

    def _on_delete_profile(self) -> None:
        if not self.selected_profile or self.selected_profile == self.current_profile:
            return

        res = QMessageBox.question(
            self,
            "Confirmation de suppression",
            f"Êtes-vous sûr de vouloir supprimer définitivement l'espace de travail « {self.selected_profile} » ?\nToutes les cartes, documents, personas et médias associés seront effacés.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            try:
                self.pm.delete_profile(self.selected_profile)
                self.profiles = self.pm.list_profiles()
                self.selected_profile = self.current_profile
                self._populate_profiles()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer le profil : {e}")

    def get_selected_profile(self) -> str:
        return self.selected_profile
