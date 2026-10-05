"""Extraction et compilation des catalogues i18n AnkiForge (mécanique Qt Linguist).

Ce script est l'unique producteur des fichiers ``src/ankiforge/resources/translations/`` :

1. ``pyside6-lupdate`` balaie ``src/ankiforge`` et écrit un ``.ts`` par langue, en
   réécriture exhaustive (``-locations relative -noobsolete``) : un message disparu du code
   disparaît du catalogue au lieu d'y rester pour toujours ;
2. ``pyside6-lrelease`` compile chaque ``.ts`` en ``.qm``, binaire que Qt charge à
   l'exécution.

Décisions de dépôt :

- les ``.ts`` (source française, cible anglaise) **sont versionnés** : ils sont la
  matière du travail de traduction humaine, dont le ticket frère
  ``Doc - Traduction Humaine des Catalogues i8n vers l Anglais`` a la charge ;
- les ``.qm`` sont **ignorés** : ce sont des artefacts de build, reproductibles, dont la
  présence dépend des outils Qt présents sur le poste qui a lancé la compilation.

Aucune traduction automatique n'est produite ici : un catalogue vide est un catalogue
honnête, une traduction automatique faite en lot est une faute silencieuse.

Usage :
    uv run python script/extract_translations.py            # extraction + compilation
    uv run python script/extract_translations.py --check    # les .ts versionnés sont-ils à jour ?
    uv run python script/extract_translations.py -l en      # une seule langue
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AnkiForgeTranslations")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = PROJECT_ROOT / "src" / "ankiforge"
TRANSLATIONS_DIR = SOURCE_DIR / "resources" / "translations"
CATALOG_STEM = "ankiforge"

#: Langues dont un catalogue doit exister : la source (français) sert de référence, les
#: autres sont des cibles de traduction humaine. Aucune n'est remplie automatiquement.
LANGUAGES: tuple[str, ...] = ("fr", "en")

#: Options communes : ``-locations relative`` conserve la ligne d'appel (indispensable pour
#: désambiguïser un libellé), ``-noobsolete`` supprime les messages disparus du code.
LUPDATE_FLAGS: tuple[str, ...] = ("-locations", "relative", "-noobsolete")
_LOCATION_RE = re.compile(rb'filename="([^"]+)"')


def tool(name: str) -> Path:
    """Renvoie le chemin de l'outil PySide6 demandé, ou lève une erreur explicite."""
    executable = f"{name}.exe" if sys.platform == "win32" else name
    candidate = Path(sys.executable).parent / executable
    if candidate.exists():
        return candidate

    found = shutil.which(name)
    if found:
        return Path(found)
    raise FileNotFoundError(f"Outil Qt Linguist introuvable : {name} (attendu à {candidate})")


def ts_path(language: str) -> Path:
    """Chemin du catalogue source d'une langue."""
    return TRANSLATIONS_DIR / f"{CATALOG_STEM}_{language}.ts"


def qm_path(language: str) -> Path:
    """Chemin du catalogue compilé d'une langue."""
    return TRANSLATIONS_DIR / f"{CATALOG_STEM}_{language}.qm"


def _run(command: list[str]) -> str:
    """Exécute une commande Qt Linguist et échoue bruyamment en cas d'erreur.

    La commande n'est jamais journalisée en entier : elle porte la liste des ~470
    fichiers sources, ce qui noierait le rapport d'erreur sous une ligne de 30 ko.
    """
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        tail = (result.stdout + result.stderr).strip().splitlines()[-15:]
        raise RuntimeError(f"Échec de {Path(command[0]).name} :\n" + "\n".join(tail))
    return result.stdout


def _lupdate_command(target: Path) -> list[str]:
    sources = sorted(str(path.relative_to(PROJECT_ROOT)) for path in SOURCE_DIR.rglob("*.py"))
    return [str(tool("pyside6-lupdate")), *sources, "-ts", str(target), *LUPDATE_FLAGS]


