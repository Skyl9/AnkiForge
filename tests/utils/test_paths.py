from pathlib import Path
from unittest.mock import patch

import pytest

from ankiforge.utils.paths import get_project_root, get_app_data_dir


def test_get_project_root_success():
    """Vérifie qu'on trouve bien la racine (là où est pyproject.toml)."""
    root = get_project_root()
    assert isinstance(root, Path)
    assert (root / "pyproject.toml").exists(), "La racine trouvée ne contient pas pyproject.toml"


@patch("ankiforge.utils.paths.Path.exists")
def test_get_project_root_failure(mock_exists):
    """Vérifie que ça plante proprement si le pyproject.toml a disparu."""
    # On force exists() à renvoyer False pour simuler l'absence du fichier
    mock_exists.return_value = False

    with pytest.raises(RuntimeError) as exc_info:
        get_project_root()

    assert "Impossible de trouver la racine" in str(exc_info.value)


@patch("ankiforge.utils.paths.sys")
def test_get_app_data_dir_dev_mode(mock_sys):
    """Test le chemin en mode Développement (sys.frozen = False)."""
    mock_sys.frozen = False

    app_dir = get_app_data_dir()

    # En mode dev, ça doit être dans le dossier du projet, sous ".ankiforge"
    assert app_dir.name == ".ankiforge"
    assert app_dir.parent == get_project_root()
    assert app_dir.exists()
