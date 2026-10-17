"""Tests unitaires et UI pour MCPWorkspaceGuideWidget et l'intégration dans MCPServerDashboardWidget."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog

from ankiforge.database.models import PersonaModel
from ankiforge.services.ai.mcp_server import _GUIDE_VERSION_HASH
from ankiforge.ui.views.consultant_view.widgets.mcp_dashboard_widget import (
    MCPServerDashboardWidget,
)
from ankiforge.ui.views.consultant_view.widgets.mcp_workspace_guide_widget import (
    MCPWorkspaceGuideWidget,
)

pytestmark = pytest.mark.ui


def test_workspace_guide_widget_initialization(qtbot) -> None:
    """Vérifie la bonne instanciation des composants du sous-onglet Guides & Workspaces."""
    widget = MCPWorkspaceGuideWidget()
    qtbot.addWidget(widget)

    # 1. Sélecteur de type d'agent
    assert widget.combo_agent_type is not None
    assert widget.combo_agent_type.count() == 5
    agent_keys = [widget.combo_agent_type.itemData(i) for i in range(widget.combo_agent_type.count())]
    assert "claude" in agent_keys
    assert "gemini" in agent_keys
    assert "cursor" in agent_keys
    assert "agy" in agent_keys
    assert "generic" in agent_keys

    # 2. Champ de chemin et bouton parcourir
    assert widget.edit_workspace_path is not None
    assert widget.edit_workspace_path.text() == ""
    assert widget.btn_browse is not None

    # 3. Case à cocher catalogue (cochée par défaut)
    assert widget.chk_include_catalogue is not None
    assert widget.chk_include_catalogue.isChecked()

    # 4. Boutons d'action
    assert widget.btn_init_workspace is not None
    assert widget.btn_check_version is not None
    assert widget.badge_version_status is not None

    # 5. Visualiseur Markdown
    assert widget.preview_browser is not None
    assert len(widget.current_guide_content) > 0
    assert "AnkiForge" in widget.current_guide_content

    # 6. Section des Personas
    assert widget.list_personas is not None
    assert widget.edit_persona_prompt is not None


def test_workspace_guide_agent_type_change_updates_preview(qtbot) -> None:
    """Vérifie que la modification du type d'agent réactualise la prévisualisation et le badge de fichier."""
    widget = MCPWorkspaceGuideWidget()
    qtbot.addWidget(widget)

    # Bascule vers Cursor
    idx_cursor = widget.combo_agent_type.findData("cursor")
    assert idx_cursor >= 0
    widget.combo_agent_type.setCurrentIndex(idx_cursor)
    assert widget.current_target_filename == ".cursorrules"
    assert widget.badge_target_file.text() == ".cursorrules"
    assert ".cursorrules" in widget.current_guide_content

    # Bascule vers Claude
    idx_claude = widget.combo_agent_type.findData("claude")
    widget.combo_agent_type.setCurrentIndex(idx_claude)
    assert widget.current_target_filename == "CLAUDE.md"
    assert widget.badge_target_file.text() == "CLAUDE.md"
    assert "CLAUDE.md" in widget.current_guide_content

    # Bascule vers agy
    idx_agy = widget.combo_agent_type.findData("agy")
    widget.combo_agent_type.setCurrentIndex(idx_agy)
    assert widget.current_target_filename == "GEMINI.md"
    assert widget.badge_target_file.text() == "GEMINI.md"
    assert "GEMINI.md" in widget.current_guide_content


def test_workspace_guide_toggle_catalogue(qtbot) -> None:
    """Vérifie l'inclusion conditionnelle du catalogue d'outils dans le guide."""
    widget = MCPWorkspaceGuideWidget()
    qtbot.addWidget(widget)

    content_with = widget.current_guide_content
    assert "Catalogue" in content_with

    # Décochage de la case catalogue
    widget.chk_include_catalogue.setChecked(False)
    content_without = widget.current_guide_content
    assert "Catalogue exhaustif" not in content_without
    assert content_with != content_without

    # Recochage
    widget.chk_include_catalogue.setChecked(True)
    assert "Catalogue" in widget.current_guide_content


def test_workspace_guide_init_workspace_execution(qtbot, tmp_path: Path) -> None:
    """Vérifie l'amorçage effectif du workspace sur disque et l'affichage du toast."""
    widget = MCPWorkspaceGuideWidget()
    qtbot.addWidget(widget)

    target_dir = tmp_path / "agent_project"
    widget.edit_workspace_path.setText(str(target_dir))

    idx_claude = widget.combo_agent_type.findData("claude")
    widget.combo_agent_type.setCurrentIndex(idx_claude)

    widget.btn_init_workspace.click()

    generated_file = target_dir / "CLAUDE.md"
    assert generated_file.exists()
    content = generated_file.read_text(encoding="utf-8")
    assert f"ankiforge-guide-version: sha256:{_GUIDE_VERSION_HASH}" in content

    # Le statut doit être immédiatement marqué à jour
    assert "À jour" in widget.badge_version_status.text()


