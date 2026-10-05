"""Tests du packaging des catalogues i18n dans le bundle Nuitka (ADR 0013).

Un catalogue absent du bundle ne provoque **aucune erreur** : l'application démarre et
parle français. C'est précisément ce qui rend le défaut invisible jusqu'à ce qu'un
utilisateur anglophone signale que le sélecteur de langue est vide. Ces tests vérifient
donc la copie **et** la résolution, dans une arborescence qui reproduit fidèlement celle
d'un bundle compilé — c'est le seul moyen de ne pas reproduire l'erreur de chemin
masquée par `tests/database/test_models.py`.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ``build_standalone.py`` importe ses frères par nom plat (``copy_runtime_dependencies``),
# ce qui n'est résolu que si ``script/`` est sur le ``sys.path``. Le paquet ``script.*``
# ne suffit pas : c'est la même raison pour laquelle le script refuse d'être exécuté
# depuis un autre répertoire sans ``PYTHONPATH``.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))

from build_standalone import copy_app_resources_to_bundle  # noqa: E402 — dépend du sys.path ci-dessus

from ankiforge.utils import i18n  # noqa: E402 — idem


@pytest.fixture
def frozen_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Reproduit un bundle Nuitka : exécutable dans ``Contents/MacOS``, données dans ``Contents/Resources``."""
    dist_dir = tmp_path / "AnkiForge.app"
    macos_dir = dist_dir / "Contents" / "MacOS"
    macos_dir.mkdir(parents=True)
    executable = macos_dir / "AnkiForge"
    executable.touch()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    return dist_dir


def test_catalogs_are_copied_into_the_mac_bundle(frozen_bundle: Path) -> None:
    """``copy_app_resources_to_bundle`` doit déposer les catalogues là où Qt ira les lire."""
    copy_app_resources_to_bundle(frozen_bundle, "darwin")

    translations = frozen_bundle / "Contents" / "Resources" / "src" / "ankiforge" / "resources" / "translations"
    assert translations.is_dir(), f"Catalogues absents du bundle : {translations}"
    assert list(translations.glob("*.ts")), "Aucun catalogue source embarqué"


def test_catalogs_survive_a_missing_legacy_resources_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``src/ressources`` absent ne doit plus faire disparaître ``src/ankiforge/resources``.

    L'ancien code faisait un ``return`` dès que le premier dossier manquait : les
    catalogues, qui vivent dans le second, disparaissaient du bundle sans le moindre
    avertissement.
    """
    project_root = tmp_path / "projet"
    (project_root / "src" / "ankiforge" / "resources" / "translations").mkdir(parents=True)
    (project_root / "src" / "ankiforge" / "resources" / "translations" / "ankiforge_en.ts").write_text("<TS/>", encoding="utf-8")

    monkeypatch.setattr("build_standalone.PROJECT_ROOT", project_root)
    copy_app_resources_to_bundle(tmp_path / "dist", "linux")

    copied = tmp_path / "dist" / "src" / "ankiforge" / "resources" / "translations" / "ankiforge_en.ts"
    assert copied.is_file(), f"Catalogues non copiés : {copied}"


def test_translations_resolve_inside_a_frozen_mac_bundle(frozen_bundle: Path) -> None:
    """Résolution de bout en bout : chemin bundle → ``get_resource_path`` → catalogue trouvé."""
    copy_app_resources_to_bundle(frozen_bundle, "darwin")
    source_ts = Path(i18n.translations_dir()) / f"{i18n.CATALOG_STEM}_{i18n.SOURCE_LANGUAGE}.ts"
    if not source_ts.is_file():
        pytest.skip("Catalogue source absent : lancer script/extract_translations.py")

    resolved = i18n.translations_dir()
    assert resolved == frozen_bundle / "Contents" / "Resources" / "src" / "ankiforge" / "resources" / "translations"
    assert source_ts.name in {path.name for path in resolved.glob("*.ts")}


def test_translations_resolve_inside_a_flat_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hors macOS, l'exécutable est à la racine du dossier distribué : même contrat de résolution."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    executable = dist_dir / "AnkiForge"
    executable.touch()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    copy_app_resources_to_bundle(dist_dir, "linux")

    assert i18n.translations_dir() == dist_dir / "src" / "ankiforge" / "resources" / "translations"


# ── 2. Les deux coutures de build déclarent les catalogues compilés ──────────────
#
# Les `.ts` seuls ne servent qu'à l'extraction : à l'exécution, Qt lit le `.qm`. Or les
# `.qm` sont des artefacts de compilation, donc ignorés par Git — et, par ricochet, par
# hatchling, qui respecte les fichiers d'exclusion du VCS. Un artefact absent d'une couture
# de build ne produit aucune erreur : l'application démarre en français.


def test_nuitka_config_embeds_compiled_catalogs() -> None:
    config = json.loads((PROJECT_ROOT / "build_script" / "nuitka_config.json").read_text(encoding="utf-8"))
    data_files = config["common"]["include_data_files"]

    qm_patterns = {pattern for pattern in data_files if pattern.endswith(".qm")}
    assert qm_patterns, f"Aucun catalogue compilé dans nuitka_config.json : {sorted(data_files)}"

    translations_dir = Path(*i18n.TRANSLATIONS_RELPATH[1:])
    destinations = {data_files[pattern] for pattern in qm_patterns}
    assert any(str(destinations_entry).endswith(str(translations_dir)) for destinations_entry in destinations), f"Les `.qm` ne sont pas copiés vers {translations_dir} : {destinations}"


def test_wheel_reincludes_compiled_catalogs() -> None:
    """Hatchling exclut ce que Git ignore : sans `artifacts`, le wheel n'a aucun catalogue."""
    config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    artifacts = config["tool"]["hatch"]["build"]["targets"]["wheel"].get("artifacts", [])

    assert any(pattern.endswith(".qm") for pattern in artifacts), f"pyproject.toml ne réintègre pas les `.qm` : le wheel partirait sans traduction. Déclaré : {artifacts}"
