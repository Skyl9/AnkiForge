"""
Tests unitaires et d'intégration pour l'export et l'import de thèmes JSON (ADR 0005 & 0006).
Couvre :
- Sérialisation et conteneur de Famille (version, dark, light)
- Exclusion des jetons d'exécution et des jetons dérivés vides
- Inclusion des jetons dérivés explicitement définis
- Aller-retour export/import garantissant l'identité stricte
- Tolérance de la charge utile (champs optionnels et jetons partiels)
- Préservation des valeurs non déclarées (aucun reset au défaut)
- Rejet strict des versions majeures futures (avec version attendue et reçue)
- Rejet strict des champs invalides (couleurs mal formées, valeurs hors domaine)
- Renommage sur collision (suffixe numérique) sans écrasement
- Réécriture de l'identifiant de Variante et Famille dérivé du nom de fichier
- Balayage du répertoire au démarrage de StyleEngine et survie au redémarrage
- Intégration UI dans GeneralTab (boutons importer/exporter, sélection)
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ankiforge.ui.style_engine import (
    JETBRAINS_DARK,
    JETBRAINS_LIGHT,
    ThemeFamily,
    ThemeProfile,
    get_style_engine,
)
from ankiforge.ui.style_engine.theme_storage import (
    CURRENT_FORMAT_VERSION,
    CURRENT_MAJOR_VERSION,
    ThemeValidationError,
    UnsupportedThemeVersionError,
    import_theme_file,
    resolve_unique_theme_path,
    save_theme_family_to_library,
    theme_family_from_dict,
    theme_family_from_json,
    theme_family_to_dict,
    theme_family_to_json,
)


@pytest.fixture(autouse=True)
def clean_style_engine():
    engine = get_style_engine()
    engine.clear_custom_library()
    yield
    engine.clear_custom_library()


@pytest.fixture
def temp_themes_dir(tmp_path: Path) -> Path:
    """Répertoire temporaire isolé pour la bibliothèque de thèmes."""
    themes_dir = tmp_path / "themes"
    themes_dir.mkdir(parents=True, exist_ok=True)
    return themes_dir


@pytest.fixture
def sample_family() -> ThemeFamily:
    """Famille de thème personnalisée pour les tests avec jetons dérivés explicites."""
    dark = ThemeProfile(
        id="sample_dark",
        name="Sample Dark",
        description="Dark variant description",
        is_dark=True,
        bg_main="#121314",
        bg_sidebar="#18191a",
        bg_panel="#202122",
        bg_input="#252627",
        bg_hover="#303132",
        bg_active="rgba(100, 150, 200, 0.2)",
        accent_primary="#4f46e5",
        accent_hover="#4338ca",
        accent_glow="rgba(79, 70, 229, 0.4)",
        text_primary="#ffffff",
        text_secondary="#cbd5e1",
        text_muted="#94a3b8",
        border_color="#334155",
        border_light="rgba(255, 255, 255, 0.05)",
        border_focus="#4f46e5",
        color_blue="#38bdf8",
        color_green="#22c55e",
        color_yellow="#eab308",
        color_red="#ef4444",
        color_purple="#a855f7",
        radius_sm=4,
        radius_md=8,
        radius_lg=12,
        # Jeton dérivé explicitement défini
        accent_bg="rgba(79, 70, 229, 0.15)",
        color_green_bg="rgba(34, 197, 94, 0.20)",
        # Les autres jetons dérivés restent "" (non définis)
    )

    light = ThemeProfile(
        id="sample_light",
        name="Sample Light",
        description="Light variant description",
        is_dark=False,
        bg_main="#ffffff",
        bg_sidebar="#f8fafc",
        bg_panel="#f1f5f9",
        bg_input="#ffffff",
        bg_hover="#e2e8f0",
        bg_active="rgba(79, 70, 229, 0.12)",
        accent_primary="#4f46e5",
        accent_hover="#4338ca",
        accent_glow="rgba(79, 70, 229, 0.3)",
        text_primary="#0f172a",
        text_secondary="#475569",
        text_muted="#64748b",
        border_color="#cbd5e1",
        border_light="rgba(0, 0, 0, 0.05)",
        border_focus="#4f46e5",
        color_blue="#0284c7",
        color_green="#16a34a",
        color_yellow="#ca8a04",
        color_red="#dc2626",
        color_purple="#9333ea",
        radius_sm=4,
        radius_md=8,
        radius_lg=12,
    )

    return ThemeFamily(
        id="sample",
        name="Sample Theme",
        icon="ph.palette",
        description="Description de test",
        dark_theme=dark,
        light_theme=light,
    )


# ── 1. Conteneur Famille, Version et Sérialisation ──────────────────────────


@pytest.mark.unit
def test_theme_family_to_dict_and_json(sample_family: ThemeFamily):
    """Vérifie la structure du conteneur de Famille et la sérialisation conforme à l'ADR 0006."""
    data = theme_family_to_dict(sample_family)

    assert data["version"] == CURRENT_FORMAT_VERSION
    assert data["id"] == "sample"
    assert data["name"] == "Sample Theme"
    assert data["icon"] == "ph.palette"
    assert data["description"] == "Description de test"
    assert "dark" in data
    assert "light" in data

    # Vérification des jetons dérivés :
    # accent_bg et color_green_bg sont explicitement définis -> doivent être présents
    assert data["dark"]["accent_bg"] == "rgba(79, 70, 229, 0.15)"
    assert data["dark"]["color_green_bg"] == "rgba(34, 197, 94, 0.20)"

    # color_red_bg n'est pas défini ("") -> ne doit PAS être exporté
    assert "color_red_bg" not in data["dark"]
    assert "color_yellow_bg" not in data["dark"]

    # Jetons d'exécution DesignTokens non présents dans le conteneur
    assert "BRANCH_A" not in data["dark"]
    assert "SHADOW_SM_BLUR" not in data["dark"]
    assert "SIDEBAR_WIDTH_EXPANDED" not in data["dark"]

    json_str = theme_family_to_json(sample_family)
    parsed = json.loads(json_str)
    assert parsed["id"] == "sample"
    assert parsed["version"] == CURRENT_FORMAT_VERSION


