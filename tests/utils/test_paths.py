import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from ankiforge.utils.paths import (
    get_active_profile,
    get_app_data_dir,
    get_media_dir,
    get_profile_dir,
    get_project_root,
    get_resource_path,
    set_active_profile,
)

pytestmark = pytest.mark.unit


def test_get_project_root_dev():
    """Vérifie qu'en mode dev on trouve bien la racine avec pyproject.toml."""
    root = get_project_root()
    assert isinstance(root, Path)
    assert (root / "pyproject.toml").exists(), "La racine trouvée ne contient pas pyproject.toml"


def test_get_project_root_frozen():
    """Vérifie qu'en mode gelé (bundle/nuitka/pyinstaller) on ne crash pas et on renvoie un Path valide."""
    with patch.object(sys, "frozen", True, create=True):
        root = get_project_root()
        assert isinstance(root, Path)


def test_get_app_data_dir_dev_mode():
    """Test le chemin en mode Développement (sys.frozen = False)."""
    with patch.object(sys, "frozen", False, create=True):
        app_dir = get_app_data_dir()
        assert isinstance(app_dir, Path)
        assert app_dir.exists()


def test_get_app_data_dir_frozen_mode():
    """Test le chemin en mode Production / Frozen."""
    with patch.object(sys, "frozen", True, create=True):
        app_dir = get_app_data_dir()
        assert isinstance(app_dir, Path)
        assert app_dir.exists()


def test_get_resource_path():
    """Vérifie que get_resource_path trouve les icônes existantes."""
    logo = get_resource_path("src", "ressources", "icons", "logo.svg")
    assert isinstance(logo, Path)
    assert logo.exists(), f"logo.svg non trouvé à {logo}"


def test_profiles_and_media_paths():
    """Vérifie la gestion des profils et dossiers media."""
    orig_profile = get_active_profile()
    try:
        set_active_profile("test_profile")
        assert get_active_profile() == "test_profile"

        p_dir = get_profile_dir("test_profile")
        assert p_dir.exists()
        assert p_dir.name == "test_profile"

        m_dir = get_media_dir()
        assert m_dir.exists()
        assert m_dir.name == "media"
        assert m_dir.parent == p_dir
    finally:
        set_active_profile(orig_profile)


def test_ensure_media_decompressed(tmp_path):
    """Vérifie la décompression automatique des fichiers Zstandard (Anki v3)."""
    import zstandard as zstd

    from ankiforge.utils.paths import ensure_media_decompressed

    raw_content = b"Contenu d'image PNG non compresse"
    cctx = zstd.ZstdCompressor()
    compressed = cctx.compress(raw_content)

    test_file = tmp_path / "compressed_img.png"
    test_file.write_bytes(compressed)

    assert test_file.read_bytes().startswith(b"\x28\xb5\x2f\xfd")

    result = ensure_media_decompressed(test_file)
    assert result == test_file
    assert result.read_bytes() == raw_content
