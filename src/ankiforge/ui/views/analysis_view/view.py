import contextlib
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ankiforge.ui.components.buttons import IconButton
from ankiforge.ui.components.panels import IdePanel
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.analysis_view.tabs import (
    AIDuplicatesMergeTab,
    AISourcesDiagnosticTab,
    AITokensSrsTab,
    AIWozniakLinterTab,
)


class AnalysisView(QWidget):
    """Vue Principale Analyse & Audit IA avec barre d'onglets JetBrains-style."""

    request_navigation = Signal(str, object)

    def __init__(self, ai_manager: Any | None = None, profile_name: str = "default", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.profile_name = profile_name
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Utilisation de IdePanel (Onglets et StackedWidget intégrés)
        self.main_panel = IdePanel(detachable=True, parent=self)

        self.tab_wozniak = AIWozniakLinterTab()
        self.tab_sources = AISourcesDiagnosticTab()
        self.tab_tokens = AITokensSrsTab()
        self.tab_duplicates = AIDuplicatesMergeTab()

        self.tab_sources.request_navigation.connect(self.request_navigation)

        self.main_panel.add_tab("Audit && Linter Wozniak", self.tab_wozniak, icon_name="sparkle", icon_color=DesignTokens.COLOR_YELLOW)
        self.main_panel.add_tab("Documents", self.tab_sources, icon_name="file-text", icon_color=DesignTokens.COLOR_BLUE)
        self.main_panel.add_tab("Jetons && SRS", self.tab_tokens, icon_name="currency-dollar", icon_color=DesignTokens.COLOR_GREEN)
        self.main_panel.add_tab("Fusions && Doublons", self.tab_duplicates, icon_name="git-merge", icon_color=DesignTokens.COLOR_PURPLE)

        # Bouton de paramètres ajouté au header
        self.btn_settings = IconButton("gear", "Paramètres de l'Analyse", 24)
        self.btn_settings.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        self.main_panel.add_header_widget(self.btn_settings)

        layout.addWidget(self.main_panel)
        self.main_panel.set_active_tab(0)

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les onglets et composants lors d'un switch de thème."""
        if hasattr(self, "main_panel") and hasattr(self.main_panel, "refresh_theme"):
            self.main_panel.refresh_theme(profile)
            color_map = {
                0: getattr(profile, "color_yellow", DesignTokens.COLOR_YELLOW),
                1: getattr(profile, "color_blue", DesignTokens.COLOR_BLUE),
                2: getattr(profile, "color_green", DesignTokens.COLOR_GREEN),
                3: getattr(profile, "color_purple", DesignTokens.COLOR_PURPLE),
            }
            for idx, color in color_map.items():
                if hasattr(self.main_panel, "set_tab_icon_color"):
                    self.main_panel.set_tab_icon_color(idx, color)
        if hasattr(self, "btn_settings") and hasattr(self.btn_settings, "refresh_theme"):
            self.btn_settings.refresh_theme(profile)
        for tab in [getattr(self, "tab_wozniak", None), getattr(self, "tab_sources", None), getattr(self, "tab_tokens", None), getattr(self, "tab_duplicates", None)]:
            if tab and hasattr(tab, "refresh_theme"):
                with contextlib.suppress(Exception):
                    tab.refresh_theme(profile)

    def refresh_data(self) -> None:
        """Recalcule les données de l'onglet actif (appelé à chaque navigation)."""
        if hasattr(self, "tab_sources") and hasattr(self.tab_sources, "refresh_data"):
            with contextlib.suppress(Exception):
                self.tab_sources.refresh_data()

    def set_active_tab_by_name(self, tab_name: str) -> None:
        """Active l'onglet spécifié par son nom ou alias."""
        tab_lower = tab_name.lower().strip()
        tab_map = {
            "audit": 0,
            "wozniak": 0,
            "sources": 1,
            "coverage": 1,
            "documents": 1,
            "tokens": 2,
            "srs": 2,
            "cost": 2,
            "budget": 2,
            "duplicates": 3,
            "merge": 3,
            "fusions": 3,
        }
        idx = tab_map.get(tab_lower)
        if idx is not None:
            self.main_panel.set_active_tab(idx)