# ── 2. Aller-retour Export / Import & Égalité stricte ────────────────────────


@pytest.mark.unit
def test_roundtrip_export_import_equality(sample_family: ThemeFamily):
    """Vérifie qu'un thème exporté puis réimporté est identique à l'original (critère 5)."""
    json_str = theme_family_to_json(sample_family)
    imported = theme_family_from_json(json_str, file_stem="sample")

    assert imported.id == sample_family.id
    assert imported.name == sample_family.name
    assert imported.icon == sample_family.icon
    assert imported.description == sample_family.description

    # Les variantes dérivent du stem
    assert imported.dark_theme.id == "sample_dark"
    assert imported.light_theme.id == "sample_light"

    # Comparaison de l'ensemble des champs visuels (sombres)
    for field_name in (
        "bg_main",
        "bg_sidebar",
        "bg_panel",
        "bg_input",
        "bg_hover",
        "bg_active",
        "accent_primary",
        "accent_hover",
        "accent_glow",
        "text_primary",
        "text_secondary",
        "text_muted",
        "border_color",
        "border_light",
        "border_focus",
        "color_blue",
        "color_green",
        "color_yellow",
        "color_red",
        "color_purple",
        "radius_sm",
        "radius_md",
        "radius_lg",
        "font_main",
        "font_code",
        "font_size_base",
        "font_size_sm",
        "syntax_tag",
        "syntax_attr",
        "syntax_string",
        "syntax_keyword",
        "syntax_variable",
        "syntax_comment",
        "syntax_number",
        "accent_bg",
        "color_green_bg",
    ):
        assert getattr(imported.dark_theme, field_name) == getattr(sample_family.dark_theme, field_name)

    # Les jetons dérivés non définis restent ""
    assert imported.dark_theme.color_red_bg == ""
    assert imported.dark_theme.color_yellow_bg == ""


# ── 3. Tolérance de la charge utile & Jetons partiels ────────────────────────


@pytest.mark.unit
def test_payload_tolerance_partial_variant_does_not_reset_to_default():
    """Chaque variante ne déclare que ce qu'elle définit ; un jeton absent ne remet jamais une valeur à son défaut."""
    raw_payload = {
        "version": 1,
        "name": "Custom Partial",
        "dark": {
            "bg_main": "#050505",
            "accent_primary": "#ff0077",
            # Des champs optionnels inconnus sont tolérés sans erreur
            "future_spec_custom_shadow": "0 4px 10px rgba(0,0,0,0.5)",
            "author_notes": "Theme designed for night reading",
        },
    }

    imported = theme_family_from_dict(raw_payload, file_stem="custom_partial")
    assert imported.id == "custom_partial"
    assert imported.dark_theme.bg_main == "#050505"
    assert imported.dark_theme.accent_primary == "#ff0077"

    # Les champs non précisés conservent les valeurs de la base (JETBRAINS_DARK)
    assert imported.dark_theme.bg_sidebar == JETBRAINS_DARK.bg_sidebar
    assert imported.dark_theme.text_primary == JETBRAINS_DARK.text_primary
    assert imported.dark_theme.color_blue == JETBRAINS_DARK.color_blue

    # La variante claire absente du dict est générée à partir du repli clair sans planter
    assert imported.light_theme.bg_main == JETBRAINS_LIGHT.bg_main


