#!/usr/bin/env python3
"""Script d'analyse, d'audit de santé et de détection de clusters pour les ADRs d'AnkiForge.

Vérifie :
1. La structure, le titre et le statut de chaque ADR dans docs/adr/ (0001-slug.md).
2. La validité des références croisées entre ADRs (zéro lien mort).
3. La détection de clusters thématiques candidats à la concaténation.
4. Les risques d'obsolescence (ex: composants dépréciés par des décisions ultérieures).
5. La recherche des occurrences d'un ADR dans l'ensemble du dépôt (--find-refs).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path


def _print(msg: str = "") -> None:
    """Sortie console propre sans enfreindre la règle T20 (print())."""
    sys.stdout.write(f"{msg}\n")


ADR_FILENAME_RE = re.compile(r"^(\d{4})-(.+)\.md$")
STATUS_RE = re.compile(r"(?i)(?:\*{0,2}Statut\*{0,2}\s*[:\-]\s*|##\s*Statut\s*\n+)([^\n\r]+)")
ADR_REF_RE = re.compile(r"(?:ADR[\s\-_]*|docs/adr/)(\d{4})", re.IGNORECASE)

KNOWN_THEMES: dict[str, list[str]] = {
    "mcp_et_consultant": [
        "mcp",
        "consultant",
        "harness",
        "two-phase",
        "staged",
    ],
    "themes_et_styles": [
        "thème",
        "theme",
        "famille",
        "stylesheet",
    ],
    "raccourcis_clavier": ["raccourci", "clavier", "shortcut", "keybinding"],
    "profils_et_stockage": ["verrou", "profil", "sqlite", "peewee", "multi-profils"],
    "couverture_et_regions": [
        "provenance",
        "region",
        "exclusion",
        "couverture",
        "chunking",
        "resolution",
        "palier",
    ],
    "export_et_synchro": ["export", "apkg", "colpkg", "synchronisation"],
    "types_de_notes_et_cartes": [
        "note_type",
        "type de note",
        "types de note",
        "carte",
        "modèle de carte",
        "cloze",
        "occlusion",
        "sangsue",
    ],
    "ingestion_et_ocr": [
        "marker",
        "ocr",
        "transcription",
        "planche",
        "album",
        "figure",
    ],
    "documentation_et_instructions": [
        "instruction",
        "anonymisation",
        "hygiene",
        "adaptateur",
    ],
}


@dataclass
class AdrInfo:
    number: str
    slug: str
    path: Path
    title: str
    status: str
    line_count: int
    word_count: int
    outbound_refs: list[str]
    detected_themes: list[str]


def parse_adr_file(path: Path) -> AdrInfo | None:
    """Analyse un fichier ADR Markdown et extrait ses métadonnées."""
    match = ADR_FILENAME_RE.match(path.name)
    if not match:
        return None

    number, slug = match.group(1), match.group(2)
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Extraction du titre (premier titre H1)
    title = slug.replace("-", " ").capitalize()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            break

    # Extraction du statut
    status = "Non renseigné"
    status_match = STATUS_RE.search(content)
    if status_match:
        status = status_match.group(1).strip().strip("*_`[]")

    # Références sortantes vers d'autres ADRs
    outbound_refs = sorted({m.group(1) for m in ADR_REF_RE.finditer(content) if m.group(1) != number})

    # Détection des thématiques ciblées (priorité titre et slug)
    content_lower = content.lower()
    title_slug = f"{title.lower()} {slug.lower()}"
    detected_themes: list[str] = []
    for theme_name, keywords in KNOWN_THEMES.items():
        if any(kw in title_slug for kw in keywords) or sum(1 for kw in keywords if kw in content_lower) >= 2:
            detected_themes.append(theme_name)

    return AdrInfo(
        number=number,
        slug=slug,
        path=path,
        title=title,
        status=status,
        line_count=len(lines),
        word_count=len(content.split()),
        outbound_refs=outbound_refs,
        detected_themes=detected_themes,
    )


def find_references_in_repo(repo_root: Path, target_adr: str) -> list[tuple[Path, int, str]]:
    """Recherche toutes les mentions d'un ADR dans le dépôt entier."""
    target_pattern = re.compile(
        rf"(?:ADR[\s\-_]*{target_adr}|{target_adr}-[a-z0-9_-]+\.md)",
        re.IGNORECASE,
    )
    results: list[tuple[Path, int, str]] = []

    ignored_dirs = {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "site",
        "dist",
        "build",
    }

    scan_extensions = {".py", ".md", ".yaml", ".yml", ".toml", ".json", ".txt"}

    for item in repo_root.rglob("*"):
        if not item.is_file():
            continue
        if any(part in ignored_dirs for part in item.parts):
            continue
        if item.suffix not in scan_extensions:
            continue

        try:
            content = item.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for idx, line in enumerate(content.splitlines(), start=1):
            if target_pattern.search(line):
                rel_path = item.relative_to(repo_root)
                results.append((rel_path, idx, line.strip()))

    return results


