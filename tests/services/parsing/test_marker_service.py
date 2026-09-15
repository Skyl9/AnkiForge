"""Tests unitaires et de régression pour MarkerService."""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from ankiforge.services.parsing.marker_service import MarkerService


def test_is_python_compatible_accepts_valid_version() -> None:
    """Vérifie que _is_python_compatible accepte un interpréteur dans [3.10, 3.14)."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        with patch.object(Path, "exists", return_value=True):
            assert MarkerService._is_python_compatible("/usr/bin/python3.12") is True


def test_is_python_compatible_rejects_old_python_39() -> None:
    """Vérifie que _is_python_compatible rejette un Python 3.9 ou antérieur."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=1)
        with patch.object(Path, "exists", return_value=True):
            assert MarkerService._is_python_compatible("/usr/bin/python3.9") is False


def test_is_python_compatible_handles_nonexistent_or_crash() -> None:
    """Vérifie la robustesse si le binaire n'existe pas ou crashe."""
    assert MarkerService._is_python_compatible("/non/existent/python") is False

    with patch("subprocess.run", side_effect=OSError("Exec format error")), patch.object(Path, "exists", return_value=True):
        assert MarkerService._is_python_compatible("/corrupted/python") is False


def test_find_python_selects_first_compatible_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie que _find_python ignore les binaires incompatibles (ex: 3.9) et sélectionne le premier compatible."""
    monkeypatch.setattr("ankiforge.utils.environment.is_standalone_runtime", lambda: True)
    monkeypatch.setattr(MarkerService, "_find_uv", lambda: None)

    def mock_which(cmd: str) -> str | None:
        if cmd == "python3":
            return "/usr/bin/python3"  # Incompatible (3.9)
        if cmd == "python3.12":
            return "/usr/local/bin/python3.12"  # Compatible (3.12)
        return None

    monkeypatch.setattr("shutil.which", mock_which)

    def mock_is_compat(candidate: str | Path) -> bool:
        return "3.12" in str(candidate)

    monkeypatch.setattr(MarkerService, "_is_python_compatible", mock_is_compat)

    chosen = MarkerService._find_python()
    assert "3.12" in chosen


def test_find_python_raises_runtime_error_if_no_compatible_python(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie qu'une exception détaillée est levée si aucun Python compatible n'est présent."""
    monkeypatch.setattr("ankiforge.utils.environment.is_standalone_runtime", lambda: True)
    monkeypatch.setattr(MarkerService, "_find_uv", lambda: None)
    monkeypatch.setattr("shutil.which", lambda _: None)
    monkeypatch.setattr(MarkerService, "_is_python_compatible", lambda _: False)

    with pytest.raises(RuntimeError) as exc_info:
        MarkerService._find_python()

    assert "Aucun interpréteur Python compatible" in str(exc_info.value)
    assert "Python 3.9 n'est pas supporté" in str(exc_info.value)


def test_get_executable_rejects_incompatible_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie que get_executable renvoie None si le venv associé utilise un Python incompatible (< 3.10)."""
    tools_dir = tmp_path / "tools"
    venv_dir = tools_dir / "marker" / "venv"
    bin_dir = venv_dir / "bin"
    bin_dir.mkdir(parents=True)

    marker = bin_dir / "marker_single"
    marker.write_text("#!/bin/sh")
    marker.chmod(marker.stat().st_mode | stat.S_IXUSR)

    python = bin_dir / "python"
    python.write_text("#!/bin/sh")

    monkeypatch.setattr("ankiforge.services.parsing.marker_service.get_tools_search_dirs", lambda: [tools_dir])
    # Simuler un Python incompatible (ex: 3.9)
    monkeypatch.setattr(MarkerService, "_is_python_compatible", lambda _: False)

    assert MarkerService.get_executable() is None


def test_install_purges_incompatible_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie que install() purge automatiquement un venv existant s'il n'est pas compatible."""
    tools_dir = tmp_path / "tools"
    venv_dir = tools_dir / "marker" / "venv"
    bin_dir = venv_dir / "bin"
    bin_dir.mkdir(parents=True)

    # Ancien marker résiduel et ancien python d'un venv 3.9
    old_marker = bin_dir / "marker_single"
    old_marker.write_text("old 3.9 marker")
    old_python = bin_dir / "python"
    old_python.write_text("old 3.9 python")

    monkeypatch.setattr("ankiforge.services.parsing.marker_service.get_tools_search_dirs", lambda: [tools_dir])
    monkeypatch.setattr(MarkerService, "_find_python", lambda: "/usr/local/bin/python3.12")
    monkeypatch.setattr(MarkerService, "_find_uv", lambda: None)

    # Le venv existant est incompatible (3.9), mais le nouveau Python 3.12 sera compatible
    created_new_env = False

    def mock_is_compat(candidate: str | Path) -> bool:
        candidate_str = str(candidate)
        if "python3.12" in candidate_str:
            return True
        # L'interpréteur du venv n'est compatible que si le nouveau venv a été créé
        return created_new_env and candidate_str.endswith("bin/python")

    monkeypatch.setattr(MarkerService, "_is_python_compatible", mock_is_compat)

    class FakeProcess:
        stdout = ()

        def wait(self) -> int:
            return 0

    commands: list[list[str]] = []

    def fake_popen(command: list[str], **_: object) -> FakeProcess:
        nonlocal created_new_env
        created_new_env = True
        commands.append(command)
        # Recréation propre par venv
        bin_dir.mkdir(parents=True, exist_ok=True)
        (bin_dir / "python").write_text("#!/bin/sh")
        new_marker = bin_dir / "marker_single"
        new_marker.write_text("new 3.12 marker")
        new_marker.chmod(new_marker.stat().st_mode | stat.S_IXUSR)
        return FakeProcess()

    monkeypatch.setattr("ankiforge.services.parsing.marker_service.subprocess.Popen", fake_popen)

    executable = MarkerService.install()
    assert executable == bin_dir / "marker_single"
    assert executable.read_text() == "new 3.12 marker"
    # Vérifie que la commande venv a bien été appelée pour recréer l'environnement
    assert commands[0][:3] == ["/usr/local/bin/python3.12", "-m", "venv"]


def test_marker_service_package_pinned_below_2() -> None:
    """Garantit que la version de Marker demandée est verrouillée sur la branche autonome < 2.0.0."""
    assert "<2.0.0" in MarkerService.PACKAGE_NAME
    assert "marker-pdf" in MarkerService.PACKAGE_NAME


def test_is_venv_compatible_rejects_marker_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie que _is_venv_compatible rejette un venv si marker-pdf 2.x (exigeant llama-server) y est installé."""
    venv_dir = tmp_path / "venv"
    bin_dir = venv_dir / "bin"
    bin_dir.mkdir(parents=True)

    marker = bin_dir / "marker_single"
    marker.write_text("#!/bin/sh")
    marker.chmod(marker.stat().st_mode | stat.S_IXUSR)

    python = bin_dir / "python"
    python.write_text("#!/bin/sh")

    monkeypatch.setattr(MarkerService, "_is_python_compatible", lambda _: True)

    with patch("subprocess.run") as mock_run:
        # Code 1 : la version de marker est >= 2
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=1)
        assert MarkerService._is_venv_compatible(venv_dir) is False

        # Code 0 : la version de marker est < 2 (autonome)
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        assert MarkerService._is_venv_compatible(venv_dir) is True
