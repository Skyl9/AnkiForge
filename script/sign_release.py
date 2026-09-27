#!/usr/bin/env python3
"""Script de signature cryptographique Ed25519 pour les manifestes de release AnkiForge.

Permet de signer le fichier manifeste checksums.txt lors des workflows de release CI/CD
ou manuellement par les mainteneurs du projet.

Usage:
    # Signer checksums.txt via variable d'environnement ANKIFORGE_RELEASE_SIGNING_KEY_ED25519 :
    python script/sign_release.py path/to/checksums.txt

    # Signer en passant la clé privée directement ou un fichier :
    python script/sign_release.py path/to/checksums.txt --key <hex_or_pem>
    python script/sign_release.py path/to/checksums.txt --key-file release.key

    # Générer une nouvelle paire de clés Ed25519 (utile pour initialiser les secrets CI) :
    python script/sign_release.py --generate-keypair
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from ankiforge.security.signatures import (
    TRUSTED_PUBLIC_KEYS,
    verify_manifest_signature,
)

ENV_SIGNING_KEY = "ANKIFORGE_RELEASE_SIGNING_KEY_ED25519"


def generate_keypair() -> tuple[str, str]:
    """Génère une nouvelle paire de clés Ed25519 au format hexadécimal.

    Returns:
        tuple[str, str]: (private_key_hex, public_key_hex)
    """
    private_key = Ed25519PrivateKey.generate()
    priv_bytes = private_key.private_bytes_raw()
    pub_bytes = private_key.public_key().public_bytes_raw()
    return priv_bytes.hex(), pub_bytes.hex()


def load_private_key(
    key_str: str | None = None,
    key_file: Path | str | None = None,
) -> Ed25519PrivateKey:
    """Charge une clé privée Ed25519 depuis une chaîne, un fichier ou la variable d'environnement.

    Supporte les formats :
      - Chaîne hexadécimale de 64 caractères (32 octets de seed)
      - Octets bruts (32 octets)
      - Fichier / chaîne PEM (PKCS#8 ou OpenSSH)

    Raises:
        ValueError: Si aucune clé n'est trouvée ou si le format est invalide.
    """
    raw_content: bytes | None = None

    if key_str:
        candidate = key_str.strip()
        # Si c'est le nom d'une variable d'environnement, lire sa valeur
        if candidate.startswith("$"):
            candidate = os.environ.get(candidate.lstrip("$"), "").strip()
        elif candidate.startswith("ENV:"):
            candidate = os.environ.get(candidate[4:], "").strip()

        if candidate.startswith("-----BEGIN"):
            raw_content = candidate.encode("utf-8")
        elif len(candidate) == 64:
            try:
                raw_content = bytes.fromhex(candidate)
            except ValueError as err:
                raise ValueError(f"La clé hexadécimale fournie est invalide : {err}") from err
        else:
            raw_content = candidate.encode("utf-8")

    elif key_file:
        path = Path(key_file)
        if not path.is_file():
            raise ValueError(f"Fichier de clé introuvable : {path}")
        content = path.read_bytes()
        stripped = content.strip()
        if stripped.startswith(b"-----BEGIN"):
            raw_content = stripped
        elif len(stripped) == 64:
            try:
                raw_content = bytes.fromhex(stripped.decode("ascii"))
            except (ValueError, UnicodeDecodeError) as err:
                raise ValueError(f"Contenu hexadécimal invalide dans le fichier de clé {path} : {err}") from err
        elif len(stripped) == 32:
            raw_content = stripped
        else:
            raw_content = stripped

    else:
        # Fallback sur la variable d'environnement
        env_val = os.environ.get(ENV_SIGNING_KEY, "").strip()
        if not env_val:
            raise ValueError(f"Aucune clé privée fournie. Spécifiez --key, --key-file ou la variable d'environnement {ENV_SIGNING_KEY}.")
        if env_val.startswith("-----BEGIN"):
            raw_content = env_val.encode("utf-8")
        elif len(env_val) == 64:
            try:
                raw_content = bytes.fromhex(env_val)
            except ValueError as err:
                raise ValueError(f"Valeur hexadécimale invalide dans ${ENV_SIGNING_KEY} : {err}") from err
        else:
            raw_content = env_val.encode("utf-8")

    if not raw_content:
        raise ValueError("Impossible de charger les octets de la clé privée.")

    # 1. Tentative chargement 32 octets bruts (Seed Ed25519)
    if len(raw_content) == 32:
        try:
            return Ed25519PrivateKey.from_private_bytes(raw_content)
        except Exception as err:
            raise ValueError(f"Échec de chargement de la clé Ed25519 (32 octets) : {err}") from err

    # 2. Tentative chargement PEM
    if b"-----BEGIN" in raw_content:
        try:
            loaded_key = serialization.load_pem_private_key(raw_content, password=None)
            if not isinstance(loaded_key, Ed25519PrivateKey):
                raise ValueError(f"Type de clé non supporté (attendu Ed25519, reçu {type(loaded_key).__name__})")
            return loaded_key
        except Exception as err:
            raise ValueError(f"Échec de décodage PEM de la clé privée : {err}") from err

    # 3. Tentative conversion hex si 64 octets ascii
    if len(raw_content) == 64:
        try:
            decoded = bytes.fromhex(raw_content.decode("ascii"))
            if len(decoded) == 32:
                return Ed25519PrivateKey.from_private_bytes(decoded)
        except (ValueError, UnicodeDecodeError):
            pass

    raise ValueError(f"Format de clé privée non reconnu (taille brute reçue : {len(raw_content)} octets).")


def sign_manifest(
    manifest_path: Path | str,
    private_key: Ed25519PrivateKey,
    output_path: Path | str | None = None,
    as_hex: bool = False,
) -> tuple[Path, bytes, str]:
    """Signe un fichier manifeste avec une clé Ed25519 et sauvegarde la signature.

    Args:
        manifest_path: Chemin vers le fichier manifeste (ex: checksums.txt).
        private_key: Instance de la clé privée Ed25519.
        output_path: Chemin du fichier de signature (.sig). Par défaut: <manifest_path>.sig.
        as_hex: Si True, enregistre la signature sous forme de texte hexadécimal (128 chars).
                Si False, enregistre les 64 octets bruts (format binaire standard).

    Returns:
        tuple[Path, bytes, str]: (Chemin du fichier .sig, Octets bruts de la signature (64 octets), Clé publique hex)
    """
    path = Path(manifest_path)
    if not path.is_file():
        raise FileNotFoundError(f"Manifeste introuvable : {path}")

    manifest_bytes = path.read_bytes()
    if not manifest_bytes:
        raise ValueError(f"Le fichier manifeste est vide : {path}")

    # Calcul de la signature Ed25519 (64 octets)
    signature_bytes = private_key.sign(manifest_bytes)
    if len(signature_bytes) != 64:
        raise RuntimeError(f"Taille de signature inattendue : {len(signature_bytes)} octets (attendu 64).")

    # Clé publique correspondante
    pub_key: Ed25519PublicKey = private_key.public_key()
    pub_hex = pub_key.public_bytes_raw().hex()

    # Détermination du chemin de sortie
    target_out = Path(output_path) if output_path else path.with_suffix(path.suffix + ".sig")

    if as_hex:
        target_out.write_text(signature_bytes.hex(), encoding="ascii")
    else:
        target_out.write_bytes(signature_bytes)

    # Auto-vérification immédiate
    verified = verify_manifest_signature(
        manifest_content=manifest_bytes,
        signature_raw=signature_bytes,
        public_keys=[pub_hex],
    )
    if not verified:
        target_out.unlink(missing_ok=True)
        raise RuntimeError("Échec critique de la contre-vérification de la signature générée !")

    return target_out, signature_bytes, pub_hex


def main() -> int:
    """Point d'entrée CLI pour le script de signature de release."""
    parser = argparse.ArgumentParser(description="Signature cryptographique Ed25519 pour manifestes de release AnkiForge.")
    parser.add_argument(
        "manifest",
        nargs="?",
        help="Chemin vers le fichier manifeste à signer (ex: checksums.txt)",
    )
    parser.add_argument(
        "--key",
        "-k",
        help="Clé privée Ed25519 (chaîne hex 64 chars, PEM, ou préfixée $ENV_VAR)",
    )
    parser.add_argument(
        "--key-file",
        "-f",
        help="Chemin vers le fichier contenant la clé privée Ed25519",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Chemin de sortie pour la signature (défaut : <manifest>.sig)",
    )
    parser.add_argument(
        "--hex",
        action="store_true",
        help="Enregistrer la signature en texte hexadécimal au lieu de 64 octets bruts",
    )
    parser.add_argument(
        "--generate-keypair",
        action="store_true",
        help="Génère une nouvelle paire de clés Ed25519 et l'affiche sur stdout",
    )

    args = parser.parse_args()

    if args.generate_keypair:
        priv_hex, pub_hex = generate_keypair()
        print("=== Paire de clés Ed25519 générée avec succès ===")
        print(f"Clé privée (Secret CI/CD {ENV_SIGNING_KEY}) : {priv_hex}")
        print(f"Clé publique (À ajouter dans TRUSTED_PUBLIC_KEYS)   : {pub_hex}")
        return 0

    if not args.manifest:
        parser.print_help()
        print("\n[ERREUR] Veuillez spécifier le fichier manifeste à signer ou utiliser --generate-keypair.", file=sys.stderr)
        return 1

    try:
        priv_key = load_private_key(key_str=args.key, key_file=args.key_file)
        sig_path, sig_bytes, pub_hex = sign_manifest(
            manifest_path=args.manifest,
            private_key=priv_key,
            output_path=args.output,
            as_hex=args.hex,
        )

        is_official = pub_hex.lower() in [k.lower() for k in TRUSTED_PUBLIC_KEYS]
        print(f"[SUCCESS] Manifeste signé avec succès : {sig_path}")
        print(f"          Empreinte signature : {sig_bytes.hex()[:32]}... ({len(sig_bytes)} octets)")
        print(f"          Clé publique Ed25519 : {pub_hex}")

        if is_official:
            print("          [STATUT] Clé officielle AnkiForge reconnue par TRUSTED_PUBLIC_KEYS ✅")
        else:
            print("          [AVERTISSEMENT] Clé valide mais non présente dans TRUSTED_PUBLIC_KEYS (clé de dev/staging)")

        return 0

    except Exception as err:
        print(f"[ERREUR] Échec de signature : {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
