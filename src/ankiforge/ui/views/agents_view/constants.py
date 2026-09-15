from PySide6.QtWidgets import QLabel

from ankiforge.services.ai.tools_catalog import (
    TOOLS_CATALOG,
)


def apply_pill_style(badge: QLabel, color_hex: str) -> None:
    """Applique un style de capsule/pill parfaitement arrondie avec fond translucide et bordure assortie."""
    hex_c = color_hex.lstrip("#")
    r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    badge.setStyleSheet(f"""
        QLabel {{
            background-color: rgba({r}, {g}, {b}, 0.15) !important;
            color: {color_hex};
            border: 1px solid rgba({r}, {g}, {b}, 0.35);
            border-radius: 9999px;
            padding: 3px 12px;
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 0.5px;
        }}
    """)


# Types d'usage disponibles pour les Personas
PERSONA_TYPE_SPECS: dict[str, dict[str, str]] = {
    "pipeline": {
        "label": "⚡ Pipeline de Forge (DAG)",
        "badge_text": "Pipeline",
        "badge_color": "#6366f1",
        "badge_variant": "primary",
        "desc": "Conçu pour les étapes de workflow d'ingestion et de création de cartes flashcards.",
    },
    "mcp": {
        "label": "🤝 Consultant IA (Serveur MCP)",
        "badge_text": "Consultant MCP",
        "badge_color": "#10b981",
        "badge_variant": "success",
        "desc": "Conçu pour les diagnostics conversationnels, la boucle autonome ReAct et l'appel d'outils.",
    },
    "universal": {
        "label": "🌐 Universel (Forge & MCP)",
        "badge_text": "Universel",
        "badge_color": "#f59e0b",
        "badge_variant": "warning",
        "desc": "Polyvalent : disponible aussi bien dans les étapes de pipelines que pour le Consultant.",
    },
}

# Registre exhaustif des outils MCP du Consultant & de la Forge
MCP_BASE_TOOLS_SPEC: dict[str, dict[str, str]] = {
    t.key: {
        "label": t.label,
        "desc": t.description,
        "category": t.category,
        "color": t.color,
    }
    for t in TOOLS_CATALOG
}

# Snippets Jinja2 usuels pour les Prompts
JINJA2_SNIPPETS: list[tuple[str, str, str]] = [
    ("{{ text_source }}", "Texte Source", "Contenu brut du document ou de la section sélectionnée"),
    ("{{ last_output }}", "Sortie Précédente", "Résultat de l'étape DAG immédiatement antérieure"),
    ("{{ fields }}", "Champs NoteType", "Liste des champs du modèle de note cible (ex: Front, Back)"),
    ("{{ retrieved_chunks }}", "Extraits RAG", "Fragments documentaires pertinents extraits par FAISS"),
    ("{{ item }}", "Élément Lot (Map-Reduce)", "Objet ou texte en cours de traitement en boucle parallèle"),
    ("{{ initial_prompt }}", "Consigne Initiale", "Consigne d'origine saisie par l'utilisateur"),
    ("{{ state.variables.xxx }}", "Variable DAG", "Accès à une variable arbitraire du PipelineRunState"),
]
