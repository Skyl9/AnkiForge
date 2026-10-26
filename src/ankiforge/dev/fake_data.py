"""Factories de données factices déterministes pour le mode développeur.

Ces factories alimentent la galerie de widgets : elles produisent des charges utiles
réalistes et **déterministes**, sans jamais écrire en base ni dépendre d'un service
externe. Les imports de modèles et de services sont différés au corps des fonctions
pour ne pas alourdir le chargement du module en production.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ankiforge.database.models import (
        DocumentModel,
        NoteModel,
        NoteTypeModel,
        NoteVersionModel,
        PersonaModel,
        PersonaVersionModel,
        PythonToolModel,
    )
    from ankiforge.services.ai.model_catalog import ModelSpec
    from ankiforge.services.ai.state import PipelineRunState
    from ankiforge.services.cards.bulk_hygiene_service import TagClustersReport
    from ankiforge.services.cards.import_manager import ConflictItem
    from ankiforge.services.cards.snippet_library import SnippetItem
    from ankiforge.services.crash_reporter_service import CrashReport
    from ankiforge.services.markdown.models import HeadingRepairItem
    from ankiforge.services.update_checker import UpdateInfo


@dataclass
class FakeDeck:
    id: int
    name: str
    parent: str | None = None


@dataclass
class FakeNoteType:
    id: int
    name: str
    fields: list[str] = field(default_factory=list)


@dataclass
class FakeNote:
    id: int
    note_type: str
    fields: dict[str, str] = field(default_factory=dict)


@dataclass
class FakeDocument:
    id: int
    title: str
    page_count: int = 10


@dataclass
class FakePipeline:
    id: int
    name: str
    steps: list[str] = field(default_factory=list)


@dataclass
class FakePersona:
    id: int
    name: str
    role: str = ""


def make_fake_decks() -> list[FakeDeck]:
    return [
        FakeDeck(id=1, name="Default"),
        FakeDeck(id=2, name="Langues", parent=None),
        FakeDeck(id=3, name="Langues::Anglais", parent="Langues"),
    ]


def make_fake_note_types() -> list[FakeNoteType]:
    return [
        FakeNoteType(id=1, name="Basique", fields=["Recto", "Verso"]),
        FakeNoteType(id=2, name="Recto/Verso", fields=["Front", "Back", "Tags"]),
    ]


def make_fake_notes() -> list[FakeNote]:
    return [
        FakeNote(id=1, note_type="Basique", fields={"Recto": "Question", "Verso": "Réponse"}),
        FakeNote(id=2, note_type="Recto/Verso", fields={"Front": "Hello", "Back": "Bonjour"}),
    ]


def make_fake_documents() -> list[FakeDocument]:
    return [
        FakeDocument(id=1, title="Cours de statistiques", page_count=42),
        FakeDocument(id=2, title="Manuel d'anglais", page_count=120),
    ]


def make_fake_pipelines() -> list[FakePipeline]:
    return [
        FakePipeline(id=1, name="Extraction cartes", steps=["RAG", "LLM", "Validation"]),
        FakePipeline(id=2, name="Résumé", steps=["MAP_REDUCE"]),
    ]


def make_fake_personas() -> list[FakePersona]:
    return [
        FakePersona(id=1, name="Tuteur", role="Explique simplement"),
        FakePersona(id=2, name="Examinateur", role="Pose des questions"),
    ]


def make_fake_collection() -> dict[str, Any]:
    """Retourne un dictionnaire agrégé de données factices déterministes."""
    return {
        "decks": make_fake_decks(),
        "note_types": make_fake_note_types(),
        "notes": make_fake_notes(),
        "documents": make_fake_documents(),
        "pipelines": make_fake_pipelines(),
        "personas": make_fake_personas(),
    }


# ── Charges utiles pour la galerie de dialogues ────────────────────────────────


def make_fake_note_ids() -> list[int]:
    """Identifiants de notes factices, jamais présents en base."""
    return [9001, 9002, 9003]


_DEMO_CSS = ".card { font-family: sans-serif; } .front { color: #2c3e50; }"

_DEMO_TEMPLATES: tuple[dict[str, str], ...] = (
    {
        "name": "Carte 1",
        "front": "<div class='front'>{{Front}}</div>",
        "back": "<div class='back'>{{FrontSide}}<hr id=answer>{{Back}}</div>",
    },
    {
        "name": "Carte 2",
        "front": "<div class='front'>{{Back}}</div>",
        "back": "<div class='back'>{{FrontSide}}<hr id=answer>{{Front}}</div>",
    },
)


def _demo_templates() -> list[dict[str, str]]:
    """Copie défensive des gabarits de démonstration partagés."""
    return [dict(template) for template in _DEMO_TEMPLATES]


def make_fake_note_type(name: str = "Biologie Fondamentale") -> NoteTypeModel:
    """Type de note non persisté, complet (champs, gabarits, CSS)."""
    from ankiforge.database.models import NoteTypeModel

    return NoteTypeModel(
        id=9901,
        name=name,
        description="Gabarit de démonstration pour la galerie (aucune écriture en base).",
        fields_schema=json.dumps(["Front", "Back", "Source"], ensure_ascii=False),
        templates=json.dumps(_demo_templates(), ensure_ascii=False),
        css_style=_DEMO_CSS,
    )


def make_fake_note() -> NoteModel:
    """Note non persistée, rattachée à un type de note factice."""
    from ankiforge.database.models import NoteModel

    note = NoteModel(
        id=9999,
        guid="mock-gallery-guid",
        tags="biologie mitose",
        sort_field="Qu'est-ce que la mitose ?",
    )
    note.note_type = make_fake_note_type()
    return note


def make_fake_document(
    title: str = "Cours de statistiques",
    total_pages: int = 3,
) -> DocumentModel:
    """Document Markdown non persisté, avec un contenu de démonstration."""
    from ankiforge.database.models import DocumentModel

    return DocumentModel(
        id=4242,
        title=title,
        content=(
            "# Introduction aux données\n\n"
            "Une variable aléatoire associe chaque issue d'une expérience à une valeur numérique.\n\n"
            "## Statistiques descriptives\n\n"
            "La moyenne arithmétique est la somme des valeurs divisée par le nombre d'observations.\n\n"
            "## Probabilités\n\n"
            "La fonction de répartition est croissante et converge vers l'unité en l'infini.\n"
        ),
        file_type="md",
        total_pages=total_pages,
    )


def make_fake_crash_report() -> CrashReport:
    """Rapport de crash réaliste pour les tests visuels de la modale d'incident."""
    from ankiforge.services.crash_reporter_service import CrashReport

    return CrashReport(
        timestamp="2026-10-11 20:45:12 UTC",
        os_platform="macOS 15.0.1 (arm64)",
        python_version="3.12.9",
        active_profile="dev",
        traceback=(
            "Traceback (most recent call last):\n"
            '  File "src/ankiforge/services/parsing/marker_service.py", line 142, in extract_markdown\n'
            "    result = self._run_pipeline(document_path)\n"
            '  File "src/ankiforge/services/parsing/marker_service.py", line 88, in _run_pipeline\n'
            "ZeroDivisionError: float division by zero"
        ),
        raw_block=("CRASH REPORT [2026-10-11 20:45:12 UTC] - Darwin-24.1.0-arm64 | Python 3.12.9\nProfil actif : dev\nZeroDivisionError: float division by zero"),
        fingerprint="mock_crash_gallery_001",
    )


