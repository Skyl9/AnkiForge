"""
Gestionnaire d'échange et de stockage de thèmes au format JSON (ADR 0005 & 0006).

Définit le format d'échange conteneur de Famille de Thème (variantes sombre & claire),
la validation stricte des champs, la tolérance de charge utile, la gestion de version,
la résolution de collisions de noms de fichiers et la persistance sur disque.
"""

import dataclasses
import json
import logging
import re
from pathlib import Path
from typing import Any

from ankiforge.ui.style_engine.theme_profile import ThemeProfile
from ankiforge.ui.style_engine.themes import (
    JETBRAINS_DARK,
    JETBRAINS_LIGHT,
    ThemeFamily,
)
from ankiforge.utils import paths

logger = logging.getLogger(__name__)

# ── Spécification du Format d'Échange ────────────────────────────────────────

CURRENT_FORMAT_VERSION = "1.0"
CURRENT_MAJOR_VERSION = 1

# Jetons dérivés optionnels (omissions acceptées ; chaîne vide = dérivé dynamiquement à l'exécution)
DERIVED_FIELDS = frozenset(
    {
        "accent_bg",
        "color_red_bg",
        "color_green_bg",
        "color_yellow_bg",
        "color_blue_bg",
        "color_purple_bg",
        "color_red_text",
        "color_green_text",
        "color_yellow_text",
        "color_blue_text",
        "color_purple_text",
        "text_on_accent",
        "accent_border",
        "color_red_border",
        "color_green_border",
        "color_yellow_border",
        "color_blue_border",
        "color_purple_border",
    }
)

# Champs de couleur devant respecter une syntaxe hexadécimale, rgb ou rgba valide
COLOR_FIELDS = frozenset(
    {
        "bg_main",
        "bg_sidebar",
        "bg_panel",
        "bg_input",
        "bg_hover",
        "bg_active",
        "accent_primary",
        "accent_hover",
        "accent_glow",
        "text_primary",
        "text_secondary",
        "text_muted",
        "border_color",
        "border_light",
        "border_focus",
        "color_blue",
        "color_green",
        "color_yellow",
        "color_red",
        "color_purple",
        "syntax_tag",
        "syntax_attr",
        "syntax_string",
        "syntax_keyword",
        "syntax_variable",
        "syntax_comment",
        "syntax_number",
        *DERIVED_FIELDS,
    }
)

INTEGER_NON_NEGATIVE_FIELDS = frozenset({"radius_sm", "radius_md", "radius_lg"})
INTEGER_POSITIVE_FIELDS = frozenset({"font_size_base", "font_size_sm"})
STRING_NON_EMPTY_FIELDS = frozenset({"name", "font_main", "font_code"})
BOOLEAN_FIELDS = frozenset({"is_dark"})


# ── Exceptions Métier ────────────────────────────────────────────────────────


class ThemeExchangeError(Exception):
    """Exception de base pour les erreurs d'échange et de stockage de thèmes."""


class UnsupportedThemeVersionError(ThemeExchangeError):
    """Rejet lors d'une version majeure de format de thème supérieure à celle supportée."""


class ThemeValidationError(ThemeExchangeError):
    """Rejet lors d'un champ présent mais invalide (couleur mal formée, type incorrect, etc.)."""


# ── Validation & Color Parsing ───────────────────────────────────────────────

_HEX_COLOR_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_RGB_RGBA_RE = re.compile(r"^rgba?\(\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})(?:\s*,\s*(?:0|1|0?\.[0-9]+|\.[0-9]+)\s*)?\)$")


def is_valid_color(val: Any) -> bool:
    """Valide si une valeur est une spécification de couleur CSS/Qt valide (hex, rgb, rgba, transparent)."""
    if not isinstance(val, str):
        return False
    s = val.strip()
    if not s:
        return False
    if s.lower() == "transparent":
        return True
    if _HEX_COLOR_RE.match(s):
        return True
    m = _RGB_RGBA_RE.match(s)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255
    return False


