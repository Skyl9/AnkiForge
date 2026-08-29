from typing import Optional
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget

from ankiforge.ui.components import Badge, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class ResponsiveAgentTopActionBar(QFrame):
    """Barre d'action supérieure adaptative pour l'éditeur d'agents IA."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("agentTopActionBar")
        self.setFixedHeight(44)
        self.setStyleSheet(f"""
            QFrame#agentTopActionBar {{
                background-color: {DesignTokens.BG_PANEL};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        # Icône Agent
        self.lbl_agent_icon = QLabel()
        self.lbl_agent_icon.setFixedSize(22, 22)
        self.lbl_agent_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_agent_icon.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.ACCENT_PRIMARY).pixmap(18, 18))
        self.lbl_agent_icon.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.lbl_agent_icon, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Titre de l'Agent
        self.lbl_agent_title = QLabel("Agent sélectionné")
        self.lbl_agent_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        self.lbl_agent_title.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.lbl_agent_title, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Badges sémantiques
        self.scope_badge = Badge("Pipeline", variant="primary")
        self.scope_badge.setFixedHeight(20)
        layout.addWidget(self.scope_badge, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.format_badge = Badge("JSON", variant="warning")
        self.format_badge.setFixedHeight(20)
        layout.addWidget(self.format_badge, alignment=Qt.AlignmentFlag.AlignVCenter)

        layout.addStretch(1)

        # Actions d'en-tête
        self.btn_history = SecondaryButton("Historique")
        self.btn_history.setIcon(load_phosphor_icon("ph.clock-counter-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_history.setIconSize(QSize(14, 14))
        self.btn_history.setFixedHeight(30)
        self.btn_history.setToolTip("Machine à Remonter le Temps : Historique et diffs des prompts")

        self.btn_test = SecondaryButton("Tester")
        self.btn_test.setIcon(load_phosphor_icon("ph.flask", color=DesignTokens.TEXT_PRIMARY))
        self.btn_test.setIconSize(QSize(14, 14))
        self.btn_test.setFixedHeight(30)
        self.btn_test.setToolTip("Tester unitairement cet agent avec un extrait de texte")

        self.btn_save = PrimaryButton("Sauvegarder")
        self.btn_save.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        self.btn_save.setIconSize(QSize(14, 14))
        self.btn_save.setFixedHeight(30)
        self.btn_save.setMinimumWidth(110)
        self.btn_save.setToolTip("Enregistrer les modifications de l'agent")

        layout.addWidget(self.btn_history)
        layout.addWidget(self.btn_test)
        layout.addWidget(self.btn_save)
