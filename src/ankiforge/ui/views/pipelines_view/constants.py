from typing import Any

from PySide6.QtWidgets import QLabel

# Métadonnées des types d'étapes DAG
STEP_TYPES_META: dict[str, dict[str, Any]] = {
    "LLM_PROMPT": {
        "label": "Agent IA (LLM)",
        "badge": "LLM",
        "badge_variant": "status",
        "badge_color": "#8b5cf6",
        "icon": "ph.sparkle",
        "default_title": "Exécution d'un Agent IA",
        "requires_persona": True,
        "default_input": "text_source",
        "default_output": "generated_cards",
    },
    "HUMAN_VALIDATION": {
        "label": "Pause Copilote (Validation)",
        "badge": "PAUSE",
        "badge_variant": "warning",
        "badge_color": "#f59e0b",
        "icon": "ph.pause-circle",
        "default_title": "Pause Copilote (Validation Humaine)",
        "requires_persona": False,
        "default_input": "plan_cours",
        "default_output": "plan_valide",
    },
    "RAG_RETRIEVAL": {
        "label": "Recherche RAG Vectorielle",
        "badge": "RAG",
        "badge_variant": "info",
        "badge_color": "#06b6d4",
        "icon": "ph.database",
        "default_title": "Recherche Sémantique Documentaire",
        "requires_persona": False,
        "default_input": "initial_prompt",
        "default_output": "text_source",
    },
    "MAP_REDUCE": {
        "label": "Génération Parallèle (par lots)",
        "badge": "PARALLÈLE",
        "badge_variant": "success",
        "badge_color": "#10b981",
        "icon": "ph.stack",
        "default_title": "Génération Parallèle par Lots",
        "requires_persona": True,
        "default_input": "text_source",
        "default_output": "generated_cards",
    },
    "PYTHON_TOOL": {
        "label": "Outil Python Déterministe",
        "badge": "OUTIL",
        "badge_variant": "neutral",
        "badge_color": "#f97316",
        "icon": "ph.code",
        "default_title": "Exécution d'un Script / Outil",
        "requires_persona": False,
        "default_input": "generated_cards",
        "default_output": "generated_cards",
    },
    "AUDIO_TTS": {
        "label": "Génération Audio (TTS)",
        "badge": "TTS",
        "badge_variant": "status",
        "badge_color": "#ec4899",
        "icon": "ph.speaker-high",
        "default_title": "Synthèse Vocale des Cartes",
        "requires_persona": False,
        "default_input": "generated_cards",
        "default_output": "generated_cards",
    },
}