def validate_theme_field(name: str, value: Any) -> None:
    """Valide un champ d'un ThemeProfile. Lève ThemeValidationError si la valeur est invalide."""
    if name in DERIVED_FIELDS:
        # Les jetons dérivés acceptent soit une couleur valide, soit une chaîne vide explicite
        if value == "":
            return
        if not is_valid_color(value):
            raise ThemeValidationError(f"Champ de couleur dérivé '{name}' invalide : '{value}' (doit être une couleur valide ou vide)")
        return

    if name in COLOR_FIELDS:
        if not is_valid_color(value):
            raise ThemeValidationError(f"Champ de couleur '{name}' invalide : '{value}'")
        return

    if name in INTEGER_NON_NEGATIVE_FIELDS:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ThemeValidationError(f"Rayon '{name}' invalide : '{value}' (doit être un entier >= 0)")
        return

    if name in INTEGER_POSITIVE_FIELDS:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ThemeValidationError(f"Taille de police '{name}' invalide : '{value}' (doit être un entier >= 1)")
        return

    if name in STRING_NON_EMPTY_FIELDS:
        if not isinstance(value, str) or not value.strip():
            raise ThemeValidationError(f"Champ texte '{name}' invalide : '{value}' (doit être une chaîne non vide)")
        return

    if name == "description":
        if not isinstance(value, str):
            raise ThemeValidationError(f"Champ texte '{name}' invalide : '{value}' (doit être une chaîne de caractères)")
        return

    if name in BOOLEAN_FIELDS:
        if not isinstance(value, bool):
            raise ThemeValidationError(f"Indicateur booléen '{name}' invalide : '{value}' (doit être un booléen True/False)")
        return


def parse_major_version(raw_version: Any) -> int:
    """Extrait le numéro de version majeure à partir d'un entier, float ou chaîne (ex: '1.0' -> 1)."""
    if isinstance(raw_version, int) and not isinstance(raw_version, bool):
        return raw_version
    if isinstance(raw_version, float):
        return int(raw_version)
    if isinstance(raw_version, str):
        parts = raw_version.strip().split(".")
        if parts and parts[0].isdigit():
            return int(parts[0])
    raise UnsupportedThemeVersionError(f"Format de version de thème invalide : '{raw_version}' (version attendue : {CURRENT_MAJOR_VERSION}.x)")


# ── Sérialisation (Export) ───────────────────────────────────────────────────


def theme_profile_to_dict(profile: ThemeProfile) -> dict[str, Any]:
    """Sérialise un ThemeProfile en dictionnaire.

    Règles ADR 0006 :
    - Les jetons dérivés vides ("") sont omis du dictionnaire.
    - Seuls les jetons dérivés explicitement définis (non vides) sont exportés.
    - Les jetons d'exécution DesignTokens ne sont jamais exportés.
    """
    result: dict[str, Any] = {}
    for f in dataclasses.fields(ThemeProfile):
        val = getattr(profile, f.name)
        if f.name in DERIVED_FIELDS:
            if val != "":
                result[f.name] = val
        else:
            result[f.name] = val
    return result


def theme_family_to_dict(family: ThemeFamily) -> dict[str, Any]:
    """Sérialise une ThemeFamily en conteneur d'échange JSON conforme à l'ADR 0006."""
    return {
        "version": CURRENT_FORMAT_VERSION,
        "id": family.id,
        "name": family.name,
        "icon": family.icon,
        "description": family.description,
        "dark": theme_profile_to_dict(family.dark_theme),
        "light": theme_profile_to_dict(family.light_theme),
    }


def theme_family_to_json(family: ThemeFamily, indent: int = 2) -> str:
    """Sérialise une ThemeFamily en chaîne JSON formatée UTF-8."""
    return json.dumps(theme_family_to_dict(family), indent=indent, ensure_ascii=False)


# ── Désérialisation (Import) ─────────────────────────────────────────────────


def merge_variant_payload(
    base: ThemeProfile,
    payload: dict[str, Any],
    variant_id: str,
    is_dark: bool,
) -> ThemeProfile:
    """Fusionne une charge utile de variante sur une base de profil avec tolérance.

    Règles ADR 0006 :
    - Un champ présent écrase le champ correspondant après validation.
    - Un jeton absent ne remet jamais une valeur à son défaut (il conserve la valeur de base).
    - Les champs optionnels inconnus sont tolérés sans erreur.
    - L'identifiant de la variante est réécrit selon variant_id.
    """
    fields_dict = dataclasses.asdict(base)
    known_field_names = {f.name for f in dataclasses.fields(ThemeProfile)}

    for key, val in payload.items():
        if key in known_field_names:
            validate_theme_field(key, val)
            fields_dict[key] = val
        else:
            logger.debug("Champ optionnel ou non reconnu toléré dans la charge utile : %s", key)

    fields_dict["id"] = variant_id
    fields_dict["is_dark"] = is_dark

    return ThemeProfile(**fields_dict)


