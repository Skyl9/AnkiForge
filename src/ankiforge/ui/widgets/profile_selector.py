"""
Dialogue de gestion et de bascule des espaces de travail / profils AnkiForge.
Architecture moderne conforme aux DesignTokens et au référentiel DESIGN.md.
"""

import logging
import re
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_logo_icon, load_phosphor_icon

logger = logging.getLogger(__name__)


class ProfileItemWidget(QFrame):
    """Tuile personnalisée moderne représentant un profil / espace de travail."""

    def __init__(
        self,
        name: str,
        is_current: bool = False,
        is_selected: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.name = name
        self.is_current = is_current
        self.is_selected = is_selected
        self.setObjectName("ProfileItemCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(58)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # 1. Icône Phosphor
        self.icon_lbl = QLabel()
        icon_name = "cards" if is_current else "folder"
        icon_color = DesignTokens.ACCENT_PRIMARY if is_current else DesignTokens.TEXT_SECONDARY
        self.icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(22, 22))
        self.icon_lbl.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.icon_lbl)

        # 2. Textes (Nom + Chemin relatif)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self.name_lbl = QLabel(name)
        self.name_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.DemiBold))
        self.name_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

        path_hint = f"~/.ankiforge/profiles/{name}"
        self.path_lbl = QLabel(path_hint)
        self.path_lbl.setFont(QFont(DesignTokens.FONT_CODE, 9))
        self.path_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")

        text_layout.addWidget(self.name_lbl)
        text_layout.addWidget(self.path_lbl)
        layout.addLayout(text_layout, 1)

        # 3. Badge Actif
        if is_current:
            self.active_badge = QLabel("ACTIF")
            self.active_badge.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
            self.active_badge.setStyleSheet(f"""
                QLabel {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    color: {DesignTokens.COLOR_GREEN};
                    border: 1px solid {DesignTokens.COLOR_GREEN};
                    border-radius: 9px;
                    padding: 2px 8px;
                }}
            """)
            layout.addWidget(self.active_badge)
        else:
            self.active_badge = None

        self._update_style()

    def set_selected_state(self, selected: bool) -> None:
        self.is_selected = selected
        self._update_style()

    def _update_style(self) -> None:
        if self.is_selected:
            self.setStyleSheet(f"""
                QFrame#ProfileItemCard {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    border: 1.5px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame#ProfileItemCard {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                }}
                QFrame#ProfileItemCard:hover {{
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                    background-color: {DesignTokens.BG_HOVER};
                }}
            """)

    def refresh_theme(self, profile: Any) -> None:
        icon_name = "cards" if self.is_current else "folder"
        icon_color = profile.accent_primary if self.is_current else profile.text_secondary
        self.icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(22, 22))
        self._update_style()


