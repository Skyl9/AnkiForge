"""Tests de l'extraction sécurisée d'archives (anti zip-slip / traversal)."""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from ankiforge.utils.archive_utils import safe_extract_tar, safe_extract_zip

pytestmark = pytest.mark.unit


def _write_zip(path: Path, entries: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries:
            zf.writestr(name, content)


def _write_tar(path: Path, entries: list[tuple[str, bytes]]) -> None:
    with tarfile.open(path, "w:gz") as tf:
        for name, content in entries:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))


def test_plain_zip_extracts_normally(tmp_path: Path) -> None:
    z = tmp_path / "a.zip"
    _write_zip(z, [("hello.txt", b"world")])
    out = tmp_path / "out"
    out.mkdir()

    count = safe_extract_zip(z, out)

    assert count == 1
    assert (out / "hello.txt").read_bytes() == b"world"


def test_zip_slip_path_traversal_rejected(tmp_path: Path) -> None:
    z = tmp_path / "evil.zip"
    _write_zip(z, [("../escape.txt", b"pwned")])
    out = tmp_path / "out"
    out.mkdir()

    with pytest.raises(ValueError):
        safe_extract_zip(z, out)
    assert not (tmp_path.parent / "escape.txt").exists()


def test_zip_absolute_path_rejected(tmp_path: Path) -> None:
    z = tmp_path / "abs.zip"
    _write_zip(z, [("/etc/pwned", b"pwned")])
    out = tmp_path / "out"
    out.mkdir()

    with pytest.raises(ValueError):
        safe_extract_zip(z, out)


def test_zip_size_bomb_rejected(tmp_path: Path) -> None:
    z = tmp_path / "bomb.zip"
    _write_zip(z, [("big.bin", b"x" * 1024)])
    out = tmp_path / "out"
    out.mkdir()

    with pytest.raises(ValueError):
        safe_extract_zip(z, out, max_total_size=100)


def test_plain_tar_extracts_normally(tmp_path: Path) -> None:
    t = tmp_path / "a.tar.gz"
    _write_tar(t, [("dir/file.txt", b"content")])
    out = tmp_path / "out"
    out.mkdir()

    safe_extract_tar(t, out)

    assert (out / "dir" / "file.txt").read_bytes() == b"content"


def test_tar_path_traversal_rejected(tmp_path: Path) -> None:
    t = tmp_path / "evil.tar.gz"
    _write_tar(t, [("../escape.txt", b"pwned")])
    out = tmp_path / "out"
    out.mkdir()

    with pytest.raises((ValueError, tarfile.TarError)):
        safe_extract_tar(t, out)
    assert not (tmp_path.parent / "escape.txt").exists()


def test_tar_size_bomb_rejected(tmp_path: Path) -> None:
    t = tmp_path / "bomb.tar.gz"
    _write_tar(t, [("big.bin", b"x" * 1024)])
    out = tmp_path / "out"
    out.mkdir()

    with pytest.raises(ValueError):
        safe_extract_tar(t, out, max_total_size=100)
