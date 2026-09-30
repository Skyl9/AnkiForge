"""Tests unitaires et d'intégration pour le script de signature de release (script/sign_release.py)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ankiforge.security.signatures import verify_manifest_signature
from script.sign_release import (
    ENV_SIGNING_KEY,
    generate_keypair,
    load_private_key,
    main,
    sign_manifest,
)


@pytest.fixture
def temp_manifest(tmp_path: Path) -> Path:
    """Crée un fichier checksums.txt temporaire pour les tests."""
    manifest = tmp_path / "checksums.txt"
    manifest.write_text(
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  AnkiForge-x86_64.AppImage\nca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb  AnkiForge-macos-arm64.dmg\n"
    )
    return manifest


def test_generate_keypair() -> None:
    """Vérifie la génération d'une paire de clés Ed25519 hexadécimale valide."""
    priv_hex, pub_hex = generate_keypair()
    assert len(priv_hex) == 64
    assert len(pub_hex) == 64

    # Chargement et validation de cohérence
    priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex))
    assert priv.public_key().public_bytes_raw().hex() == pub_hex


def test_load_private_key_from_hex() -> None:
    """Charge une clé privée directement depuis une chaîne hexadécimale."""
    priv_hex, pub_hex = generate_keypair()
    priv = load_private_key(key_str=priv_hex)
    assert priv.public_key().public_bytes_raw().hex() == pub_hex


def test_load_private_key_from_pem() -> None:
    """Charge une clé privée encodée au format PEM."""
    priv_gen = Ed25519PrivateKey.generate()
    pem_bytes = priv_gen.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    loaded = load_private_key(key_str=pem_bytes.decode("ascii"))
    assert loaded.public_key().public_bytes_raw() == priv_gen.public_key().public_bytes_raw()


def test_load_private_key_from_file(tmp_path: Path) -> None:
    """Charge une clé privée depuis un fichier sur disque."""
    priv_hex, pub_hex = generate_keypair()
    key_file = tmp_path / "release.key"
    key_file.write_text(priv_hex)

    loaded = load_private_key(key_file=key_file)
    assert loaded.public_key().public_bytes_raw().hex() == pub_hex


def test_load_private_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Charge la clé privée depuis la variable d'environnement dédiée."""
    priv_hex, pub_hex = generate_keypair()
    monkeypatch.setenv(ENV_SIGNING_KEY, priv_hex)

    loaded = load_private_key()
    assert loaded.public_key().public_bytes_raw().hex() == pub_hex


def test_load_private_key_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie les rejets stricts sur clé manquante ou corrompue."""
    monkeypatch.delenv(ENV_SIGNING_KEY, raising=False)

    # 1. Aucune clé
    with pytest.raises(ValueError, match="Aucune clé privée fournie"):
        load_private_key()

    # 2. Fichier inexistant
    with pytest.raises(ValueError, match="Fichier de clé introuvable"):
        load_private_key(key_file=tmp_path / "absent.key")

    # 3. Hex 64 chars invalide
    with pytest.raises(ValueError, match="invalide"):
        load_private_key(key_str="z" * 64)

    # 4. Format non reconnu
    with pytest.raises(ValueError, match="non reconnu"):
        load_private_key(key_str="bad_key_content")


def test_sign_manifest_binary_output(temp_manifest: Path) -> None:
    """Signe un manifeste et produit un fichier binaire standard de 64 octets."""
    priv = Ed25519PrivateKey.generate()
    pub_hex = priv.public_key().public_bytes_raw().hex()

    sig_path, sig_bytes, reported_pub = sign_manifest(
        manifest_path=temp_manifest,
        private_key=priv,
    )

    assert sig_path == temp_manifest.with_suffix(".txt.sig")
    assert sig_path.is_file()
    assert len(sig_bytes) == 64
    assert reported_pub == pub_hex
    assert sig_path.read_bytes() == sig_bytes

    # Vérification avec le vérificateur de sécurité AnkiForge
    assert (
        verify_manifest_signature(
            manifest_content=temp_manifest.read_bytes(),
            signature_raw=sig_bytes,
            public_keys=[pub_hex],
        )
        is True
    )


def test_sign_manifest_hex_output(temp_manifest: Path, tmp_path: Path) -> None:
    """Signe un manifeste avec l'option as_hex=True (texte de 128 caractères)."""
    priv = Ed25519PrivateKey.generate()
    pub_hex = priv.public_key().public_bytes_raw().hex()
    custom_out = tmp_path / "custom.sig"

    sig_path, sig_bytes, reported_pub = sign_manifest(
        manifest_path=temp_manifest,
        private_key=priv,
        output_path=custom_out,
        as_hex=True,
    )

    assert sig_path == custom_out
    assert len(sig_bytes) == 64
    assert reported_pub == pub_hex

    # Le fichier contient 128 caractères hexadécimaux
    content = custom_out.read_text(encoding="ascii")
    assert len(content) == 128
    assert content == sig_bytes.hex()

    # Le vérificateur accepte aussi le texte hexadécimal
    assert (
        verify_manifest_signature(
            manifest_content=temp_manifest.read_bytes(),
            signature_raw=content,
            public_keys=[pub_hex],
        )
        is True
    )


def test_sign_manifest_tampered_fails(temp_manifest: Path) -> None:
    """Vérifie que la modification du manifeste invalide la signature."""
    priv = Ed25519PrivateKey.generate()
    pub_hex = priv.public_key().public_bytes_raw().hex()

    _, sig_bytes, _ = sign_manifest(manifest_path=temp_manifest, private_key=priv)

    tampered_manifest = temp_manifest.read_bytes() + b"\nextra_line"
    assert (
        verify_manifest_signature(
            manifest_content=tampered_manifest,
            signature_raw=sig_bytes,
            public_keys=[pub_hex],
        )
        is False
    )


def test_sign_manifest_empty_error(tmp_path: Path) -> None:
    """Un manifeste vide lève une exception."""
    empty = tmp_path / "empty.txt"
    empty.write_text("")
    priv = Ed25519PrivateKey.generate()

    with pytest.raises(ValueError, match="vide"):
        sign_manifest(manifest_path=empty, private_key=priv)


def test_main_cli_generate_keypair(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie l'exécution CLI avec le flag --generate-keypair."""
    monkeypatch.setattr(sys, "argv", ["sign_release.py", "--generate-keypair"])
    exit_code = main()
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Clé privée" in captured.out
    assert "Clé publique" in captured.out


def test_main_cli_sign_file(temp_manifest: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie l'exécution CLI complète pour la signature d'un fichier."""
    priv_hex, pub_hex = generate_keypair()
    sig_out = temp_manifest.parent / "out.sig"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sign_release.py",
            str(temp_manifest),
            "--key",
            priv_hex,
            "--output",
            str(sig_out),
        ],
    )
    exit_code = main()
    assert exit_code == 0
    assert sig_out.is_file()
    captured = capsys.readouterr()
    assert "[SUCCESS]" in captured.out
