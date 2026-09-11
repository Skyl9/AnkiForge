"""Catalogue centralisé des outils MCP et des profils d'agents spécialisés (Presets)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    """Spécification d'un outil MCP disponible pour le Consultant et les agents dédiés."""

    key: str
    label: str
    description: str
    category: str
    color: str


# =====================================================================
# REGISTRE DES 24 OUTILS MCP D'ANKIFORGE
# =====================================================================

TOOLS_CATALOG: list[ToolSpec] = [
    # ── 🛡️ Audit & Qualité Wozniak ──────────────────────────────────────
    ToolSpec(
        key="audit_deck_wozniak",
        label="Audit Wozniak (Paquet)",
        description="Audit ergonomique global d'un paquet selon les 20 règles de formulation (atomicité, interférences).",
        category="Audit & Qualité",
        color="#ef4444",
    ),
    ToolSpec(
        key="audit_card_wozniak",
        label="Audit Wozniak (Carte)",
        description="Analyse chirurgicale d'une carte spécifique au regard des 20 règles de Piotr Wozniak.",
        category="Audit & Qualité",
        color="#ef4444",
    ),
    ToolSpec(
        key="find_duplicate_cards",
        label="Détection Doublons (Levenshtein)",
        description="Détecte les cartes doublons ou formulées de manière quasi-identique via distance Levenshtein.",
        category="Audit & Qualité",
        color="#ef4444",
    ),
    ToolSpec(
        key="propose_card_refactor",
        label="Refactorisation de Carte (Diff)",
        description="Propose une reformulation de carte avec aperçu Diff comparatif pour validation humaine.",
        category="Audit & Qualité",
        color="#ef4444",
    ),
    ToolSpec(
        key="propose_card_split",
        label="Scission de Carte Dense (Diff)",
        description="Propose de scinder une note complexe en N cartes atomiques avec Diff comparatif.",
        category="Audit & Qualité",
        color="#ef4444",
    ),
    # ── 🎨 Modèles de Cartes & CSS ───────────────────────────────────────
    ToolSpec(
        key="list_note_types",
        label="Liste des Modèles de Cartes",
        description="Consulte tous les modèles de cartes (Note Types) enregistrés et leurs champs.",
        category="Modèles & CSS",
        color="#8b5cf6",
    ),
    ToolSpec(
        key="get_note_type_details",
        label="Détails d'un Modèle (Structure & CSS)",
        description="Structure complète d'un modèle : champs requis, gabarits HTML recto/verso et feuille de style CSS.",
        category="Modèles & CSS",
        color="#8b5cf6",
    ),
    ToolSpec(
        key="propose_note_type_refactor",
        label="Évolution de Modèle (Diff)",
        description="Propose une modification structurelle d'un modèle (champs, CSS, templates) avec Garde-Fou.",
        category="Modèles & CSS",
        color="#8b5cf6",
    ),
    ToolSpec(
        key="propose_css_tune",
        label="Ajustement CSS Live",
        description="Injecte des règles ou snippets CSS dans un modèle de carte avec prévisualisation immédiate.",
        category="Modèles & CSS",
        color="#8b5cf6",
    ),
    # ── 📊 Analyse SRS & Santé de Collection ────────────────────────────
    ToolSpec(
        key="get_collection_panorama_360",
        label="Panorama 360° de la Collection",
        description="Vision globale exhaustive : paquets, cartes, sangsues, documents sources et santé globale.",
        category="SRS & Collection",
        color="#10b981",
    ),
    ToolSpec(
        key="get_deck_stats",
        label="Statistiques SRS du Paquet",
        description="Statistiques détaillées : total de cartes, cartes à réviser, difficultés et taux d'oubli.",
        category="SRS & Collection",
        color="#10b981",
    ),
    ToolSpec(
        key="inspect_deck_deep_scan",
        label="Scan Approfondi d'un Paquet",
        description="Analyse des distributions d'intervalles SRS et identification des cartes sangsues prioritaires.",
        category="SRS & Collection",
        color="#10b981",
    ),
    ToolSpec(
        key="get_cards_by_deck_or_tag",
        label="Consultation Cartes (Tag/Paquet)",
        description="Récupère la liste des cartes filtrée par nom de paquet ou par tag avec pagination.",
        category="SRS & Collection",
        color="#10b981",
    ),
    ToolSpec(
        key="find_cards_by_content",
        label="Recherche Cartes par Mot-Clé",
        description="Recherche dans les questions/réponses pour retrouver le note_id et le contenu exact d'une carte.",
        category="SRS & Collection",
        color="#10b981",
    ),
    ToolSpec(
        key="get_note_full_profile_360",
        label="Profil Note 360° & Time Machine",
        description="Profil complet d'une note : champs, modèle, cartes physiques, historique de versions et stats.",
        category="SRS & Collection",
        color="#10b981",
    ),
    # ── 📚 Documents, RAG & Documentation ───────────────────────────────
    ToolSpec(
        key="search_document",
        label="Recherche Vectorielle FAISS Document",
        description="Interroge l'index sémantique FAISS d'un document importé spécifique.",
        category="RAG & Documentation",
        color="#06b6d4",
    ),
    ToolSpec(
        key="search_attached_documents",
        label="Recherche Documents Attachés",
        description="Recherche sémantique globale dans l'ensemble des documents sources de la collection.",
        category="RAG & Documentation",
        color="#06b6d4",
    ),
    ToolSpec(
        key="analyze_coverage_gaps",
        label="Smart Coverage & Détection Lacunes",
        description="Compare un paquet avec un document source pour identifier les notions non encore créées.",
        category="RAG & Documentation",
        color="#06b6d4",
    ),
    ToolSpec(
        key="search_app_documentation",
        label="Recherche Doc Zensical FTS5",
        description="Recherche plein-texte BM25 avec extraits dans la documentation officielle d'AnkiForge.",
        category="RAG & Documentation",
        color="#06b6d4",
    ),
    ToolSpec(
        key="read_app_doc_page",
        label="Lecture Page Documentation",
        description="Consulte le contenu intégral ou une section spécifique de la documentation officielle.",
        category="RAG & Documentation",
        color="#06b6d4",
    ),
    ToolSpec(
        key="list_app_doc_topics",
        label="Sommaire Documentation Officielle",
        description="Consulte le sommaire complet classé par catégories (Démarrage, Fonctionnalités, Architecture).",
        category="RAG & Documentation",
        color="#06b6d4",
    ),
    ToolSpec(
        key="get_feature_quick_help",
        label="Aide Rapide Fonctionnalité",
        description="Fiche synthétique immédiate sur un concept (Ollama, KaTeX, DAG, RAG, Wozniak, Smart Merge).",
        category="RAG & Documentation",
        color="#06b6d4",
    ),
    # ── ⚡ Données & Scripts Python ──────────────────────────────────────
    ToolSpec(
        key="query_peewee",
        label="Requête SQL SELECT Directe",
        description="Exécute une requête SQL SELECT en lecture seule sur la base SQLite de la collection.",
        category="Données & Scripts",
        color="#f59e0b",
    ),
    ToolSpec(
        key="execute_python_tool",
        label="Exécution d'Outil Python",
        description="Lance un calcul ou une transformation déterministe via les scripts d'outils Python.",
        category="Données & Scripts",
        color="#f59e0b",
    ),
]

