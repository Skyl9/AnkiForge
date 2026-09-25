"""
Tests unitaires et d'intégration CLI pour le mode serveur MCP headless d'AnkiForge (MCP-02).
"""

from __future__ import annotations

import json
import signal
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from ankiforge.__main__ import main, parse_cli_args
from ankiforge.services.ai.mcp_cli import resolve_target_profile, run_mcp_server_cli
from ankiforge.services.profile_manager import ProfileManager
from ankiforge.utils.paths import get_active_profile


@pytest.mark.unit
def test_parse_cli_args_defaults() -> None:
    """Vérifie les valeurs par défaut des arguments CLI."""
    known, extra = parse_cli_args([])
    assert known.help is False
    assert known.version is False
    assert known.smoke_test is False
    assert known.mcp_server is False
    assert known.port == 8765
    assert known.profile is None
    assert extra == []


@pytest.mark.unit
def test_parse_cli_args_mcp_server_flags() -> None:
    """Vérifie la reconnaissance des drapeaux --mcp-server, --port et --profile."""
    argv = ["--mcp-server", "--port", "9123", "--profile", "Medecine"]
    known, extra = parse_cli_args(argv)
    assert known.mcp_server is True
    assert known.port == 9123
    assert known.profile == "Medecine"
    assert extra == []


@pytest.mark.unit
def test_parse_cli_args_short_flags_and_extra() -> None:
    """Vérifie la gestion des flags courts et des arguments inconnus (ex. Qt/OS)."""
    known, extra = parse_cli_args(["-h", "-platform", "offscreen"])
    assert known.help is True
    assert extra == ["-platform", "offscreen"]


@pytest.mark.unit
def test_cli_help_documents_mcp_server_options(capsys: pytest.CaptureFixture[str]) -> None:
    """Vérifie que 'ankiforge --help' documente explicitement --mcp-server, --port et --profile."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "--mcp-server" in captured.out
    assert "--port <port>" in captured.out
    assert "--profile <nom>" in captured.out


@pytest.mark.unit
def test_cli_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """Vérifie le fonctionnement du drapeau --version."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "AnkiForge v" in captured.out


@pytest.mark.unit
def test_cli_smoke_test_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """Vérifie le fonctionnement du drapeau --smoke-test."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--smoke-test"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Smoke Test Passed" in captured.out


@pytest.mark.unit
def test_cli_invalid_port_exits_code_2(capsys: pytest.CaptureFixture[str]) -> None:
    """Vérifie qu'un port hors de la plage 1-65535 déclenche un code de sortie 2 et un message d'erreur."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--mcp-server", "--port", "99999"])
    assert exc_info.value.code == 2

    captured = capsys.readouterr()
    assert "Erreur" in captured.err
    assert "99999" in captured.err


