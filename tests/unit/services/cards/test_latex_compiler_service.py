"""Tests unitaires pour LatexCompilerService."""

import hashlib
import logging
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ankidraft.database.models.cards import NoteTypeModel
from ankidraft.services.cards.latex_compiler_service import (
    LatexCompilationError,
    LatexCompilerService,
)
from ankidraft.services.cards.latex_environment_service import (
    LatexBinaryInfo,
)

pytestmark = pytest.mark.unit

logger = logging.getLogger(__name__)


class TestLatexCompilerService:
    """Tests pour le service de compilation LaTeX sécurisé."""

    def _make_mock_note_type(self, latex_pre: str = None, latex_post: str = None, latex_svg: bool = True) -> NoteTypeModel:
        """Crée un NoteTypeModel mock avec les champs LaTeX."""
        mock = MagicMock(spec=NoteTypeModel)
        mock.latex_pre = latex_pre or r"\documentclass{article}\begin{document}"
        mock.latex_post = latex_post or r"\end{document}"
        mock.latex_svg = latex_svg
        return mock

    def _make_mock_env_service(self, latex_available: bool = True, latex_path: str = "/usr/bin/latex", dvisvgm_path: str = "/usr/bin/dvisvgm"):
        """Crée un LatexEnvironmentService mock."""
        mock_env = MagicMock()
        if latex_available:
            mock_env.is_latex_available.return_value = True
            mock_env.detect_latex_binary.return_value = LatexBinaryInfo(name="latex", path=latex_path)
            mock_env.detect_dvisvgm_binary.return_value = LatexBinaryInfo(name="dvisvgm", path=dvisvgm_path)
        else:
            mock_env.is_latex_available.return_value = False
            mock_env.detect_latex_binary.return_value = None
            mock_env.detect_dvisvgm_binary.return_value = None
        return mock_env

    def test_compute_media_filename_deterministic(self) -> None:
        """Teste que le calcul du hash est déterministe et correspond à Anki."""
        service = LatexCompilerService()
        model = self._make_mock_note_type()
        snippet = r"\frac{1}{2}"

        filename1 = service._compute_media_filename(snippet, model)
        filename2 = service._compute_media_filename(snippet, model)

        assert filename1 == filename2
        assert filename1.startswith("latex-")
        assert filename1.endswith(".svg")

    def test_compute_media_filename_changes_with_snippet(self) -> None:
        """Teste que le hash change quand le snippet change."""
        service = LatexCompilerService()
        model = self._make_mock_note_type()

        filename1 = service._compute_media_filename(r"\frac{1}{2}", model)
        filename2 = service._compute_media_filename(r"\frac{1}{3}", model)

        assert filename1 != filename2

    def test_compute_media_filename_changes_with_preamble(self) -> None:
        """Teste que le hash change quand le préambule change."""
        service = LatexCompilerService()
        snippet = r"\frac{1}{2}"

        model1 = self._make_mock_note_type(latex_pre=r"\documentclass{article}\begin{document}")
        model2 = self._make_mock_note_type(latex_pre=r"\documentclass{article}\usepackage{tikz}\begin{document}")

        filename1 = service._compute_media_filename(snippet, model1)
        filename2 = service._compute_media_filename(snippet, model2)

        assert filename1 != filename2

    def test_compute_media_filename_changes_with_svg_flag(self) -> None:
        """Teste que le hash change quand le flag SVG change."""
        service = LatexCompilerService()
        snippet = r"\frac{1}{2}"

        model_svg = self._make_mock_note_type(latex_svg=True)
        model_png = self._make_mock_note_type(latex_svg=False)

        filename_svg = service._compute_media_filename(snippet, model_svg)
        filename_png = service._compute_media_filename(snippet, model_png)

        assert filename_svg != filename_png
        assert filename_svg.endswith(".svg")
        assert filename_png.endswith(".png")

    def test_compute_media_filename_matches_anki_algorithm(self) -> None:
        """Teste que l'algorithme de hash correspond exactement à Anki Desktop."""
        service = LatexCompilerService()
        model = self._make_mock_note_type(
            latex_pre=r"\documentclass{article}\begin{document}",
            latex_post=r"\end{document}",
            latex_svg=True,
        )
        snippet = r"E = mc^2"

        # Calcul manuel selon l'algorithme d'Anki
        payload = f"{model.latex_pre}\n{snippet}\n{model.latex_post}\n1".encode()
        expected_hash = hashlib.sha1(payload).hexdigest()
        expected_filename = f"latex-{expected_hash}.svg"

        actual_filename = service._compute_media_filename(snippet, model)

        assert actual_filename == expected_filename

    @patch("ankidraft.services.cards.latex_compiler_service.LatexCompilerService._get_latex_env_service")
    @patch("ankidraft.services.cards.latex_compiler_service.get_active_profile")
    @patch("ankidraft.services.profile_manager.ProfileManager.get_media_dir")
    def test_compile_snippet_cache_hit(
        self,
        mock_get_media_dir,
        mock_get_active_profile,
        mock_get_latex_env_service,
    ) -> None:
        """Teste le cache hit : retourne le fichier existant sans compiler."""
        # Setup
        mock_get_active_profile.return_value = "test_profile"
        mock_media_dir = Path("/fake/media/dir")
        mock_get_media_dir.return_value = mock_media_dir

        mock_env = self._make_mock_env_service()
        mock_get_latex_env_service.return_value = mock_env

        service = LatexCompilerService()
        model = self._make_mock_note_type()
        snippet = r"\frac{1}{2}"

        # Calculer le nom de fichier attendu
        expected_filename = service._compute_media_filename(snippet, model)

        # Mock le cache hit
        with patch("pathlib.Path.exists", return_value=True):
            result = service.compile_snippet_to_media(snippet, model)

        assert result == expected_filename
        # Vérifier que les binaires n'ont pas été appelés (cache hit)
        mock_env.detect_latex_binary.assert_not_called()
        mock_env.detect_dvisvgm_binary.assert_not_called()

    @patch("ankidraft.services.cards.latex_compiler_service.LatexCompilerService._get_latex_env_service")
    def test_compile_snippet_latex_unavailable(self, mock_get_latex_env_service) -> None:
        """Teste l'erreur quand l'environnement LaTeX n'est pas disponible."""
        mock_env = self._make_mock_env_service(latex_available=False)
        mock_get_latex_env_service.return_value = mock_env

        service = LatexCompilerService()
        model = self._make_mock_note_type()
        snippet = r"\frac{1}{2}"

        with patch("pathlib.Path.exists", return_value=False), pytest.raises(LatexCompilationError) as exc_info:
            service.compile_snippet_to_media(snippet, model)

        assert "Environnement LaTeX non disponible" in str(exc_info.value)

    @patch("ankidraft.services.cards.latex_compiler_service.LatexCompilerService._get_latex_env_service")
    @patch("ankidraft.services.cards.latex_compiler_service.get_active_profile")
    @patch("ankidraft.services.profile_manager.ProfileManager.get_media_dir")
    @patch("ankidraft.services.cards.latex_compiler_service.tempfile.TemporaryDirectory")
    @patch("subprocess.run")
    def test_compile_snippet_success(
        self,
        mock_subprocess_run,
        mock_temp_dir,
        mock_get_media_dir,
        mock_get_active_profile,
        mock_get_latex_env_service,
    ) -> None:
        """Teste une compilation réussie complète."""
        # Setup environnement
        mock_get_active_profile.return_value = "test_profile"

        # Mock media_dir et media_path
        mock_media_dir = MagicMock()
        mock_media_path = MagicMock()
        mock_media_path.exists.return_value = False  # Cache miss
        mock_media_dir.__truediv__ = MagicMock(return_value=mock_media_path)
        mock_media_dir.mkdir = MagicMock()
        mock_get_media_dir.return_value = mock_media_dir

        mock_env = self._make_mock_env_service()
        mock_get_latex_env_service.return_value = mock_env

        # Setup répertoire temporaire
        mock_tmp_dir = MagicMock()
        mock_tmp_dir.__enter__ = MagicMock(return_value="/tmp/fake")
        mock_tmp_dir.__exit__ = MagicMock(return_value=False)
        mock_temp_dir.return_value = mock_tmp_dir

        # Mock Path pour les fichiers temporaires (dvi, svg, log)
        with (
            patch("pathlib.Path.write_text"),
            patch("pathlib.Path.exists", side_effect=[True, True, False]),
            patch("shutil.copy2"),
            patch("ankidraft.services.cards.latex_compiler_service.MediaModel.get_or_create"),
        ):
            # Mock subprocess.run pour latex et dvisvgm
            mock_latex_result = MagicMock()
            mock_latex_result.returncode = 0
            mock_latex_result.stdout = ""
            mock_latex_result.stderr = ""

            mock_dvisvgm_result = MagicMock()
            mock_dvisvgm_result.returncode = 0
            mock_dvisvgm_result.stdout = ""
            mock_dvisvgm_result.stderr = ""

            mock_subprocess_run.side_effect = [mock_latex_result, mock_dvisvgm_result]

            service = LatexCompilerService()
            model = self._make_mock_note_type()
            snippet = r"\frac{1}{2}"

            result = service.compile_snippet_to_media(snippet, model)

            # Vérifications
            assert result.startswith("latex-")
            assert result.endswith(".svg")

            # Vérifier les appels subprocess
            assert mock_subprocess_run.call_count == 2

            # Premier appel : latex
            latex_call = mock_subprocess_run.call_args_list[0]
            assert "latex" in latex_call[0][0][0]
            assert "-interaction=nonstopmode" in latex_call[0][0]
            assert "-halt-on-error" in latex_call[0][0]
            assert "-no-shell-escape" in latex_call[0][0]
            assert "tmp.tex" in latex_call[0][0]

            # Deuxième appel : dvisvgm
            dvisvgm_call = mock_subprocess_run.call_args_list[1]
            assert "dvisvgm" in dvisvgm_call[0][0][0]
            assert "--no-fonts" in dvisvgm_call[0][0]
            assert "--exact" in dvisvgm_call[0][0]
            assert "-Z" in dvisvgm_call[0][0]
            assert "2" in dvisvgm_call[0][0]
            assert "tmp.dvi" in dvisvgm_call[0][0]
            assert "-o" in dvisvgm_call[0][0]
            assert "tmp.svg" in dvisvgm_call[0][0]

            # Vérifier timeout
            for call in mock_subprocess_run.call_args_list:
                assert call[1]["timeout"] == 10.0

    @patch("ankidraft.services.cards.latex_compiler_service.LatexCompilerService._get_latex_env_service")
    @patch("ankidraft.services.cards.latex_compiler_service.get_active_profile")
    @patch("ankidraft.services.profile_manager.ProfileManager.get_media_dir")
    @patch("ankidraft.services.cards.latex_compiler_service.tempfile.TemporaryDirectory")
    @patch("subprocess.run")
    def test_compile_snippet_latex_failure(
        self,
        mock_subprocess_run,
        mock_temp_dir,
        mock_get_media_dir,
        mock_get_active_profile,
        mock_get_latex_env_service,
    ) -> None:
        """Teste l'erreur quand latex échoue."""
        mock_get_active_profile.return_value = "test_profile"
        mock_media_dir = Path("/fake/media/dir")
        mock_get_media_dir.return_value = mock_media_dir

        mock_env = self._make_mock_env_service()
        mock_get_latex_env_service.return_value = mock_env

        mock_tmp_dir = MagicMock()
        mock_tmp_dir.__enter__ = MagicMock(return_value="/tmp/fake")
        mock_tmp_dir.__exit__ = MagicMock(return_value=False)
        mock_temp_dir.return_value = mock_tmp_dir

        # Mock subprocess.run pour simuler un échec de latex
        mock_latex_result = MagicMock()
        mock_latex_result.returncode = 1
        mock_latex_result.stdout = "! Undefined control sequence."
        mock_latex_result.stderr = "Error"

        mock_subprocess_run.return_value = mock_latex_result

        with patch("pathlib.Path.write_text"), patch("pathlib.Path.exists", side_effect=[False, True]):
            service = LatexCompilerService()
            model = self._make_mock_note_type()
            snippet = r"\undefined_command"

            with pytest.raises(LatexCompilationError) as exc_info:
                service.compile_snippet_to_media(snippet, model)

            assert "Échec de la compilation LaTeX" in str(exc_info.value)
            assert exc_info.value.log_excerpt is not None

    @patch("ankidraft.services.cards.latex_compiler_service.LatexCompilerService._get_latex_env_service")
    @patch("ankidraft.services.cards.latex_compiler_service.get_active_profile")
    @patch("ankidraft.services.profile_manager.ProfileManager.get_media_dir")
    @patch("ankidraft.services.cards.latex_compiler_service.tempfile.TemporaryDirectory")
    @patch("subprocess.run")
    def test_compile_snippet_timeout(
        self,
        mock_subprocess_run,
        mock_temp_dir,
        mock_get_media_dir,
        mock_get_active_profile,
        mock_get_latex_env_service,
    ) -> None:
        """Teste le timeout lors de la compilation."""
        mock_get_active_profile.return_value = "test_profile"
        mock_media_dir = Path("/fake/media/dir")
        mock_get_media_dir.return_value = mock_media_dir

        mock_env = self._make_mock_env_service()
        mock_get_latex_env_service.return_value = mock_env

        mock_tmp_dir = MagicMock()
        mock_tmp_dir.__enter__ = MagicMock(return_value="/tmp/fake")
        mock_tmp_dir.__exit__ = MagicMock(return_value=False)
        mock_temp_dir.return_value = mock_tmp_dir

        # Mock subprocess.run pour simuler un timeout
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired("latex", 10)

        with patch("pathlib.Path.write_text"), patch("pathlib.Path.exists", return_value=False):
            service = LatexCompilerService()
            model = self._make_mock_note_type()
            snippet = r"\loop\repeat"  # Boucle infinie

            with pytest.raises(LatexCompilationError) as exc_info:
                service.compile_snippet_to_media(snippet, model)

            assert "Timeout" in str(exc_info.value)

    @patch("ankidraft.services.cards.latex_compiler_service.LatexCompilerService._get_latex_env_service")
    @patch("ankidraft.services.cards.latex_compiler_service.get_active_profile")
    @patch("ankidraft.services.profile_manager.ProfileManager.get_media_dir")
    @patch("ankidraft.services.cards.latex_compiler_service.tempfile.TemporaryDirectory")
    @patch("subprocess.run")
    def test_compile_snippet_dvisvgm_failure(
        self,
        mock_subprocess_run,
        mock_temp_dir,
        mock_get_media_dir,
        mock_get_active_profile,
        mock_get_latex_env_service,
    ) -> None:
        """Teste l'erreur quand dvisvgm échoue."""
        mock_get_active_profile.return_value = "test_profile"
        mock_media_dir = Path("/fake/media/dir")
        mock_get_media_dir.return_value = mock_media_dir

        mock_env = self._make_mock_env_service()
        mock_get_latex_env_service.return_value = mock_env

        mock_tmp_dir = MagicMock()
        mock_tmp_dir.__enter__ = MagicMock(return_value="/tmp/fake")
        mock_tmp_dir.__exit__ = MagicMock(return_value=False)
        mock_temp_dir.return_value = mock_tmp_dir

        # Premier appel (latex) réussit, deuxième (dvisvgm) échoue
        mock_latex_result = MagicMock()
        mock_latex_result.returncode = 0

        mock_dvisvgm_result = MagicMock()
        mock_dvisvgm_result.returncode = 1
        mock_dvisvgm_result.stderr = "dvisvgm error"

        mock_subprocess_run.side_effect = [mock_latex_result, mock_dvisvgm_result]

        with patch("pathlib.Path.write_text"), patch("pathlib.Path.exists", side_effect=[False, True, False]):
            service = LatexCompilerService()
            model = self._make_mock_note_type()
            snippet = r"\frac{1}{2}"

            with pytest.raises(LatexCompilationError) as exc_info:
                service.compile_snippet_to_media(snippet, model)

            assert "Échec de la conversion DVI vers SVG" in str(exc_info.value)

    def test_is_ready_true(self) -> None:
        """Teste is_ready quand l'environnement est disponible."""
        with patch.object(LatexCompilerService, "_get_latex_env_service") as mock_get_env:
            mock_env = self._make_mock_env_service(latex_available=True)
            mock_get_env.return_value = mock_env

            service = LatexCompilerService()
            assert service.is_ready() is True

    def test_is_ready_false(self) -> None:
        """Teste is_ready quand l'environnement n'est pas disponible."""
        with patch.object(LatexCompilerService, "_get_latex_env_service") as mock_get_env:
            mock_env = self._make_mock_env_service(latex_available=False)
            mock_get_env.return_value = mock_env

            service = LatexCompilerService()
            assert service.is_ready() is False

    def test_latex_compilation_error_attributes(self) -> None:
        """Teste les attributs de LatexCompilationError."""
        error = LatexCompilationError("Test message", "Log excerpt")
        assert error.message == "Test message"
        assert error.log_excerpt == "Log excerpt"
        assert str(error) == "Test message"

    def test_latex_compilation_error_without_log(self) -> None:
        """Teste LatexCompilationError sans extrait de log."""
        error = LatexCompilationError("Test message")
        assert error.message == "Test message"
        assert error.log_excerpt == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
