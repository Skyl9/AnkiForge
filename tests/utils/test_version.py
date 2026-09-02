"""Tests unitaires pour le module de version et métadonnées ankiforge.version."""

from __future__ import annotations

from ankiforge.version import (
    AppVersionInfo,
    __version__,
    get_version_info,
)


def test_version_info_structure() -> None:
    """Vérifie la cohérence et les propriétés de la dataclass AppVersionInfo."""
    info = get_version_info()
    assert isinstance(info, AppVersionInfo)
    assert info.version == "1.0.5"
    assert __version__ == "1.0.5"
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