@pytest.mark.unit
def test_payload_tolerance_with_explicit_base_profile(sample_family: ThemeFamily):
    """L'import sur une base existante n'écrase que les champs présents."""
    patch_data = {
        "version": "1.0",
        "dark": {
            "bg_main": "#990000",
        },
    }

    imported = theme_family_from_dict(patch_data, file_stem="patched", base_family=sample_family)
    # bg_main est écrasé
    assert imported.dark_theme.bg_main == "#990000"
    # Les autres champs de sample_family sont préservés, pas remis à JETBRAINS_DARK
    assert imported.dark_theme.bg_sidebar == sample_family.dark_theme.bg_sidebar
    assert imported.dark_theme.accent_primary == sample_family.dark_theme.accent_primary
    assert imported.dark_theme.accent_bg == sample_family.dark_theme.accent_bg


# ── 4. Versionnage strict & Rejet des versions majeures supérieures ──────────


@pytest.mark.unit
def test_reject_unsupported_major_version():
    """Un fichier avec version majeure > connue est rejeté avec message nommant version attendue et reçue."""
    data = {
        "version": "2.0",
        "id": "future_theme",
        "name": "Future Theme",
        "dark": {"bg_main": "#000000"},
    }

    with pytest.raises(UnsupportedThemeVersionError) as exc_info:
        theme_family_from_dict(data)

    msg = str(exc_info.value)
    # Le message nomme explicitement la version attendue et la version reçue
    assert "2.0" in msg or "2" in msg
    assert str(CURRENT_MAJOR_VERSION) in msg or "1" in msg


@pytest.mark.unit
def test_reject_invalid_version_format():
    """Une version mal formée lève une erreur de version."""
    data = {
        "version": "invalide",
        "name": "Bad Version",
    }
    with pytest.raises(UnsupportedThemeVersionError):
        theme_family_from_dict(data)


# ── 5. Validation des champs (Rejet sans application silencieuse) ────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("bg_main", "not_a_color"),
        ("bg_main", "#xyz"),
        ("bg_main", "rgba(300, 0, 0, 1)"),
        ("bg_main", 12345),
        ("radius_sm", -1),
        ("radius_sm", "small"),
        ("font_size_base", 0),
        ("font_size_base", -5),
        ("font_size_base", "12px"),
        ("is_dark", "true"),
        ("is_dark", 1),
    ],
)
def test_reject_invalid_fields(field: str, bad_value: object):
    """Un champ présent mais invalide est rejeté, jamais appliqué silencieusement (critère 8)."""
    data = {
        "version": 1,
        "name": "Invalid Field Test",
        "dark": {
            field: bad_value,
        },
    }
    with pytest.raises(ThemeValidationError) as exc_info:
        theme_family_from_dict(data)

    assert field in str(exc_info.value)


# ── 6. Résolution de collision & Réécriture d'identifiant ─────────────────────


@pytest.mark.unit
def test_collision_resolution_numeric_suffix(temp_themes_dir: Path):
    """L'import d'un fichier en collision renomme systématiquement avec suffixe numérique sans écraser."""
    # Créer un fichier existant
    (temp_themes_dir / "my_theme.json").write_text('{"existing": true}', encoding="utf-8")

    path1 = resolve_unique_theme_path(temp_themes_dir, "my_theme")
    assert path1.name == "my_theme_1.json"

    # Créer le premier suffixé
    path1.write_text('{"existing_1": true}', encoding="utf-8")
    path2 = resolve_unique_theme_path(temp_themes_dir, "my_theme")
    assert path2.name == "my_theme_2.json"

    # Le fichier initial n'a pas été écrasé
    assert (temp_themes_dir / "my_theme.json").read_text(encoding="utf-8") == '{"existing": true}'


