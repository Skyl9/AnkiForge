"""Tests headless pytest-qt pour la refonte adaptative de MCPWorkspaceGuideWidget.

Cible : tests/ui/test_mcp_workspace_guide_widget.py
Commande ciblée : uv run pytest tests/ui/test_mcp_workspace_guide_widget.py
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from ankidraft.services.ai.workspace_sync_service import (
    _TEMPLATE_TARGETS,
    WorkspaceSyncService,
)
from ankidraft.ui.views.consultant_view.widgets.mcp_workspace_guide_widget import (
    MCPWorkspaceGuideWidget,
)

pytestmark = pytest.mark.ui

_HOME_TEST_ROOT = Path.home() / ".ankidraft-test-workspaces-ui"


@pytest.fixture
def ws_path() -> Path:
    """Crée un répertoire de workspace temporaire sous le dossier utilisateur (confinement validate_workspace_path)."""
    name = f"ws-{uuid.uuid4().hex[:8]}"
    path = _HOME_TEST_ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def service() -> WorkspaceSyncService:
    """Service sans introspection MCP (tests déterministes et rapides)."""
    return WorkspaceSyncService(mcp_tools=[], active_profile="profil_test")


def _write_conformant_workspace(workspace: Path, service: WorkspaceSyncService) -> None:
    for template_rel, target_rel in _TEMPLATE_TARGETS.items():
        target_path = workspace / target_rel
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(service._render(template_rel), encoding="utf-8")


def test_qsettings_persistence_across_instances(qtbot, ws_path: Path, service: WorkspaceSyncService) -> None:
    """Le chemin de workspace est mémorisé dans QSettings et rechargé à l'instanciation."""
    widget = MCPWorkspaceGuideWidget(service=service)
    qtbot.addWidget(widget)
    widget.edit_workspace_path.setText(str(ws_path))
    widget.edit_workspace_path.editingFinished.emit()
    widget.btn_verify_drift.click()

    restored = MCPWorkspaceGuideWidget(service=service)
    qtbot.addWidget(restored)
    assert restored.edit_workspace_path.text() == str(ws_path)


def test_qsettings_fallback_path(qtbot, service: WorkspaceSyncService) -> None:
    """Sans chemin mémorisé, repli sur le répertoire personnel de l'utilisateur."""
    widget = MCPWorkspaceGuideWidget(service=service)
    qtbot.addWidget(widget)
    expected = str(Path.home() / "ankiforge_agentique") if (Path.home() / "ankiforge_agentique").exists() else str(Path.home())
    assert widget.edit_workspace_path.text() == expected


def test_verify_drift_updates_badge_and_splitter(qtbot, ws_path: Path, service: WorkspaceSyncService) -> None:
    """Le clic sur Vérifier le drift met à jour le hero badge, la matrice et le splitteur."""
    widget = MCPWorkspaceGuideWidget(service=service)
    qtbot.addWidget(widget)
    widget.edit_workspace_path.setText(str(ws_path))
    widget.resize(1200, 800)

    size_calls: list[list[int]] = []
    with patch.object(widget.splitter, "setSizes", side_effect=lambda s: size_calls.append(list(s))):
        widget.btn_verify_drift.click()

    assert "Non Initialisé" in widget.hero_badge.text()
    assert widget.matrix.rowCount() == 6
    # Déjà en not_initialisé depuis le constructeur : aucune transition de splitteur.
    assert size_calls == []

    _write_conformant_workspace(ws_path, service)
    size_calls.clear()
    with patch.object(widget.splitter, "setSizes", side_effect=lambda s: size_calls.append(list(s))):
        widget.btn_verify_drift.click()

    assert "Synchronisé" in widget.hero_badge.text()
    assert [450, 550] in size_calls


def test_splitter_adaptive_layout_transitions(qtbot, service: WorkspaceSyncService) -> None:
    """_update_adaptive_layout applique les ratios par état et ne relaye pas un état identique."""
    widget = MCPWorkspaceGuideWidget(service=service)
    qtbot.addWidget(widget)

    size_calls: list[list[int]] = []
    with patch.object(widget.splitter, "setSizes", side_effect=lambda s: size_calls.append(list(s))):
        widget._update_adaptive_layout("drift_detected")
        widget._update_adaptive_layout("drift_detected")
        widget._update_adaptive_layout("synchronized")
        widget._update_adaptive_layout("not_initialized")

    assert size_calls == [[500, 500], [450, 550], [650, 350]]


def test_init_and_sync_buttons(qtbot, ws_path: Path, service: WorkspaceSyncService) -> None:
    """Les boutons Amorcer et Resynchroniser pilotent le service et actualisent l'UI."""
    widget = MCPWorkspaceGuideWidget(service=service)
    qtbot.addWidget(widget)
    widget.edit_workspace_path.setText(str(ws_path))
    widget.resize(1200, 800)

    widget.btn_init_workspace.click()
    assert "Synchronisé" in widget.hero_badge.text()

    widget.btn_sync_workspace.click()
    assert "Synchronisé" in widget.hero_badge.text()


def test_matrix_rows_reflect_report(qtbot, ws_path: Path, service: WorkspaceSyncService) -> None:
    """La matrice de conformité affiche une ligne par composant du rapport."""
    widget = MCPWorkspaceGuideWidget(service=service)
    qtbot.addWidget(widget)
    widget.edit_workspace_path.setText(str(ws_path))
    widget.resize(1200, 800)
    widget.btn_verify_drift.click()

    assert widget.matrix.rowCount() == 6
    labels = [widget.matrix.item(row, 0).text() for row in range(widget.matrix.rowCount())]
    assert "Structure" in labels
    assert "Profil actif" in labels
    assert "Catalogue FastMCP" in labels
    assert "Conventions" in labels
    assert "Compétences" in labels
    assert "Éléments utilisateur protégés" in labels


def test_cleanup_qt_widgets(qtbot, service: WorkspaceSyncService) -> None:
    """Le widget se nettoie sans verrou résiduel (mock_db / cleanup_qt_widgets)."""
    widget = MCPWorkspaceGuideWidget(service=service)
    qtbot.addWidget(widget)
    widget.edit_workspace_path.setText(str(Path.home() / ".ankidraft-test-workspaces-ui"))
    widget.btn_verify_drift.click()
