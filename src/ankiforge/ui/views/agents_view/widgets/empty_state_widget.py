"""Widget d'état d'accueil (Empty State) engageant pour l'Atelier de Personas."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class PersonaEmptyStateWidget(QWidget):
    """
    Écran d'accueil affiché lorsqu'aucun agent n'est sélectionné ou que la liste est vide.
    Guide l'utilisateur avec des explications claires et des raccourcis d'onboarding.
    """

    create_from_template_requested = Signal()
    create_custom_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 32, 32, 32)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        container = QFrame()
        container.setMaximumWidth(580)
        container.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(28, 28, 28, 28)
        container_layout.setSpacing(16)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Icône principale illustrée
        lbl_icon = QLabel()
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_icon.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.ACCENT_PRIMARY).pixmap(52, 52))
        lbl_icon.setStyleSheet("border: none; background: transparent;")
        container_layout.addWidget(lbl_icon)

        # Titre engageant
        lbl_title = QLabel("Atelier de Personas & Modèles d'Agents")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setStyleSheet(f"""
            color: {DesignTokens.TEXT_PRIMARY};
            font-size: 18px;
            font-weight: bold;
            border: none;
            background: transparent;
        """)
        container_layout.addWidget(lbl_title)

        # Sous-titre vulgarisé
        lbl_desc = QLabel(
            "Les <b>Personas</b> définissent la personnalité, les règles pédagogiques et les capacités "
            "de vos assistants IA dans AnkiForge. Ils régissent la formulation minimale selon les 20 règles de Wozniak, "
            "l'extraction de vocabulaire ou encore les diagnostics autonomes du Consultant MCP."
        )
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"""
            color: {DesignTokens.TEXT_MUTED};
            font-size: 12.5px;
            line-height: 1.5;
            border: none;
            background: transparent;
        """)
        container_layout.addWidget(lbl_desc)

        # Boutons d'appel à l'action (CTAs)
        cta_layout = QHBoxLayout()
        cta_layout.setSpacing(12)
        cta_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_templates = PrimaryButton("✨ Parcourir les Modèles Prêts à l'Emploi")
        self.btn_templates.setIcon(load_phosphor_icon("ph.sparkle", color="white"))
        self.btn_templates.setIconSize(QSize(16, 16))
        self.btn_templates.setFixedHeight(36)
        self.btn_templates.clicked.connect(self.create_from_template_requested.emit)
        cta_layout.addWidget(self.btn_templates)

        self.btn_blank = SecondaryButton("➕ Créer un Agent Vierge")
        self.btn_blank.setFixedHeight(36)
        self.btn_blank.clicked.connect(self.create_custom_requested.emit)
        cta_layout.addWidget(self.btn_blank)

        container_layout.addLayout(cta_layout)

        # Mini guide d'onboarding en 3 étapes
        guide_frame = QFrame()
        guide_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px dashed {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 10px;
            }}
        """)
        guide_layout = QVBoxLayout(guide_frame)
        guide_layout.setContentsMargins(12, 10, 12, 10)
        guide_layout.setSpacing(8)

        lbl_guide_title = QLabel("💡 Comment tirer le meilleur parti des Personas :")
        lbl_guide_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        guide_layout.addWidget(lbl_guide_title)

        tips = [
            ("1. Choisissez un modèle", "Sélectionnez un profil pré-configuré (Langues, Médecine, Sciences, Wozniak, Cloze)."),
            ("2. Testez en 1-clic", "Utilisez le simulateur unitaire avec un extrait de cours pour valider les cartes générées."),
            ("3. Déployez en production", "Intégrez votre persona dans un pipeline DAG de création ou activez-le dans le Consultant MCP."),
        ]

        for step, text in tips:
            row = QHBoxLayout()
            row.setSpacing(6)
            lbl_step = QLabel(step)
            lbl_step.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 11px; font-weight: bold; border: none; background: transparent;")
            lbl_text = QLabel(f"— {text}")
            lbl_text.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
            row.addWidget(lbl_step)
            row.addWidget(lbl_text, 1)
            guide_layout.addLayout(row)

        container_layout.addWidget(guide_frame)
        main_layout.addWidget(container)
