#!/usr/bin/env python3
"""Script de synchronisation et d'élagage des icônes Phosphor selon le manifeste.

Permet de ne conserver dans ``src/ressources/phosphor-icons/`` que les seuls SVGs
strictement déclarés dans ``src/ressources/icons_manifest.txt``.
Supporte le remplissage depuis un dossier source local ou le téléchargement direct
depuis le dépôt officiel GitHub de Phosphor Icons (phosphor-icons/core).
"""

from __future__ import annotations

import argparse
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    import certifi

    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except Exception:
    SSL_CONTEXT = ssl.create_default_context()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "src" / "ressources" / "icons_manifest.txt"
DEFAULT_TARGET_DIR = PROJECT_ROOT / "src" / "ressources" / "phosphor-icons"
UPSTREAM_BASE_URL = "https://raw.githubusercontent.com/phosphor-icons/core/main/assets"


def read_manifest(manifest_path: Path) -> set[str]:
    """Lit et parse le fichier manifeste en retournant un ensemble de chemins relatifs."""
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Fichier manifeste introuvable : {manifest_path}")

    entries: set[str] = set()
    for raw_line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        entries.add(line.replace("\\", "/"))
    return entries


def download_upstream_svg(relpath: str) -> bytes | None:
    """Télécharge un fichier SVG depuis le dépôt officiel Phosphor GitHub."""
    # relpath est de la forme SVGs/<poids>/<fichier>.svg
    parts = Path(relpath).parts
    if len(parts) < 3 or parts[0] != "SVGs":
        return None

    weight = parts[1]
    filename = parts[2]
    url = f"{UPSTREAM_BASE_URL}/{weight}/{filename}"

    req = urllib.request.Request(url, headers={"User-Agent": "AnkiForge-IconSync/1.0"})
    try:
        with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=10) as resp:
            if resp.status == 200:
                return resp.read()
    except Exception as err:
        print(f"[sync_icons] Échec téléchargement {url}: {err}", file=sys.stderr)
    return None


def sync_icons(
    manifest_path: Path,
    target_dir: Path,
    source_dir: Path | None = None,
    download_missing: bool = True,
    prune_unmanifested: bool = True,
    dry_run: bool = False,
) -> tuple[int, int, int, int]:
    """Synchronise le dossier cible selon le manifeste.

    Retourne:
        tuple[int, int, int, int]: (conservés, copiés, téléchargés, élagués)
    """
    manifest_entries = read_manifest(manifest_path)
    svg_root = target_dir / "SVGs"

    preserved_count = 0
    copied_count = 0
    downloaded_count = 0
    pruned_count = 0

    print(f"[sync_icons] Synchronisation de {len(manifest_entries)} icônes vers {target_dir}...")

    # 1. Peuplement / Restauration des fichiers manquants
    for relpath in sorted(manifest_entries):
        dest_file = target_dir / relpath
        if dest_file.exists():
            preserved_count += 1
            continue

        # Le fichier manque dans la cible
        content: bytes | None = None
        source_type = ""

        # Tentative 1 : Copie depuis dossier source local
        if source_dir is not None:
            src_candidate = source_dir / relpath
            if src_candidate.is_file():
                content = src_candidate.read_bytes()
                source_type = "copie_locale"

        # Tentative 2 : Téléchargement distant upstream
        if content is None and download_missing:
            content = download_upstream_svg(relpath)
            if content is not None:
                source_type = "telechargement_http"

        if content is not None:
            if not dry_run:
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                dest_file.write_bytes(content)
            if source_type == "copie_locale":
                copied_count += 1
            else:
                downloaded_count += 1
            print(f"  + Ajouté [{source_type}] : {relpath}")
        else:
            print(f"  ! MANQUANT (introuvable localement et en ligne) : {relpath}", file=sys.stderr)

    # 2. Élagage (pruning) des SVGs non déclarés dans le manifeste
    if prune_unmanifested and svg_root.exists():
        for svg_file in svg_root.rglob("*.svg"):
            rel = svg_file.relative_to(target_dir).as_posix()
            if rel not in manifest_entries:
                if not dry_run:
                    svg_file.unlink()
                pruned_count += 1

    return preserved_count, copied_count, downloaded_count, pruned_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronisation et élagage des icônes Phosphor selon le manifeste.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH, help="Chemin vers icons_manifest.txt")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET_DIR, help="Répertoire cible (phosphor-icons)")
    parser.add_argument("--source", type=Path, default=None, help="Dossier source complet local (optionnel)")
    parser.add_argument("--no-download", action="store_true", help="Désactive le téléchargement distant")
    parser.add_argument("--no-prune", action="store_true", help="Désactive l'élagage des fichiers hors manifeste")
    parser.add_argument("--dry-run", action="store_true", help="Simule l'opération sans modifier le disque")
    args = parser.parse_args()

    if not args.manifest.is_file():
        print(f"[sync_icons] Erreur : Manifeste {args.manifest} introuvable.", file=sys.stderr)
        return 1

    preserved, copied, downloaded, pruned = sync_icons(
        manifest_path=args.manifest,
        target_dir=args.target,
        source_dir=args.source,
        download_missing=not args.no_download,
        prune_unmanifested=not args.no_prune,
        dry_run=args.dry_run,
    )

    prefix = "[SIMULATION] " if args.dry_run else ""
    print(f"[sync_icons] {prefix}Résultat : {preserved} conservés, {copied} copiés, {downloaded} téléchargés, {pruned} élagués.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
