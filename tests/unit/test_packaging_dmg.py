import subprocess
from pathlib import Path

import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT_DIR = REPO_ROOT / "build_script"
DMG_SETTINGS_PATH = BUILD_SCRIPT_DIR / "dmg_settings.py"
DMG_SCRIPT_PATH = BUILD_SCRIPT_DIR / "package_dmg.sh"
OBSOLETE_SCRIPT_PATH = BUILD_SCRIPT_DIR / "create_dmg_mac.sh"
ASSETS_DIR = BUILD_SCRIPT_DIR / "assets"
BG_1X_PATH = ASSETS_DIR / "dmg_background.png"
BG_2X_PATH = ASSETS_DIR / "dmg_background@2x.png"


@pytest.mark.unit
def test_dmg_settings_file_and_parameters() -> None:
    """Vérifie que dmg_settings.py existe et expose les spécifications arrêtées."""
    assert DMG_SETTINGS_PATH.is_file(), f"Fichier de configuration manquant : {DMG_SETTINGS_PATH}"

    # Charger le fichier de configuration de manière isolée
    settings: dict[str, object] = {"__file__": str(DMG_SETTINGS_PATH)}
    with open(DMG_SETTINGS_PATH, encoding="utf-8") as f:
        exec(compile(f.read(), str(DMG_SETTINGS_PATH), "exec"), settings, settings)

    assert settings.get("volume_name") == "AnkiForge"
    assert settings.get("format") == "UDZO"
    assert settings.get("icon_size") == 120

    window_rect = settings.get("window_rect")
    assert isinstance(window_rect, tuple)
    assert len(window_rect) == 2
    # Dimensions (largeur, hauteur) : 640x420
    assert window_rect[1] == (640, 420)

    icon_locations = settings.get("icon_locations")
    assert isinstance(icon_locations, dict)
    assert icon_locations.get("AnkiForge.app") == (160, 205)
    assert icon_locations.get("Applications") == (480, 205)

    symlinks = settings.get("symlinks")
    assert isinstance(symlinks, dict)
    assert symlinks.get("Applications") == "/Applications"

    icon_path = settings.get("icon")
    assert icon_path is not None
    assert Path(str(icon_path)).is_file() or (REPO_ROOT / str(icon_path)).is_file()


@pytest.mark.unit
def test_dmg_background_assets_geometry() -> None:
    """Vérifie que les assets d'arrière-plan 1x et Retina 2x existent et ont les bonnes dimensions."""
    assert BG_1X_PATH.is_file(), f"Asset 1x manquant : {BG_1X_PATH}"
    assert BG_2X_PATH.is_file(), f"Asset 2x manquant : {BG_2X_PATH}"

    with Image.open(BG_1X_PATH) as img_1x:
        assert img_1x.format == "PNG"
        assert img_1x.size == (640, 420)

    with Image.open(BG_2X_PATH) as img_2x:
        assert img_2x.format == "PNG"
        assert img_2x.size == (1280, 840)


@pytest.mark.unit
def test_package_dmg_script_integrity() -> None:
    """Vérifie l'intégrité du script bash package_dmg.sh et la suppression du doublon obsolète."""
    assert DMG_SCRIPT_PATH.is_file(), f"Script manquant : {DMG_SCRIPT_PATH}"
    assert not OBSOLETE_SCRIPT_PATH.exists(), f"L'ancien script obsolète {OBSOLETE_SCRIPT_PATH} doit être supprimé"

    # Vérification syntaxique bash
    proc = subprocess.run(
        ["bash", "-n", str(DMG_SCRIPT_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"Erreur de syntaxe bash dans {DMG_SCRIPT_PATH} : {proc.stderr}"

    content = DMG_SCRIPT_PATH.read_text(encoding="utf-8")
    assert "dmgbuild" in content
    assert "dmg_settings.py" in content
    assert "set -euo pipefail" in content
