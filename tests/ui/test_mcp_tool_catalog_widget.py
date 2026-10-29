"""Tests unitaires et UI pour MCPToolCatalogWidget."""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QListWidget, QTableWidget

from ankiforge.ui.views.consultant_view.widgets.mcp_dashboard_widget import (
    MCPServerDashboardWidget,
)
from ankiforge.ui.views.consultant_view.widgets.mcp_tool_catalog_widget import (
    MCPToolCatalogWidget,
    MCPToolItem,
    get_all_mcp_tools,
)

pytestmark = pytest.mark.ui


class DummyTool:
    """Outil factice pour tester l'introspection et l'affichage sans dépendance réseau."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters or {"properties": {}, "required": [], "type": "object"}


@pytest.fixture
def dummy_tools() -> list[DummyTool]:
    """Jeu de données de test pour le catalogue."""
    return [
        DummyTool(
            name="create_note_type",
            description="Propose la création d'un type de note complet via un StagedPatch.\nValidation Tout-ou-Rien.",
            parameters={
                "properties": {
                    "name": {"type": "string", "description": "Nom du modèle"},
                    "fields": {"type": "array", "description": "Liste des champs"},
                    "description": {"type": "string", "default": "", "description": "Description"},
                },
                "required": ["name", "fields"],
                "type": "object",
            },
        ),
        DummyTool(
            name="audit_card_wozniak",
            description="Analyse chirurgicale d'une carte au regard des 20 règles de formulation de Wozniak.",
            parameters={
                "properties": {
                    "note_id": {"type": "integer", "description": "ID de la note"},
                },
                "required": ["note_id"],
                "type": "object",
            },
        ),
        DummyTool(
            name="create_deck",
            description="Crée un paquet et toute son arborescence hiérarchique en écriture directe.",
            parameters={
                "properties": {
                    "deck_name": {"type": "string", "description": "Nom hiérarchique (Parent::Enfant)"},
                    "description": {"type": "string", "default": "", "description": "Description du paquet"},
                },
                "required": ["deck_name"],
                "type": "object",
            },
        ),
        DummyTool(
            name="set_tags_bulk",
            description="Pose ou retire des tags sur un lot de notes via l'écrivain canonique.",
            parameters={
                "properties": {
                    "note_ids": {"type": "array", "description": "IDs des notes"},
                    "tags": {"type": "string", "description": "Tags séparés par des espaces"},
                },
                "required": ["note_ids", "tags"],
                "type": "object",
            },
        ),
        DummyTool(
            name="search_knowledge_context",
            description="Interroge la bibliothèque documentaire via RAG pour extraire des citations.",
            parameters={
                "properties": {
                    "query": {"type": "string", "description": "Requête sémantique"},
                },
                "required": ["query"],
                "type": "object",
            },
        ),
        DummyTool(
            name="list_albums",
            description="Liste les albums d'images et planches enregistrés.",
            parameters={"properties": {}, "required": [], "type": "object"},
        ),
        DummyTool(
            name="list_pipelines",
            description="Liste les pipelines DAG configurés dans AnkiForge.",
            parameters={"properties": {}, "required": [], "type": "object"},
        ),
        DummyTool(
            name="init_agent_workspace",
            description="Génère un guide méthodologique adapté au type d'agent dans le workspace.",
            parameters={
                "properties": {
                    "workspace_path": {"type": "string", "description": "Chemin du workspace"},
                    "agent_type": {"type": "string", "description": "Type d'agent (claude, cursor, etc.)"},
                },
                "required": ["workspace_path", "agent_type"],
                "type": "object",
            },
        ),
        DummyTool(
            name="get_feature_quick_help",
            description="Obtient une synthèse immédiate d'une fonctionnalité clé de l'application.",
            parameters={
                "properties": {
                    "topic": {"type": "string", "description": "Sujet ou mot-clé"},
                },
                "required": ["topic"],
                "type": "object",
            },
        ),
    ]


def test_introspection_fastmcp_real_tools() -> None:
    """Vérifie que l'introspection réelle extrait bien les 82 outils MCP sans lever d'erreur."""
    tools = get_all_mcp_tools()
    assert len(tools) == 82
    tool_names = {t.name for t in tools}
    assert "create_note" in tool_names
    assert "create_note_type" in tool_names
    assert "trigger_pipeline_run" in tool_names
    assert "audit_deck_wozniak" in tool_names
    assert "check_guide_version" in tool_names
    assert "init_agent_workspace" in tool_names
    assert "propose_card_deletion" in tool_names
    assert "propose_deck_rename" in tool_names
    assert "export_deck_apkg" in tool_names
    assert "set_card_flag" in tool_names


def test_mcp_tool_catalog_widget_initialization(qtbot: Any, dummy_tools: list[DummyTool]) -> None:
    """Vérifie l'initialisation du widget avec les puces de domaines et la liste gauche."""
    widget = MCPToolCatalogWidget(raw_tools=dummy_tools)
    qtbot.addWidget(widget)

    # 1. Vérification de la barre de recherche et du compteur
    assert hasattr(widget, "edit_search")
    assert hasattr(widget, "lbl_tool_count")
    assert "9" in widget.lbl_tool_count.text()

    # 2. Vérification des puces de filtrage (Tous + 9 domaines)
    assert hasattr(widget, "chip_all")
    assert widget.chip_all.isChecked()
    assert hasattr(widget, "domain_chips")
    assert len(widget.domain_chips) == 9

    # 3. Vérification de la liste
    assert isinstance(widget.tool_list, QListWidget)
    assert widget.tool_list.count() == 9

    # 4. Fiche technique droite sélectionne le premier outil par défaut (ordre alphabétique)
    assert widget.current_selected_tool is not None
    assert widget.current_selected_tool.name == "audit_card_wozniak"
    assert "audit_card_wozniak" in widget.lbl_detail_name.text()
    assert "Wozniak" in widget.lbl_detail_desc.text()