def theme_family_from_dict(
    data: dict[str, Any],
    file_stem: str | None = None,
    base_family: ThemeFamily | None = None,
) -> ThemeFamily:
    """Instancie une ThemeFamily depuis un conteneur d'échange tolérant.

    - Valide la version majeure du format (rejet si supérieure à CURRENT_MAJOR_VERSION).
    - Réécrit les identifiants pour dériver du nom de fichier (file_stem) s'il est fourni.
    - Reconstitue les deux variantes (dark et light) par fusion tolérante.
    """
    raw_version = data.get("version", CURRENT_FORMAT_VERSION)
    major_version = parse_major_version(raw_version)
    if major_version > CURRENT_MAJOR_VERSION:
        raise UnsupportedThemeVersionError(f"Version de format de thème non supportée : reçue version '{raw_version}' (majeure {major_version}), version maximale attendue {CURRENT_MAJOR_VERSION}.x")

    # L'identifiant de famille et de variantes dérive du nom de fichier s'il est disponible
    effective_id = file_stem or data.get("id") or "custom_theme"
    dark_id = f"{effective_id}_dark"
    light_id = f"{effective_id}_light"

    family_name = str(data.get("name") or effective_id.replace("_", " ").title())
    family_icon = str(data.get("icon") or "ph.palette")
    family_desc = str(data.get("description") or "")

    dark_payload = data.get("dark") or data.get("dark_theme") or {}
    light_payload = data.get("light") or data.get("light_theme") or {}

    if not isinstance(dark_payload, dict):
        raise ThemeValidationError("La variante sombre ('dark') doit être un objet JSON.")
    if not isinstance(light_payload, dict):
        raise ThemeValidationError("La variante claire ('light') doit être un objet JSON.")

    base_dark = base_family.dark_theme if base_family is not None else JETBRAINS_DARK
    base_light = base_family.light_theme if base_family is not None else JETBRAINS_LIGHT

    dark_theme = merge_variant_payload(base_dark, dark_payload, variant_id=dark_id, is_dark=True)
    light_theme = merge_variant_payload(base_light, light_payload, variant_id=light_id, is_dark=False)

    return ThemeFamily(
        id=effective_id,
        name=family_name,
        icon=family_icon,
        description=family_desc,
        dark_theme=dark_theme,
        light_theme=light_theme,
    )


def theme_family_from_json(
    json_str: str,
    file_stem: str | None = None,
    base_family: ThemeFamily | None = None,
) -> ThemeFamily:
    """Désérialise une chaîne JSON en ThemeFamily."""
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as err:
        raise ThemeValidationError(f"Fichier de thème JSON invalide : {err}") from err

    if not isinstance(data, dict):
        raise ThemeValidationError("Le fichier de thème JSON doit contenir un objet à la racine.")

    return theme_family_from_dict(data, file_stem=file_stem, base_family=base_family)


# ── Stockage & Bibliothèque sur Disque (ADR 0005) ───────────────────────────


def resolve_unique_theme_path(themes_dir: Path, base_name: str) -> Path:
    """Détermine un chemin unique pour un fichier de thème dans la bibliothèque.

    En cas de collision avec un fichier existant, ajoute un suffixe numérique (_1, _2...)
    sans jamais écraser le fichier présent.
    """
    clean_stem = re.sub(r"[^a-zA-Z0-9_-]", "_", base_name).strip("_").lower()
    if not clean_stem:
        clean_stem = "custom_theme"

    candidate_file = themes_dir / f"{clean_stem}.json"
    if not candidate_file.exists():
        return candidate_file

    counter = 1
    while True:
        candidate_file = themes_dir / f"{clean_stem}_{counter}.json"
        if not candidate_file.exists():
            return candidate_file
        counter += 1


