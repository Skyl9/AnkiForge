"""Tests unitaires du moteur d'audit de dérive du workspace agentique (ADR 0059).

Cible : < 1,5 seconde, sans BDD ni GUI. Les workspaces de test sont créés sous
le dossier utilisateur (``home``) pour respecter la règle de confinement de
:func:`validate_workspace_path`.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from ankiforge.services.ai.workspace_sync_service import (
    _TEMPLATE_TARGETS,
    DriftCategory,
    DriftItem,
    DriftSeverity,
    WorkspaceDriftReport,
    WorkspaceSyncService,
    compute_content_hash,
    compute_file_hash,
    validate_workspace_path,
)

pytestmark = pytest.mark.unit

_HOME_TEST_ROOT = Path.home() / ".ankiforge-test-workspaces"


@pytest.fixture
def workspace():
    """Crée un répertoire de workspace temporaire sous le dossier utilisateur."""
    name = f"test-ws-{uuid.uuid4().hex[:8]}"
    path = _HOME_TEST_ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _write_conformant_workspace(workspace: Path, service: WorkspaceSyncService) -> None:
    """Écrit tous les fichiers cibles rendus par le service dans le workspace."""
    for template_rel, target_rel in _TEMPLATE_TARGETS.items():
        target_path = workspace / target_rel
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(service._render(template_rel), encoding="utf-8")


# ---------------------------------------------------------------------------
# compute_content_hash
# ---------------------------------------------------------------------------


def test_compute_content_hash_deterministic():
    """Même contenu → même empreinte."""
    h1 = compute_content_hash("Bonjour le monde\n")
    h2 = compute_content_hash("Bonjour le monde\n")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_compute_content_hash_normalizes_crlf():
    """Les sauts de ligne CRLF et LF produisent la même empreinte."""
    h_crlf = compute_content_hash("Ligne 1\r\nLigne 2\r\n")
    h_lf = compute_content_hash("Ligne 1\nLigne 2\n")
    assert h_crlf == h_lf


def test_compute_content_hash_sensitive_to_content():
    """Contenu différent → empreinte différente."""
    assert compute_content_hash("a") != compute_content_hash("b")


def test_compute_file_hash_none_when_missing(tmp_path):
    """Fichier absent → None."""
    assert compute_file_hash(tmp_path / "inexistant.md") is None


# ---------------------------------------------------------------------------
# validate_workspace_path
# ---------------------------------------------------------------------------


def test_validate_workspace_path_accepts_under_home():
    """Un répertoire sous le dossier utilisateur est accepté."""
    path = _HOME_TEST_ROOT / "accepted"
    path.mkdir(parents=True, exist_ok=True)
    try:
        resolved = validate_workspace_path(str(path))
        assert resolved == path.resolve()
        assert resolved.is_relative_to(Path.home())
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_validate_workspace_path_rejects_root():
    assert _raises(validate_workspace_path, "/")


def test_validate_workspace_path_rejects_system_roots():
    for root in ("/System", "/etc", "/usr", "/bin", "/sbin"):
        assert _raises(validate_workspace_path, root)


def test_validate_workspace_path_rejects_non_home():
    """Un répertoire hors home (ex: /tmp) est refusé."""
    assert _raises(validate_workspace_path, "/tmp")


def _raises(func, *args):
    try:
        func(*args)
    except ValueError:
        return True
    return False


# ---------------------------------------------------------------------------
# WorkspaceSyncService construction
# ---------------------------------------------------------------------------


def test_service_default_profile_override():
    service = WorkspaceSyncService(active_profile="default")
    assert service.active_profile == "default"
    assert isinstance(service.mcp_tools, list)


def test_service_fallback_to_get_active_profile(monkeypatch):
    import ankiforge.services.ai.workspace_sync_service as wss_module

    monkeypatch.setattr(wss_module, "get_active_profile", lambda: "profil_fallback")
    service = WorkspaceSyncService(mcp_tools=[])
    assert service.active_profile == "profil_fallback"
    assert service.mcp_tools == []


def test_service_uses_overrides():
    service = WorkspaceSyncService(mcp_tools=["Zeta", "alpha", "Beta"], active_profile="mon_profil")
    assert service.active_profile == "mon_profil"
    assert service.mcp_tools == ["Zeta", "alpha", "Beta"]


def test_mcp_tools_sorted_case_insensitive(monkeypatch):
    """L'introspection trie les outils MCP lexicographiquement, insensible à la casse."""
    import ankiforge.services.ai.mcp_server as mcp_server

    class _FakeTool:
        def __init__(self, name: str) -> None:
            self.name = name

    monkeypatch.setattr(
        mcp_server.mcp._tool_manager,
        "list_tools",
        lambda: [_FakeTool("Zeta"), _FakeTool("alpha"), _FakeTool("Beta")],
    )
    service = WorkspaceSyncService()
    assert service.mcp_tools == ["alpha", "Beta", "Zeta"]


