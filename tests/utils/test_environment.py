"""
Tests unitaires pour le module ankiforge.utils.environment et le cloisonnement Dev/Prod/Test.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from ankiforge.services.profile_manager import ProfileManager
from ankiforge.utils.environment import (
    AppEnvironment,
    clone_production_data_to_development,
    get_current_environment,
    get_environment_display_name,
    get_settings_app_name,
    get_settings_org_name,
    is_development,
    is_production,
    is_testing,
    set_environment,
)
from ankiforge.utils.paths import get_app_data_dir, get_tools_search_dirs

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_environment_state():
    """Réinitialise l'état global de l'environnement après chaque test."""
    original_env_var = os.environ.get("ANKIFORGE_ENV")
    original_custom_dir = os.environ.get("ANKIFORGE_DATA_DIR")
    yield
    import ankiforge.utils.environment as env_mod

    env_mod._current_env = None
    if original_env_var is not None:
        os.environ["ANKIFORGE_ENV"] = original_env_var
    else:
        os.environ.pop("ANKIFORGE_ENV", None)

    if original_custom_dir is not None:
        os.environ["ANKIFORGE_DATA_DIR"] = original_custom_dir
    else:
        os.environ.pop("ANKIFORGE_DATA_DIR", None)


def test_environment_explicit_env_vars():
    """Vérifie la détection via la variable ANKIFORGE_ENV."""
    set_environment(AppEnvironment.DEVELOPMENT)
    assert is_development()
    assert not is_production()
    assert not is_testing()
    assert get_environment_display_name() == "Développement"

    set_environment(AppEnvironment.PRODUCTION)
    assert is_production()
    assert not is_development()
    assert not is_testing()
    assert get_environment_display_name() == "Production"

    set_environment(AppEnvironment.TESTING)
    assert is_testing()
    assert not is_development()
    assert not is_production()
    assert get_environment_display_name() == "Test"


def test_set_environment_string_aliases():
    """Vérifie que les chaînes 'dev', 'prod' et 'test' sont correctement parsées."""
    set_environment("dev")
    assert is_development()

    set_environment("prod")
    assert is_production()

    set_environment("test")
    assert is_testing()

    with pytest.raises(ValueError, match="Environnement inconnu"):
        set_environment("invalid_env")


def test_cli_flags_override():
    """Vérifie que les drapeaux CLI --dev et --prod sont respectés."""
    import ankiforge.utils.environment as env_mod

    env_mod._current_env = None
    os.environ.pop("ANKIFORGE_ENV", None)
    os.environ.pop("PYTEST_CURRENT_TEST", None)

    with patch.object(sys, "argv", ["ankiforge", "--dev"]):
        assert get_current_environment() == AppEnvironment.DEVELOPMENT

    env_mod._current_env = None
    with patch.object(sys, "argv", ["ankiforge", "--prod"]):
        assert get_current_environment() == AppEnvironment.PRODUCTION


def test_frozen_binary_detection():
    """Vérifie qu'un binaire gelé sans drapeau CLI est identifié comme Production."""
    import ankiforge.utils.environment as env_mod

    env_mod._current_env = None
    os.environ.pop("ANKIFORGE_ENV", None)
    os.environ.pop("PYTEST_CURRENT_TEST", None)

    with patch.object(sys, "argv", ["ankiforge"]), patch.object(sys, "frozen", True, create=True):
        assert get_current_environment() == AppEnvironment.PRODUCTION


def test_app_data_dir_isolation():
    """Vérifie que get_app_data_dir() retourne des répertoires hermétiquement distincts."""
    os.environ.pop("ANKIFORGE_DATA_DIR", None)

    set_environment(AppEnvironment.DEVELOPMENT)
    dev_dir = get_app_data_dir()
    assert dev_dir.name == ".ankiforge-dev"
    assert dev_dir.parent == Path.home()

    set_environment(AppEnvironment.PRODUCTION)
    prod_dir = get_app_data_dir()
    assert prod_dir.name == ".ankiforge"
    assert prod_dir.parent == Path.home()

    set_environment(AppEnvironment.TESTING)
    test_dir = get_app_data_dir()
    assert test_dir.name == ".ankiforge-test"
    assert test_dir.parent == Path.home()

    assert dev_dir != prod_dir
    assert dev_dir != test_dir
    assert prod_dir != test_dir


