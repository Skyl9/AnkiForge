"""Tests d'intégrité des constantes de téléchargement Piper (assertions de plomb)."""

from __future__ import annotations

import re

import pytest

from ankiforge.services.cards.tts_service import (
    _MAX_PIPER_ARCHIVE_BYTES,
    _PIPER_ASSETS,
    _PIPER_VOICE_SHA256,
)

pytestmark = pytest.mark.unit


def test_all_assets_are_sha256_hex() -> None:
    for (sys_name, arch), (asset, sha, is_tar) in _PIPER_ASSETS.items():
        assert re.fullmatch(r"[0-9a-f]{64}", sha), f"SHA-256 invalide pour {sys_name}/{arch}"
        assert sys_name in {"Darwin", "Linux", "Windows"}
        assert asset.endswith(".tar.gz") if is_tar else asset.endswith(".zip")


def test_all_supported_platforms_covered() -> None:
    keys = set(_PIPER_ASSETS)
    assert ("Darwin", "arm64") in keys
    assert ("Darwin", "x86_64") in keys
    assert ("Linux", "arm64") in keys
    assert ("Linux", "x86_64") in keys
    assert ("Windows", "amd64") in keys
    assert len(keys) == 5


def test_voice_hashes_are_sha256_hex() -> None:
    for fname, sha in _PIPER_VOICE_SHA256.items():
        assert fname.endswith(".onnx") or fname.endswith(".onnx.json")
        assert re.fullmatch(r"[0-9a-f]{64}", sha), f"SHA-256 invalide pour {fname}"


def test_archive_size_cap_sane() -> None:
    # Les archives Piper pèsent ~20-26 Mo ; le plafond doit rester confortable
    # tout en refusant un grossissement anormal des binaires (~150 Mo répartis)
    assert _MAX_PIPER_ARCHIVE_BYTES >= 50 * 1024 * 1024
