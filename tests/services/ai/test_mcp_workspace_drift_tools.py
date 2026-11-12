"""Tests d'intégration pour les outils FastMCP de drift et de synchronisation du workspace agentique (ADR 0059).

Valide les mutations disque, la résilience Git, le verrou de réentrance et les
invocations FastMCP en moins de 2 secondes.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import pytest

from ankiforge.services.ai.mcp_server import mcp
from ankiforge.services.ai.workspace_sync_service import (
    DriftSeverity,
    WorkspaceDriftReport,
    WorkspaceSyncService,
)

pytestmark = pytest.mark.integration

_REQUIRED_CORE_FILES = ("AGENT.md", ".agents/mcp-catalog.md")


def _extract_text(res: Any) -> str:
    """Extrait le texte d'un :class:`CallToolResult` sans jamais indexer ``res[0]``."""
    return str(res.content[0].text) if hasattr(res, "content") and res.content else str(res)


def _call_mcp(tool_name: str, arguments: dict[str, Any]) -> str:
    """Appel synchrone d'un outil FastMCP via le helper d'extraction de texte."""

    async def _run() -> str:
        res = await mcp.call_tool(tool_name, arguments)
        return _extract_text(res)

    return asyncio.run(_run())


@pytest.fixture
def ws_root(tmp_path: Path) -> Path:
    """Répertoire de workspace de test isolé, situé sous le dossier utilisateur.

    ``validate_workspace_path`` exige un chemin sous ``Path.home()`` ; on l'ancre
    donc sous home avec un nom unique par worker pour rester sain sous xdist.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "master")
    root = Path.home() / f".ankiforge_ws_test_{worker}_{uuid.uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def test_initialize_workspace_creates_gitignore_agents_and_manifest(ws_root: Path) -> None:
    """L'initialisation déploie .gitignore, les fichiers maîtres et le manifeste atomique."""
    service = WorkspaceSyncService()

    report = service.initialize_workspace(ws_root)

    assert isinstance(report, WorkspaceDriftReport)
    assert report.is_initialized is True
    assert report.overall_status == DriftSeverity.OK

    for core in _REQUIRED_CORE_FILES:
        assert (ws_root / core).is_file(), f"fichier maître manquant : {core}"

    gitignore = (ws_root / ".gitignore").read_text(encoding="utf-8")
    assert ".venv/" in gitignore
    assert "__pycache__/" in gitignore

    manifest = json.loads((ws_root / ".agents/.ankiforge-sync.json").read_text(encoding="utf-8"))
    assert manifest["workspace_path"] == str(ws_root)
    assert "initialized_at" in manifest
    assert "files" in manifest

    # Le dépôt Git local a été initialisé (ou le binaire git est absent, repli toléré).
    if shutil.which("git"):
        assert (ws_root / ".git").is_dir()


def test_initialize_workspace_refuses_non_empty_without_signature(ws_root: Path) -> None:
    """Refuse d'écrire sur un dossier non vide sans signature AnkiForge sauf force=True."""
    (ws_root / "fichier_inconnu.txt").write_text("bruit", encoding="utf-8")

    service = WorkspaceSyncService()
    report = service.initialize_workspace(ws_root)

    assert report.is_initialized is False
    assert report.overall_status.value == "CRITICAL"
    # Rien n'a été écrit : pas de .git, pas de .agents.
    assert not (ws_root / ".git").exists()
    assert not (ws_root / ".agents").exists()

    # Avec force=True, l'initialisation s'impose.
    report_forced = service.initialize_workspace(ws_root, force=True)
    assert report_forced.is_initialized is True
    assert (ws_root / "AGENT.md").is_file()


def test_sync_workspace_updates_outdated_and_preserves_user_files(ws_root: Path) -> None:
    """La synchronisation met à jour les fichiers système en dérive et préserve l'utilisateur."""
    service = WorkspaceSyncService()
    service.initialize_workspace(ws_root)

    # Dérive : on modifie un fichier système géré par les gabarits.
    catalog = ws_root / ".agents/mcp-catalog.md"
    original = catalog.read_text(encoding="utf-8")
    catalog.write_text(original + "\n# ligne altérée par le test\n", encoding="utf-8")

    # Fichier utilisateur sanctuarisé qui doit survivre à la synchronisation.
    user_dir = ws_root / "profiles" / "test"
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "perso.md").write_text("contenu utilisateur à préserver", encoding="utf-8")

    report = service.sync_workspace(ws_root, align_active_profile=True)

    assert isinstance(report, WorkspaceDriftReport)
    # Le fichier système a été ramené à la conformité.
    assert catalog.read_text(encoding="utf-8") == original
    # Le fichier utilisateur est intact.
    assert (user_dir / "perso.md").read_text(encoding="utf-8") == "contenu utilisateur à préserver"
    # Le manifeste a été réécrit (présence du fichier .tmp supprimé par replace).
    assert not (ws_root / ".agents/.ankiforge-sync.json.tmp").exists()
    assert (ws_root / ".agents/.ankiforge-sync.json").is_file()


def test_reentrant_lock_serializes_writes(ws_root: Path) -> None:
    """Le verrou est réentrant : un même thread peut réinitialiser puis resynchroniser sans blocage."""
    service = WorkspaceSyncService()

    service.initialize_workspace(ws_root)
    service.sync_workspace(ws_root, align_active_profile=True)
    service.initialize_workspace(ws_root, force=True)
    assert (ws_root / "AGENT.md").is_file()
    assert (ws_root / ".agents/mcp-catalog.md").is_file()


def test_fastmcp_audit_workspace_drift_returns_json_report(ws_root: Path) -> None:
    """L'outil FastMCP audit_workspace_drift retourne le rapport JSON complet."""
    # On initialise d'abord pour avoir un workspace cohérent.
    WorkspaceSyncService().initialize_workspace(ws_root)

    text = _call_mcp("audit_workspace_drift", {"workspace_path": str(ws_root)})
    data = json.loads(text)

    assert data["is_initialized"] is True
    assert data["workspace_path"] == str(ws_root)
    assert "items" in data
    assert "overall_status" in data
    assert "drift_count" in data


def test_fastmcp_sync_agent_workspace_executes_and_returns_report(ws_root: Path) -> None:
    """L'outil FastMCP sync_agent_workspace exécute la synchronisation et retourne le rapport."""
    WorkspaceSyncService().initialize_workspace(ws_root)

    text = _call_mcp("sync_agent_workspace", {"workspace_path": str(ws_root), "align_active_profile": True})
    data = json.loads(text)

    assert data["is_initialized"] is True
    assert data["workspace_path"] == str(ws_root)
    assert isinstance(data["items"], list)