# ---------------------------------------------------------------------------
# audit_workspace
# ---------------------------------------------------------------------------


def test_audit_missing_root_critical(workspace):
    """Workspace absent → CRITICAL, non initialisé."""
    missing = workspace / "n'existe pas"
    service = WorkspaceSyncService(active_profile="mon_profil")
    report = service.audit_workspace(missing)
    assert isinstance(report, WorkspaceDriftReport)
    assert report.is_initialized is False
    assert report.overall_status == DriftSeverity.CRITICAL
    assert report.drift_count == 1
    assert report.items[0].severity == DriftSeverity.CRITICAL
    assert report.items[0].category == DriftCategory.STRUCTURE


def test_audit_empty_workspace_critical(workspace):
    """Workspace vide → fichiers maîtres manquants (CRITICAL), non initialisé."""
    service = WorkspaceSyncService(active_profile="mon_profil")
    report = service.audit_workspace(workspace)
    assert report.is_initialized is False
    assert report.overall_status == DriftSeverity.CRITICAL
    assert report.drift_count == len(_TEMPLATE_TARGETS)
    missing = {i.relative_path for i in report.items if i.severity == DriftSeverity.CRITICAL}
    assert "AGENT.md" in missing
    assert ".agents/mcp-catalog.md" in missing


def test_audit_conformant_workspace_ok(workspace):
    """Workspace conforme aux gabarits → tout OK, drift nul, initialisé."""
    service = WorkspaceSyncService(mcp_tools=["alpha", "Beta"], active_profile="mon_profil")
    _write_conformant_workspace(workspace, service)
    report = service.audit_workspace(workspace)
    assert report.is_initialized is True
    assert report.overall_status == DriftSeverity.OK
    assert report.drift_count == 0
    assert all(item.severity == DriftSeverity.OK for item in report.items)
    assert report.active_profile_name == "mon_profil"


def test_audit_modified_file_outdated(workspace):
    """Fichier modifié → OUTDATED pour ce fichier uniquement."""
    service = WorkspaceSyncService(mcp_tools=["alpha", "Beta"], active_profile="mon_profil")
    _write_conformant_workspace(workspace, service)
    readme = workspace / "README.md"
    readme.write_text("Contenu altéré qui ne correspond pas au gabarit.\n", encoding="utf-8")
    report = service.audit_workspace(workspace)
    assert report.overall_status == DriftSeverity.OUTDATED
    assert report.drift_count == 1
    outdated = [i for i in report.items if i.severity == DriftSeverity.OUTDATED]
    assert len(outdated) == 1
    assert outdated[0].relative_path == "README.md"
    assert outdated[0].local_hash is not None
    assert outdated[0].base_hash is not None
    assert outdated[0].target_hash is not None
    assert outdated[0].local_hash != outdated[0].target_hash


def test_audit_missing_core_file_critical(workspace):
    """Fichier maître manquant → CRITICAL et non initialisé."""
    service = WorkspaceSyncService(mcp_tools=["alpha"], active_profile="mon_profil")
    _write_conformant_workspace(workspace, service)
    (workspace / "AGENT.md").unlink()
    report = service.audit_workspace(workspace)
    assert report.is_initialized is False
    assert report.overall_status == DriftSeverity.CRITICAL
    assert any(i.relative_path == "AGENT.md" and i.severity == DriftSeverity.CRITICAL for i in report.items)