def make_fake_heading_repairs() -> list[HeadingRepairItem]:
    """Propositions de correction de niveaux de titres Markdown incohérents."""
    from ankiforge.services.markdown.models import HeadingRepairItem

    return [
        HeadingRepairItem(
            line_number=12,
            raw_line="### 2 - Statistiques descriptives",
            title="2 - Statistiques descriptives",
            old_level=3,
            new_level=2,
            reason="Saut de niveau détecté : le titre parent est de niveau 1.",
        ),
        HeadingRepairItem(
            line_number=27,
            raw_line="##### Probabilités",
            title="Probabilités",
            old_level=5,
            new_level=3,
            reason="Niveau trop profond par rapport au titre précédent.",
        ),
    ]


def make_fake_conflict_item() -> ConflictItem:
    """Conflit d'import avéré entre une note locale et une note entrante."""
    from ankiforge.services.cards.import_manager import ConflictItem

    return ConflictItem(
        note_id=9001,
        guid="mock-conflict-guid-001",
        note_type_name="Biologie Fondamentale",
        local_content={
            "Front": "Qu'est-ce que la mitose ?",
            "Back": "Une division cellulaire.",
            "Source": "Manuel p.12",
        },
        incoming_content={
            "Front": "Qu'est-ce que la mitose en biologie ?",
            "Back": "Division cellulaire eucaryote créant deux cellules filles.",
            "Source": "Manuel p.12-14",
        },
        local_deck="Biologie::Cellule",
        incoming_deck="Biologie::Cellule",
        local_tags=["biologie", "mitose"],
        incoming_tags=["biologie", "mitose", "division"],
        similarity_score=0.78,
        field_diffs={
            "Front": {"local": "Qu'est-ce que la mitose ?", "incoming": "Qu'est-ce que la mitose en biologie ?"},
        },
    )


