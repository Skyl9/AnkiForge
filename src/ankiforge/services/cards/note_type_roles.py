"""
Catalogue et définitions des archétypes de rôles IA pour les types de note (NoteTypeModel).

Ce module fournit un catalogue structuré d'archétypes de types de note pour guider l'utilisateur
dans la configuration du champ « Rôle IA » (description sémantique) consommé par l'orchestrateur
dans la balise {{ available_card_models }} et par les agents MCP.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ankiforge.utils.i18n import tr


@dataclass(frozen=True)
class NoteTypeRoleArchetype:
    """Archétype de rôle IA documentant la sémantique et les directives d'un type de note."""

    archetype_id: str
    name: str
    category: str
    use_case: str
    suggested_fields: list[str]
    ai_heuristic_directive: str


def get_standard_role_archetypes() -> list[NoteTypeRoleArchetype]:
    """
    Retourne la liste ordonnée des 6 archétypes canoniques de rôles IA pour les types de note.

    Les chaînes destinées à l'affichage utilisateur sont traduites via tr() à l'exécution
    pour respecter ADR 0013 (aucune constante figée à l'import).
    """
    return [
        NoteTypeRoleArchetype(
            archetype_id="basic",
            name=tr("Basique (Q/R standard)"),
            category=tr("Général"),
            use_case=tr("Questions directes, définitions factuelles, relations de cause à effet simples."),
            suggested_fields=["Front", "Back"],
            ai_heuristic_directive=tr("Questions directes, définitions conceptuelles, relations de cause à effet simples. Format Q/R standard."),
        ),
        NoteTypeRoleArchetype(
            archetype_id="cloze",
            name=tr("Texte à trous (Cloze)"),
            category=tr("Mémorisation"),
            use_case=tr("Mémorisation contextuelle, citations, listes ordonnées et dates clés."),
            suggested_fields=["Texte", "Remarques extra"],
            ai_heuristic_directive=tr("Phrases denses, citations, listes ordonnées et dates clés. Utilise la syntaxe {{c1::mot}} pour masquer l'information clé dans le champ Texte."),
        ),
        NoteTypeRoleArchetype(
            archetype_id="medical_qcm",
            name=tr("QCM & Cas pratiques"),
            category=tr("Médecine & Concours"),
            use_case=tr("Questions à choix multiples avec distracteurs, justification clinique ou méthodologique et mention de source."),
            suggested_fields=["Question", "Options", "Reponse_Correcte", "Explication", "Pathologie", "Source"],
            ai_heuristic_directive=tr("Gabarit pour questions à choix multiples (QCM) avec options A/B/C/D, justification physiopathologique ou méthodologique et mention de source."),
        ),
        NoteTypeRoleArchetype(
            archetype_id="dev_code",
            name=tr("Dev & Code"),
            category=tr("Informatique & Dev"),
            use_case=tr("Algorithmes, syntaxe, fonctions, extraits de code et complexité temporelle/spatiale."),
            suggested_fields=["Concept", "Code_Snippet", "Solution", "Complexite", "Documentation"],
            ai_heuristic_directive=tr("Cartes techniques de code : présentation d'un problème ou extrait de code, solution pas à pas avec syntaxe précise et indication de complexité algorithmique."),
        ),
        NoteTypeRoleArchetype(
            archetype_id="math_katex",
            name=tr("Maths & Sciences"),
            category=tr("Maths & Sciences"),
            use_case=tr("Théorèmes, lemmes, formules KaTeX et démonstrations pas à pas."),
            suggested_fields=["Theoreme", "Enonce_Formule", "Hypotheses", "Demonstration"],
            ai_heuristic_directive=tr("Théorèmes et formules mathématiques rigoureuses en notation KaTeX ($ et $$), avec séparation stricte des hypothèses et de la démonstration étape par étape."),
        ),
        NoteTypeRoleArchetype(
            archetype_id="vocab_languages",
            name=tr("Vocabulaire & Langues"),
            category=tr("Langues & Vocabulaire"),
            use_case=tr("Acquisition lexicale avec phonétique IPA, catégorie grammaticale et phrases d'exemple en contexte."),
            suggested_fields=["Mot_Etranger", "Phonetique", "Traduction", "Classe_Grammaticale", "Exemple_Phrase", "Traduction_Exemple"],
            ai_heuristic_directive=tr(
                "Acquisition linguistique : mot ou expression cible avec transcription phonétique IPA, catégorie grammaticale, traduction fidèle et phrase d'exemple en contexte."
            ),
        ),
    ]


def find_role_archetype_by_id(archetype_id: str) -> NoteTypeRoleArchetype | None:
    """Recherche un archétype de rôle standard par son identifiant unique."""
    for archetype in get_standard_role_archetypes():
        if archetype.archetype_id == archetype_id:
            return archetype
    return None


