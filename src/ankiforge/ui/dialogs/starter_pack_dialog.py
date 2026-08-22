"""
Dialogue de Sélection et d'Installation des Modèles Communautaires Préconfigurés (Starter Pack).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteTypeModel
from ankiforge.services.cards.card_model_io import CardModelIO
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon


class StarterModelCardWidget(QFrame):
    """Carte graphique représentant un modèle communautaire du starter pack."""

    def __init__(
        self,
        pack: Dict[str, Any],
        on_install_callback: Any,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.pack = pack
        self.on_install_callback = on_install_callback

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 14px;
            }}
            QFrame:hover {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Ligne du haut : Badge Catégorie + Version
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        cat_badge = QLabel(pack.get("category", "Général"))
        cat_badge.setStyleSheet(f"""
            background-color: rgba(99, 102, 241, 0.15);
            color: {DesignTokens.ACCENT_PRIMARY};
            border: 1px solid rgba(99, 102, 241, 0.35);
            border-radius: 9999px;
            padding: 2px 8px;
            font-size: 10px;
            font-weight: bold;
        """)
        top_row.addWidget(cat_badge)
        top_row.addStretch()

        ver_lbl = QLabel(f"v{pack.get('version', '1.0.0')}")
        ver_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px;")
        top_row.addWidget(ver_lbl)
        layout.addLayout(top_row)

        # Titre & Auteur
        title_lbl = QLabel(pack.get("name", "Modèle"))
        title_lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        layout.addWidget(title_lbl)

        author_lbl = QLabel(f"Par : {pack.get('author', 'AnkiForge')}")
        author_lbl.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED};")
        layout.addWidget(author_lbl)

        # Description
        desc_lbl = QLabel(pack.get("description", ""))
        desc_lbl.setStyleSheet(f"font-size: 12px; color: {DesignTokens.TEXT_SECONDARY}; line-height: 1.4;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # Champs requis
        fields = pack.get("fields_schema", [])
        fields_str = ", ".join(fields)
        fields_lbl = QLabel(f"<b>Champs :</b> {fields_str}")
        fields_lbl.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED};")
        fields_lbl.setWordWrap(True)
        layout.addWidget(fields_lbl)

        layout.addStretch()

        # Bouton Installer
        btn_install = PrimaryButton("Installer ce Modèle")
        btn_install.setIcon(load_phosphor_icon("ph.plus-circle", color="white"))
        btn_install.clicked.connect(lambda: self.on_install_callback(self.pack))
        layout.addWidget(btn_install)


class StarterPackDialog(QDialog):
    """Dialogue modal de catalogue de styles communautaires intégrés."""

    model_installed = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Catalogue de Modèles Communautaires (Starter Pack)")
        self.setMinimumSize(850, 600)
        self.resize(920, 650)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # En-tête
        header = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.ACCENT_PRIMARY).pixmap(26, 26))
        header.addWidget(icon_lbl)

        title_box = QVBoxLayout()
        title_lbl = QLabel("Modèles Communautaires & Professionnels Prêts à l'Emploi")
        title_lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        subtitle_lbl = QLabel("Installez en un clic des gabarits conçus pour la médecine, le code, les maths et les langues.")
        subtitle_lbl.setStyleSheet(f"font-size: 12px; color: {DesignTokens.TEXT_MUTED};")
        title_box.addWidget(title_lbl)
        title_box.addWidget(subtitle_lbl)
        header.addLayout(title_box, 1)

        layout.addLayout(header)

        # Grille de modèles
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        grid_layout = QGridLayout(scroll_content)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(14)

        packs = CardModelIO.get_starter_pack_models()
        for idx, pack in enumerate(packs):
            card = StarterModelCardWidget(pack, on_install_callback=self._on_install_pack)
            row = idx // 2
            col = idx % 2
            grid_layout.addWidget(card, row, col)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        # Footer
        footer = QHBoxLayout()
        btn_close = SecondaryButton("Fermer")
        btn_close.clicked.connect(self.accept)
        footer.addStretch()
        footer.addWidget(btn_close)
        layout.addLayout(footer)

    def _on_install_pack(self, pack: Dict[str, Any]) -> None:
        name = pack.get("name", "Modèle")
        exists = NoteTypeModel.get_or_none(NoteTypeModel.name == name) is not None

        overwrite = False
        if exists:
            res = QMessageBox.question(
                self,
                "Modèle Existant",
                f"Le modèle '{name}' est déjà présent dans votre collection.\n\nVoulez-vous le dupliquer (Non) ou écraser sa configuration (Oui) ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.No,
            )
            if res == QMessageBox.StandardButton.Cancel:
                return
            overwrite = res == QMessageBox.StandardButton.Yes

        try:
            model_inst, _ = CardModelIO.save_model_to_db(pack, overwrite_existing=overwrite)
            show_toast(self, f"Modèle '{model_inst.name}' installé avec succès !")
            self.model_installed.emit(model_inst.id)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Échec de l'installation : {str(e)}")
