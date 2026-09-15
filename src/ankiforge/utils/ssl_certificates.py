"""
Module d'initialisation et de sécurisation des certificats SSL/TLS d'AnkiForge.

Assure la disponibilité permanente des certificats racines d'autorité (CA)
pour httpx, requests, aiohttp et google-genai, que l'application s'exécute
en mode développement, en binaire compilé Nuitka ou dans un bundle macOS .app.
"""

from __future__ import annotations

import logging
import os
import ssl
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def find_valid_ca_bundle() -> Path | None:
    """
    Recherche un bundle de certificats CA valide et existant sur le système de fichiers.

    Returns:
        Path | None: Le chemin absolu vers le bundle cacert.pem ou certificat système valide.
    """
    candidates: list[Path] = []

    # 1. Variable d'environnement existante si elle pointe vers un fichier réel
    env_ssl = os.environ.get("SSL_CERT_FILE")
    if env_ssl:
        p = Path(env_ssl)
        if p.is_file():
            return p

    # 2. Emplacement certifi officiel
    try:
        import certifi

        certifi_path = Path(certifi.where())
        if certifi_path.is_file():
            candidates.append(certifi_path)
    except Exception as e:
        logger.debug("Échec de localisation via certifi : %s", e)

    # 3. Emplacements dans le bundle macOS / Standalone Nuitka
    exe_dir = Path(sys.executable).resolve().parent
    candidates.extend(
        [
            exe_dir.parent / "Resources" / "certifi" / "cacert.pem",
            exe_dir / "certifi" / "cacert.pem",
            exe_dir / "cacert.pem",
            exe_dir.parent / "Resources" / "cacert.pem",
        ]
    )

    # 4. Chemins système standards (Linux / macOS / Unix)
    candidates.extend(
        [
            Path("/etc/ssl/cert.pem"),
            Path("/etc/ssl/certs/ca-certificates.crt"),
            Path("/etc/pki/tls/certs/ca-bundle.crt"),
            Path("/etc/ssl/ca-bundle.pem"),
            Path("/usr/local/etc/openssl/cert.pem"),
            Path("/opt/homebrew/etc/openssl/cert.pem"),
        ]
    )

    for cand in candidates:
        try:
            if cand.is_file() and cand.stat().st_size > 0:
                return cand
        except (OSError, PermissionError):
            continue

    return None


def setup_ssl_certificates() -> str | None:
    """
    Configure automatiquement l'environnement SSL (SSL_CERT_FILE) pour garantir
    que toutes les connexions HTTPS (Gemini, OpenAI, Groq, Releases GitHub, Ollama)
    fonctionnent de manière fiable sans lever de FileNotFoundError sous Nuitka.

    Returns:
        str | None: Le chemin vers le fichier de certificats configuré, ou None si non trouvé.
    """
    bundle_path = find_valid_ca_bundle()
    if bundle_path:
        str_path = str(bundle_path.resolve())
        os.environ["SSL_CERT_FILE"] = str_path
        logger.debug("Certificats SSL initialisés avec succès : %s", str_path)
        return str_path

    # Ne jamais laisser une variable héritée pointer vers un fichier disparu :
    # httpx lève alors FileNotFoundError au démarrage du client.
    invalid_env = os.environ.pop("SSL_CERT_FILE", None)
    if invalid_env:
        logger.warning("Bundle SSL introuvable (%s), utilisation du magasin système.", invalid_env)

    # Repli : si aucun bundle fichier n'est trouvé, créer un contexte par défaut sans cafile forcé
    try:
        ssl.create_default_context()
        logger.debug("Contexte SSL par défaut utilisé sans SSL_CERT_FILE spécifique.")
    except Exception as err:
        logger.warning("Impossible d'initialiser le contexte SSL par défaut : %s", err)

    return None