def is_markdown_table(text: str) -> bool:
    """Vérifie si une chaîne contient une structure de tableau Markdown avec séparateur (|---|)."""
    if not text or "|" not in text:
        return False
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    has_separator = any(re.match(r"^\|?\s*[-:]+\s*(\|[-:\s]+)+\|?$", line) for line in lines)
    has_pipes = all("|" in line for line in lines[:2])
    return has_pipes and has_separator


def generate_markdown_table(
    rows: list[dict[str, str]],
    headers: list[str] | None = None,
) -> str:
    """
    Construit un tableau Markdown normalisé à partir d'une liste de dictionnaires de lignes.
    Par défaut, les colonnes sont :
    ["Concept / Cas d'usage", "Directive sémantique pour l'IA", "Champs cibles"]
    """
    if headers is None:
        headers = [
            tr("Concept / Cas d'usage"),
            tr("Directive sémantique pour l'IA"),
            tr("Champs cibles"),
        ]

    keys = ["concept", "directive", "fields"]
    lines = [
        f"| {' | '.join(headers)} |",
        f"| {' | '.join(['---'] * len(headers))} |",
    ]

    for row in rows:
        c = row.get(keys[0], "").replace("|", "\\|").replace("\n", " ").strip()
        d = row.get(keys[1], "").replace("|", "\\|").replace("\n", " ").strip()
        f = row.get(keys[2], "").replace("|", "\\|").replace("\n", " ").strip()
        lines.append(f"| {c} | {d} | {f} |")

    return "\n".join(lines)


def parse_markdown_table(md_text: str) -> tuple[list[str], list[dict[str, str]]]:
    """
    Parse un tableau Markdown et extrait les en-têtes ainsi que les lignes sous forme de dictionnaires.
    Retourne (en-têtes, lignes).
    """
    if not is_markdown_table(md_text):
        return [], []

    raw_lines = [line.strip() for line in md_text.strip().splitlines() if line.strip() and "|" in line]
    if len(raw_lines) < 2:
        return [], []

    def split_row(line: str) -> list[str]:
        parts = [p.strip() for p in line.split("|")]
        if parts and parts[0] == "":
            parts.pop(0)
        if parts and parts[-1] == "":
            parts.pop()
        return parts

    headers = split_row(raw_lines[0])
    content_lines = raw_lines[2:]
    keys = ["concept", "directive", "fields"]

    rows: list[dict[str, str]] = []
    for line in content_lines:
        if re.match(r"^\|?\s*[-:]+\s*(\|[-:\s]+)+\|?$", line):
            continue
        cells = split_row(line)
        row_dict: dict[str, str] = {}
        for idx, key in enumerate(keys):
            row_dict[key] = cells[idx] if idx < len(cells) else ""
        rows.append(row_dict)

    return headers, rows


def get_table_creation_templates() -> list[dict[str, str]]:
    """
    Fournit un ensemble de briques / règles types suggérées pour assister la création
    d'un tableau sémantique personnalisé.
    """
    return [
        {
            "concept": tr("Définition & Concept clé"),
            "directive": tr("Formuler une question directe sans ambiguïté. Réponse atomique mémorisable."),
            "fields": "Front, Back",
        },
        {
            "concept": tr("Théorème, formule ou loi scientifique"),
            "directive": tr("Énoncer le résultat en notation KaTeX ($$). Séparer hypothèses et démonstration."),
            "fields": "Theoreme, Enonce_Formule, Hypotheses, Demonstration",
        },
        {
            "concept": tr("Algorithme, fonction ou extrait de code"),
            "directive": tr("Présenter un snippet concis, donner la solution pas à pas et la complexité temporelle/spatiale."),
            "fields": "Concept, Code_Snippet, Solution, Complexite",
        },
        {
            "concept": tr("Question à choix multiples (QCM) / Diagnostic"),
            "directive": tr("Créer 4 options avec distracteurs plausibles et justification physiopathologique ou méthodique."),
            "fields": "Question, Options, Reponse_Correcte, Explication, Source",
        },
        {
            "concept": tr("Vocabulaire, locution ou faux-ami"),
            "directive": tr("Indiquer la transcription phonétique IPA, la classe grammaticale et un exemple contextualisé."),
            "fields": "Mot_Etranger, Phonetique, Traduction, Classe_Grammaticale, Exemple_Phrase",
        },
        {
            "concept": tr("Contre-exemple, piège ou cas d'exclusion"),
            "directive": tr("Insister sur la distinction critique pour éviter l'interférence mémorielle."),
            "fields": "Piege, Contexte, Regle, Solution",
        },
    ]