def make_fake_update_info() -> UpdateInfo:
    """Manifeste de mise à jour disponible, sans asset téléchargeable réel."""
    from ankiforge.services.update_checker import UpdateInfo

    return UpdateInfo(
        version="3.2.0",
        title="AnkiForge 3.2.0 — Galerie de widgets enrichie",
        release_notes=("### Nouveautés\n\n- Galerie de widgets complète pour le mode développeur.\n- Nouveaux gabarits de cartes communautaires.\n- Corrections de stabilité sur le pipeline DAG.\n"),
        html_url="https://github.com/Skyl9/AnkiForge/releases/tag/v3.2.0",
        published_at="2026-10-20T09:00:00Z",
        channel="stable",
        is_prerelease=False,
        assets=[],
    )


def make_fake_leech_data() -> dict[str, Any]:
    """Carte sangsue factice, prête pour le diagnostic Wozniak."""
    return {
        "note_id": 9001,
        "card_id": 7001,
        "lapses": 14,
        "stability": 1.8,
        "deck_name": "Biologie::Cellule",
        "full_content": {
            "Front": "Qu'est-ce que la mitose et quelles en sont les phases ?",
            "Back": "Une division cellulaire composée de la prophase, la métaphase, l'anaphase et la télophase.",
        },
        "front_snippet": "Qu'est-ce que la mitose et quelles en sont les phases ?",
        "back_snippet": "Prophase, métaphase, anaphase, télophase.",
    }


def make_fake_model_package() -> dict[str, Any]:
    """Paquet de type de note (.afmodel) factice pour la prévisualisation d'import."""
    return {
        "name": "Biologie Fondamentale (import)",
        "metadata": {
            "author": "Galerie AnkiForge",
            "version": "1.2.0",
            "description": "Gabarit de démonstration avec champs source et styles modulaires.",
            "tags": ["biologie", "sciences"],
        },
        "fields_schema": ["Front", "Back", "Source"],
        "templates": _demo_templates(),
        "css_style": _DEMO_CSS,
        "demo_cards": [
            {
                "Front": "Qu'est-ce que la mitose ?",
                "Back": "Une division cellulaire eucaryote.",
                "Source": "Manuel p.12",
            }
        ],
    }


def make_fake_pipeline_state() -> PipelineRunState:
    """État de pipeline en pause pour la validation humaine."""
    from ankiforge.services.ai.state import PipelineRunState

    state = PipelineRunState(document_id=4242, initial_prompt="Génère des cartes sur la mitose.")
    state.set_variable(
        "human_validation_config",
        {
            "human_title": "Validation du plan de cours",
            "human_message": ("L'IA a extrait les concepts clés ci-dessous. Vérifiez, modifiez ou complétez la liste avant de reprendre le pipeline."),
        },
    )
    state.set_variable(
        "last_output",
        {
            "concepts_cles": [
                "Définition de la mitose",
                "Les quatre phases de la mitose",
                "Rôle biologique de la division cellulaire",
            ]
        },
    )
    return state


