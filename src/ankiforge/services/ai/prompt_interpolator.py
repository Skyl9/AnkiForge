"""
Service d'interpolation et de résolution de prompts Jinja2 pour l'orchestration de pipelines.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from jinja2 import BaseLoader, Environment

from ankiforge.services.ai.state import PipelineRunState
from ankiforge.services.ai.utils import format_available_card_models_prompt

logger = logging.getLogger(__name__)


@dataclass
class InterpolationResult:
    """Résultat détaillé de l'interpolation d'un prompt d'étape de pipeline."""

    system_prompt: str
    user_prompt: str
    is_valid: bool
    error_message: str | None = None
    estimated_system_tokens: int = 0
    estimated_user_tokens: int = 0
    source_type: str = "persona"  # "override" | "persona" | "default" | "query"
    persona_name: str | None = None
    target_model_name: str | None = None
    input_variable: str = "text_source"
    output_variable: str = "generated_cards"
    raw_template: str = ""
    resolved_context: dict[str, Any] = field(default_factory=dict)


class PipelinePromptInterpolator:
    """Moteur de résolution et prévisualisation réaliste des templates Jinja2 de pipeline."""

    DEFAULT_TEXT_SOURCE = (
        "Soit A une matrice carrée n x n à coefficients réels. A est diagonalisable s'il existe une base "
        "de vecteurs propres de A. Les valeurs propres sont les racines du polynôme caractéristique P(X) = det(A - X*I)."
    )

    DEFAULT_INITIAL_PROMPT = "Créer 5 flashcards de révision sur la diagonalisation matricielle."

    DEFAULT_GENERATED_CARDS = [
        {"Front": "Définition d'une matrice diagonalisable", "Back": "Il existe une base de vecteurs propres."},
        {"Front": "Comment calcule-t-on le polynôme caractéristique ?", "Back": "det(A - lambda * I)"},
    ]

    @classmethod
    def build_sample_context(
        cls,
        step_data: dict[str, Any] | None = None,
        all_steps: list[dict[str, Any]] | None = None,
        custom_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Construit un contexte Jinja2 complet et réaliste, parfaitement aligné sur
        PipelineOrchestrator._render_prompt_template.
        """
        state = PipelineRunState(initial_prompt=cls.DEFAULT_INITIAL_PROMPT)
        state.set_variable("text_source", cls.DEFAULT_TEXT_SOURCE)
        state.set_variable("last_output", "5 cartes générées avec succès.")
        state.set_variable("generated_cards", cls.DEFAULT_GENERATED_CARDS)
        state.set_variable(
            "plan_cours",
            "1. Définition et notations\n2. Valeurs propres et vecteurs propres\n3. Théorème de diagonalisation",
        )
        state.set_variable("target_deck", "Mathématiques::Algèbre")
        state.set_variable("note_type", "Basique")
        state.add_retrieved_chunks(["Extrait 1 : Valeurs propres et polynôme caractéristique de l'endomorphisme."])

        # Découverte des variables déclarées par les étapes amont
        if all_steps:
            current_step_order = (step_data.get("step_order") or 1) if step_data else len(all_steps)
            for idx, s in enumerate(all_steps, start=1):
                if idx >= current_step_order:
                    break
                s_cfg = s.get("config", {})
                out_var = s_cfg.get("output_variable")
                if out_var and out_var not in state.variables:
                    state.set_variable(out_var, f"Donnée produite par l'étape {idx} ({s.get('type', 'ÉTAPE')})")

        if custom_overrides:
            for k, v in custom_overrides.items():
                state.set_variable(k, v)

        fields_list = ["Front", "Back"]
        fields_str = ", ".join([f'"{f}"' for f in fields_list])
        models_catalog_str = format_available_card_models_prompt()

        text_source_val = state.get_variable("text_source", cls.DEFAULT_TEXT_SOURCE)
        last_output_val = state.get_variable("last_output", "")

        context: dict[str, Any] = {
            "state": state,
            "variables": state.variables,
            "retrieved_chunks": state.retrieved_chunks,
            "initial_prompt": state.initial_prompt,
            "document_id": state.document_id,
            "text_source": text_source_val,
            "last_output": last_output_val,
            "fields": fields_list,
            "fields_str": fields_str,
            "first_field": "Front",
            "second_field": "Back",
            "available_card_models": models_catalog_str,
            "card_models_catalog": models_catalog_str,
            "card_models": models_catalog_str,
            "document_chunk": state.get_variable("document_chunk", "") or text_source_val,
            "target_deck": state.get_variable("target_deck", "Default"),
            "note_type": state.get_variable("note_type", "Basique"),
            "item": "Section 1 : Définition des endomorphismes et matrices associées",
            "index": 1,
        }

        # Injecter également les variables d'état directement au premier niveau pour Jinja2
        for k, v in state.variables.items():
            if k not in context:
                context[k] = v

        return context

    @classmethod
    def interpolate_step(
        cls,
        step_data: dict[str, Any],
        all_steps: list[dict[str, Any]] | None = None,
        custom_overrides: dict[str, Any] | None = None,
    ) -> InterpolationResult:
        """
        Résout le prompt d'une étape (système et entrée utilisateur) avec toutes ses variables.
        """
        stype = step_data.get("type", "LLM_PROMPT")
        cfg = step_data.get("config", {})
        persona = step_data.get("persona")

        context = cls.build_sample_context(
            step_data=step_data,
            all_steps=all_steps,
            custom_overrides=custom_overrides,
        )

        # 1. Résolution du prompt de requête pour RAG_RETRIEVAL
        if stype == "RAG_RETRIEVAL":
            raw_query = str(cfg.get("rag_query_template") or "{{ state.initial_prompt }}")
            is_valid = True
            error_msg: str | None = None
            try:
                env = Environment(loader=BaseLoader(), autoescape=False)  # nosec B701
                tpl = env.from_string(raw_query)
                rendered_query = tpl.render(**context)
            except Exception as e:
                is_valid = False
                error_msg = str(e)
                rendered_query = f"❌ Erreur de syntaxe Jinja2 :\n{e}"

            est_tokens = max(1, len(rendered_query.split()) * 4 // 3) if is_valid else 0
            return InterpolationResult(
                system_prompt=rendered_query,
                user_prompt=f"Recherche sémantique Top-K : {cfg.get('top_k', 5)} fragments",
                is_valid=is_valid,
                error_message=error_msg,
                estimated_system_tokens=est_tokens,
                estimated_user_tokens=0,
                source_type="query",
                persona_name=None,
                target_model_name="Index FAISS / RAG Local",
                input_variable="rag_query_template",
                output_variable=cfg.get("output_variable", "text_source"),
                raw_template=raw_query,
                resolved_context=context,
            )

        # 2. Détermination de la source du System Prompt
        prompt_override = str(cfg.get("prompt_override", "") or "").strip()
        persona_prompt = str(getattr(persona, "system_prompt", "") or "").strip() if persona else ""

        if prompt_override:
            raw_template = prompt_override
            source_type = "override"
        elif persona_prompt:
            raw_template = persona_prompt
            source_type = "persona"
        else:
            raw_template = "Extrais les concepts clés et génère des flashcards Anki atomiques au format JSON."
            source_type = "default"

        persona_name = getattr(persona, "name", None) if persona else None

        # 3. Rendu Jinja2 du Prompt Système
        rendered_sys = ""
        is_valid = True
        error_msg = None
        try:
            env = Environment(loader=BaseLoader(), autoescape=False)  # nosec B701
            tpl = env.from_string(raw_template)
            rendered_sys = tpl.render(**context)
        except Exception as e:
            is_valid = False
            error_msg = str(e)
            rendered_sys = f"❌ Erreur de syntaxe Jinja2 dans le template :\n{e}"

        # 4. Résolution de l'Entrée Utilisateur (Payload)
        input_var = cfg.get("input_variable", "text_source")
        output_var = cfg.get("output_variable", "generated_cards")
        raw_user_val = context.get(input_var) or context["variables"].get(input_var) or context.get("text_source", "")
        user_prompt_str = json.dumps(raw_user_val, ensure_ascii=False, indent=2) if isinstance(raw_user_val, dict | list) else str(raw_user_val)

        # 5. Estimation des Tokens
        sys_tokens = max(1, len(rendered_sys.split()) * 4 // 3) if is_valid and rendered_sys else 0
        user_tokens = max(1, len(user_prompt_str.split()) * 4 // 3) if user_prompt_str else 0

        # Modèle cible
        llm_cfg_id = cfg.get("llm_config_id")
        target_model = f"Modèle dédié #{llm_cfg_id}" if llm_cfg_id else "Modèle par défaut du profil"

        return InterpolationResult(
            system_prompt=rendered_sys,
            user_prompt=user_prompt_str,
            is_valid=is_valid,
            error_message=error_msg,
            estimated_system_tokens=sys_tokens,
            estimated_user_tokens=user_tokens,
            source_type=source_type,
            persona_name=persona_name,
            target_model_name=target_model,
            input_variable=input_var,
            output_variable=output_var,
            raw_template=raw_template,
            resolved_context=context,
        )
