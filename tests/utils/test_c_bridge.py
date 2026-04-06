# tests/utils/test_c_bridge.py
import pytest
from unittest.mock import patch, MagicMock

# On importe le module complet pour pouvoir patcher ses variables globales
import ankiforge.utils.c_bridge as c_bridge


def test_get_similarity_python_fallback():
    """Vérifie que si le C n'est pas là, difflib prend le relais correctement."""
    # On force la variable globale à False
    with patch.object(c_bridge, 'C_MATCHER_LOADED', False):
        score = c_bridge.get_similarity("chien", "chiens")

        # difflib donnera un score > 0 mais < 1
        assert 0.8 < score < 1.0


def test_get_similarity_c_extension():
    """Vérifie que l'appel à la librairie C se fait avec le bon encodage (bytes)."""

    # On crée un faux objet qui imite ta librairie C
    mock_lib = MagicMock()
    mock_lib.calculate_similarity.return_value = 0.95

    # On force le module à utiliser notre fausse librairie
    with patch.object(c_bridge, 'C_MATCHER_LOADED', True), \
            patch.object(c_bridge, '_matcher_lib', mock_lib):
        score = c_bridge.get_similarity("test", "tests")

        # Le C exige des bytes, on vérifie que le bridge a bien fait la conversion .encode('utf-8')
        mock_lib.calculate_similarity.assert_called_once_with(b"test", b"tests")
        assert score == 0.95