"""
Tests unitaires pour CrashReporterService.
Vérifie le parsing de crash.log, la détection des crashs non acquittés,
la redaction des secrets sur le payload généré, l'URL GitHub et les préférences.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ankiforge.services.crash_reporter_service import (
    CrashReporterService,
)
from ankiforge.services.feedback_service import SystemDiagnosticInfo

SAMPLE_CRASH_BLOCK_1 = """======================================================================
CRASH REPORT [2026-10-10 14:30:00 UTC] - Darwin-24.1.0-arm64 | Python 3.12.9
Profil actif : test_profile
======================================================================
Traceback (most recent call last):
  File "src/ankiforge/ui/components/panels.py", line 739, in dragEnterEvent
    if tabs_mod._dragged_tab_info:
AttributeError: module 'ankiforge.ui.components.tabs' has no attribute '_dragged_tab_info'
"""

SAMPLE_CRASH_BLOCK_WITH_SECRETS = """======================================================================
CRASH REPORT [2026-10-10 15:00:00 UTC] - Linux-6.5.0-x86_64 | Python 3.12.9
Profil actif : default
======================================================================
Traceback (most recent call last):
  File "src/ankiforge/services/ai.py", line 42, in query
    client = OpenAI(api_key="sk-abcdef1234567890abcdef1234567890")
RuntimeError: Échec avec Bearer eyJhbGciOiJIUzI1NiJ9.secret12345
"""

SAMPLE_CRASH_BLOCK_OLD_FORMAT = """======================================================================
CRASH REPORT - Windows-10-10.0.19045 | Python 3.12.8
Profil actif : user1
======================================================================
Traceback (most recent call last):
  File "main.py", line 10, in <module>
    ZeroDivisionError: division by zero
"""


class TestCrashReporterServiceParsing:
    def test_parse_empty_content(self) -> None:
        """Vérifie qu'un contenu vide ne retourne aucun crash."""
        reports = CrashReporterService.parse_crash_log_content("")
        assert reports == []

    def test_parse_single_block(self) -> None:
        """Vérifie le parsing d'un bloc de crash standard avec horodatage."""
        reports = CrashReporterService.parse_crash_log_content(SAMPLE_CRASH_BLOCK_1)
        assert len(reports) == 1
        rep = reports[0]
        assert rep.timestamp == "2026-10-10 14:30:00 UTC"
        assert "Darwin" in rep.os_platform
        assert rep.python_version == "3.12.9"
        assert rep.active_profile == "test_profile"
        assert "AttributeError" in rep.traceback
        assert rep.fingerprint != ""

    def test_parse_old_format_without_timestamp(self) -> None:
        """Vérifie le parsing d'un bloc sans horodatage explicite dans le header."""
        reports = CrashReporterService.parse_crash_log_content(SAMPLE_CRASH_BLOCK_OLD_FORMAT)
        assert len(reports) == 1
        rep = reports[0]
        assert "Windows" in rep.os_platform
        assert rep.python_version == "3.12.8"
        assert rep.active_profile == "user1"
        assert "ZeroDivisionError" in rep.traceback

    def test_parse_multiple_blocks(self) -> None:
        """Vérifie que plusieurs blocs dans un fichier sont tous extraits dans l'ordre."""
        content = f"{SAMPLE_CRASH_BLOCK_1}\n\n{SAMPLE_CRASH_BLOCK_OLD_FORMAT}"
        reports = CrashReporterService.parse_crash_log_content(content)
        assert len(reports) == 2
        assert "Darwin" in reports[0].os_platform
        assert "Windows" in reports[1].os_platform

    def test_get_latest_crash(self, tmp_path: Path) -> None:
        """Vérifie que get_latest_crash retourne le dernier bloc du fichier."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        crash_file = log_dir / "crash.log"
        crash_file.write_text(f"{SAMPLE_CRASH_BLOCK_1}\n\n{SAMPLE_CRASH_BLOCK_OLD_FORMAT}", encoding="utf-8")

        latest = CrashReporterService.get_latest_crash(log_dir=log_dir)
        assert latest is not None
        assert "Windows" in latest.os_platform
        assert latest.active_profile == "user1"

    def test_get_latest_crash_when_no_file(self, tmp_path: Path) -> None:
        """Vérifie qu'aucun crash n'est retourné si crash.log n'existe pas."""
        latest = CrashReporterService.get_latest_crash(log_dir=tmp_path / "empty")
        assert latest is None