@pytest.mark.unit
def test_resolve_target_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie la logique de résolution du profil cible avec repli sécurisé."""
    monkeypatch.setattr(ProfileManager, "PROFILES_DIR", tmp_path / "profiles")

    # 1. Spécification explicite
    assert resolve_target_profile("custom_prof") == "custom_prof"

    # 2. Aucun profil existant -> fallback "default"
    assert resolve_target_profile(None) == "default"

    # 3. Création de profils et fallback vers premier ou 'default'
    pm = ProfileManager()
    pm.create_profile("first_profile")
    pm.create_profile("second_profile")
    assert resolve_target_profile(None) in ("first_profile", "second_profile")

    pm.create_profile("default")
    assert resolve_target_profile(None) == "default"


@pytest.mark.unit
def test_run_mcp_server_cli_initializes_db_and_banner(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vérifie l'initialisation BDD, l'affichage de la bannière et l'arrêt propre via stop_event."""
    monkeypatch.setattr("ankiforge.services.ai.mcp_cli.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(ProfileManager, "PROFILES_DIR", tmp_path / "profiles")

    stop_event = threading.Event()

    class DummyDaemon:
        def __init__(self, host: str = "127.0.0.1", base_port: int = 8765, data_dir: Path | None = None) -> None:
            self._host = host
            self._port = base_port
            self._data_dir = data_dir or tmp_path
            self._is_running = False
            self.stop_called = False

        @property
        def is_running(self) -> bool:
            return self._is_running

        @property
        def port(self) -> int:
            return self._port

        @property
        def sse_url(self) -> str:
            return f"http://{self._host}:{self._port}/sse"

        @property
        def token_file(self) -> Path:
            return self._data_dir / "mcp_auth_token"

        @property
        def state_file(self) -> Path:
            return self._data_dir / "mcp_server.json"

        def start(self, timeout: float = 5.0) -> bool:
            self._is_running = True

            def _trigger_stop() -> None:
                time.sleep(0.05)
                stop_event.set()

            threading.Thread(target=_trigger_stop, daemon=True).start()
            return True

        def stop(self, timeout: float = 5.0) -> None:
            self._is_running = False
            self.stop_called = True

    exit_code = run_mcp_server_cli(
        port=8765,
        profile_name="cli_test_profile",
        stop_event=stop_event,
        daemon_class=DummyDaemon,  # type: ignore[arg-type]
    )

    assert exit_code == 0
    assert get_active_profile() == "cli_test_profile"

    captured = capsys.readouterr()
    assert "AnkiForge MCP Server" in captured.out
    assert "Profil actif        : cli_test_profile" in captured.out
    assert "Point d'entrée SSE  : http://127.0.0.1:8765/sse" in captured.out
    assert "Serveur MCP AnkiForge arrêté avec succès." in captured.out


@pytest.mark.unit
def test_run_mcp_server_cli_startup_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vérifie le comportement en cas d'échec de démarrage du daemon (code de sortie 1)."""
    monkeypatch.setattr("ankiforge.services.ai.mcp_cli.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(ProfileManager, "PROFILES_DIR", tmp_path / "profiles")

    class FailingDaemon:
        def __init__(self, host: str = "127.0.0.1", base_port: int = 8765, data_dir: Path | None = None) -> None:
            pass

        def start(self, timeout: float = 5.0) -> bool:
            return False

        def stop(self, timeout: float = 5.0) -> None:
            pass

    exit_code = run_mcp_server_cli(
        port=8765,
        profile_name="failing_prof",
        daemon_class=FailingDaemon,  # type: ignore[arg-type]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Erreur : Impossible de démarrer le serveur MCP" in captured.err


@pytest.mark.unit
def test_run_mcp_server_cli_unexpected_daemon_death(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vérifie qu'un crash inattendu du thread daemon est détecté et renvoie le code 1."""
    monkeypatch.setattr("ankiforge.services.ai.mcp_cli.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(ProfileManager, "PROFILES_DIR", tmp_path / "profiles")

    class CrashingDaemon:
        def __init__(self, host: str = "127.0.0.1", base_port: int = 8765, data_dir: Path | None = None) -> None:
            self._running = True

        @property
        def is_running(self) -> bool:
            return self._running

        @property
        def port(self) -> int:
            return 8765

        @property
        def sse_url(self) -> str:
            return "http://127.0.0.1:8765/sse"

        @property
        def token_file(self) -> Path:
            return tmp_path / "mcp_auth_token"

        @property
        def state_file(self) -> Path:
            return tmp_path / "mcp_server.json"

        def start(self, timeout: float = 5.0) -> bool:
            def _crash() -> None:
                time.sleep(0.05)
                self._running = False

            threading.Thread(target=_crash, daemon=True).start()
            return True

        def stop(self, timeout: float = 5.0) -> None:
            self._running = False

    exit_code = run_mcp_server_cli(
        port=8765,
        profile_name="crash_test",
        daemon_class=CrashingDaemon,  # type: ignore[arg-type]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Le serveur MCP s'est arrêté de manière inattendue" in captured.err


@pytest.mark.unit
def test_run_mcp_server_cli_signal_interception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vérifie l'interception de signaux système (SIGINT/SIGTERM) et l'arrêt ordonné."""
    monkeypatch.setattr("ankiforge.services.ai.mcp_cli.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(ProfileManager, "PROFILES_DIR", tmp_path / "profiles")

    signal_handlers: dict[int, Any] = {}

    def mock_signal(sig: int, handler: Any) -> Any:
        signal_handlers[sig] = handler
        return signal.SIG_DFL

    monkeypatch.setattr(signal, "signal", mock_signal)

    class FastDaemon:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.stopped = False

        @property
        def is_running(self) -> bool:
            return not self.stopped

        @property
        def port(self) -> int:
            return 8765

        @property
        def sse_url(self) -> str:
            return "http://127.0.0.1:8765/sse"

        @property
        def token_file(self) -> Path:
            return tmp_path / "mcp_auth_token"

        @property
        def state_file(self) -> Path:
            return tmp_path / "mcp_server.json"

        def start(self, timeout: float = 5.0) -> bool:
            def _trigger_signal() -> None:
                time.sleep(0.05)
                sigint_handler = signal_handlers.get(signal.SIGINT)
                if sigint_handler:
                    sigint_handler(signal.SIGINT, None)

            threading.Thread(target=_trigger_signal, daemon=True).start()
            return True

        def stop(self, timeout: float = 5.0) -> None:
            self.stopped = True

    exit_code = run_mcp_server_cli(
        port=8765,
        profile_name="sig_test",
        daemon_class=FastDaemon,  # type: ignore[arg-type]
    )
    assert exit_code == 0


@pytest.mark.integration
def test_run_mcp_server_cli_e2e_real_daemon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test d'intégration simulant l'invocation CLI et le cycle de vie réseau réel avec arrêt gracieux."""
    monkeypatch.setattr("ankiforge.utils.paths.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(ProfileManager, "PROFILES_DIR", tmp_path / "profiles")

    from ankiforge.services.ai.mcp_daemon import find_available_port

    test_port = find_available_port(start_port=9600)
    stop_event = threading.Event()
    results: dict[str, Any] = {}

    def _run_worker() -> None:
        results["exit_code"] = run_mcp_server_cli(
            port=test_port,
            profile_name="integration_mcp_prof",
            stop_event=stop_event,
            data_dir=tmp_path,
        )

    cli_thread = threading.Thread(target=_run_worker, daemon=True)
    cli_thread.start()

    state_file = tmp_path / "mcp_server.json"
    token_file = tmp_path / "mcp_auth_token"

    # Attente active de la publication de l'état (max 5 secondes)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if state_file.is_file():
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
                if data.get("status") == "running":
                    break
            except Exception:
                pass
        time.sleep(0.05)

    assert state_file.is_file()
    state_data = json.loads(state_file.read_text(encoding="utf-8"))
    assert state_data["status"] == "running"
    actual_port = state_data["port"]
    token = state_data["token"]
    assert token_file.is_file()

    # Requête HTTP/SSE authentifiée pour vérifier que le point de terminaison répond
    url = f"http://127.0.0.1:{actual_port}/sse"
    with httpx.stream("GET", url, headers={"Authorization": f"Bearer {token}"}, timeout=3.0) as resp:
        assert resp.status_code == 200

    # Déclenchement de l'arrêt gracieux
    stop_event.set()
    cli_thread.join(timeout=5.0)
    assert not cli_thread.is_alive()
    assert results.get("exit_code") == 0

    # Vérification de l'état final nettoyé
    assert not token_file.exists()
    assert state_file.exists()
    final_state = json.loads(state_file.read_text(encoding="utf-8"))
    assert final_state["status"] == "stopped"
