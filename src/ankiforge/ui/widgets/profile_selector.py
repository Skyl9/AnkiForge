from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.paths import get_project_root
from ankiforge.ui.components.buttons import PrimaryButton


class ProfileSelectorDialog(QDialog):
    def __init__(self, profiles: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choix du Profil - AnkiForge")
        self.setFixedSize(400, 450)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; color: {DesignTokens.TEXT_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        icon_lbl = QLabel()
        logo_path = get_project_root() / "src" / "ankiforge" / "ressources" / "icons" / "logo.svg"
        icon_lbl.setPixmap(QIcon(str(logo_path)).pixmap(48, 48))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_lbl)

        title = QLabel("Sélectionnez un Espace de Travail")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 8px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 12px;
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                color: white;
            }}
        """)

        for p in profiles:
            item = QListWidgetItem(p)
            self.list_widget.addItem(item)

        if profiles:
            self.list_widget.setCurrentRow(0)

        layout.addWidget(self.list_widget)

        self.btn_select = PrimaryButton("Lancer AnkiForge")
        self.btn_select.setFixedHeight(40)
        self.btn_select.clicked.connect(self.accept)
        layout.addWidget(self.btn_select)

        self.selected_profile = profiles[0] if profiles else "default"
        self.list_widget.currentItemChanged.connect(self._on_item_changed)

    def _on_item_changed(self, current, previous):
        if current:
            self.selected_profile = current.text()

    def get_selected_profile(self) -> str:
        return self.selected_profile