@pytest.mark.unit
def test_import_theme_file_rewrites_variant_id_from_filename(temp_themes_dir: Path, sample_family: ThemeFamily):
    """L'identifiant de la Variante et Famille est réécrit pour dériver du nom de fichier final."""
    # Exporter le sample dans un fichier source
    source_file = temp_themes_dir / "external_download.json"
    source_file.write_text(theme_family_to_json(sample_family), encoding="utf-8")

    # Créer au préalable un fichier cible pour forcer une collision
    (temp_themes_dir / "external_download.json").touch()

    # Importer dans le répertoire
    family, saved_path = import_theme_file(source_file, themes_dir=temp_themes_dir)

    # Doit avoir été renommé avec un suffixe numérique
    assert saved_path.name == "external_download_1.json"
    assert family.id == "external_download_1"
    assert family.dark_theme.id == "external_download_1_dark"
    assert family.light_theme.id == "external_download_1_light"

    # Le contenu JSON sauvegardé sur disque porte aussi ces identifiants réécrits
    saved_json = json.loads(saved_path.read_text(encoding="utf-8"))
    assert saved_json["id"] == "external_download_1"
    assert saved_json["dark"]["id"] == "external_download_1_dark"
    assert saved_json["light"]["id"] == "external_download_1_light"


# ── 7. Bibliothèque globale & Balayage StyleEngine au démarrage ──────────────


@pytest.mark.unit
def test_style_engine_scans_library_and_survives_restart(temp_themes_dir: Path, sample_family: ThemeFamily):
    """Le registre mémoire est peuplé par balayage du répertoire et survit au redémarrage."""
    engine = get_style_engine()

    # Sauvegarder un thème personnalisé dans le dossier de bibliothèque
    save_theme_family_to_library(sample_family, themes_dir=temp_themes_dir, target_stem="persisted_custom")

    # Balayer la bibliothèque avec le dossier temporaire
    with patch("ankiforge.utils.paths.get_themes_dir", return_value=temp_themes_dir):
        loaded_families = engine.load_theme_library(themes_dir=temp_themes_dir)
        assert any(f.id == "persisted_custom" for f in loaded_families)

        # Vérifier présence dans StyleEngine
        all_families = engine.get_theme_families()
        assert any(f.id == "persisted_custom" for f in all_families)

        # Vérifier que les variantes sont accessibles par get_theme
        assert engine.get_theme("persisted_custom_dark").bg_main == sample_family.dark_theme.bg_main
        assert engine.get_theme("persisted_custom_light").bg_main == sample_family.light_theme.bg_main

        # Vérifier que get_family_for_theme retrouve la famille
        fam = engine.get_family_for_theme("persisted_custom_dark")
        assert fam is not None
        assert fam.id == "persisted_custom"

        # Simuler un redémarrage (nouvel appel de balayage)
        engine.load_theme_library(themes_dir=temp_themes_dir)
        assert engine.get_family_for_theme("persisted_custom") is not None


# ── 8. Intégration UI dans GeneralTab ─────────────────────────────────────────


@pytest.mark.ui
def test_general_tab_theme_import_export_buttons(qtbot, temp_themes_dir: Path, sample_family: ThemeFamily):
    """Vérifie la présence des boutons d'import/export et la sélection du thème importé dans l'onglet Général."""
    from ankiforge.ui.widgets.settings_modal.tabs.general_tab import GeneralTab

    with patch("ankiforge.utils.paths.get_themes_dir", return_value=temp_themes_dir):
        engine = get_style_engine()
        engine.load_theme_library(themes_dir=temp_themes_dir)

        tab = GeneralTab()
        qtbot.addWidget(tab)

        assert hasattr(tab, "btn_import_theme")
        assert hasattr(tab, "btn_export_theme")

        # Exporter un fichier de test en dehors de la bibliothèque (ex: dossier de téléchargements)
        downloads_dir = temp_themes_dir.parent / "downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        export_file = downloads_dir / "test_import.json"
        export_file.write_text(theme_family_to_json(sample_family), encoding="utf-8")

        # Simuler un import via QFileDialog
        with patch("PySide6.QtWidgets.QFileDialog.getOpenFileName", return_value=(str(export_file), "JSON")):
            tab._import_theme()

        # Le thème importé doit maintenant être présent et sélectionné dans cb_theme
        assert tab.cb_theme.currentData() == "test_import"

        # Simuler également un export via QFileDialog
        target_export = downloads_dir / "exported_theme.json"
        with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(target_export), "JSON")):
            tab._export_theme()

        assert target_export.exists()
        exported_data = json.loads(target_export.read_text(encoding="utf-8"))
        assert exported_data["id"] == "test_import"