_TOOLS_BY_KEY: dict[str, ToolSpec] = {t.key: t for t in TOOLS_CATALOG}


def get_tool_spec(key: str) -> ToolSpec | None:
    """Retourne la spécification d'un outil d'après sa clé unique."""
    return _TOOLS_BY_KEY.get(key)


def get_tools_by_category() -> dict[str, list[ToolSpec]]:
    """Retourne l'ensemble des outils indexés par catégorie ordonnée."""
    categories: dict[str, list[ToolSpec]] = {}
    for t in TOOLS_CATALOG:
        categories.setdefault(t.category, []).append(t)
    return categories


# =====================================================================
# PRÉSÉLECTIONS D'AGENTS DÉDIÉS (PRESETS D'USINE)
# =====================================================================

AGENT_PRESETS: dict[str, dict[str, Any]] = {
    "wozniak_auditor": {
        "label": "🛡️ Auditeur Wozniak",
        "description": "Expert en qualité de formulation, atomicité, détection de doublons et scission de cartes.",
        "tools": [
            "audit_deck_wozniak",
            "audit_card_wozniak",
            "find_duplicate_cards",
            "propose_card_refactor",
            "propose_card_split",
            "find_cards_by_content",
            "search_app_documentation",
            "get_feature_quick_help",
        ],
    },
    "css_architect": {
        "label": "🎨 Architecte Modèles & CSS",
        "description": "Spécialiste de la conception de modèles de cartes, templates HTML/Jinja2 et feuilles de style CSS.",
        "tools": [
            "list_note_types",
            "get_note_type_details",
            "propose_note_type_refactor",
            "propose_css_tune",
            "search_app_documentation",
            "get_feature_quick_help",
        ],
    },
    "srs_analyst": {
        "label": "📊 Analyste Rétention & SRS",
        "description": "Spécialiste de l'analyse des métriques d'apprentissage, santé des paquets et cartes sangsues.",
        "tools": [
            "get_collection_panorama_360",
            "get_deck_stats",
            "inspect_deck_deep_scan",
            "get_cards_by_deck_or_tag",
            "find_cards_by_content",
            "get_note_full_profile_360",
            "search_app_documentation",
        ],
    },
    "rag_researcher": {
        "label": "📚 Chercheur RAG & Documents",
        "description": "Spécialiste de l'exploration des sources documentaires, index vectoriels et couverture de cours.",
        "tools": [
            "search_document",
            "search_attached_documents",
            "analyze_coverage_gaps",
            "search_app_documentation",
            "read_app_doc_page",
            "list_app_doc_topics",
            "get_feature_quick_help",
        ],
    },
    "database_admin": {
        "label": "⚡ Administrateur BDD & Scripts",
        "description": "Expert technique autorisé à exécuter des requêtes SQL Peewee et des outils Python sur mesure.",
        "tools": [
            "query_peewee",
            "execute_python_tool",
            "get_collection_panorama_360",
            "list_note_types",
            "search_app_documentation",
        ],
    },
    "universal": {
        "label": "🌐 Consultant Universel",
        "description": "Agent polyvalent disposant d'un accès intégral et sans restriction à tous les outils du système.",
        "tools": ["*"],
    },
}
