"""
Types et formateur de prompt pour la transcription d'albums.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AlbumTranscriptionOptions:
    """Options de configuration pour la transcription d'un album ou de planches sélectionnées."""

    scope_mode: str  # "all", "untranscribed", "stale", "custom"
    custom_range: str
    target_page_ids: list[int]
    category_id: str
    model_override: str | None = None
    temperature_override: float | None = None
    thinking_budget_override: int | None = None
    include_latex: bool = True
    include_tables: bool = True
    include_figures: bool = False
    include_headings: bool = True
    custom_instructions: str = ""


def parse_page_ranges(range_str: str, max_page: int) -> set[int]:
    """
    Parse une chaîne d'intervalles (ex: "1-3, 5, 8-10") et renvoie l'ensemble des numéros de pages valides.

    Les numéros hors bornes [1, max_page] sont ignorés.
    """
    valid_pages: set[int] = set()
    cleaned = range_str.strip()
    if not cleaned or max_page < 1:
        return valid_pages

    chunks = [c.strip() for c in cleaned.split(",") if c.strip()]
    pattern = re.compile(r"^(\d+)(?:\s*-\s*(\d+))?$")

    for chunk in chunks:
        match = pattern.match(chunk)
        if not match:
            continue
        start_str = match.group(1)
        end_str = match.group(2)

        start = int(start_str)
        end = int(end_str) if end_str is not None else start

        if start > end:
            start, end = end, start

        for p in range(start, end + 1):
            if 1 <= p <= max_page:
                valid_pages.add(p)

    return valid_pages


def build_album_transcription_prompt(options: AlbumTranscriptionOptions, base_instructions: str = "") -> str:
    """
    Assemble le prompt multimodal complet à partir des directives de formatage et instructions personnalisées.
    """
    directives: list[str] = ["Transcris fidèlement et intégralement le contenu textuel et conceptuel de cette planche au format Markdown propre."]

    if options.include_headings:
        directives.append("Structure le document avec des titres Markdown hiérarchiques (#, ##, ###) fidèles à la mise en page.")

    if options.include_latex:
        directives.append("Convertis toutes les formules mathématiques et expressions scientifiques en syntaxe LaTeX standard ($...$ pour les formules en ligne, $$...$$ pour les blocs).")

    if options.include_tables:
        directives.append("Convertis tous les tableaux en syntaxe Markdown propre ou en table HTML si les cellules sont fusionnées.")

    if options.include_figures:
        directives.append("Fournis une description textuelle dense et concise des schémas, graphiques et illustrations entre crochets [Figure: ...].")

    if base_instructions.strip():
        directives.append(f"Directives de la catégorie : {base_instructions.strip()}")

    if options.custom_instructions.strip():
        directives.append(f"Directives spécifiques : {options.custom_instructions.strip()}")

    directives.append("Ne produis aucun préambule, bavardage ou explication méta, uniquement le contenu transcrit.")

    return "\n".join(directives)