def make_fake_persona_versions() -> list[PersonaVersionModel]:
    """Trois versions non persistées d'un agent, de la plus ancienne à la plus récente."""
    from ankiforge.database.models import PersonaVersionModel

    now = datetime(2026, 10, 20, 9, 0, 0)
    return [
        PersonaVersionModel(
            id=1,
            version_number=1,
            system_prompt="Tu es un tuteur pédagogique concis.",
            description="Version initiale",
            commit_message="Version initiale",
            created_at=now - timedelta(days=5),
            is_active=False,
        ),
        PersonaVersionModel(
            id=2,
            version_number=2,
            system_prompt="Tu es un tuteur pédagogique concis, citant toujours la source.",
            description="Ajout de la traçabilité",
            commit_message="Ajout de la traçabilité des sources",
            created_at=now - timedelta(days=2),
            is_active=False,
        ),
        PersonaVersionModel(
            id=3,
            version_number=3,
            system_prompt=("Tu es un tuteur pédagogique concis, citant toujours la source et proposant une question de contrôle à la fin de chaque réponse."),
            description="Ajout d'une question de contrôle",
            commit_message="Ajout d'une question de contrôle",
            created_at=now,
            is_active=True,
        ),
    ]


_GALLERY_PROFILES_DIR: Path | None = None


def make_fake_profiles_dir() -> Path:
    """Dossier de profils factices isolé, créé une seule fois par processus."""
    global _GALLERY_PROFILES_DIR
    if _GALLERY_PROFILES_DIR is None:
        _GALLERY_PROFILES_DIR = Path(tempfile.mkdtemp(prefix="ankiforge_gallery_profiles_"))
        for name in ("default", "recherche", "lecture"):
            (_GALLERY_PROFILES_DIR / name).mkdir(parents=True, exist_ok=True)
    return _GALLERY_PROFILES_DIR


def make_fake_note_versions() -> list[NoteVersionModel]:
    """Trois versions non persistées d'une note, de la plus récente à la plus ancienne."""
    from ankiforge.database.models import NoteVersionModel

    now = datetime(2026, 10, 20, 9, 0, 0)
    contents = [
        (
            3,
            "manual",
            True,
            {
                "Front": "Qu'est-ce que la mitose en biologie cellulaire ?",
                "Back": "Division cellulaire eucaryote créant deux cellules filles génétiquement identiques.",
                "Source": "Manuel p.12-14",
            },
        ),
        (
            2,
            "linter",
            False,
            {
                "Front": "Qu'est-ce que la mitose en biologie ?",
                "Back": "Division cellulaire créant deux cellules filles.",
                "Source": "Manuel p.12",
            },
        ),
        (
            1,
            "initial",
            False,
            {
                "Front": "Qu'est-ce que la mitose ?",
                "Back": "Une division cellulaire.",
                "Source": "Manuel p.12",
            },
        ),
    ]
    versions: list[NoteVersionModel] = []
    for offset, (number, source, is_active, content) in enumerate(contents):
        versions.append(
            NoteVersionModel(
                id=number,
                version_number=number,
                source=source,
                is_active=is_active,
                created_at=now - timedelta(days=offset * 2),
                content=json.dumps(content, ensure_ascii=False),
            )
        )
    return versions


def make_fake_persona() -> PersonaModel:
    """Agent non persisté, avec un prompt Jinja2 de démonstration."""
    from ankiforge.database.models import PersonaModel

    return PersonaModel(
        id=9902,
        name="Tuteur Pédagogique",
        description="Explique les concepts difficiles avec des exemples progressifs.",
        system_prompt="Tu es un tuteur pédagogique. Explique {{ concept }} en trois étapes simples.",
        output_format="json",
        persona_type="pipeline",
        allowed_tools='["rag_retrieval"]',
    )


def make_fake_python_tool() -> PythonToolModel:
    """Outil Python non persisté, prêt à être édité dans l'éditeur d'outils."""
    from ankiforge.database.models import PythonToolModel

    return PythonToolModel(
        id=9903,
        display_name="Normalisation du champ Front",
        description="Supprime les espaces superflus du champ Front des cartes générées.",
        script=(
            "def run(state):\n"
            '    cards = state.get_variable("generated_cards")\n'
            "    if isinstance(cards, list):\n"
            "        for card in cards:\n"
            '            if isinstance(card, dict) and "Front" in card:\n'
            '                card["Front"] = card["Front"].strip()\n'
            '    return {"status": "success"}\n'
        ),
        is_active=True,
    )