# Modèles de pipelines prédéfinis
PRESET_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "Pipeline Standard Cours",
        "description": "Workflow équilibré : Extraction RAG ➔ Architecte IA ➔ Linter Wozniak.",
        "steps": [
            {"type": "RAG_RETRIEVAL", "title": "Recherche Contexte", "config": {"top_k": 4, "input_variable": "initial_prompt", "output_variable": "text_source"}},
            {"type": "LLM_PROMPT", "title": "Architecte de Flashcards", "config": {"input_variable": "text_source", "output_variable": "generated_cards", "output_format": "json"}},
            {"type": "PYTHON_TOOL", "title": "Nettoyage HTML/LaTeX", "config": {"tool_name": "clean_html_latex", "input_variable": "generated_cards", "output_variable": "generated_cards"}},
            {"type": "LLM_PROMPT", "title": "Linter Wozniak (Audit)", "config": {"input_variable": "generated_cards", "output_variable": "generated_cards", "output_format": "json"}},
        ],
    },
    {
        "name": "Pipeline Copilote avec Validation Humaine",
        "description": "Recherche RAG ➔ Plan de Cours ➔ 🤝 Pause Humaine ➔ Forge Finale ➔ Déduplication.",
        "steps": [
            {"type": "RAG_RETRIEVAL", "title": "Recherche Documentaire", "config": {"top_k": 5, "input_variable": "initial_prompt", "output_variable": "text_source"}},
            {"type": "LLM_PROMPT", "title": "Générateur de Plan", "config": {"input_variable": "text_source", "output_variable": "plan_cours"}},
            {"type": "HUMAN_VALIDATION", "title": "Validation du Plan", "config": {"human_title": "Validez le plan avant génération"}},
            {"type": "LLM_PROMPT", "title": "Forge des Cartes Anki", "config": {"input_variable": "plan_cours", "output_variable": "generated_cards", "output_format": "json"}},
            {
                "type": "PYTHON_TOOL",
                "title": "Déduplication Levenshtein",
                "config": {"tool_name": "deduplicate_cards_levenshtein", "input_variable": "generated_cards", "output_variable": "generated_cards"},
            },
        ],
    },
    {
        "name": "Pipeline Haute Précision (Map-Reduce & RAG)",
        "description": "Découpage par lots parallèles pour les longs documents et cours denses.",
        "steps": [
            {"type": "RAG_RETRIEVAL", "title": "Vectorisation & Contexte", "config": {"top_k": 6, "input_variable": "initial_prompt", "output_variable": "text_source"}},
            {"type": "MAP_REDUCE", "title": "Forge Parallèle par Lots", "config": {"batch_size": 3, "split_mode": "page", "input_variable": "text_source", "output_variable": "generated_cards"}},
            {"type": "PYTHON_TOOL", "title": "Validation Schéma JSON", "config": {"tool_name": "validate_json_schema", "input_variable": "generated_cards", "output_variable": "generated_cards"}},
            {"type": "LLM_PROMPT", "title": "Synthèse et Audit", "config": {"input_variable": "generated_cards", "output_variable": "generated_cards", "output_format": "json"}},
        ],
    },
]


def audit_pipeline_dag(steps: list[dict[str, Any]]) -> list[str]:
    """Analyse statique et linter du graphe DAG pour détecter les incohérences ou risques de cycles."""
    issues: list[str] = []
    if not steps:
        return ["Workflow vide : ajoutez au moins une étape pour démarrer."]

    produced_vars = {"initial_prompt", "text_source", "raw_document", "media_url", "generated_cards"}

    for idx, s in enumerate(steps, start=1):
        stype = s.get("type", "LLM_PROMPT")
        cfg = s.get("config", {})

        # 1. Vérification des Personas pour LLM
        if stype in ("LLM_PROMPT", "MAP_REDUCE") and not s.get("persona") and not cfg.get("prompt_override"):
            issues.append(f"Étape {idx} : Aucun agent IA ni prompt personnalisé assigné.")

        # 2. Vérification des variables d'entrée consommées
        in_var = cfg.get("input_variable")
        if in_var and in_var not in produced_vars and not in_var.startswith("state."):
            issues.append(f"Étape {idx} : Variable d'entrée '{in_var}' requise mais pas encore produite en amont.")

        # 3. Enregistrement de la variable produite
        out_var = cfg.get("output_variable") or ("generated_cards" if stype == "LLM_PROMPT" else f"output_{idx}")
        produced_vars.add(out_var)

        # 4. Vérification des cycles de saut
        succ_order = s.get("on_success_order")
        if succ_order and succ_order <= idx:
            issues.append(f"Étape {idx} : Saut conditionnel vers une étape antérieure ({succ_order}) pouvant créer une boucle infinie.")

    return issues


def apply_pill_style(badge: QLabel, color_hex: str) -> None:
    """Applique un style de capsule/pill parfaitement arrondie avec fond translucide et bordure assortie."""
    hex_c = color_hex.lstrip("#")
    r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    badge.setStyleSheet(f"""
        QLabel {{
            background-color: rgba({r}, {g}, {b}, 0.15);
            color: {color_hex};
            border: 1px solid rgba({r}, {g}, {b}, 0.35);
            border-radius: 9999px;
            padding: 2px 10px;
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 0.5px;
        }}
    """)
