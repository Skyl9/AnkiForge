from unittest.mock import MagicMock, patch

import pytest

# On importe le module complet pour pouvoir patcher ses variables globales
import ankiforge.utils.c_bridge as c_bridge

pytestmark = pytest.mark.unit


def test_get_similarity_real_execution():
    """Vérifie le calcul de similarité réel sans mock."""
    assert c_bridge.get_similarity("arbre", "arbre") == 1.0
    assert c_bridge.get_similarity("arbre", "foret") < 0.5
    assert c_bridge.get_similarity("", "") == 1.0
    assert c_bridge.get_similarity("pomme", "poire") > 0.0


def test_get_similarity_python_fallback():
    """Vérifie que si le C n'est pas là, difflib prend le relais correctement."""
    with patch.object(c_bridge, "C_MATCHER_LOADED", False):
        score = c_bridge.get_similarity("chien", "chiens")
        assert 0.8 < score < 1.0


def test_get_similarity_c_extension_mock():
    """Vérifie que l'appel à la librairie C se fait avec le bon encodage (bytes)."""
    mock_lib = MagicMock()
    mock_lib.calculate_similarity.return_value = 0.95

    with patch.object(c_bridge, "C_MATCHER_LOADED", True), patch.object(c_bridge, "_matcher_lib", mock_lib):
        score = c_bridge.get_similarity("test", "tests")
        mock_lib.calculate_similarity.assert_called_once_with(b"test", b"tests")
        assert score == 0.95


def test_get_similarity_c_extension_failure_fallback():
    """Vérifie que si la librairie C lève une exception à l'exécution, on retombe sur difflib."""
    mock_lib = MagicMock()
    mock_lib.calculate_similarity.side_effect = RuntimeError("Crash C")

    with patch.object(c_bridge, "C_MATCHER_LOADED", True), patch.object(c_bridge, "_matcher_lib", mock_lib):
        score = c_bridge.get_similarity("chat", "chat")
        assert score == 1.0


def test_init_c_matcher_missing_file_logs_warning(caplog):
    """Vérifie qu'un warning explicite est émis si l'extension C est absente."""
    import logging
    from pathlib import Path

    with caplog.at_level(logging.WARNING, logger="ankiforge.utils.c_bridge"):
        loaded = c_bridge.init_c_matcher(Path("/path/to/nonexistent/levenshtein.so"))
        assert loaded is False
        assert any(record.levelno == logging.WARNING and "Extension C Levenshtein non trouvée" in record.message for record in caplog.records)


def test_init_c_matcher_load_error_logs_warning(caplog, tmp_path):
    """Vérifie qu'une erreur de chargement ctypes produit un warning."""
    import logging

    corrupt_lib = tmp_path / "corrupt.so"
    corrupt_lib.write_text("invalid binary")

    with caplog.at_level(logging.WARNING, logger="ankiforge.utils.c_bridge"):
        loaded = c_bridge.init_c_matcher(corrupt_lib)
        assert loaded is False
        assert any(record.levelno == logging.WARNING and "Erreur lors du chargement de l'extension C" in record.message for record in caplog.records)
