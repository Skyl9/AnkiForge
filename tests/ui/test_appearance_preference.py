"""Contrat de persistance à deux axes de l'apparence (cf. ADR 0004).

L'apparence n'est plus persistée comme un identifiant de thème unique : on persiste
la Famille de Thème choisie et la Source du Mode, et la Variante effective est un
calcul dérivé des deux.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from ankiforge.database.models import SettingModel
from ankiforge.ui.layouts.layout_manager import LayoutManager
from ankiforge.ui.style_engine import ModeSource, StyleEngine, ThemeFamily, get_style_engine
from ankiforge.ui.style_engine.appearance import AppearancePreference
from ankiforge.utils.environment import get_app_qsettings

pytestmark = pytest.mark.ui

LAYOUT_IDS = ("ide", "dashboard", "glassmorphism", "macos")
MANUAL_SOURCES = (ModeSource.DARK, ModeSource.LIGHT)


@pytest.fixture(autouse=True)
def clear_appearance_store() -> Iterator[None]:
    """Isole la BDD et le QSettings scopé « obsidian » où vivent les préférences d'apparence."""
    from ankiforge.ui.style_engine import appearance

    appearance.release_system_mode_source()
    get_app_qsettings("obsidian").clear()
    yield
    appearance.release_system_mode_source()
    get_app_qsettings("obsidian").clear()
    SettingModel.delete().where(SettingModel.key.startswith("profiles/")).execute()


def _family(engine: StyleEngine, family_id: str) -> ThemeFamily:
    family = engine.get_family_for_theme(family_id)
    assert family is not None, f"famille inconnue : {family_id}"
    return family


def _expected_variant_id(engine: StyleEngine, family_id: str, source: ModeSource) -> str:
    family = _family(engine, family_id)
    return family.dark_theme.id if source is ModeSource.DARK else family.light_theme.id


# ─────────────────────────────── Source du Mode ───────────────────────────────


@pytest.mark.parametrize("source", MANUAL_SOURCES)
def test_manual_mode_source_forces_the_regime(source: ModeSource) -> None:
    engine = get_style_engine()
    preference = AppearancePreference(family_id="nord", mode_source=source, last_manual_mode=source)

    variant = engine.resolve_appearance(preference)

    assert variant.id == _expected_variant_id(engine, "nord", source)


def test_system_source_uses_the_regime_declared_by_the_platform() -> None:
    from ankiforge.ui.style_engine import appearance

    engine = get_style_engine()
    appearance.force_system_mode_source(ModeSource.LIGHT)
    preference = AppearancePreference(family_id="tokyo", mode_source=ModeSource.SYSTEM, last_manual_mode=ModeSource.DARK)

    variant = engine.resolve_appearance(preference)

    assert variant.id == _expected_variant_id(engine, "tokyo", ModeSource.LIGHT)
    assert variant.is_dark is False


def test_system_source_falls_back_to_last_manual_mode_when_platform_declares_nothing() -> None:
    from ankiforge.ui.style_engine import appearance

    engine = get_style_engine()
    appearance.release_system_mode_source()
    preference = AppearancePreference(family_id="tokyo", mode_source=ModeSource.SYSTEM, last_manual_mode=ModeSource.LIGHT)

    variant = engine.resolve_appearance(preference)

    assert variant.id == _expected_variant_id(engine, "tokyo", ModeSource.LIGHT)


def test_manual_mode_source_ignores_the_platform_regime() -> None:
    from ankiforge.ui.style_engine import appearance

    engine = get_style_engine()
    appearance.force_system_mode_source(ModeSource.LIGHT)
    preference = AppearancePreference(family_id="solarized", mode_source=ModeSource.DARK, last_manual_mode=ModeSource.DARK)

    assert engine.resolve_appearance(preference).id == _expected_variant_id(engine, "solarized", ModeSource.DARK)


def test_last_manual_mode_is_always_a_manual_regime() -> None:
    """Invariant : le repli porte toujours un régime choisi à la main, jamais « Système »."""
    coerced = AppearancePreference(family_id="dracula", mode_source=ModeSource.LIGHT, last_manual_mode=ModeSource.SYSTEM)
    assert coerced.last_manual_mode is ModeSource.LIGHT

    followed = AppearancePreference(family_id="dracula", mode_source=ModeSource.SYSTEM, last_manual_mode=ModeSource.LIGHT)
    assert followed.last_manual_mode is ModeSource.LIGHT
    assert followed.resolve_mode() is ModeSource.LIGHT


def test_mode_source_coercion_is_tolerant_to_garbage() -> None:
    assert ModeSource.coerce("light") is ModeSource.LIGHT
    assert ModeSource.coerce("SYSTEM") is ModeSource.SYSTEM
    assert ModeSource.coerce("turbo") is ModeSource.DARK
    assert ModeSource.coerce(None, default=ModeSource.LIGHT) is ModeSource.LIGHT
    assert ModeSource.coerce(42, default=ModeSource.LIGHT) is ModeSource.LIGHT


