"""Tests unitaires pour les outils MCP d'artefacts d'échange agent (anti-troncature).

Couvre :
- get_artifacts_dir (résolution et création du dossier artifacts par profil)
- write_mcp_artifact (écriture UTF-8, assainissement du nom, retour référence vérifiée)
- read_mcp_artifact (relecture sécurisée, plafonnement max_bytes)
- Ressource MCP artifact://{filename} (lecture standardisée via le handler)
- Enregistrement des outils sur le serveur FastMCP et dans DEFAULT_CONSULTANT_TOOLS
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from ankiforge.services.ai.mcp_server import mcp
from ankiforge.services.ai.mcp_tool_registry import DEFAULT_CONSULTANT_TOOLS, MCPToolRegistry
from ankiforge.utils.paths import get_artifacts_dir

pytestmark = pytest.mark.integration


def _extract_text(res: object) -> str:
    return str(res.content[0].text) if hasattr(res, "content") and res.content else str(res)


@pytest.fixture
def artifacts_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isole le dossier artifacts sur un tmp_path avec un profil dédié."""
    monkeypatch.setenv("ANKIFORGE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("ankiforge.utils.paths.get_active_profile", lambda: "profil_artefacts")
    directory = get_artifacts_dir()
    assert directory == tmp_path / "profiles" / "profil_artefacts" / "artifacts"
    return directory


def test_get_artifacts_dir_creates_profile_directory(artifacts_dir: Path) -> None:
    """Le répertoire artifacts du profil est créé automatiquement."""
    assert artifacts_dir.is_dir()
    assert artifacts_dir == get_artifacts_dir(profile_name="profil_artefacts")


def test_get_artifacts_dir_profil_par_defaut(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Sans nom de profil, le profil actif est utilisé."""
    monkeypatch.setenv("ANKIFORGE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("ankiforge.utils.paths.get_active_profile", lambda: "autre_profil")
    assert get_artifacts_dir() == tmp_path / "profiles" / "autre_profil" / "artifacts"


def test_write_mcp_artifact_ecrit_et_retourne_reference(artifacts_dir: Path) -> None:
    """Écriture UTF-8 et retour du dictionnaire de référence vérifiée."""
    contenu = "Ligne une\nLigne deux\nLigne trois"
    res = MCPToolRegistry.write_mcp_artifact("script.py", contenu, mime_type="text/x-python")
    data = json.loads(res)
    assert data["status"] == "success"
    assert data["filename"] == "script.py"
    assert data["file_path"] == str(artifacts_dir / "script.py")
    assert data["file_uri"].startswith("file://")
    assert data["size_bytes"] == len(contenu.encode("utf-8"))
    assert data["lines_count"] == 3
    assert data["sha256"] == hashlib.sha256(contenu.encode("utf-8")).hexdigest()
    assert (artifacts_dir / "script.py").read_text(encoding="utf-8") == contenu


def test_write_mcp_artifact_nom_invalide_rejete(artifacts_dir: Path) -> None:
    """Les noms '.' / '..' / vide sont rejetés sans écriture."""
    for mauvais in (".", "..", ""):
        res = MCPToolRegistry.write_mcp_artifact(mauvais, "contenu")
        assert json.loads(res)["status"] == "error"
    assert not any(artifacts_dir.iterdir())


def test_write_mcp_artifact_bloque_traversement_repertoire(artifacts_dir: Path) -> None:
    """Une traversée '../' est assainie : le fichier reste dans artifacts/."""
    res = MCPToolRegistry.write_mcp_artifact("../../../etc/passwd", "x")
    data = json.loads(res)
    assert data["status"] == "success"
    assert data["filename"] == "passwd"
    assert Path(data["file_path"]).resolve().is_relative_to(artifacts_dir)
    assert (artifacts_dir / "passwd").exists()
    assert (artifacts_dir.parent / "passwd").exists() is False


def test_read_mcp_artifact_lecture_et_retourne_contenu(artifacts_dir: Path) -> None:
    """Relecture d'un artefact précédemment écrit."""
    contenu = "Contenu de l'artefact d'echange entre agents."
    MCPToolRegistry.write_mcp_artifact("note.md", contenu)
    res = MCPToolRegistry.read_mcp_artifact("note.md")
    data = json.loads(res)
    assert data["status"] == "success"
    assert data["filename"] == "note.md"
    assert data["content"] == contenu
    assert data["size_bytes"] == len(contenu.encode("utf-8"))
    assert data["read_bytes"] == len(contenu.encode("utf-8"))
    assert data["truncated"] is False


def test_read_mcp_artifact_plafonne_max_bytes(artifacts_dir: Path) -> None:
    """La lecture est bornee a max_bytes avec drapeau truncated."""
    contenu = "A" * 1000
    MCPToolRegistry.write_mcp_artifact("long.txt", contenu)
    res = MCPToolRegistry.read_mcp_artifact("long.txt", max_bytes=100)
    data = json.loads(res)
    assert data["status"] == "success"
    assert data["read_bytes"] == 100
    assert data["content"] == contenu[:100]
    assert data["size_bytes"] == len(contenu.encode("utf-8"))
    assert data["truncated"] is True


def test_read_mcp_artifact_inexistant_rejete(artifacts_dir: Path) -> None:
    """La lecture d'un artefact absent retourne une erreur."""
    res = MCPToolRegistry.read_mcp_artifact("inconnu.txt")
    assert json.loads(res)["status"] == "error"


def test_ressource_artifact_lecture_via_handler(artifacts_dir: Path) -> None:
    """Le handler de la ressource artifact://{filename} renvoie le contenu."""
    from ankiforge.services.ai.mcp_server import get_artifact_resource

    contenu = "Contenu accessible par la ressource MCP."
    MCPToolRegistry.write_mcp_artifact("fichier.txt", contenu)
    res = get_artifact_resource("fichier.txt")
    data = json.loads(res)
    assert data["status"] == "success"
    assert data["content"] == contenu


def test_outils_artifacts_enregistres_serveur() -> None:
    """Les outils sont declares sur le serveur FastMCP et dans DEFAULT_CONSULTANT_TOOLS."""
    noms_default = [t["function"]["name"] for t in DEFAULT_CONSULTANT_TOOLS]
    assert "write_mcp_artifact" in noms_default
    assert "read_mcp_artifact" in noms_default

    outils = mcp._tool_manager.list_tools()
    noms_serveur = {o.name for o in outils}
    assert "write_mcp_artifact" in noms_serveur
    assert "read_mcp_artifact" in noms_serveur


def test_write_then_read_via_mcp_call_tool(artifacts_dir: Path) -> None:
    """Appel bout en bout via mcp.call_tool (Write puis Read)."""

    async def _run() -> None:
        contenu = "Contenu volumineux de l'artefact d'echange agent."
        res_write = await mcp.call_tool(
            "write_mcp_artifact",
            {"filename": "note.md", "content": contenu, "mime_type": "text/markdown"},
        )
        data_write = json.loads(_extract_text(res_write))
        assert data_write["status"] == "success"
        assert data_write["sha256"] == hashlib.sha256(contenu.encode("utf-8")).hexdigest()

        res_read = await mcp.call_tool(
            "read_mcp_artifact",
            {"filename": "note.md", "max_bytes": 10000},
        )
        data_read = json.loads(_extract_text(res_read))
        assert data_read["status"] == "success"
        assert data_read["content"] == contenu

    asyncio.run(_run())
