"""Tests unitaires pour la vérification cryptographique Ed25519 et l'intégrité SHA-256 des mises à jour."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ankiforge.security.signatures import (
    parse_checksums_manifest,
    verify_binary_against_manifest,
    verify_file_sha256,
    verify_manifest_signature,
)


@pytest.fixture
def keypair() -> tuple[Ed25519PrivateKey, str]:
    """Génère une paire de clés Ed25519 pour les tests."""
    private_key = Ed25519PrivateKey.generate()
    public_bytes = private_key.public_key().public_bytes_raw()
    public_hex = public_bytes.hex()
    return private_key, public_hex


class TestManifestParsing:
    """Tests de découpage et validation du fichier checksums.txt."""

    def test_parse_valid_manifest(self) -> None:
        raw_manifest = (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  AnkiForge-macos-arm64.dmg\n"
            "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945 *AnkiForge-x86_64.AppImage\n"
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad  ankiforge-windows-x64.zip\r\n"
        )
        parsed = parse_checksums_manifest(raw_manifest)
        assert len(parsed) == 3
        assert parsed["AnkiForge-macos-arm64.dmg"] == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert parsed["AnkiForge-x86_64.AppImage"] == "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
        assert parsed["ankiforge-windows-x64.zip"] == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

    def test_parse_ignores_comments_and_empty_lines(self) -> None:
        raw_manifest = "# Empreintes SHA-256 officielles AnkiForge\n\n   \nba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad  AnkiForge-macos-arm64.dmg\n# Fin du fichier\n"
        parsed = parse_checksums_manifest(raw_manifest)
        assert len(parsed) == 1
        assert "AnkiForge-macos-arm64.dmg" in parsed

    def test_parse_strips_paths_and_uppercases(self) -> None:
        raw_manifest = "BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD  ./dist/AnkiForge.dmg\n"
        parsed = parse_checksums_manifest(raw_manifest)
        assert parsed["AnkiForge.dmg"] == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

    def test_parse_handles_malformed_lines_gracefully(self) -> None:
        raw_manifest = "not-a-hash  file1.dmg\nba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad\nba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad  valid.dmg\n"
        parsed = parse_checksums_manifest(raw_manifest)
        assert len(parsed) == 1
        assert "valid.dmg" in parsed


class TestSignatureVerification:
    """Tests de vérification cryptographique asymétrique Ed25519."""

    def test_verify_valid_signature_raw_bytes(self, keypair: tuple[Ed25519PrivateKey, str]) -> None:
        priv_key, pub_hex = keypair
        manifest_data = b"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  app.dmg\n"
        signature = priv_key.sign(manifest_data)

        # Vérification avec clé en hexadécimal
        assert verify_manifest_signature(manifest_data, signature, public_keys=[pub_hex]) is True

    def test_verify_valid_signature_hex_string(self, keypair: tuple[Ed25519PrivateKey, str]) -> None:
        priv_key, pub_hex = keypair
        manifest_data = b"hash  app.dmg\n"
        signature = priv_key.sign(manifest_data)
        signature_hex = signature.hex()

        assert verify_manifest_signature(manifest_data, signature_hex, public_keys=[pub_hex]) is True

    def test_verify_rejects_tampered_manifest(self, keypair: tuple[Ed25519PrivateKey, str]) -> None:
        priv_key, pub_hex = keypair
        manifest_data = b"original data\n"
        signature = priv_key.sign(manifest_data)

        tampered_data = b"altered data\n"
        assert verify_manifest_signature(tampered_data, signature, public_keys=[pub_hex]) is False

    def test_verify_rejects_tampered_signature(self, keypair: tuple[Ed25519PrivateKey, str]) -> None:
        priv_key, pub_hex = keypair
        manifest_data = b"valid data\n"
        signature = bytearray(priv_key.sign(manifest_data))
        signature[0] ^= 0xFF  # Altération d'un octet

        assert verify_manifest_signature(manifest_data, bytes(signature), public_keys=[pub_hex]) is False

    def test_verify_rejects_unknown_public_key(self, keypair: tuple[Ed25519PrivateKey, str]) -> None:
        priv_key, _ = keypair
        other_key = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
        manifest_data = b"valid data\n"
        signature = priv_key.sign(manifest_data)

        assert verify_manifest_signature(manifest_data, signature, public_keys=[other_key]) is False

    def test_verify_succeeds_with_multi_key_keyring(self, keypair: tuple[Ed25519PrivateKey, str]) -> None:
        priv_key, pub_hex = keypair
        dummy_old_key = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
        manifest_data = b"valid data\n"
        signature = priv_key.sign(manifest_data)

        # Le trousseau contient une ancienne clé ET la nouvelle clé valide
        keyring = [dummy_old_key, pub_hex]
        assert verify_manifest_signature(manifest_data, signature, public_keys=keyring) is True

    def test_verify_handles_malformed_signatures_gracefully(self, keypair: tuple[Ed25519PrivateKey, str]) -> None:
        _, pub_hex = keypair
        manifest_data = b"data\n"

        # Signatures trop courtes ou corrompues
        assert verify_manifest_signature(manifest_data, b"short", public_keys=[pub_hex]) is False
        assert verify_manifest_signature(manifest_data, b"", public_keys=[pub_hex]) is False
        assert verify_manifest_signature(manifest_data, "not-hex-at-all", public_keys=[pub_hex]) is False
        assert verify_manifest_signature(manifest_data, b"\x00" * 63, public_keys=[pub_hex]) is False


class TestFileSha256Verification:
    """Tests de calcul et vérification du SHA-256 de fichiers binaires."""

    def test_verify_file_sha256_success(self, tmp_path: Path) -> None:
        test_file = tmp_path / "sample.bin"
        content = b"AnkiForge Secure Binary Content " * 1024
        test_file.write_bytes(content)

        expected_hash = hashlib.sha256(content).hexdigest()
        assert verify_file_sha256(test_file, expected_hash) is True
        # Insensible à la casse
        assert verify_file_sha256(test_file, expected_hash.upper()) is True

    def test_verify_file_sha256_mismatch(self, tmp_path: Path) -> None:
        test_file = tmp_path / "sample.bin"
        test_file.write_bytes(b"Original Content")
        wrong_hash = hashlib.sha256(b"Different Content").hexdigest()

        assert verify_file_sha256(test_file, wrong_hash) is False

    def test_verify_file_sha256_missing_file(self, tmp_path: Path) -> None:
        missing_file = tmp_path / "does_not_exist.bin"
        assert verify_file_sha256(missing_file, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad") is False


class TestBinaryAgainstManifest:
    """Tests d'intégration de validation d'un binaire contre un manifeste textuel."""

    def test_verify_binary_against_manifest_success(self, tmp_path: Path) -> None:
        bin_path = tmp_path / "AnkiForge-macos-arm64.dmg"
        bin_content = b"Binary Payload 123456"
        bin_path.write_bytes(bin_content)
        bin_hash = hashlib.sha256(bin_content).hexdigest()

        manifest = f"{bin_hash}  AnkiForge-macos-arm64.dmg\n"
        ok, msg = verify_binary_against_manifest(bin_path, manifest)
        assert ok is True
        assert "réussie" in msg

    def test_verify_binary_against_manifest_hash_mismatch(self, tmp_path: Path) -> None:
        bin_path = tmp_path / "AnkiForge-macos-arm64.dmg"
        bin_path.write_bytes(b"Corrupted Payload")

        manifest = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad  AnkiForge-macos-arm64.dmg\n"
        ok, msg = verify_binary_against_manifest(bin_path, manifest)
        assert ok is False
        assert "discordante" in msg

    def test_verify_binary_against_manifest_missing_entry(self, tmp_path: Path) -> None:
        bin_path = tmp_path / "AnkiForge-linux-x86_64.AppImage"
        bin_path.write_bytes(b"Payload")

        manifest = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad  AnkiForge-macos-arm64.dmg\n"
        ok, msg = verify_binary_against_manifest(bin_path, manifest)
        assert ok is False
        assert "introuvable dans le manifeste" in msg
