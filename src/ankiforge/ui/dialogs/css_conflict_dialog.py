"""
Dialogue d'Arbitrage des Conflits de Styles CSS pour l'Atelier de Modèles.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class CSSConflictDialog(QDialog):
    """Dialogue modal permettant d'arbitrer une collision de sélecteurs CSS lors de l'insertion d'un snippet."""

    def __init__(
        self,
        conflicting_classes: list[str],
        snippet_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.conflicting_classes = conflicting_classes
        self.snippet_name = snippet_name
        self.selected_action = "cancel"  # "replace" | "rename" | "html_only" | "cancel"

        self.setWindowTitle("Conflit de Styles CSS Détecté")
        self.setFixedWidth(520)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # En-tête
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.warning-diamond", color=DesignTokens.COLOR_YELLOW).pixmap(28, 28))
        icon_lbl.setStyleSheet("border: none; background: transparent;")

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)

        title_lbl = QLabel("Collision de classes CSS")
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 15px; font-weight: bold; border: none;")

        subtitle_lbl = QLabel(f"Le snippet « {self.snippet_name} » utilise des classes déjà présentes dans votre modèle.")
        subtitle_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px; border: none;")
        subtitle_lbl.setWordWrap(True)

        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(subtitle_lbl)

        header_layout.addWidget(icon_lbl)
        header_layout.addLayout(title_vbox, 1)
        layout.addLayout(header_layout)

        # Cadre listant les classes en collision
        classes_frame = QFrame()
        classes_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px;
            }}
        """)
        classes_layout = QVBoxLayout(classes_frame)
        classes_layout.setContentsMargins(8, 8, 8, 8)
        classes_layout.setSpacing(4)

        classes_title = QLabel("Classes en conflit :")
        classes_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; border: none;")
        classes_layout.addWidget(classes_title)

        classes_str = ", ".join(f".{c}" for c in self.conflicting_classes)
        classes_text = QLabel(classes_str)
        classes_text.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-family: '{DesignTokens.FONT_CODE}'; font-size: 12px; font-weight: bold; border: none;")
        classes_text.setWordWrap(True)
        classes_layout.addWidget(classes_text)

        layout.addWidget(classes_frame)

        # Explications des choix
        info_lbl = QLabel("Comment souhaitez-vous intégrer ce composant ?")
        info_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 600; border: none;")
        layout.addWidget(info_lbl)

        # Options d'actions
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(10)

        # Option 1 : Créer une variante unique (Recommandé)
        self.btn_rename = PrimaryButton("✨ Créer une variante unique (Recommandé)")
        self.btn_rename.setIcon(load_phosphor_icon("ph.sparkle", color="white"))
        self.btn_rename.setToolTip("Renomme automatiquement les classes pour éviter toute perturbation du style existant.")
        self.btn_rename.clicked.connect(self._on_rename_clicked)
        btn_layout.addWidget(self.btn_rename)

        # Option 2 : Remplacer la règle CSS
        self.btn_replace = SecondaryButton("🔄 Remplacer les règles CSS existantes")
        self.btn_replace.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_replace.setToolTip("Écrase les définitions CSS précédentes par celles du nouveau snippet.")
        self.btn_replace.clicked.connect(self._on_replace_clicked)
        btn_layout.addWidget(self.btn_replace)

        # Option 3 : Insérer le HTML seul
        self.btn_html_only = SecondaryButton("📄 Insérer le HTML uniquement (Conserver le CSS actuel)")
        self.btn_html_only.setIcon(load_phosphor_icon("ph.file-html", color=DesignTokens.TEXT_PRIMARY))
        self.btn_html_only.setToolTip("Insère le balisage HTML sans modifier la feuille de styles CSS.")
        self.btn_html_only.clicked.connect(self._on_html_only_clicked)
        btn_layout.addWidget(self.btn_html_only)

        layout.addLayout(btn_layout)

        # Bouton Annuler
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()

        btn_cancel = SecondaryButton("Annuler l'insertion")
        btn_cancel.clicked.connect(self.reject)
        bottom_row.addWidget(btn_cancel)

        layout.addLayout(bottom_row)

    def _on_rename_clicked(self) -> None:
        self.selected_action = "rename"
        self.accept()

    def _on_replace_clicked(self) -> None:
        self.selected_action = "replace"
        self.accept()

    def _on_html_only_clicked(self) -> None:
        self.selected_action = "html_only"
        self.accept()