def test_app_data_dir_custom_override(tmp_path: Path):
    """Vérifie que la variable ANKIFORGE_DATA_DIR a toujours la priorité absolue."""
    os.environ["ANKIFORGE_DATA_DIR"] = str(tmp_path / "custom_dir")
    set_environment(AppEnvironment.PRODUCTION)
    app_dir = get_app_data_dir()
    assert app_dir == tmp_path / "custom_dir"


def test_qsettings_isolation():
    """Vérifie que les domaines QSettings sont strictement séparés entre Dev, Prod et Test."""
    set_environment(AppEnvironment.DEVELOPMENT)
    assert get_settings_org_name() == "AnkiForgeOrg-Dev"
    assert get_settings_app_name() == "AnkiForge-Dev"

    set_environment(AppEnvironment.PRODUCTION)
    assert get_settings_org_name() == "AnkiForgeOrg"
    assert get_settings_app_name() == "AnkiForge"

    set_environment(AppEnvironment.TESTING)
    assert get_settings_org_name() == "AnkiForgeOrg-Test"
    assert get_settings_app_name() == "AnkiForge-Test"


def test_profile_manager_dynamic_profiles_dir():
    """Vérifie que ProfileManager s'adapte immédiatement au changement d'environnement."""
    os.environ.pop("ANKIFORGE_DATA_DIR", None)
    pm = ProfileManager()

    set_environment(AppEnvironment.DEVELOPMENT)
    assert pm.profiles_dir.name == "profiles"
    assert pm.profiles_dir.parent.name == ".ankiforge-dev"
    assert ProfileManager.PROFILES_DIR.parent.name == ".ankiforge-dev"

    set_environment(AppEnvironment.PRODUCTION)
    assert pm.profiles_dir.parent.name == ".ankiforge"
    assert ProfileManager.PROFILES_DIR.parent.name == ".ankiforge"


def test_get_tools_search_dirs():
    """Vérifie la chaîne de recherche des outils en mode développement."""
    os.environ.pop("ANKIFORGE_DATA_DIR", None)
    set_environment(AppEnvironment.DEVELOPMENT)

    search_dirs = get_tools_search_dirs()
    assert len(search_dirs) == 2
    assert search_dirs[0] == Path.home() / ".ankiforge-dev" / "tools"
    assert search_dirs[1] == Path.home() / ".ankiforge" / "tools"

    set_environment(AppEnvironment.PRODUCTION)
    search_dirs_prod = get_tools_search_dirs()
    assert len(search_dirs_prod) == 1
    assert search_dirs_prod[0] == Path.home() / ".ankiforge" / "tools"


def test_clone_production_data_to_development(tmp_path: Path):
    """Vérifie la copie sécurisée des profils et médias de production vers dev."""
    fake_prod = tmp_path / ".ankiforge"
    fake_dev = tmp_path / ".ankiforge-dev"

    prod_profile = fake_prod / "profiles" / "mon_espace"
    prod_profile.mkdir(parents=True)
    (prod_profile / "ankiforge.db").write_text("fake sqlite content")

    media_dir = prod_profile / "media"
    media_dir.mkdir()
    (media_dir / "sample_audio.mp3").write_text("fake audio")

    with patch.object(Path, "home", return_value=tmp_path):
        cloned_profiles, copied_media = clone_production_data_to_development(copy_media=True)

        assert cloned_profiles == 1
        assert copied_media == 1

        dev_db = fake_dev / "profiles" / "mon_espace" / "ankiforge.db"
        dev_media = fake_dev / "profiles" / "mon_espace" / "media" / "sample_audio.mp3"

        assert dev_db.exists()
        assert dev_db.read_text() == "fake sqlite content"
        assert dev_media.exists()
        assert dev_media.read_text() == "fake audio"