def test_mcp_tool_catalog_filter_by_domain(qtbot: Any, dummy_tools: list[DummyTool]) -> None:
    """Vérifie le filtrage réactif de la liste en cliquant sur les puces de domaine."""
    widget = MCPToolCatalogWidget(raw_tools=dummy_tools)
    qtbot.addWidget(widget)

    # Clic sur la puce "Paquets"
    chip_decks = widget.domain_chips["decks"]
    chip_decks.click()
    qtbot.wait(20)

    assert chip_decks.isChecked()
    assert not widget.chip_all.isChecked()
    # Seul create_deck doit être visible
    assert widget.tool_list.count() == 1
    item = widget.tool_list.item(0)
    assert item is not None
    data = item.data(Qt.ItemDataRole.UserRole)
    assert isinstance(data, MCPToolItem)
    assert data.name == "create_deck"

    # Fiche technique mise à jour vers create_deck
    assert widget.current_selected_tool is not None
    assert widget.current_selected_tool.name == "create_deck"
    assert "create_deck" in widget.lbl_detail_name.text()

    # Retour à "Tous"
    widget.chip_all.click()
    qtbot.wait(20)
    assert widget.tool_list.count() == 9


def test_mcp_tool_catalog_filter_by_search_text(qtbot: Any, dummy_tools: list[DummyTool]) -> None:
    """Vérifie le filtrage instantané via la barre de recherche textuelle."""
    widget = MCPToolCatalogWidget(raw_tools=dummy_tools)
    qtbot.addWidget(widget)
    widget.show()  # Ensure widget is visible in headless mode

    # Recherche par nom canonique
    widget.edit_search.setText("wozniak")
    qtbot.wait(20)
    assert widget.tool_list.count() == 1
    assert widget.current_selected_tool is not None
    assert widget.current_selected_tool.name == "audit_card_wozniak"

    # Recherche par mot-clé de description
    widget.edit_search.setText("guide méthodologique")
    qtbot.wait(20)
    assert widget.tool_list.count() == 1
    assert widget.current_selected_tool is not None
    assert widget.current_selected_tool.name == "init_agent_workspace"

    # Recherche sans résultat : état explicite "Aucun résultat"
    widget.edit_search.setText("mot_qui_n_existe_pas_12345")
    qtbot.wait(20)
    assert widget.tool_list.count() == 0
    assert widget.current_selected_tool is None
    assert widget.detail_stack.currentIndex() == 2  # Page "Aucun outil ne correspond à votre recherche"
    assert widget.btn_reset_filters.isVisible()
    assert widget.lbl_tool_count.text() == "Aucun outil ne correspond à votre recherche"

    # Clic sur le bouton de réinitialisation : la liste doit se repeupler
    widget.btn_reset_filters.click()
    qtbot.wait(20)
    assert widget.tool_list.count() == 9
    assert widget.detail_stack.currentIndex() == 1
    assert widget.current_selected_tool is not None
    assert not widget.btn_reset_filters.isVisible()  # Bouton masqué quand aucun filtre n'est actif


