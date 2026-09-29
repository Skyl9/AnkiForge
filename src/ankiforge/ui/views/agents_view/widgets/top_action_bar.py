from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget

from ankiforge.ui.components import Badge, PrimaryButton, SecondaryButton
from ankiforge.ui.components.buttons import apply_compact_style
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon


class ResponsiveAgentTopActionBar(QFrame):
    """Barre d'action supérieure adaptative pour l'éditeur d'agents IA."""

    def __init__(self, parent: QWidget | None = None) -> None:
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
        self.lbl_agent_title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.lbl_agent_title.setMaximumWidth(220)
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
        apply_compact_style(self.btn_history, height=30)
        self.btn_history.setToolTip("Machine à Remonter le Temps : Historique et diffs des prompts")

        self.btn_test = SecondaryButton("Tester")
        self.btn_test.setIcon(load_phosphor_icon("ph.flask", color=DesignTokens.TEXT_PRIMARY))
        self.btn_test.setIconSize(QSize(14, 14))
        apply_compact_style(self.btn_test, height=30)
        self.btn_test.setToolTip("Tester unitairement cet agent avec un extrait de texte")

        self.btn_import = SecondaryButton("Importer")
        self.btn_import.setIcon(load_phosphor_icon("ph.download-simple", color=DesignTokens.TEXT_PRIMARY))
        self.btn_import.setIconSize(QSize(14, 14))
        apply_compact_style(self.btn_import, height=30)
        self.btn_import.setToolTip("Importer un agent depuis un autre profil")

        self.btn_save = PrimaryButton("Sauvegarder")
        self.btn_save.setIcon(load_on_accent_icon("ph.floppy-disk"))
        self.btn_save.setIconSize(QSize(14, 14))
        apply_compact_style(self.btn_save, height=30)
        self.btn_save.setToolTip("Enregistrer les modifications de l'agent")

        layout.addWidget(self.btn_history)
        layout.addWidget(self.btn_test)
        layout.addWidget(self.btn_import)
        layout.addWidget(self.btn_save)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        w = self.width()
        compact = w < 760
        self.btn_history.setText("" if compact else "Historique")
        self.btn_test.setText("" if compact else "Tester")
        self.btn_import.setText("" if compact else "Importer")
        self.btn_save.setText("Sauvegarder" if w >= 560 else "Enregistrer")