class ProfileSelectorDialog(QDialog):
    """
    Dialogue de gestion et de bascule des espaces de travail / profils AnkiForge.
    Permet de sélectionner un profil existant, d'en créer un nouveau ou de supprimer un profil inutilisé.
    """

    def __init__(self, profiles: list[str], current_profile: str = "default", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Espaces de Travail & Profils — AnkiForge")
        self.setFixedSize(560, 630)
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
        self._card_widgets: list[ProfileItemWidget] = []

        self._setup_ui()
        self._populate_profiles()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        # ── 1. En-tête avec Logo et Description ──
        header_card = QFrame()
        header_card.setObjectName("ProfileHeaderCard")
        header_card.setStyleSheet(f"""
            QFrame#ProfileHeaderCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 12px;
            }}
        """)
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(14)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.logo_lbl = QLabel()
        self.logo_lbl.setPixmap(load_logo_icon(DesignTokens.ACCENT_PRIMARY).pixmap(38, 38))
        self.logo_lbl.setStyleSheet("border: none; background: transparent;")
        header_layout.addWidget(self.logo_lbl)

        title_layout = QVBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)

        self.title_lbl = QLabel("Espaces de Travail & Profils")
        self.title_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 13, QFont.Weight.Bold))
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

        self.subtitle_lbl = QLabel("Chaque profil possède sa propre base SQLite et ses médias isolés.")
        self.subtitle_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        self.subtitle_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        self.subtitle_lbl.setWordWrap(True)

        title_layout.addWidget(self.title_lbl)
        title_layout.addWidget(self.subtitle_lbl)
        header_layout.addLayout(title_layout, 1)

        # Badge total de profils
        self.count_badge = QLabel(f"{len(self.profiles)} profil{'s' if len(self.profiles) > 1 else ''}")
        self.count_badge.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        self.count_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_SECONDARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 9px;
                padding: 2px 8px;
            }}
        """)
        header_layout.addWidget(self.count_badge)

        layout.addWidget(header_card)

        # ── 2. Barre de recherche ──
        self.search_input = GlowLineEdit(placeholder="Filtrer les espaces de travail...")
        self.search_input.setFixedHeight(36)
        self.search_input.textChanged.connect(self._filter_profiles)
        layout.addWidget(self.search_input)

        # ── 3. Liste des profils ──
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("ProfileListWidget")
        self.list_widget.setFrameShape(QFrame.Shape.NoFrame)
        self.list_widget.setSpacing(6)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setStyleSheet("""
            QListWidget#ProfileListWidget {
                background-color: transparent;
                border: none;
                outline: none;
            }
            QListWidget#ProfileListWidget::item {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
        """)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self.list_widget, 1)

        # ── 4. Formulaire de création d'un nouvel espace ──
        create_frame = QFrame()
        create_frame.setObjectName("ProfileCreateCard")
        create_frame.setStyleSheet(f"""
            QFrame#ProfileCreateCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        create_layout = QVBoxLayout(create_frame)
        create_layout.setContentsMargins(12, 10, 12, 10)
        create_layout.setSpacing(8)

        lbl_create_title = QLabel("CRÉER UN NOUVEL ESPACE DE TRAVAIL")
        lbl_create_title.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        lbl_create_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; letter-spacing: 0.5px; border: none; background: transparent;")
        create_layout.addWidget(lbl_create_title)

        input_box = QHBoxLayout()
        input_box.setSpacing(8)

        self.new_profile_input = StyledLineEdit(icon_name="folder-plus", placeholder="Nom du nouvel espace (ex: droit, medecine)...")
        self.new_profile_input.setFixedHeight(34)
        self.new_profile_input.returnPressed.connect(self._on_create_profile)

        self.btn_create = SecondaryButton("+ Créer")
        self.btn_create.setFixedHeight(34)
        self.btn_create.clicked.connect(self._on_create_profile)

        input_box.addWidget(self.new_profile_input, 1)
        input_box.addWidget(self.btn_create)
        create_layout.addLayout(input_box)

        layout.addWidget(create_frame)

        # ── 5. Option : Bascule automatique au démarrage ──
        auto_box = QHBoxLayout()
        auto_box.setContentsMargins(4, 2, 4, 2)
        auto_box.setSpacing(8)

        self.chk_auto_open = QCheckBox("Toujours ouvrir automatiquement cet espace au démarrage")
        self.chk_auto_open.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        self.chk_auto_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_auto_open.setStyleSheet(f"""
            QCheckBox {{
                color: {DesignTokens.TEXT_SECONDARY};
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                background-color: {DesignTokens.BG_INPUT};
            }}
            QCheckBox::indicator:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QCheckBox::indicator:checked {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        # Initialiser l'état depuis QSettings
        from PySide6.QtCore import QSettings

        settings = QSettings("AnkiForgeOrg", "AnkiForge")
        auto_open_val = settings.value("profiles/auto_open_startup", False, type=bool)
        default_prof = str(settings.value("profiles/default_startup_profile", "default"))
        self.chk_auto_open.setChecked(bool(auto_open_val and (self.selected_profile == default_prof)))

        auto_box.addWidget(self.chk_auto_open)
        auto_box.addStretch()
        layout.addLayout(auto_box)

        # ── 6. Pied de boîte & Actions de validation / suppression ──
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 4, 0, 0)
        bottom_layout.setSpacing(10)

        self.delete_btn = DangerButton("Supprimer cet espace")
        self.delete_btn.setFixedHeight(36)
        self.delete_btn.setIcon(load_phosphor_icon("trash", color=DesignTokens.COLOR_RED))
        self.delete_btn.clicked.connect(self._on_delete_profile)
        self.delete_btn.setEnabled(False)
        bottom_layout.addWidget(self.delete_btn)

        bottom_layout.addStretch()

        self.btn_cancel = SecondaryButton("Annuler")
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_cancel)

        self.btn_select = PrimaryButton("Basculer vers cet Espace")
        self.btn_select.setFixedHeight(36)
        self.btn_select.setIcon(load_phosphor_icon("arrow-right", color="#ffffff"))
        self.btn_select.clicked.connect(self.accept)
        bottom_layout.addWidget(self.btn_select)

        layout.addLayout(bottom_layout)

    def accept(self) -> None:
        """Enregistre les préférences de bascule automatique avant d'accepter."""
        from PySide6.QtCore import QSettings

        settings = QSettings("AnkiForgeOrg", "AnkiForge")
        if hasattr(self, "chk_auto_open") and self.chk_auto_open.isChecked():
            settings.setValue("profiles/auto_open_startup", True)
            settings.setValue("profiles/default_startup_profile", self.selected_profile)
        else:
            settings.setValue("profiles/auto_open_startup", False)
        super().accept()

    def _populate_profiles(self) -> None:
        """Remplit la liste avec tous les profils disponibles."""
        self.list_widget.clear()
        self._card_widgets.clear()
        target_row = 0

        for idx, p in enumerate(self.profiles):
            is_cur = p == self.current_profile
            is_sel = p == self.selected_profile

            item = QListWidgetItem(self.list_widget)
            item.setSizeHint(QSize(0, 58))
            item.setData(Qt.ItemDataRole.UserRole, p)

            card = ProfileItemWidget(name=p, is_current=is_cur, is_selected=is_sel)
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, card)
            self._card_widgets.append(card)

            if is_sel:
                target_row = idx

        if self.profiles:
            self.list_widget.setCurrentRow(target_row)

        if hasattr(self, "count_badge"):
            self.count_badge.setText(f"{len(self.profiles)} profil{'s' if len(self.profiles) > 1 else ''}")

    def _filter_profiles(self, query: str) -> None:
        """Filtre les profils selon la requête textuelle."""
        q = query.strip().lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            raw_name = item.data(Qt.ItemDataRole.UserRole) or ""
            item.setHidden(bool(q and q not in raw_name.lower()))

    def _on_selection_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if not current:
            self.delete_btn.setEnabled(False)
            return

        raw_name = current.data(Qt.ItemDataRole.UserRole)
        if raw_name:
            self.selected_profile = raw_name
            # Mise à jour de l'apparence des cartes
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                card = self.list_widget.itemWidget(item)
                if isinstance(card, ProfileItemWidget):
                    card.set_selected_state(card.name == raw_name)

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
            logger.error("Erreur lors de la création du profil '%s': %s", clean_name, e, exc_info=True)
            QMessageBox.critical(self, "Erreur", f"Impossible de créer le profil : {e}")

    def _on_delete_profile(self) -> None:
        if not self.selected_profile or self.selected_profile == self.current_profile:
            return

        res = QMessageBox.question(
            self,
            "Confirmation de suppression",
            f"Êtes-vous sûr de vouloir supprimer définitivement l'espace de travail « {self.selected_profile} » ?\n\n"
            "Toutes les cartes, documents, personas et médias associés seront définitivement effacés.",
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
                logger.error("Erreur lors de la suppression du profil '%s': %s", self.selected_profile, e, exc_info=True)
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer le profil : {e}")

    def get_selected_profile(self) -> str:
        return self.selected_profile

    def refresh_theme(self, profile: Any) -> None:
        if hasattr(self, "logo_lbl"):
            self.logo_lbl.setPixmap(load_logo_icon(profile.accent_primary).pixmap(38, 38))
        if hasattr(self, "delete_btn"):
            self.delete_btn.setIcon(load_phosphor_icon("trash", color=profile.color_red))
        for card in self._card_widgets:
            card.refresh_theme(profile)