def test_audit_protected_dirs_sanctuarized(workspace):
    """Dossiers profiles/ et _shared_models/ → PROTECTED, non comptés comme dérive."""
    service = WorkspaceSyncService(mcp_tools=["alpha"], active_profile="mon_profil")
    _write_conformant_workspace(workspace, service)
    (workspace / "profiles" / "mon_profil" / "ankiforge.db").parent.mkdir(parents=True, exist_ok=True)
    (workspace / "_shared_models" / "card.html").parent.mkdir(parents=True, exist_ok=True)
    report = service.audit_workspace(workspace)
    protected = [i for i in report.items if i.is_user_protected]
    assert any(i.relative_path == "profiles" for i in protected)
    assert any(i.relative_path == "_shared_models" for i in protected)
    assert all(i.severity == DriftSeverity.PROTECTED for i in protected)
    assert all(i.category == DriftCategory.USER_CONTEXT for i in protected)
    # Les dossiers protégés ne comptent pas dans le décompte de dérive.
    assert report.drift_count == 0


def test_audit_symlink_sanctuarized(workspace, tmp_path):
    """Lien symbolique → PROTECTED, is_user_protected True."""
    service = WorkspaceSyncService(mcp_tools=["alpha"], active_profile="mon_profil")
    _write_conformant_workspace(workspace, service)
    target = tmp_path / "cible.md"
    target.write_text("cible\n", encoding="utf-8")
    (workspace / "AGENT.md").unlink()
    (workspace / "AGENT.md").symlink_to(target)
    report = service.audit_workspace(workspace)
    symlinks = [i for i in report.items if i.relative_path == "AGENT.md"]
    assert len(symlinks) == 1
    assert symlinks[0].severity == DriftSeverity.PROTECTED
    assert symlinks[0].is_user_protected is True


def test_audit_detected_profile_name(workspace):
    """Le profil actif déclaré dans le workspace est détecté."""
    service = WorkspaceSyncService(mcp_tools=["alpha"], active_profile="mon_profil")
    _write_conformant_workspace(workspace, service)
    profile_path = workspace / ".agents/active-profile.md"
    content = profile_path.read_text(encoding="utf-8")
    assert "Profil actif : mon_profil" in content
    profile_path.write_text(content.replace("mon_profil", "profil_detecte"), encoding="utf-8")
    report = service.audit_workspace(workspace)
    assert report.detected_profile_name == "profil_detecte"
    # active_profile_name reflète le profil de la session AnkiForge, pas le fichier.
    assert report.active_profile_name == "mon_profil"


# ---------------------------------------------------------------------------
# sérialisation
# ---------------------------------------------------------------------------


def test_report_to_dict_and_json(workspace):
    """to_dict / to_json produisent une représentation cohérente et sérialisable."""
    service = WorkspaceSyncService(mcp_tools=["x"], active_profile="mon_profil")
    _write_conformant_workspace(workspace, service)
    report = service.audit_workspace(workspace)
    data = report.to_dict()
    assert data["workspace_path"] == str(workspace.resolve())
    assert data["is_initialized"] is True
    assert data["overall_status"] == "OK"
    assert data["active_profile_name"] == "mon_profil"
    assert data["drift_count"] == 0
    assert isinstance(data["items"], list)
    json_str = report.to_json()
    assert json_str.startswith("{")
    assert '"overall_status": "OK"' in json_str


# ---------------------------------------------------------------------------
# énumérations et dataclass
# ---------------------------------------------------------------------------


def test_drift_severity_values():
    assert {e.value for e in DriftSeverity} == {
        "CRITICAL",
        "DESYNC",
        "OUTDATED",
        "CUSTOMIZED",
        "PROTECTED",
        "OK",
    }


def test_drift_category_values():
    assert {e.value for e in DriftCategory} == {
        "STRUCTURE",
        "CORE_SYSTEM",
        "ACTIVE_PROFILE",
        "MCP_CATALOG",
        "SKILLS",
        "USER_CONTEXT",
    }


def test_drift_item_defaults():
    item = DriftItem(
        relative_path="AGENT.md",
        category=DriftCategory.CORE_SYSTEM,
        severity=DriftSeverity.OK,
        message="ok",
    )
    assert item.local_hash is None
    assert item.base_hash is None
    assert item.target_hash is None
    assert item.is_user_protected is False