def test_workspace_guide_check_version_status(qtbot, tmp_path: Path) -> None:
    """Vérifie les 3 états d'audit : absent, à jour, obsolète."""
    widget = MCPWorkspaceGuideWidget()
    qtbot.addWidget(widget)

    target_dir = tmp_path / "audit_test"
    target_dir.mkdir(parents=True, exist_ok=True)
    widget.edit_workspace_path.setText(str(target_dir))

    idx_gemini = widget.combo_agent_type.findData("gemini")
    widget.combo_agent_type.setCurrentIndex(idx_gemini)

    # 1. Fichier absent
    widget.btn_check_version.click()
    assert "Absent" in widget.badge_version_status.text() or "Non trouvé" in widget.badge_version_status.text()

    # 2. Fichier présent et à jour
    target_file = target_dir / "GEMINI.md"
    target_file.write_text(f"<!-- ankiforge-guide-version: sha256:{_GUIDE_VERSION_HASH} -->\nContenu", encoding="utf-8")
    widget.btn_check_version.click()
    assert "À jour" in widget.badge_version_status.text()

    # 3. Fichier présent mais obsolète
    target_file.write_text("<!-- ankiforge-guide-version: sha256:old_hash_12345 -->\nAncien contenu", encoding="utf-8")
    widget.btn_check_version.click()
    assert "Obsolète" in widget.badge_version_status.text()


def test_workspace_guide_browse_directory(qtbot, tmp_path: Path, monkeypatch) -> None:
    """Vérifie que le bouton Parcourir met à jour le champ de texte."""
    widget = MCPWorkspaceGuideWidget()
    qtbot.addWidget(widget)

    mock_dir = str(tmp_path / "choosen_dir")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: mock_dir)

    widget.btn_browse.click()
    assert widget.edit_workspace_path.text() == mock_dir


def test_workspace_guide_personas_display(qtbot) -> None:
    """Vérifie la liste des personas et la consultation de leur prompt système."""
    # Création d'une persona de test
    p = PersonaModel.create(
        name="Auditeur Wozniak Test",
        description="Vérifie la formulation atomique des cartes",
        system_prompt="Tu es un auditeur selon les 20 règles de Wozniak.",
        persona_type="mcp",
        allowed_tools=json.dumps(["audit_deck_wozniak"]),
    )

    widget = MCPWorkspaceGuideWidget()
    qtbot.addWidget(widget)

    widget.reload_personas()

    # Vérification que la persona apparaît dans la liste
    matching_items = widget.list_personas.findItems("Auditeur Wozniak Test", Qt.MatchFlag.MatchContains)
    assert len(matching_items) > 0

    # Sélection de l'item
    widget.list_personas.setCurrentItem(matching_items[0])

    # Le prompt système et la description doivent s'afficher dans le visualiseur
    assert "20 règles de Wozniak" in widget.edit_persona_prompt.toPlainText()
    assert "atomique" in widget.lbl_persona_description.text()

    # Nettoyage
    p.delete_instance()


def test_workspace_guide_copy_markdown(qtbot) -> None:
    """Vérifie la copie du Markdown compilé dans le presse-papiers."""
    widget = MCPWorkspaceGuideWidget()
    qtbot.addWidget(widget)

    widget.btn_copy_guide.click()
    clipboard = QGuiApplication.clipboard()
    assert clipboard is not None
    assert clipboard.text() == widget.current_guide_content


def test_workspace_guide_refresh_theme(qtbot) -> None:
    """Vérifie l'application sans crash des thèmes sombre et clair."""
    from ankiforge.ui.style_engine import StyleEngine

    widget = MCPWorkspaceGuideWidget()
    qtbot.addWidget(widget)

    engine = StyleEngine()
    dark_profile = engine.get_theme("dracula")
    widget.refresh_theme(dark_profile)

    light_profile = engine.get_theme("macos")
    widget.refresh_theme(light_profile)


def test_mcp_dashboard_integration_workspaces_tab(qtbot) -> None:
    """Vérifie l'intégration du 5e sous-onglet dans MCPServerDashboardWidget."""
    dashboard = MCPServerDashboardWidget(initial_status="running", initial_port=8765)
    qtbot.addWidget(dashboard)

    # 5 sous-onglets attendus
    assert dashboard.sub_tab_bar.count() == 5
    assert dashboard.sub_tab_bar._tabs[4].tab_id == "workspaces"
    assert "Guides" in dashboard.sub_tab_bar.tabText(4)

    # Bascule vers le 5e sous-onglet
    dashboard.sub_tab_bar.setCurrentIndex(4)
    assert dashboard.stacked_widget.currentIndex() == 4
    assert isinstance(dashboard.workspace_guide_widget, MCPWorkspaceGuideWidget)
