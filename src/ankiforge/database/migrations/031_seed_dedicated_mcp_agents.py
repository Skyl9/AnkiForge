"""Migration 031 : Initialisation des Personas et Agents dédiés au serveur MCP."""

import json
import logging

import peewee as pw
from peewee_migrate import Migrator

from ankiforge.services.ai.tools_catalog import AGENT_PRESETS

logger = logging.getLogger(__name__)


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Crée ou met à jour les personas d'usine dédiés au serveur MCP et au Consultant IA."""
    if fake:
        return

    # Définition des agents dédiés d'usine
    mcp_agents = [
        {
            "name": "Consultant Généraliste",
            "description": "Assistant conversationnel polyvalent doté d'un accès intégral à la collection et aux outils.",
            "persona_type": "mcp",
            "allowed_tools": json.dumps(["*"]),
            "system_prompt": (
                "Tu es le Consultant Généraliste AnkiForge. Ton rôle est d'accompagner l'utilisateur dans l'analyse de sa collection, "
                "l'optimisation de ses modèles et la formulation de ses cartes. Tu disposes d'un accès sans restriction à l'ensemble "
                "des outils d'audit, de diagnostic et de documentation."
            ),
        },
        {
            "name": "Auditeur Wozniak",
            "description": "Expert en qualité de formulation, atomicité, détection de doublons et scission selon les 20 règles de Piotr Wozniak.",
            "persona_type": "mcp",
            "allowed_tools": json.dumps(AGENT_PRESETS["wozniak_auditor"]["tools"]),
            "system_prompt": (
                "Tu es l'Auditeur Qualité Wozniak d'AnkiForge. Ton rôle exclusif est d'analyser la clarté et la rétention des cartes "
                "au regard des 20 règles fondamentales de Piotr Wozniak. Tu traques le manque d'atomicité, les listes complexes "
                "et les interférences. Tu proposes des reformulations précises sous forme de Staged Diffs."
            ),
        },
        {
            "name": "Architecte Modèles & CSS",
            "description": "Spécialiste de la structure des types de cartes, gabarits HTML/KaTeX et personnalisation visuelle CSS.",
            "persona_type": "mcp",
            "allowed_tools": json.dumps(AGENT_PRESETS["css_architect"]["tools"]),
            "system_prompt": (
                "Tu es l'Architecte Modèles & CSS d'AnkiForge. Ton rôle est de concevoir, auditer et améliorer les types de notes, "
                "les schémas de champs, les templates Jinja2/KaTeX et les styles CSS. Tu t'assures de l'ergonomie visuelle sur mobile et desktop."
            ),
        },
        {
            "name": "Analyste SRS & Sangsues",
            "description": "Spécialiste de la dynamique d'apprentissage, analyse des taux d'oubli, cartes sangsues et prédictions FSRS.",
            "persona_type": "mcp",
            "allowed_tools": json.dumps(AGENT_PRESETS["srs_analyst"]["tools"]),
            "system_prompt": (
                "Tu es l'Analyste SRS d'AnkiForge. Ton rôle est d'examiner en profondeur les métriques d'apprentissage de la collection : "
                "distribution des intervalles, cartes provoquant des échecs répétés (sangsues), et charge de révision future."
            ),
        },
        {
            "name": "Chercheur RAG & Documents",
            "description": "Spécialiste de l'interrogation des sources documentaires importées, index sémantiques et analyse de couverture.",
            "persona_type": "mcp",
            "allowed_tools": json.dumps(AGENT_PRESETS["rag_researcher"]["tools"]),
            "system_prompt": (
                "Tu es le Chercheur RAG d'AnkiForge. Ton rôle est d'explorer les documents sources importés (PDF, web, transcriptions) "
                "et la documentation officielle pour vérifier que toutes les notions clés ont été convenablement transformées en flashcards."
            ),
        },
        {
            "name": "Administrateur BDD Peewee",
            "description": "Expert technique habilité à effectuer des diagnostics SQL directs et à exécuter des scripts Python.",
            "persona_type": "mcp",
            "allowed_tools": json.dumps(AGENT_PRESETS["database_admin"]["tools"]),
            "system_prompt": (
                "Tu es l'Administrateur BDD Peewee d'AnkiForge. Tu disposes des autorisations pour exécuter des requêtes SQL SELECT "
                "en lecture seule et lancer des outils d'ingénierie Python afin d'extraire des rapports statistiques avancés."
            ),
        },
    ]

    try:
        # Vérification si la table personas existe
        cursor = database.execute_sql("SELECT name FROM sqlite_master WHERE type='table' AND name='personas'")
        if not cursor.fetchone():
            return

        for agent in mcp_agents:
            cursor = database.execute_sql("SELECT id FROM personas WHERE name = ?", (agent["name"],))
            row = cursor.fetchone()
            if row:
                # Mise à jour du persona existant avec son typage MCP et ses outils autorisés
                database.execute_sql(
                    "UPDATE personas SET persona_type = ?, allowed_tools = ?, description = ? WHERE id = ?",
                    (agent["persona_type"], agent["allowed_tools"], agent["description"], row[0]),
                )
            else:
                # Insertion d'un nouvel agent dédié
                database.execute_sql(
                    "INSERT INTO personas (name, description, system_prompt, output_format, persona_type, allowed_tools) VALUES (?, ?, ?, 'json', ?, ?)",
                    (agent["name"], agent["description"], agent["system_prompt"], agent["persona_type"], agent["allowed_tools"]),
                )
    except Exception as e:
        logger.warning("Erreur lors du peuplement des agents dédiés MCP : %s", e)


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 031 : Ne supprime pas les personas pour préserver les données utilisateur."""
    pass