def save_theme_family_to_library(
    family: ThemeFamily,
    themes_dir: Path | None = None,
    target_stem: str | None = None,
) -> tuple[ThemeFamily, Path]:
    """Enregistre une ThemeFamily dans le répertoire de la bibliothèque de thèmes.

    Réécrit les identifiants pour dériver du nom de fichier final afin qu'il n'existe
    pas deux vérités concurrentes (ADR 0005).
    """
    dest_dir = themes_dir or paths.get_themes_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    stem = target_stem or family.id
    target_path = resolve_unique_theme_path(dest_dir, stem)
    final_stem = target_path.stem

    # Réécriture stricte de l'identifiant de Famille et des Variantes
    persisted_family = ThemeFamily(
        id=final_stem,
        name=family.name,
        icon=family.icon,
        description=family.description,
        dark_theme=dataclasses.replace(family.dark_theme, id=f"{final_stem}_dark"),
        light_theme=dataclasses.replace(family.light_theme, id=f"{final_stem}_light"),
    )

    json_str = theme_family_to_json(persisted_family)
    target_path.write_text(json_str, encoding="utf-8")
    logger.info("Thème sauvegardé dans la bibliothèque : %s (id=%s)", target_path.name, final_stem)

    return persisted_family, target_path


def import_theme_file(
    source_path: Path | str,
    themes_dir: Path | None = None,
) -> tuple[ThemeFamily, Path]:
    """Importe un fichier de thème externe dans la bibliothèque globale.

    Effectue la lecture, la validation, le renommage anti-collision et l'enregistrement
    avec réécriture de l'identifiant.
    """
    source_p = Path(source_path)
    if not source_p.is_file():
        raise FileNotFoundError(f"Fichier de thème source introuvable : {source_p}")

    content = source_p.read_text(encoding="utf-8")
    dest_dir = themes_dir or paths.get_themes_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Étape 1 : Résolution du chemin unique anti-collision
    target_path = resolve_unique_theme_path(dest_dir, source_p.stem)
    final_stem = target_path.stem

    # Étape 2 : Parsing avec réécriture dérivée du nom de fichier final
    family = theme_family_from_json(content, file_stem=final_stem)

    # Étape 3 : Écriture sur disque de la source de vérité en préservant la charge utile d'origine
    try:
        raw_dict = json.loads(content)
        if isinstance(raw_dict, dict):
            raw_dict["id"] = final_stem
            if "dark" in raw_dict and isinstance(raw_dict["dark"], dict) and "id" in raw_dict["dark"]:
                raw_dict["dark"]["id"] = f"{final_stem}_dark"
            elif "dark_theme" in raw_dict and isinstance(raw_dict["dark_theme"], dict) and "id" in raw_dict["dark_theme"]:
                raw_dict["dark_theme"]["id"] = f"{final_stem}_dark"

            if "light" in raw_dict and isinstance(raw_dict["light"], dict) and "id" in raw_dict["light"]:
                raw_dict["light"]["id"] = f"{final_stem}_light"
            elif "light_theme" in raw_dict and isinstance(raw_dict["light_theme"], dict) and "id" in raw_dict["light_theme"]:
                raw_dict["light_theme"]["id"] = f"{final_stem}_light"

            json_to_write = json.dumps(raw_dict, indent=2, ensure_ascii=False)
        else:
            json_to_write = theme_family_to_json(family)
    except Exception:
        json_to_write = theme_family_to_json(family)

    target_path.write_text(json_to_write, encoding="utf-8")
    logger.info("Thème importé avec succès : %s dans %s", family.name, target_path)

    return family, target_path


def export_theme_file(
    family: ThemeFamily,
    target_path: Path | str,
) -> Path:
    """Exporte une ThemeFamily vers un fichier JSON externe."""
    target_p = Path(target_path)
    target_p.parent.mkdir(parents=True, exist_ok=True)
    json_str = theme_family_to_json(family)
    target_p.write_text(json_str, encoding="utf-8")
    logger.info("Thème exporté vers %s", target_p)
    return target_p


def load_custom_theme_families(themes_dir: Path | None = None) -> list[ThemeFamily]:
    """Scanne le répertoire de bibliothèque et charge toutes les familles de thèmes personnalisées."""
    dest_dir = themes_dir or paths.get_themes_dir()
    if not dest_dir.exists():
        return []

    families: list[ThemeFamily] = []
    for file_path in sorted(dest_dir.glob("*.json")):
        try:
            content = file_path.read_text(encoding="utf-8")
            family = theme_family_from_json(content, file_stem=file_path.stem)
            families.append(family)
        except Exception as err:
            logger.warning("Fichier de thème ignoré car corrompu ou invalide (%s) : %s", file_path.name, err)

    return families