def _normalize_catalog_locations(catalog: bytes) -> bytes:
    """Normalise les chemins de sources pour comparer deux extractions.

    ``pyside6-lupdate`` calcule les chemins relatifs depuis le dossier de sortie du
    catalogue. Une extraction temporaire produit donc des chemins absolus ou plus
    profonds que le catalogue versionné, sans que le code source ait changé.
    """
    source_prefix = (SOURCE_DIR.as_posix() + "/").encode()
    relative_root = Path("..") / ".."

    def replace(match: re.Match[bytes]) -> bytes:
        filename = match.group(1)
        marker = filename.find(source_prefix)
        if marker < 0:
            return match.group(0)
        source_file = Path(filename[marker + len(source_prefix) :].decode())
        normalized = (relative_root / source_file).as_posix().encode()
        return b'filename="' + normalized + b'"'

    return _LOCATION_RE.sub(replace, catalog)


def extract(language: str, target: Path | None = None) -> Path:
    """Balaie ``src/ankiforge`` et écrit le ``.ts`` de la langue donnée.

    Args:
        language: Code de langue ISO 639-1 (``"fr"``, ``"en"``).
        target: Destination ; par défaut le dossier des catalogues versionnés.

    Returns:
        Path: Le fichier ``.ts`` écrit.
    """
    destination = target or ts_path(language)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run(_lupdate_command(destination))
    logger.info("Catalogue écrit : %s", destination)
    return destination


def compile_catalog(language: str) -> Path:
    """Compile un ``.ts`` en ``.qm``, en excluant les traductions ``unfinished``.

    Args:
        language: Code de langue ISO 639-1.

    Returns:
        Path: Le ``.qm`` produit.
    """
    ts_file = ts_path(language)
    if not ts_file.is_file():
        raise FileNotFoundError(f"Catalogue source absent : {ts_file}")
    qm_file = qm_path(language)
    _run([str(tool("pyside6-lrelease")), str(ts_file), "-qm", str(qm_file)])
    return qm_file


def check() -> int:
    """Vérifie que les ``.ts`` versionnés correspondent à une extraction fraîche.

    La comparaison se fait sur une extraction vers un dossier temporaire et **vide** :
    ``pylupdate`` fusionne avec un catalogue existant, donc recopier le fichier versionné
    avant extraction ne prouverait rien — le catalogue serait toujours « à jour ».

    Returns:
        int: 0 si tout est à jour, 1 sinon.
    """
    stale: list[str] = []
    with tempfile.TemporaryDirectory(prefix="ankiforge-i18n-") as tmp:
        tmp_dir = Path(tmp)
        for language in LANGUAGES:
            reference = ts_path(language)
            if not reference.is_file():
                stale.append(f"{reference.name} absent du dépôt")
                continue
            regenerated = tmp_dir / reference.name
            try:
                extract(language, regenerated)
            except (FileNotFoundError, RuntimeError) as err:
                logger.warning("%s", err)
                return 1
            if _normalize_catalog_locations(reference.read_bytes()) != _normalize_catalog_locations(regenerated.read_bytes()):
                stale.append(reference.name)

    if stale:
        logger.error(
            "Catalogues i18n obsolètes (%s). Régénérer : uv run python script/extract_translations.py",
            ", ".join(stale),
        )
        return 1
    logger.info("Catalogues i18n à jour : %s.", ", ".join(LANGUAGES))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Extraction et compilation des catalogues i18n AnkiForge.")
    parser.add_argument("--check", action="store_true", help="Vérifier que les catalogues versionnés sont à jour, sans les modifier.")
    parser.add_argument("-l", "--language", action="append", choices=LANGUAGES, help="Limiter à une langue (répétable).")
    args = parser.parse_args()

    if args.check:
        return check()

    languages = tuple(args.language) if args.language else LANGUAGES
    for language in languages:
        extract(language)
    for language in languages:
        compiled = compile_catalog(language)
        logger.info("Catalogue compilé : %s (%d octets)", compiled.name, compiled.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
