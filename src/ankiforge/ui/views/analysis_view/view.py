import contextlib
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ankiforge.ui.components.panels import IdePanel
from ankiforge.ui.shortcuts import ShortcutId, ShortcutManager, ShortcutScope
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

    def __init__(
        self,
        ai_manager: Any | None = None,
        profile_name: str = "default",
        parent: QWidget | None = None,
        shortcut_manager: ShortcutManager | None = None,
    ) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.profile_name = profile_name
        self._shortcut_manager: ShortcutManager = shortcut_manager or ShortcutManager(self)
        if shortcut_manager is None:
            self._shortcut_manager.set_active_view(self)
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

        layout.addWidget(self.main_panel)
        self.main_panel.set_active_tab(0)
        self._setup_shortcuts()

    @property
    def shortcut_manager(self) -> ShortcutManager:
        """Manager des raccourcis clavier associé à la vue Analyse & Audit."""
        return self._shortcut_manager

    def set_shortcut_manager(self, manager: ShortcutManager) -> None:
        """Injecte le ShortcutManager central et re-lie tous les raccourcis."""
        if self._shortcut_manager is not manager:
            if self._shortcut_manager is not None:
                self._shortcut_manager.unbind(self)
            self._shortcut_manager = manager
            self._setup_shortcuts()

    def _setup_shortcuts(self) -> None:
        """Configure les raccourcis déclaratifs de la vue Analyse via ShortcutManager."""
        if not hasattr(self, "_shortcut_manager") or self._shortcut_manager is None:
            return

        vue_bindings = {
            ShortcutId.ANALYSIS_REINDEX: lambda: self._on_reindex_sources(),
            ShortcutId.ANALYSIS_ALIGN_SOURCES: lambda: self._on_align_sources(),
            ShortcutId.ANALYSIS_FORGE_FRAGMENT: lambda: self._on_forge_fragment(),
        }
        self._shortcut_manager.bind(self, vue_bindings, scope=ShortcutScope.VUE)

    def _on_run_analysis(self) -> None:
        """Déclenche l'audit de conformité Wozniak."""
        if hasattr(self, "tab_wozniak") and self.tab_wozniak is not None:
            self.tab_wozniak.refresh_audit(force=True)

    def _on_reindex_sources(self) -> None:
        """Réindexe les sources ou la matière ciblée."""
        if hasattr(self, "tab_sources") and self.tab_sources is not None:
            self.tab_sources.reindex_active_source()

    def _on_align_sources(self) -> None:
        """Synchronise et aligne les cartes Anki aux sections sources."""
        if hasattr(self, "tab_sources") and self.tab_sources is not None:
            self.tab_sources.align_sources()

    def _on_forge_fragment(self) -> None:
        """Forge le fragment ou la section ciblée dans le Studio."""
        if hasattr(self, "tab_sources") and self.tab_sources is not None:
            self.tab_sources.forge_targeted_fragment()

    def run_primary_action(self) -> None:
        """Action primaire d'analyse (Ctrl+Entrée)."""
        self._on_run_analysis()

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
        for tab in [getattr(self, "tab_wozniak", None), getattr(self, "tab_sources", None), getattr(self, "tab_tokens", None), getattr(self, "tab_duplicates", None)]:
            if tab and hasattr(tab, "refresh_theme"):
                with contextlib.suppress(Exception):
                    tab.refresh_theme(profile)

    def refresh_data(self) -> None:
        """Recalcule les données de l'onglet actif (appelé à chaque navigation)."""
        current_widget = self.main_panel.content_stack.currentWidget()
        if current_widget == getattr(self, "tab_duplicates", None) and hasattr(self.tab_duplicates, "refresh_data"):
            with contextlib.suppress(Exception):
                self.tab_duplicates.refresh_data()
        elif hasattr(self, "tab_sources") and hasattr(self.tab_sources, "refresh_data"):
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

    def open_document_inspector(self, doc_id: int) -> None:
        """Active l'onglet Documents et ouvre l'inspecteur détaillé du document ciblé."""
        self.set_active_tab_by_name("documents")
        if hasattr(self, "tab_sources") and self.tab_sources:
            from ankiforge.database.models import DocumentModel

            doc = DocumentModel.get_or_none(DocumentModel.id == doc_id)
            if doc and hasattr(self.tab_sources, "search_input"):
                self.tab_sources.search_input.setText(doc.title)
            if hasattr(self.tab_sources, "show_inspector"):
                self.tab_sources.show_inspector(doc_id)