# ─────────────────────────────── Aller-retour par profil ───────────────────────────────


@pytest.mark.parametrize("source", [ModeSource.DARK, ModeSource.LIGHT, ModeSource.SYSTEM])
@pytest.mark.parametrize("profile_name", ["atelier", "revisions"])
def test_appearance_round_trip_per_profile_for_each_mode_source(profile_name: str, source: ModeSource) -> None:
    engine = get_style_engine()
    # Seul « Système » porte un repli indépendant : un régime manuel est le dernier régime manuel.
    fallback = ModeSource.LIGHT if source is ModeSource.SYSTEM else source
    written = AppearancePreference(family_id="catppuccin", mode_source=source, last_manual_mode=fallback)

    persisted = engine.save_appearance_preference(profile_name, written)
    read_back = engine.get_appearance_preference(profile_name)

    assert read_back == written
    assert persisted == written
    assert read_back.family_id == "catppuccin"
    assert read_back.mode_source is source
    assert read_back.last_manual_mode is fallback


def test_round_trip_preserves_an_absent_family() -> None:
    """L'absence de Famille est un état valide : « suit la Famille par défaut du layout »."""
    engine = get_style_engine()
    written = AppearancePreference(family_id=None, mode_source=ModeSource.LIGHT, last_manual_mode=ModeSource.LIGHT)

    engine.save_appearance_preference("sans-famille", written)

    assert engine.get_appearance_preference("sans-famille").family_id is None


# ─────────────────────────────── Lecture héritée pré-refactoring ───────────────────────────────


@pytest.mark.parametrize(
    ("legacy_theme_id", "expected_family", "expected_source"),
    [
        ("ide", "jetbrains", ModeSource.DARK),
        ("dashboard", "emerald", ModeSource.DARK),
        ("macos_light", "macos", ModeSource.LIGHT),
        ("dracula_official", "dracula", ModeSource.DARK),
        ("cyber_glass_light", "glassmorphism", ModeSource.LIGHT),
    ],
)
def test_legacy_theme_id_is_interpreted_as_two_axes(legacy_theme_id: str, expected_family: str, expected_source: ModeSource) -> None:
    """Une préférence antérieure au refactoring produit exactement le même rendu qu'avant."""
    engine = get_style_engine()
    get_app_qsettings("obsidian").setValue("profiles/heritage/theme_id", legacy_theme_id)

    preference = engine.get_appearance_preference("heritage")
    variant = engine.resolve_appearance(preference, layout_id="ide")

    assert preference.family_id == expected_family
    assert preference.mode_source is expected_source
    assert variant.id == _expected_variant_id(engine, expected_family, expected_source)
    assert variant.id == engine.get_theme(legacy_theme_id).id


def test_legacy_preference_is_read_without_migration() -> None:
    """La lecture est normalisée, pas migrée : l'identifiant hérité n'est ni réécrit ni effacé."""
    engine = get_style_engine()
    SettingModel.set_value("profiles/heritage/theme_id", "nord_light", category="appearance")

    preference = engine.get_appearance_preference("heritage")

    assert (preference.family_id, preference.mode_source) == ("nord", ModeSource.LIGHT)
    assert SettingModel.get_value("profiles/heritage/theme_id") == "nord_light"
    assert SettingModel.get_value("profiles/heritage/mode_source") is None


def test_legacy_theme_id_read_from_the_database_is_interpreted() -> None:
    engine = get_style_engine()
    SettingModel.set_value("profiles/heritage/theme_id", "tokyo_day", category="appearance")

    preference = engine.get_appearance_preference("heritage")

    assert (preference.family_id, preference.mode_source) == ("tokyo", ModeSource.LIGHT)


def test_axes_present_suppress_the_legacy_interpretation() -> None:
    engine = get_style_engine()
    get_app_qsettings("obsidian").setValue("profiles/mixte/theme_id", "nord_light")
    get_app_qsettings("obsidian").setValue("profiles/mixte/mode_source", "dark")

    preference = engine.get_appearance_preference("mixte")

    assert preference.family_id is None
    assert preference.mode_source is ModeSource.DARK


# ─────────────────────────────── Famille par défaut du layout ───────────────────────────────


@pytest.mark.parametrize("layout_id", LAYOUT_IDS)
@pytest.mark.parametrize("source", MANUAL_SOURCES)
def test_absent_family_follows_the_layout_default(layout_id: str, source: ModeSource) -> None:
    engine = get_style_engine()
    preference = AppearancePreference(family_id=None, mode_source=source, last_manual_mode=source)

    variant = engine.resolve_appearance(preference, layout_id=layout_id)

    assert variant.id == _expected_variant_id(engine, LayoutManager.get_default_family_id(layout_id), source)