def make_fake_tag_clusters_report() -> TagClustersReport:
    """Rapport d'hygiène des tags avec une grappe de casse et une grappe de proximité."""
    from ankiforge.services.cards.bulk_hygiene_service import TagCluster, TagClustersReport, TagFrequency

    case_cluster = TagCluster(
        cluster_id="case-biologie",
        cluster_type="case",
        canonical_tag="biologie",
        tags=[TagFrequency(tag="biologie", count=8), TagFrequency(tag="Biologie", count=3)],
        total_notes_count=11,
    )
    levenshtein_cluster = TagCluster(
        cluster_id="lev-mitose",
        cluster_type="levenshtein",
        canonical_tag="mitose",
        tags=[TagFrequency(tag="mitose", count=6), TagFrequency(tag="mitoses", count=2)],
        total_notes_count=8,
    )
    return TagClustersReport(
        case_clusters=[case_cluster],
        levenshtein_clusters=[levenshtein_cluster],
        total_clusters_count=2,
        total_notes_impacted=19,
        inspected_tags_count=42,
        inspected_notes_count=25,
    )


# ── Charges utiles pour la galerie de composants ─────────────────────────────


def make_fake_snippet() -> SnippetItem:
    """Snippet HTML/CSS non persisté, prêt à être prévisualisé dans la galerie."""
    from ankiforge.services.cards.snippet_library import SnippetItem

    return SnippetItem(
        id="gallery_callout",
        name="Encadré pédagogique",
        category="Callouts & Remarques",
        description="Encadré sobre pour les remarques et informations clés.",
        icon_name="ph.info",
        html_template='<div class="af-callout af-callout-info">\n  {{Remarque}}\n</div>',
        css_style=".af-callout {\n  margin: 14px 0;\n  padding: 12px 16px;\n  border-radius: 8px;\n}",
        preview_html='<div class="af-callout">Information clé</div>',
        tags=["callout", "remarque"],
    )


def make_fake_model_spec() -> ModelSpec:
    """Spécification de modèle IA déterministe, dérivée du catalogue livré avec l'application.

    Dériver du catalogue évite qu'un modèle fictif affiche des capacités ou des tarifs
    qui divergeraient des données réelles au fil des mises à jour.
    """
    from dataclasses import replace

    from ankiforge.services.ai.model_catalog import ModelCatalog, ModelSpec

    curated = ModelCatalog.get_curated_catalog()
    if curated:
        return replace(curated[0])
    return ModelSpec(provider="ollama", model_id="modele-factice", display_name="Modèle factice")


def make_fake_linter_comparison() -> tuple[dict[str, str], dict[str, str]]:
    """Couple (carte actuelle, proposition IA) pour l'inspecteur de champs."""
    original = {
        "NoteType": "Biologie Fondamentale",
        "Recto": "Qu'est-ce que la mitose et quelles sont ses phases ?",
        "Verso": "La mitose est une division cellulaire composée de la prophase, la métaphase, l'anaphase et la télophase.",
        "Champ Annexe Extra": "Manuel de biologie cellulaire, chapitre 4.",
        "Tags": "biologie mitose division",
    }
    proposal = {
        "NoteType": "Biologie Fondamentale",
        "Recto": "Quelles sont les quatre phases de la mitose ?",
        "Verso": "Prophase, métaphase, anaphase et télophase.",
        "Champ Annexe Extra": "Manuel de biologie cellulaire, p. 12.",
        "Tags": "biologie mitose phases",
    }
    return original, proposal


def make_fake_wozniak_item() -> dict[str, Any]:
    """Carte problème Wozniak complète, avec sa proposition de refactorisation."""
    original, proposal = make_fake_linter_comparison()
    return {
        "note_id": 9001,
        "title": "Qu'est-ce que la mitose et quelles sont ses phases ?",
        "badge": "Défaut d'atomicité",
        "proposal_summary": "PROPOSITION ATOMIQUE IA :",
        "original": original,
        "proposal": proposal,
    }


def make_fake_source_diagnostic() -> dict[str, Any]:
    """Diagnostic de santé documentaire pour la carte de source du menu Analyse."""
    return {
        "doc_id": 4242,
        "title": "Cours de statistiques",
        "extension": "pdf",
        "coverage_pct": 68.5,
        "is_indexed": True,
        "total_chunks": 42,
        "covered_chunks": 29,
        "orphan_chunks": 4,
        "total_cards": 57,
        "density": 1.36,
        "word_count": 8_420,
    }