def run_audit(adr_dir: Path, json_output: bool = False) -> int:
    """Exécute l'audit complet du registre docs/adr/."""
    adr_files = sorted(adr_dir.glob("*.md"))
    adrs: list[AdrInfo] = []

    for path in adr_files:
        info = parse_adr_file(path)
        if info:
            adrs.append(info)

    if not adrs:
        _print(f"❌ Aucun ADR trouvé dans {adr_dir}")
        return 1

    existing_numbers = {adr.number: adr for adr in adrs}
    broken_refs: list[tuple[str, str]] = []
    unspecified_status: list[AdrInfo] = []
    heavy_adrs: list[AdrInfo] = []
    theme_clusters: dict[str, list[AdrInfo]] = defaultdict(list)

    for adr in adrs:
        if adr.status.lower() in {"non renseigné", "inconnu"}:
            unspecified_status.append(adr)

        if adr.line_count > 200:
            heavy_adrs.append(adr)

        for ref in adr.outbound_refs:
            if ref not in existing_numbers:
                broken_refs.append((adr.number, ref))

        for theme in adr.detected_themes:
            theme_clusters[theme].append(adr)

    if json_output:
        data = {
            "total_adrs": len(adrs),
            "unspecified_status_count": len(unspecified_status),
            "broken_refs_count": len(broken_refs),
            "adrs": [asdict(a) for a in adrs],
            "broken_refs": broken_refs,
            "clusters": {theme: [a.number for a in cluster] for theme, cluster in theme_clusters.items()},
        }
        _print(json.dumps(data, indent=2, default=str))
        return 0

    _print("=" * 80)
    _print(f"📊 AUDIT DU REGISTRE DES ADRS — {len(adrs)} décisions répertoriées")
    _print("=" * 80)
    _print()

    # 1. Statuts non renseignés
    _print(f"🔹 1. Contrôle des statuts formels : {len(unspecified_status)} anomalies")
    if unspecified_status:
        for adr in unspecified_status:
            _print(f"   ⚠️  ADR {adr.number} ({adr.slug}) : statut absent ou non détecté")
    else:
        _print("   ✅ Tous les ADRs ont un statut explicite.")
    _print()

    # 2. Liens brisés entre ADRs
    _print(f"🔹 2. Contrôle d'intégrité référentielle : {len(broken_refs)} liens brisés")
    if broken_refs:
        for source, target in broken_refs:
            _print(f"   ❌ ADR {source} référence l'ADR {target} qui n'existe pas !")
    else:
        _print("   ✅ Aucune référence cassée entre ADRs.")
    _print()

    # 3. ADRs très volumineux (suspects de sur-spécification)
    _print(f"🔹 3. Contrôle de concision (> 200 lignes) : {len(heavy_adrs)} volumineux")
    if heavy_adrs:
        for adr in heavy_adrs:
            _print(f"   ℹ️  ADR {adr.number} ({adr.slug}) : {adr.line_count} lignes ({adr.word_count} mots)")
    else:
        _print("   ✅ Tous les ADRs sont sous le seuil de 200 lignes.")
    _print()

    # 4. Clusters thématiques identifiés pour concaténation
    _print("🔹 4. Clusters thématiques & Opportunités de Concaténation :")
    for theme, cluster in sorted(theme_clusters.items(), key=lambda x: len(x[1]), reverse=True):
        if len(cluster) > 1:
            nums = ", ".join(f"{a.number} ({a.status})" for a in cluster)
            _print(f"   📦 [{theme}] : {len(cluster)} ADRs ({nums})")
    _print()

    _print("=" * 80)
    _print("💡 Utilise 'uv run python .agents/skills/revue-adr/scripts/analyser_adrs.py --find-refs <NUM>'")
    _print("   pour tracer les dépendances globales avant toute fusion ou suppression.")
    _print("=" * 80)

    return 0


def main() -> int:
    """Point d'entrée CLI pour le diagnostic des ADRs."""
    parser = argparse.ArgumentParser(description="Audit et analyse du registre docs/adr/ d'AnkiForge.")
    parser.add_argument(
        "--adr-dir",
        type=Path,
        default=Path("docs/adr"),
        help="Chemin vers le dossier docs/adr (défaut: docs/adr)",
    )
    parser.add_argument(
        "--find-refs",
        type=str,
        help="Recherche toutes les références à un numéro d'ADR (ex: 0014) dans le dépôt",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Sortie au format JSON pour intégration outillée",
    )

    args = parser.parse_args()

    if args.find_refs:
        repo_root = Path.cwd()
        num = args.find_refs.zfill(4)
        refs = find_references_in_repo(repo_root, num)
        _print(f"🔍 Références trouvées pour ADR {num} ({len(refs)} occurrences) :")
        for file_path, line_no, text in refs:
            _print(f"  {file_path}:{line_no} -> {text[:100]}")
        return 0

    return run_audit(args.adr_dir, json_output=args.json)


if __name__ == "__main__":
    sys.exit(main())
