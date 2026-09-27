"""Moteur de vérification cryptographique Ed25519 et intégrité SHA-256 pour AnkiForge.

Fournit la vérification asymétrique des manifestes de release (checksums.txt.sig)
et la validation stricte des empreintes SHA-256 des binaires téléchargés.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

logger = logging.getLogger(__name__)

# Trousseau immuable de clés publiques Ed25519 de confiance pour les releases officielles AnkiForge (hexadécimal 32 octets).
# La présence d'une liste permet une rotation transparente de clés : la version N accepte [clé_n, clé_n+1].
TRUSTED_PUBLIC_KEYS: tuple[str, ...] = (
    # Clé officielle primaire AnkiForge Release
    "2b9c99be006295b2b9ac8349dfb7fb66d01063b918335d1b9d0981bf800dd081",
)

CHUNK_SIZE = 65536  # 64 Ko par lecture pour le calcul de hash en streaming


def parse_checksums_manifest(manifest_text: str) -> dict[str, str]:
    """Parse le contenu d'un fichier manifeste d'intégrité (ex: checksums.txt ou SHA256SUMS).

    Supporte les formats standards sha256sum :
        <sha256_hex>  <filename>
        <sha256_hex> *<filename>

    Ignore les lignes vides, les commentaires débutant par '#' et les espaces superflus.
    Normalise les noms de fichiers vers leur nom de base (basename) et les hashes en minuscules.

    Args:
        manifest_text: Le contenu texte complet du manifeste.

    Returns:
        Dictionnaire associant le nom de fichier (str) à son hash SHA-256 hexadécimal (str).
    """
    checksums: dict[str, str] = {}
    for line in manifest_text.splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#"):
            continue

        parts = cleaned.split(maxsplit=1)
        if len(parts) != 2:
            continue

        raw_hash, raw_filename = parts[0].strip(), parts[1].strip()

        # Un hash SHA-256 valide fait exactement 64 caractères hexadécimaux
        if len(raw_hash) != 64 or not all(c in "0123456789abcdefABCDEF" for c in raw_hash):
            continue

        # Suppression de l'éventuel astérisque du mode binaire (ex: "*AnkiForge.AppImage")
        filename_clean = raw_filename.lstrip("*").strip()
        basename = Path(filename_clean).name

        checksums[basename] = raw_hash.lower()

    return checksums


def _normalize_key_bytes(key: str | bytes) -> bytes | None:
    """Convertit une clé publique sous forme hexadécimale ou brute en 32 octets.

    Retourne None si la clé est invalide ou corrompue.
    """
    if isinstance(key, bytes):
        return key if len(key) == 32 else None

    if isinstance(key, str):
        cleaned = key.strip()
        if len(cleaned) == 64:
            try:
                raw = bytes.fromhex(cleaned)
                return raw if len(raw) == 32 else None
            except ValueError:
                return None
    return None


def _normalize_signature_bytes(signature: bytes | str) -> bytes | None:
    """Normalise une signature Ed25519 en 64 octets bruts (supporte bytes bruts ou chaîne hexadécimale).

    Retourne None si le format ou la longueur est incorrecte.
    """
    if isinstance(signature, bytes):
        if len(signature) == 64:
            return signature
        # Tentative de décodage si passée sous forme d'octets de texte hex (128 octets ASCII)
        if len(signature) == 128:
            try:
                decoded = bytes.fromhex(signature.decode("ascii"))
                return decoded if len(decoded) == 64 else None
            except (ValueError, UnicodeDecodeError):
                return None
        return None

    if isinstance(signature, str):
        cleaned = signature.strip()
        if len(cleaned) == 128:
            try:
                decoded = bytes.fromhex(cleaned)
                return decoded if len(decoded) == 64 else None
            except ValueError:
                return None
        return None

    return None


def verify_manifest_signature(
    manifest_content: bytes,
    signature_raw: bytes | str,
    public_keys: Sequence[str | bytes] | None = None,
) -> bool:
    """Vérifie la signature Ed25519 d'un manifeste contre le trousseau de clés de confiance.

    La validation réussit dès qu'au moins une clé publique valide la signature.
    Cette fonction est strictement fail-safe : en cas d'erreur de décodage ou d'altération,
    elle retourne False sans propager d'exception.

    Args:
        manifest_content: Les octets bruts du manifeste (ex: checksums.txt).
        signature_raw: La signature sous forme de 64 octets bruts ou d'une chaîne hexadécimale de 128 caractères.
        public_keys: Liste de clés publiques candidates. Si None, utilise TRUSTED_PUBLIC_KEYS.

    Returns:
        True si la signature est authentique et valide, False sinon.
    """
    if not manifest_content:
        logger.warning("Vérification de signature rejetée : contenu du manifeste vide.")
        return False

    sig_bytes = _normalize_signature_bytes(signature_raw)
    if sig_bytes is None:
        logger.warning("Vérification de signature rejetée : signature Ed25519 invalide ou corrompue.")
        return False

    keys_to_test = public_keys if public_keys is not None else TRUSTED_PUBLIC_KEYS
    if not keys_to_test:
        logger.error("Vérification impossible : aucun trousseau de clés publiques fourni.")
        return False

    for candidate in keys_to_test:
        pub_bytes = _normalize_key_bytes(candidate)
        if pub_bytes is None:
            continue

        try:
            public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
            public_key.verify(sig_bytes, manifest_content)
            logger.info("Signature Ed25519 du manifeste validée avec succès.")
            return True
        except InvalidSignature:
            continue
        except Exception as err:
            logger.debug("Échec de vérification pour une clé candidate : %s", err)
            continue

    logger.warning("Échec de validation Ed25519 : aucune clé du trousseau n'a pu authentifier la signature.")
    return False


def verify_file_sha256(file_path: Path | str, expected_hash: str) -> bool:
    """Calcule l'empreinte SHA-256 d'un fichier en streaming et la compare à l'empreinte attendue.

    Args:
        file_path: Chemin du fichier à vérifier.
        expected_hash: Hash hexadécimal attendu (insensible à la casse).

    Returns:
        True si le fichier existe et son empreinte correspond exactement, False sinon.
    """
    path = Path(file_path)
    if not path.is_file():
        logger.warning("Fichier introuvable pour vérification SHA-256 : %s", path)
        return False

    clean_expected = expected_hash.strip().lower()
    hasher = hashlib.sha256()

    try:
        with open(path, "rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                hasher.update(chunk)
    except OSError as err:
        logger.error("Erreur de lecture lors du calcul SHA-256 sur %s : %s", path, err)
        return False

    actual_hash = hasher.hexdigest()
    if actual_hash != clean_expected:
        logger.warning("Empreinte SHA-256 discordante pour %s (calculée : %s, attendue : %s)", path.name, actual_hash, clean_expected)
        return False

    logger.debug("Empreinte SHA-256 validée pour %s.", path.name)
    return True


def verify_binary_against_manifest(binary_path: Path | str, manifest_text: str) -> tuple[bool, str]:
    """Valide qu'un binaire téléchargé correspond à son empreinte déclarée dans le manifeste d'intégrité.

    Args:
        binary_path: Chemin du binaire téléchargé.
        manifest_text: Contenu texte du manifeste d'intégrité (ex: checksums.txt).

    Returns:
        tuple[bool, str]: (Succès, Message explicatif pour l'UI ou les logs)
    """
    path = Path(binary_path)
    filename = path.name

    checksums = parse_checksums_manifest(manifest_text)
    if filename not in checksums:
        msg = f"Le fichier '{filename}' est introuvable dans le manifeste d'intégrité."
        logger.warning(msg)
        return False, msg

    expected_hash = checksums[filename]
    if not verify_file_sha256(path, expected_hash):
        msg = f"L'empreinte SHA-256 du fichier '{filename}' est discordante par rapport au manifeste."
        logger.error(msg)
        return False, msg

    success_msg = f"Vérification d'intégrité SHA-256 réussie pour '{filename}'."
    logger.info(success_msg)
    return True, success_msg