class TestCrashReporterServiceLifecycle:
    def test_has_pending_crash_and_acknowledge(self, tmp_path: Path) -> None:
        """Vérifie la détection d'un crash non acquitté puis son acquittement."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        crash_file = log_dir / "crash.log"
        crash_file.write_text(SAMPLE_CRASH_BLOCK_1, encoding="utf-8")

        mock_settings: dict[str, object] = {"feedback/prompt_on_crash": True}

        def mock_value(key: str, default: object = None, type: object = None) -> object:
            return mock_settings.get(key, default)

        def mock_set_value(key: str, val: object) -> None:
            mock_settings[key] = val

        with patch("ankiforge.services.crash_reporter_service.get_app_qsettings") as mock_get_settings:
            mock_q = mock_get_settings.return_value
            mock_q.value.side_effect = mock_value
            mock_q.setValue.side_effect = mock_set_value

            # Avant acquittement : crash en attente
            assert CrashReporterService.has_pending_crash(log_dir=log_dir) is True

            # Acquittement du crash
            latest = CrashReporterService.get_latest_crash(log_dir=log_dir)
            assert latest is not None
            CrashReporterService.acknowledge_crash(latest)

            # Après acquittement : plus de crash en attente
            assert CrashReporterService.has_pending_crash(log_dir=log_dir) is False

    def test_has_pending_crash_disabled_by_preference(self, tmp_path: Path) -> None:
        """Vérifie qu'aucun crash n'est proposé si la préférence est désactivée."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        crash_file = log_dir / "crash.log"
        crash_file.write_text(SAMPLE_CRASH_BLOCK_1, encoding="utf-8")

        mock_settings: dict[str, object] = {
            "feedback/prompt_on_crash": False,
            "feedback/last_acknowledged_crash_hash": "",
        }

        with patch("ankiforge.services.crash_reporter_service.get_app_qsettings") as mock_get_settings:
            mock_q = mock_get_settings.return_value
            mock_q.value.side_effect = lambda k, d=None, type=None: mock_settings.get(k, d)

            assert CrashReporterService.has_pending_crash(log_dir=log_dir) is False


class TestCrashReporterPayloadSecurity:
    def test_secret_redaction_in_report_markdown(self) -> None:
        """Vérifie que les clés API et tokens dans le traceback sont masqués dans le rapport Markdown."""
        reports = CrashReporterService.parse_crash_log_content(SAMPLE_CRASH_BLOCK_WITH_SECRETS)
        assert len(reports) == 1
        rep = reports[0]

        md = CrashReporterService.build_markdown_report(rep)

        # Les secrets ne doivent jamais apparaître
        assert "sk-abcdef1234567890abcdef1234567890" not in md
        assert "secret12345" not in md
        # Les marqueurs de sanitisation doivent être présents
        assert "[REDACTED_SECRET]" in md or "[REDACTED_OPENAI_KEY]" in md
        assert "[REDACTED_TOKEN]" in md

    def test_build_markdown_report_structure(self) -> None:
        """Vérifie la structure du rapport Markdown généré."""
        reports = CrashReporterService.parse_crash_log_content(SAMPLE_CRASH_BLOCK_1)
        rep = reports[0]

        diag = SystemDiagnosticInfo(ankiforge_version="0.2.0", build_channel="stable", commit_hash="abcdef12")
        md = CrashReporterService.build_markdown_report(rep, diagnostic_info=diag)

        assert "# 💥 [Crash Report]" in md
        assert "Darwin-24.1.0-arm64" in md
        assert "test_profile" in md
        assert "AttributeError" in md
        assert "0.2.0" in md

    def test_build_github_issue_url(self) -> None:
        """Vérifie la construction de l'URL GitHub Issues pré-remplie."""
        reports = CrashReporterService.parse_crash_log_content(SAMPLE_CRASH_BLOCK_1)
        rep = reports[0]

        url = CrashReporterService.build_github_issue_url(rep)
        assert "https://github.com/Skyl9/AnkiForge/issues/new" in url
        assert "labels=crash" in url
        assert "AttributeError" in url

    def test_export_crash_report(self, tmp_path: Path) -> None:
        """Vérifie l'exportation du rapport dans un fichier local."""
        reports = CrashReporterService.parse_crash_log_content(SAMPLE_CRASH_BLOCK_1)
        rep = reports[0]
        md = CrashReporterService.build_markdown_report(rep)

        out_path = tmp_path / "crash_export.md"
        CrashReporterService.export_crash_report(out_path, md)

        assert out_path.exists()
        content = out_path.read_text(encoding="utf-8")
        assert "AttributeError" in content