def test_mcp_tool_catalog_parameters_table(qtbot: Any, dummy_tools: list[DummyTool]) -> None:
    """Vérifie l'affichage du tableau des paramètres (requis vs optionnels)."""
    widget = MCPToolCatalogWidget(raw_tools=dummy_tools)
    qtbot.addWidget(widget)

    # create_note_type a 3 paramètres : name (requis), fields (requis), description (optionnel)
    widget.select_tool_by_name("create_note_type")
    qtbot.wait(20)

    assert isinstance(widget.params_table, QTableWidget)
    assert widget.params_table.rowCount() == 3

    # Paramètre 'name'
    param_names = [item.text() for r in range(3) if (item := widget.params_table.item(r, 0)) is not None]
    assert "name" in param_names
    assert "fields" in param_names
    assert "description" in param_names

    # Vérification que la colonne Requis ? est bien renseignée
    req_labels = [item.text() for r in range(3) if (item := widget.params_table.item(r, 2)) is not None]
    assert "Requis" in req_labels
    assert "Optionnel" in req_labels


def test_mcp_tool_catalog_safeguards_display(qtbot: Any, dummy_tools: list[DummyTool]) -> None:
    """Vérifie la mise en évidence des avertissements et garde-fous associés à l'outil."""
    widget = MCPToolCatalogWidget(raw_tools=dummy_tools)
    qtbot.addWidget(widget)

    # create_note_type a un garde-fou Two-Phase Commit
    widget.select_tool_by_name("create_note_type")
    assert not widget.frame_safeguards.isHidden()
    assert "Two-Phase Commit" in widget.lbl_safeguards_content.text()

    # list_albums n'a pas de garde-fou contraignant particulier
    widget.select_tool_by_name("list_albums")
    assert widget.frame_safeguards.isHidden()


def test_mcp_tool_catalog_copy_actions(qtbot: Any, dummy_tools: list[DummyTool]) -> None:
    """Vérifie la copie du nom canonique et de la signature JSON dans le presse-papiers."""
    widget = MCPToolCatalogWidget(raw_tools=dummy_tools)
    qtbot.addWidget(widget)

    widget.select_tool_by_name("create_deck")

    clipboard = QGuiApplication.clipboard()
    if clipboard is not None:
        clipboard.clear()
        widget.btn_copy_tool_name.click()
        assert clipboard.text() == "create_deck"

        clipboard.clear()
        widget.btn_copy_json_signature.click()
        assert "create_deck" in clipboard.text()
        assert "deck_name" in clipboard.text()


def test_mcp_dashboard_widget_integration_catalog_tab(qtbot: Any) -> None:
    """Vérifie l'intégration du catalogue réel comme 3e sous-onglet dans MCPServerDashboardWidget."""
    dashboard = MCPServerDashboardWidget(initial_status="stopped", initial_port=8765)
    qtbot.addWidget(dashboard)

    # Vérification que le sous-onglet Catalogue est une instance de MCPToolCatalogWidget
    assert hasattr(dashboard, "catalog_widget")
    assert isinstance(dashboard.catalog_widget, MCPToolCatalogWidget)

    # Vérification du basculement d'onglet
    dashboard.sub_tab_bar.setCurrentIndex(2)
    assert dashboard.stacked_widget.currentIndex() == 2
    assert dashboard.stacked_widget.currentWidget() == dashboard.catalog_widget
    assert dashboard.catalog_widget.tool_list.count() == 82


def test_mcp_tool_catalog_buttons_and_chips_geometry(qtbot: Any, dummy_tools: list[DummyTool]) -> None:
    """Vérifie que les boutons d'action et les puces de filtre ont des hauteurs et densités valides sans rognage."""
    from ankiforge.ui.components.buttons import COMPACT_BUTTON_HEIGHT

    widget = MCPToolCatalogWidget(raw_tools=dummy_tools)
    qtbot.addWidget(widget)

    # 1. Boutons d'action : densité compacte et hauteur 32px
    assert widget.btn_copy_tool_name.property("density") == "compact"
    assert widget.btn_copy_tool_name.height() == COMPACT_BUTTON_HEIGHT or widget.btn_copy_tool_name.maximumHeight() == COMPACT_BUTTON_HEIGHT

    assert widget.btn_copy_json_signature.property("density") == "compact"
    assert widget.btn_copy_json_signature.height() == COMPACT_BUTTON_HEIGHT or widget.btn_copy_json_signature.maximumHeight() == COMPACT_BUTTON_HEIGHT

    # 2. Ruban de puces : hauteur réservée de 46px (évite le rognage avec scrollbar)
    chips_scroll = widget.findChild(type(widget.detail_scroll), "mcp_catalog_chips_scroll")
    assert chips_scroll is not None
    assert chips_scroll.maximumHeight() == 46

    # 3. Puces de filtres : largeur minimale garantie non nulle
    assert widget.chip_all.minimumWidth() > 0
    for chip in widget.domain_chips.values():
        assert chip.minimumWidth() > 0
