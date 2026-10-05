"""Tests unitaires du mécanisme i18n (utils/i18n.py) : résolution, repli et installation."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QTranslator

from ankiforge.utils import i18n

TS_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="{language}">
<context>
    <name>DemoView</name>
    <message>
        <source>Bonjour</source>
        <translation>{translated}</translation>
    </message>
</context>
<context>
    <name></name>
    <message>
        <source>Enregistrer le document</source>
        <translation>{translated_free}</translation>
    </message>
    <message>
        <source>Fichiers traités : %1</source>
        <translation>{translated_reordered}</translation>
    </message>
</context>
</TS>
"""


def _lrelease(tool: Path, ts_file: Path) -> Path:
    """Compile un .ts en .qm via l'outil PySide6, échoue bruyamment sinon."""
    qm_file = ts_file.with_suffix(".qm")
    result = subprocess.run([str(tool), str(ts_file), "-qm", str(qm_file)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout
    assert qm_file.is_file()
    return qm_file


@pytest.fixture(scope="module")
def compiled_catalog(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Produit un vrai .qm (anglais) dans un dossier temporaire, via pyside6-lrelease."""
    catalog_dir = tmp_path_factory.mktemp("translations")
    ts_file = catalog_dir / "ankiforge_en.ts"
    tool = Path(sys.executable).parent / ("pyside6-lrelease.exe" if os.name == "nt" else "pyside6-lrelease")
    if not tool.exists():
        pytest.skip("pyside6-lrelease introuvable dans l'environnement courant")
    # La traduction réordonne le marqueur : "Fichiers traités : %1" devient "%1 fichiers
    # traités". Seul un test de substitution *après* traduction peut le constater.
    ts_file.write_text(
        TS_TEMPLATE.format(
            language="en_US",
            translated="Hello",
            translated_free="Save the document",
            translated_reordered="%1 files processed",
        ),
        encoding="utf-8",
    )
    _lrelease(tool, ts_file)
    return catalog_dir


# ── normalize_language ───────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Français", "fr"),
        ("français", "fr"),
        ("English", "en"),
        ("ENGLISH", "en"),
        ("fr", "fr"),
        ("fr_FR", "fr"),
        ("en-US", "en"),
        ("  Français  ", "fr"),
        ("de", "de"),
        (None, "fr"),
        ("", "fr"),
        (42, "fr"),
        ("???", "fr"),
    ],
)
def test_normalize_language(raw: object, expected: str) -> None:
    """Un réglage historique (« Français », « fr_FR », « English »…) ramène toujours à un code ISO."""
    assert i18n.normalize_language(raw) == expected


@pytest.mark.unit
def test_normalize_language_custom_default() -> None:
    """La valeur de repli est paramétrable, pour ne pas coder « fr » en dur chez l'appelant."""
    assert i18n.normalize_language("???", default="en") == "en"


@pytest.mark.unit
def test_normalize_language_without_match_returns_empty_default() -> None:
    """Avec un repli vide, une valeur inexploitable ne devient jamais un code inventé."""
    assert i18n.normalize_language("???", default="") == ""


# ── language_label ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_language_label_returns_endonym() -> None:
    """Un nom de langue s'affiche dans sa propre langue, quel que soit le code reçu."""
    assert i18n.language_label("fr_FR") == "Français"
    assert i18n.language_label("en") == "English"
    assert i18n.language_label("de") == "de"


# ── Résolution du dossier de catalogues ──────────────────────────────────────


def test_translations_dir_uses_paths_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le dossier est résolu par get_resource_path, et non figé depuis le module."""
    captured: list[tuple[str, ...]] = []

    def fake_get_resource_path(*subpaths: str) -> Path:
        captured.append(subpaths)
        return Path("/tmp/fake") / subpaths[-1]

    monkeypatch.setattr(i18n, "get_resource_path", fake_get_resource_path)
    assert i18n.translations_dir() == Path("/tmp/fake/translations")
    assert captured == [i18n.TRANSLATIONS_RELPATH]


def test_translations_dir_lives_inside_the_package() -> None:
    """Le dossier canonique est sous le paquet : une seule racine de ressources, pas deux.

    Régression directe du bug de nommage `src/ressources` vs `src/ankiforge/ressources`
    qui a cassé `database/seeds/initial_seed.py`.
    """
    assert i18n.TRANSLATIONS_RELPATH[:3] == ("src", "ankiforge", "resources")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("suffix", "expected"),
    [
        (".qm", "ankiforge_en.qm"),
        (".ts", "ankiforge_en.ts"),
    ],
)
def test_catalog_path_shape(tmp_path: Path, suffix: str, expected: str) -> None:
    """Le nom de catalogue dérive du préfixe, de la langue normalisée et du suffixe demandé."""
    assert i18n.catalog_path("English", suffix=suffix, directory=tmp_path) == tmp_path / expected
    assert i18n.catalog_path("fr", suffix=suffix, directory=tmp_path) == tmp_path / expected.replace("_en", "_fr")


def test_catalog_path_default_directory_is_the_resolved_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans directory explicite, le chemin passe par translations_dir()."""
    monkeypatch.setattr(i18n, "translations_dir", lambda: Path("/bundle/Contents/Resources/ankiforge/resources/translations"))
    assert i18n.catalog_path("en") == Path("/bundle/Contents/Resources/ankiforge/resources/translations/ankiforge_en.qm")


# ── available_languages ──────────────────────────────────────────────────────


def test_available_languages_empty_when_directory_missing(tmp_path: Path) -> None:
    """Sans dossier de catalogues, seule la langue source reste proposable — jamais une liste vide."""
    assert i18n.available_languages(tmp_path / "absent") == (i18n.SOURCE_LANGUAGE,)


def test_available_languages_orders_and_filters(tmp_path: Path) -> None:
    """Seuls les .qm comptent, les .ts sont ignorés, et l'ordre d'affichage est stable."""
    for name in ("ankiforge_en.qm", "ankiforge_fr.qm", "ankiforge_de.qm", "ankiforge_en.ts", "notes.txt"):
        (tmp_path / name).write_text("", encoding="utf-8")
    assert i18n.available_languages(tmp_path) == ("fr", "en", "de")


# ── install_translator ───────────────────────────────────────────────────────


@pytest.mark.ui
def test_install_translator_returns_none_for_source_language(qapp: object) -> None:
    """Le français est la langue source : aucun catalogue n'est installé, aucune erreur."""
    assert i18n.install_translator(qapp, "fr") is None  # type: ignore[arg-type]


@pytest.mark.ui
def test_install_translator_missing_catalog_falls_back_without_raising(qapp: object, tmp_path: Path) -> None:
    """Un catalogue absent ne lève pas : on reste silencieusement sur le français source."""
    assert i18n.install_translator(qapp, "en", directory=tmp_path) is None
    assert qapp.translate("", "Enregistrer le document") == "Enregistrer le document"  # type: ignore[attr-defined]


@pytest.mark.ui
def test_install_translator_reads_preferred_language_when_none(qapp: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans argument, la langue vient des réglages — et un réglage illisible retombe sur fr."""
    monkeypatch.setattr(i18n, "preferred_language", lambda: "en")
    assert i18n.install_translator(qapp, directory=tmp_path) is None

    def boom() -> str:
        raise RuntimeError("réglages indisponibles")

    monkeypatch.setattr(i18n, "preferred_language", boom)
    assert i18n.install_translator(qapp, directory=tmp_path) is None


@pytest.mark.ui
def test_install_translator_loads_real_catalog(qapp: object, compiled_catalog: Path) -> None:
    """Chaîne nominale : un vrai .qm traduit bien `self.tr()` comme `tr()`."""
    translator = i18n.install_translator(qapp, "en", directory=compiled_catalog)
    assert translator is not None
    try:
        assert QCoreApplication.translate("DemoView", "Bonjour") == "Hello"
        assert QCoreApplication.translate("", "Enregistrer le document") == "Save the document"
    finally:
        qapp.removeTranslator(translator)


@pytest.mark.ui
def test_untranslated_message_falls_back_to_source_text(qapp: object, compiled_catalog: Path) -> None:
    """Un message absent du catalogue restitue le texte source, jamais une chaîne vide."""
    translator = i18n.install_translator(qapp, "en", directory=compiled_catalog)
    assert translator is not None
    try:
        assert QCoreApplication.translate("DemoView", "Introuvable dans le catalogue") == "Introuvable dans le catalogue"
    finally:
        qapp.removeTranslator(translator)


@pytest.mark.ui
def test_install_translator_rejects_corrupted_catalog(qapp: object, tmp_path: Path) -> None:
    """Un .qm corrompu est refusé par Qt : on retombe sur le français au lieu de planter."""
    (tmp_path / "ankiforge_en.qm").write_bytes(b"ce n'est pas un catalogue Qt")
    assert i18n.install_translator(qapp, "en", directory=tmp_path) is None
    assert QCoreApplication.translate("", "Enregistrer le document") == "Enregistrer le document"


# ── tr() ─────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_tr_returns_source_without_translator() -> None:
    """Sans catalogue installé, tr() est l'identité — jamais une chaîne vide."""
    assert i18n.tr("Enregistrer le document") == "Enregistrer le document"


@pytest.mark.unit
def test_tr_uses_the_empty_context() -> None:
    """tr() parle le contexte vide : c'est la clé sous laquelle pylupdate range ces messages."""
    assert i18n.tr("Texte") == QCoreApplication.translate("", "Texte")


# ── tr() : forme interpolée ──────────────────────────────────────────────────


@pytest.mark.unit
def test_tr_resolves_numbered_placeholders() -> None:
    """Les marqueurs %1..%2 sont remplacés par les valeurs fournies, dans l'ordre."""
    assert i18n.tr("%1 sur %2", 7, 12) == "7 sur 12"


@pytest.mark.unit
def test_tr_resolves_the_free_n_marker() -> None:
    """``%n`` prend la plus petite position encore libre ; épuisé, il reste visible."""
    assert i18n.tr("%n de %n", "a") == "a de %n"
    assert i18n.tr("%n / %n", 3, 9) == "3 / 9"


@pytest.mark.unit
def test_tr_renders_a_literal_percent() -> None:
    """``%%`` produit un pourcentage littéral, sans consommer de valeur."""
    assert i18n.tr("Similarité : %1 %%", "92,5") == "Similarité : 92,5 %"


@pytest.mark.unit
def test_tr_keeps_an_orphan_placeholder_visible() -> None:
    """Un marqueur sans valeur reste affiché : une faute doit se voir, pas disparaître."""
    assert i18n.tr("%1 et %2", "seul") == "seul et %2"


@pytest.mark.unit
def test_tr_interpolated_falls_back_to_the_source_text() -> None:
    """Sans catalogue installé, la forme interpolée substitue le texte source."""
    assert i18n.tr("Note #%1 introuvable", 42) == "Note #42 introuvable"


@pytest.mark.unit
def test_tr_without_values_never_touches_placeholders() -> None:
    """Sans valeur fournie, un ``%1`` du texte est un caractère ordinaire, pas un marqueur."""
    assert i18n.tr("Couverture 100 %1") == "Couverture 100 %1"


@pytest.mark.ui
def test_tr_interpolated_uses_a_real_catalog(qapp: object, compiled_catalog: Path) -> None:
    """La substitution doit porter sur le texte TRADUIT, pas sur le source : ordre prouvant."""
    translator = QTranslator()
    assert translator.load(str(i18n.catalog_path("en", directory=compiled_catalog)))
    qapp.installTranslator(translator)
    try:
        # Le catalogue traduit "Fichiers traités : %1" en "%1 fichiers traités" : le
        # marqueur n'occupe pas la même place, seule la substitution post-traduction
        # produit le résultat attendu.
        assert i18n.tr("Fichiers traités : %1", 3) == "3 files processed"
    finally:
        qapp.removeTranslator(translator)