@pytest.mark.parametrize("layout_id", LAYOUT_IDS)
def test_explicit_family_is_never_replaced_by_a_layout_default(layout_id: str) -> None:
    engine = get_style_engine()
    preference = AppearancePreference(family_id="monokai", mode_source=ModeSource.DARK, last_manual_mode=ModeSource.DARK)

    variant = engine.resolve_appearance(preference, layout_id=layout_id)

    assert variant.id == _expected_variant_id(engine, "monokai", ModeSource.DARK)
    assert LayoutManager.get_default_family_id(layout_id) != "monokai"


@pytest.mark.parametrize("layout_id", LAYOUT_IDS)
def test_layout_switch_reapplies_the_persisted_family(layout_id: str) -> None:
    """Changer de layout réapplique l'apparence du profil sans écraser la Famille choisie."""
    engine = get_style_engine()
    engine.save_appearance_preference("hot-swap", AppearancePreference(family_id="one_pro", mode_source=ModeSource.LIGHT, last_manual_mode=ModeSource.LIGHT))

    for candidate in LAYOUT_IDS:
        LayoutManager.apply_theme_for_layout(candidate, profile_name="hot-swap")
        assert engine.current_theme.id == _expected_variant_id(engine, "one_pro", ModeSource.LIGHT)


def test_layout_switch_follows_the_default_family_when_none_is_chosen() -> None:
    engine = get_style_engine()
    engine.save_appearance_preference("suivi", AppearancePreference(family_id=None, mode_source=ModeSource.DARK, last_manual_mode=ModeSource.DARK))

    for layout_id in LAYOUT_IDS:
        LayoutManager.apply_theme_for_layout(layout_id, profile_name="suivi")
        assert engine.current_theme.id == _expected_variant_id(engine, LayoutManager.get_default_family_id(layout_id), ModeSource.DARK)


def test_unknown_layout_id_falls_back_to_the_default_layout_family() -> None:
    engine = get_style_engine()
    preference = AppearancePreference(family_id=None, mode_source=ModeSource.DARK, last_manual_mode=ModeSource.DARK)

    variant = engine.resolve_appearance(preference, layout_id="nexiste-pas")

    assert variant.id == _expected_variant_id(engine, LayoutManager.get_default_family_id(LayoutManager.DEFAULT_LAYOUT_ID), ModeSource.DARK)


# ─────────────────────────────── Application à chaud ───────────────────────────────


def test_apply_appearance_updates_tokens_and_signal() -> None:
    engine = get_style_engine()
    emitted: list[str] = []
    engine.theme_changed.connect(lambda profile: emitted.append(profile.id))

    variant = engine.apply_appearance(AppearancePreference(family_id="synthwave", mode_source=ModeSource.LIGHT, last_manual_mode=ModeSource.LIGHT), layout_id="ide")

    assert engine.current_theme is variant
    assert emitted == [variant.id]


def test_apply_appearance_for_profile_reads_then_resolves() -> None:
    from ankiforge.ui.theme import DesignTokens

    engine = get_style_engine()
    engine.save_appearance_preference("applique", AppearancePreference(family_id="glassmorphism", mode_source=ModeSource.DARK, last_manual_mode=ModeSource.DARK))

    variant = engine.apply_appearance_for_profile("applique", layout_id="macos")

    assert variant.id == _expected_variant_id(engine, "glassmorphism", ModeSource.DARK)
    assert variant.id == DesignTokens.ACTIVE_THEME_ID
    assert DesignTokens.is_dark_mode() is True


def test_nothing_persisted_resolves_to_the_default_layout_family_in_dark() -> None:
    engine = get_style_engine()

    preference = engine.get_appearance_preference("jamais-vu")
    variant = engine.resolve_appearance(preference, layout_id="ide")

    assert preference == AppearancePreference(family_id=None, mode_source=ModeSource.DARK, last_manual_mode=ModeSource.DARK)
    assert variant.id == "ide"


def test_preference_from_theme_id_interprets_a_concrete_variant() -> None:
    engine = get_style_engine()

    assert engine.preference_from_theme_id("catppuccin_mocha") == AppearancePreference(family_id="catppuccin", mode_source=ModeSource.DARK, last_manual_mode=ModeSource.DARK)
    assert engine.preference_from_theme_id("catppuccin_latte") == AppearancePreference(family_id="catppuccin", mode_source=ModeSource.LIGHT, last_manual_mode=ModeSource.LIGHT)


def test_unknown_legacy_theme_id_keeps_the_silent_fallback_regime() -> None:
    engine = get_style_engine()

    preference = engine.preference_from_theme_id("identifiant-obsolete")

    assert preference.family_id is None
    assert preference.mode_source is ModeSource.DARK
    assert engine.resolve_appearance(preference, layout_id="ide").id == "ide"
