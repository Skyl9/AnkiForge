"""
Tests unitaires pour FeedbackService et SystemDiagnosticInfo.
Vérifie la collecte de diagnostics, la sanitisation des secrets, le formatage Markdown et la génération d'URL.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ankiforge.services.feedback_service import (
    BugReportData,
    FeatureIdeaData,
    FeedbackService,
    SystemDiagnosticInfo,
)


class TestFeedbackService:
    def test_collect_diagnostics(self) -> None:
        """Vérifie que les diagnostics système sont collectés sans lever d'exception."""
        diag = FeedbackService.collect_diagnostics(log_limit=10)
        assert isinstance(diag, SystemDiagnosticInfo)
        assert diag.os_platform != ""
        assert diag.python_version != ""
        assert diag.active_profile != ""
        assert isinstance(diag.recent_logs, list)

    def test_diagnostic_to_markdown_and_dict(self) -> None:
        """Vérifie la conversion en Markdown et dictionnaire."""
        diag = SystemDiagnosticInfo(
            ankiforge_version="v1.1.5",
            build_channel="stable",
            commit_hash="abc12345",
            os_platform="macOS arm64",
            python_version="3.12.0",
            pyside_version="6.7.0",
            qt_version="6.7.0",
            active_profile="test_profile",
            active_theme="jetbrains",
            active_layout="ide",
            screen_resolution="1920x1080 @ 2.0x",
            sqlite_version="3.45.0",
            ai_provider="OpenAI",
            ai_model="gpt-4o",
            recent_logs=["[INFO] Test log 1", "[WARNING] Test log 2"],
            crash_excerpt="Traceback error dummy",
        )

        md = diag.to_markdown(include_logs=True)
        assert "### 🖥️ Informations Système & Environnement" in md
        assert "v1.1.5" in md
        assert "macOS arm64" in md
        assert "test_profile" in md
        assert "Test log 1" in md
        assert "crash.log" in md

        d = diag.to_dict()
        assert d["active_profile"] == "test_profile"
        assert d["python_version"] == "3.12.0"

    def test_build_bug_report_markdown_with_secret_redaction(self) -> None:
        """Vérifie que les clés API et tokens sont strictement masqués dans le rapport de bug."""
        secret_key = "sk-proj-secret1234567890abcdef12345"
        diag = SystemDiagnosticInfo(
            ankiforge_version="v1.1.5",
            recent_logs=[f"[DEBUG] API Key used: {secret_key}"],
        )

        data = BugReportData(
            title="Crash lors de la génération",
            severity="Élevé / Bloquant",
            steps="1. Ingestion de doc",
            observed=f"Erreur avec bearer: Bearer {secret_key}",
            expected="Cartes générées",
            include_diagnostics=True,
            diagnostic_info=diag,
            custom_traceback=f"Exception raised with key={secret_key}",
        )

        md = FeedbackService.build_bug_report_markdown(data)

        # Vérification qu'aucun secret en clair n'apparaît
        assert secret_key not in md
        assert "[REDACTED" in md
        assert "Crash lors de la génération" in md
        assert "Élevé / Bloquant" in md

    def test_build_feature_request_markdown(self) -> None:
        """Vérifie le formatage Markdown d'une proposition de fonctionnalité."""
        data = FeatureIdeaData(
            title="Raccourci pour switcher de profil",
            category="Interface & Ergonomie",
            problem="Changer de profil nécessite d'aller dans le footer",
            solution="Ajouter Ctrl+P pour ouvrir le sélecteur",
            priority="Très utile",
        )

        md = FeedbackService.build_feature_request_markdown(data)
        assert "# 💡 [Idée] Raccourci pour switcher de profil" in md
        assert "Interface & Ergonomie" in md
        assert "Très utile" in md
        assert "Changer de profil nécessite" in md
        assert "Ajouter Ctrl+P" in md

    def test_build_github_issue_url(self) -> None:
        """Vérifie la construction correcte de l'URL GitHub Issues."""
        url = FeedbackService.build_github_issue_url(
            title="Bug test",
            body="Description du bug",
            label="bug",
        )
        assert url.startswith("https://github.com/Skyl9/AnkiForge/issues/new?")
        assert "title=Bug+test" in url or "title=Bug%20test" in url
        assert "labels=bug" in url

        # Test de troncature si corps immense
        huge_body = "x" * 6000
        safe_url = FeedbackService.build_github_issue_url(title="Huge", body=huge_body)
        assert len(safe_url) < 5500
        assert "tronqu" in safe_url

    def test_export_report_to_file(self) -> None:
        """Vérifie l'exportation sur disque."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "sub" / "report.md"
            content = "# Mon Rapport"
            FeedbackService.export_report_to_file(file_path, content)

            assert file_path.exists()
            assert file_path.read_text(encoding="utf-8") == content
