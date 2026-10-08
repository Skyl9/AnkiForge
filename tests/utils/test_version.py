"""Tests unitaires pour le module de version et métadonnées ankiforge.version."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from ankiforge.version import (
    AppVersionInfo,
    __version__,
    get_version_info,
)

pytestmark = pytest.mark.unit

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _declared_version() -> str:
    """Version annoncée par la source de vérité du projet (``pyproject.toml``)."""
    pyproject = _PROJECT_ROOT / "pyproject.toml"
    if not pyproject.is_file():
        pytest.skip("pyproject.toml absent : exécution hors dépôt")
    with pyproject.open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def test_version_info_structure() -> None:
    """Vérifie la cohérence et les propriétés de la dataclass AppVersionInfo.

    La version est comparée à ``pyproject.toml`` plutôt qu'à un littéral figé : un
    chiffre en dur ici ne ferait que déplacer l'échec à la prochaine montée de
    version, au lieu de vérifier que l'application expose *bien* la version annoncée.
    """
    info = get_version_info()
    declared = _declared_version()
    assert isinstance(info, AppVersionInfo)
    assert info.version == declared
    assert __version__ == declared
    assert len(info.commit_hash) > 0
    assert len(info.platform_str) > 0
    assert info.build_channel in ("stable", "nightly", "dev")


def test_version_info_display_strings() -> None:
    """Vérifie le formatage des chaînes d'affichage courte et complète."""
    custom_info = AppVersionInfo(
        version="1.0.5",
        commit_hash="c673440a",
        build_date="2026-09-02T18:00:00Z",
        build_channel="stable",
        platform_str="macOS arm64",
        is_standalone=True,
    )

    assert custom_info.short_display_version == "v1.0.5"
    assert custom_info.full_display_version == "v1.0.5 (c673440a) · macOS arm64"

    nightly_info = AppVersionInfo(
        version="1.0.5-nightly",
        commit_hash="c673440a",
        build_date="2026-09-02T18:00:00Z",
        build_channel="nightly",
        platform_str="Linux x86_64",
        is_standalone=True,
    )
    assert "[NIGHTLY]" in nightly_info.full_display_version


def test_version_info_handles_v_prefix_cleanly() -> None:
    """Vérifie que la présence éventuelle d'un préfixe v ne produit jamais 'vv'."""
    info_with_v = AppVersionInfo(
        version="v1.1.0",
        commit_hash="abcdef12",
        build_date="2026-09-05T12:00:00Z",
        build_channel="stable",
        platform_str="macOS arm64",
        is_standalone=True,
    )
    assert info_with_v.short_display_version == "v1.1.0"
    assert info_with_v.full_display_version.startswith("v1.1.0")
    assert not info_with_v.short_display_version.startswith("vv")
