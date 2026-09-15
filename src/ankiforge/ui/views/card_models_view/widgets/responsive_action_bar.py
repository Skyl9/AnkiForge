from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget

from ankiforge.ui.components import Badge, IconButton, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class ResponsiveTopActionBar(QFrame):
    """Barre d'action supérieure adaptative pour l'éditeur de modèles de cartes."""

    preview_toggle_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("topActionBar")
        self.setFixedHeight(40)
        self.setStyleSheet(f"""
            QFrame#topActionBar {{
                background-color: {DesignTokens.BG_PANEL};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        # Badge Icône
        self.lbl_editor_icon = QLabel()
        self.lbl_editor_icon.setPixmap(load_phosphor_icon("ph.swatches", color=DesignTokens.ACCENT_PRIMARY).pixmap(18, 18))
        self.lbl_editor_icon.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.lbl_editor_icon)

        # Titre du Modèle
        self.lbl_editor_title = QLabel("Modèle sélectionné")
        self.lbl_editor_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        self.lbl_editor_title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.lbl_editor_title)

        self.model_type_badge = Badge("Standard", variant="neutral")
        self.model_type_badge.setFixedHeight(20)
        layout.addWidget(self.model_type_badge)

        self.template_count_badge = Badge("1 gabarit", variant="neutral")
        self.template_count_badge.setFixedHeight(20)
        layout.addWidget(self.template_count_badge)

        layout.addStretch(1)

        # Boutons d'action
        self.btn_export_json = IconButton("ph.export", tooltip="Exporter le modèle au format JSON standardisé AnkiForge", size=24)

        self.btn_toggle_preview = SecondaryButton("Aperçu en direct")
        self.btn_toggle_preview.setIcon(load_phosphor_icon("ph.columns", color=DesignTokens.TEXT_PRIMARY))
        self.btn_toggle_preview.setFixedHeight(28)
        self.btn_toggle_preview.setToolTip("Afficher / Masquer l'aperçu en direct à côté du code")
        self.btn_toggle_preview.clicked.connect(self.preview_toggle_requested.emit)

        self.btn_refresh = IconButton("ph.arrows-clockwise", tooltip="Actualiser la prévisualisation temps réel", size=24)

        self.btn_save = PrimaryButton("Sauvegarder")
        self.btn_save.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        self.btn_save.setFixedHeight(28)
        self.btn_save.setMinimumWidth(110)
        self.btn_save.setToolTip("Sauvegarder les modifications du modèle")

        layout.addWidget(self.btn_export_json)
        layout.addWidget(self.btn_toggle_preview)
        layout.addWidget(self.btn_refresh)
        layout.addWidget(self.btn_save)
