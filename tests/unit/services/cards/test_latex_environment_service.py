"""Tests unitaires pour LatexEnvironmentService."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from ankidraft.services.cards.latex_environment_service import (
    LatexBinaryInfo,
    LatexEnvironmentService,
    LatexEnvironmentStatus,
)

pytestmark = pytest.mark.unit

logger = logging.getLogger(__name__)


class TestLatexEnvironmentService:
    """Tests pour le service de détection d'environnement LaTeX."""

    def test_detect_latex_binary_found_in_path(self) -> None:
        """Teste la détection de latex via shutil.which."""
        with (
            patch("shutil.which", return_value="/usr/bin/latex"),
            patch(
                "ankidraft.services.cards.latex_environment_service.LatexEnvironmentService._get_version",
                return_value="pdfTeX 3.141592653-2.6-1.40.24 (TeX Live 2023)",
            ),
        ):
            service = LatexEnvironmentService()
            result = service.detect_latex_binary()

            assert result is not None
            assert isinstance(result, LatexBinaryInfo)
            assert result.name == "latex"
            assert result.path == "/usr/bin/latex"
            assert result.version == "pdfTeX 3.141592653-2.6-1.40.24 (TeX Live 2023)"
            assert result.is_available is True

    def test_detect_latex_binary_fallback_to_pdflatex(self) -> None:
        """Teste le fallback sur pdflatex quand latex n'est pas trouvé."""
        with (
            patch("shutil.which", side_effect=[None, "/usr/bin/pdflatex"]),
            patch(
                "ankidraft.services.cards.latex_environment_service.LatexEnvironmentService._get_version",
                return_value="pdfTeX 3.141592653-2.6-1.40.24",
            ),
        ):
            service = LatexEnvironmentService()
            result = service.detect_latex_binary()

            assert result is not None
            assert result.name == "pdflatex"
            assert result.path == "/usr/bin/pdflatex"

    def test_detect_latex_binary_not_found(self) -> None:
        """Teste le cas où aucun binaire latex n'est trouvé."""
        with patch("shutil.which", return_value=None), patch.object(LatexEnvironmentService, "_get_known_paths_for_platform", return_value=[]):
            service = LatexEnvironmentService()
            result = service.detect_latex_binary()

            assert result is None

    def test_detect_dvisvgm_binary_found(self) -> None:
        """Teste la détection de dvisvgm."""
        with (
            patch("shutil.which", return_value="/usr/bin/dvisvgm"),
            patch(
                "ankidraft.services.cards.latex_environment_service.LatexEnvironmentService._get_version",
                return_value="dvisvgm 3.0",
            ),
        ):
            service = LatexEnvironmentService()
            result = service.detect_dvisvgm_binary()

            assert result is not None
            assert result.name == "dvisvgm"
            assert result.path == "/usr/bin/dvisvgm"
            assert result.version == "dvisvgm 3.0"

    def test_detect_dvipng_binary_found(self) -> None:
        """Teste la détection de dvipng."""
        with (
            patch("shutil.which", return_value="/usr/bin/dvipng"),
            patch(
                "ankidraft.services.cards.latex_environment_service.LatexEnvironmentService._get_version",
                return_value="dvipng 1.17",
            ),
        ):
            service = LatexEnvironmentService()
            result = service.detect_dvipng_binary()

            assert result is not None
            assert result.name == "dvipng"
            assert result.path == "/usr/bin/dvipng"
            assert result.version == "dvipng 1.17"

    def test_is_latex_available_true(self) -> None:
        """Teste is_latex_available quand les deux binaires sont présents."""
        with patch.object(LatexEnvironmentService, "detect_latex_binary", return_value=MagicMock()), patch.object(LatexEnvironmentService, "detect_dvisvgm_binary", return_value=MagicMock()):
            service = LatexEnvironmentService()
            assert service.is_latex_available() is True

    def test_is_latex_available_false_missing_latex(self) -> None:
        """Teste is_latex_available quand latex est manquant."""
        with patch.object(LatexEnvironmentService, "detect_latex_binary", return_value=None), patch.object(LatexEnvironmentService, "detect_dvisvgm_binary", return_value=MagicMock()):
            service = LatexEnvironmentService()
            assert service.is_latex_available() is False

    def test_is_latex_available_false_missing_dvisvgm(self) -> None:
        """Teste is_latex_available quand dvisvgm est manquant."""
        with patch.object(LatexEnvironmentService, "detect_latex_binary", return_value=MagicMock()), patch.object(LatexEnvironmentService, "detect_dvisvgm_binary", return_value=None):
            service = LatexEnvironmentService()
            assert service.is_latex_available() is False

    def test_get_full_status_fully_available(self) -> None:
        """Teste get_full_status quand l'environnement est complet."""
        latex_info = LatexBinaryInfo(name="latex", path="/usr/bin/latex", version="TeX Live 2023")
        dvisvgm_info = LatexBinaryInfo(name="dvisvgm", path="/usr/bin/dvisvgm", version="3.0")
        dvipng_info = LatexBinaryInfo(name="dvipng", path="/usr/bin/dvipng", version="1.17")

        with (
            patch.object(LatexEnvironmentService, "detect_latex_binary", return_value=latex_info),
            patch.object(LatexEnvironmentService, "detect_dvisvgm_binary", return_value=dvisvgm_info),
            patch.object(LatexEnvironmentService, "detect_dvipng_binary", return_value=dvipng_info),
        ):
            service = LatexEnvironmentService()
            status = service.get_full_status()

            assert isinstance(status, LatexEnvironmentStatus)
            assert status.is_fully_available is True
            assert status.latex == latex_info
            assert status.dvisvgm == dvisvgm_info
            assert status.dvipng == dvipng_info
            assert "latex" in status.message.lower()
            assert "dvisvgm" in status.message.lower()

    def test_get_full_status_partial_latex_only(self) -> None:
        """Teste get_full_status quand seul latex est disponible."""
        latex_info = LatexBinaryInfo(name="latex", path="/usr/bin/latex", version="TeX Live 2023")

        with (
            patch.object(LatexEnvironmentService, "detect_latex_binary", return_value=latex_info),
            patch.object(LatexEnvironmentService, "detect_dvisvgm_binary", return_value=None),
            patch.object(LatexEnvironmentService, "detect_dvipng_binary", return_value=None),
        ):
            service = LatexEnvironmentService()
            status = service.get_full_status()

            assert status.is_fully_available is False
            assert status.latex == latex_info
            assert status.dvisvgm is None
            assert "dvisvgm introuvable" in status.message.lower() or "svg impossible" in status.message.lower()

    def test_get_full_status_partial_dvisvgm_only(self) -> None:
        """Teste get_full_status quand seul dvisvgm est disponible."""
        dvisvgm_info = LatexBinaryInfo(name="dvisvgm", path="/usr/bin/dvisvgm", version="3.0")

        with (
            patch.object(LatexEnvironmentService, "detect_latex_binary", return_value=None),
            patch.object(LatexEnvironmentService, "detect_dvisvgm_binary", return_value=dvisvgm_info),
            patch.object(LatexEnvironmentService, "detect_dvipng_binary", return_value=None),
        ):
            service = LatexEnvironmentService()
            status = service.get_full_status()

            assert status.is_fully_available is False
            assert status.latex is None
            assert status.dvisvgm == dvisvgm_info
            assert "latex introuvable" in status.message.lower() or "compilation impossible" in status.message.lower()

    def test_get_full_status_none_available(self) -> None:
        """Teste get_full_status quand aucun binaire n'est disponible."""
        with (
            patch.object(LatexEnvironmentService, "detect_latex_binary", return_value=None),
            patch.object(LatexEnvironmentService, "detect_dvisvgm_binary", return_value=None),
            patch.object(LatexEnvironmentService, "detect_dvipng_binary", return_value=None),
        ):
            service = LatexEnvironmentService()
            status = service.get_full_status()

            assert status.is_fully_available is False
            assert status.latex is None
            assert status.dvisvgm is None
            assert status.dvipng is None
            assert "non détecté" in status.message.lower() or "installez" in status.message.lower()

    def test_get_version_success(self) -> None:
        """Teste la récupération de version réussie."""
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "pdfTeX 3.141592653-2.6-1.40.24 (TeX Live 2023)\n"
            mock_run.return_value = mock_result

            service = LatexEnvironmentService()
            version = service._get_version("/usr/bin/latex")

            assert version == "pdfTeX 3.141592653-2.6-1.40.24 (TeX Live 2023)"

    def test_get_version_failure(self) -> None:
        """Teste la récupération de version en cas d'échec."""
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_run.return_value = mock_result

            service = LatexEnvironmentService()
            version = service._get_version("/usr/bin/latex")

            assert version is None

    def test_get_version_timeout(self) -> None:
        """Teste la récupération de version en cas de timeout."""
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("latex", 5)):
            service = LatexEnvironmentService()
            version = service._get_version("/usr/bin/latex")

            assert version is None

    def test_get_version_os_error(self) -> None:
        """Teste la récupération de version en cas d'erreur OS."""
        with patch("subprocess.run", side_effect=OSError("No such file")):
            service = LatexEnvironmentService()
            version = service._get_version("/usr/bin/latex")

            assert version is None

    def test_clear_cache(self) -> None:
        """Teste la vidange du cache."""
        with (
            patch("shutil.which", return_value="/usr/bin/latex"),
            patch(
                "ankidraft.services.cards.latex_environment_service.LatexEnvironmentService._get_version",
                return_value="TeX Live 2023",
            ),
        ):
            service = LatexEnvironmentService()
            # Premier appel peuple le cache
            result1 = service.detect_latex_binary()
            assert result1 is not None

            # Vider le cache
            service.clear_cache()

            # Deuxième appel devrait refaire la détection
            with (
                patch("shutil.which", return_value="/usr/local/bin/latex"),
                patch(
                    "ankidraft.services.cards.latex_environment_service.LatexEnvironmentService._get_version",
                    return_value="TeX Live 2024",
                ),
            ):
                result2 = service.detect_latex_binary()
                assert result2 is not None
                assert result2.path == "/usr/local/bin/latex"

    def test_known_paths_mac(self) -> None:
        """Teste les chemins connus sur macOS."""

        with patch("sys.platform", "darwin"):
            service = LatexEnvironmentService()
            paths = service._get_known_paths_for_platform()
            assert "/Library/TeX/texbin" in paths
            assert "/usr/local/bin" in paths
            assert "/opt/homebrew/bin" in paths

    def test_known_paths_linux(self) -> None:
        """Teste les chemins connus sur Linux."""
        with patch("sys.platform", "linux"):
            service = LatexEnvironmentService()
            paths = service._get_known_paths_for_platform()
            assert "/usr/bin" in paths
            assert "/usr/local/bin" in paths

    def test_known_paths_windows(self) -> None:
        """Teste les chemins connus sur Windows."""
        with patch("sys.platform", "win32"):
            service = LatexEnvironmentService()
            paths = service._get_known_paths_for_platform()
            assert any("MiKTeX" in p for p in paths)
            assert any("texlive" in p.lower() for p in paths)

    def test_get_custom_paths_from_settings(self) -> None:
        """Teste la récupération des chemins personnalisés depuis les settings."""
        with patch("ankidraft.services.settings_service.SettingsService.get", side_effect=["/custom/latex", "/custom/dvisvgm", ""]):
            service = LatexEnvironmentService()
            paths = service.get_custom_paths_from_settings()

            assert paths["latex"] == "/custom/latex"
            assert paths["dvisvgm"] == "/custom/dvisvgm"
            assert paths["dvipng"] == ""

    def test_validate_custom_paths_valid(self) -> None:
        """Teste la validation de chemins personnalisés valides."""
        with patch("pathlib.Path.exists", return_value=True), patch("pathlib.Path.is_file", return_value=True):
            service = LatexEnvironmentService()
            results = service.validate_custom_paths({"latex": "/usr/bin/latex", "dvisvgm": "/usr/bin/dvisvgm"})

            assert results["latex"] is True
            assert results["dvisvgm"] is True

    def test_validate_custom_paths_invalid(self) -> None:
        """Teste la validation de chemins personnalisés invalides."""
        with patch("pathlib.Path.exists", return_value=False):
            service = LatexEnvironmentService()
            results = service.validate_custom_paths({"latex": "/nonexistent/latex", "dvisvgm": ""})

            assert results["latex"] is False
            assert results["dvisvgm"] is False

    def test_validate_custom_paths_empty(self) -> None:
        """Teste la validation de chemins vides."""
        with patch("pathlib.Path.exists", return_value=False):
            service = LatexEnvironmentService()
            results = service.validate_custom_paths({"latex": "", "dvisvgm": "/usr/bin/dvisvgm"})

            assert results["latex"] is False
            assert results["dvisvgm"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
