from ankiforge.database.models import PersonaModel
from ankiforge.services.ai.prompt_interpolator import PipelinePromptInterpolator


def test_interpolate_step_with_prompt_override():
    """Vérifie que la surcharge d'étape est prioritaire sur le Persona."""
    persona = PersonaModel(name="Agent Défaut", system_prompt="Prompt du Persona")
    step = {
        "type": "LLM_PROMPT",
        "persona": persona,
        "config": {
            "prompt_override": "Surcharge pour : {{ text_source }}",
            "input_variable": "text_source",
        },
    }

    result = PipelinePromptInterpolator.interpolate_step(step)

    assert result.is_valid is True
    assert result.source_type == "override"
    assert "Surcharge pour :" in result.system_prompt
    assert "Soit A une matrice carrée" in result.system_prompt
    assert result.estimated_system_tokens > 0
    assert result.estimated_user_tokens > 0


def test_interpolate_step_fallback_to_persona():
    """Vérifie que le prompt du Persona est utilisé automatiquement si la surcharge est vide."""
    persona = PersonaModel(name="Architecte", system_prompt="Tu es un Architecte. Champs : {{ first_field }} et {{ second_field }}.")
    step = {
        "type": "LLM_PROMPT",
        "persona": persona,
        "config": {
            "prompt_override": "",  # Vide
            "input_variable": "text_source",
        },
    }

    result = PipelinePromptInterpolator.interpolate_step(step)

    assert result.is_valid is True
    assert result.source_type == "persona"
    assert result.persona_name == "Architecte"
    assert "Tu es un Architecte" in result.system_prompt
    assert "Champs : Front et Back." in result.system_prompt


def test_interpolate_step_with_upstream_variables():
    """Vérifie la découverte et l'injection des variables déclarées par les étapes amont."""
    all_steps = [
        {
            "step_order": 1,
            "type": "LLM_PROMPT",
            "config": {"output_variable": "plan_cours"},
        },
        {
            "step_order": 2,
            "type": "LLM_PROMPT",
            "config": {
                "prompt_override": "Plan récupéré : {{ state.variables.plan_cours }}",
                "input_variable": "plan_cours",
            },
        },
    ]

    result = PipelinePromptInterpolator.interpolate_step(step_data=all_steps[1], all_steps=all_steps)

    assert result.is_valid is True
    assert "Plan récupéré :" in result.system_prompt
    assert result.user_prompt != ""


def test_interpolate_step_rag_retrieval():
    """Vérifie l'interpolation de la requête sémantique pour l'étape RAG_RETRIEVAL."""
    step = {
        "type": "RAG_RETRIEVAL",
        "config": {
            "rag_query_template": "Requête sémantique : {{ state.initial_prompt }}",
            "top_k": 7,
        },
    }

    result = PipelinePromptInterpolator.interpolate_step(step)

    assert result.is_valid is True
    assert result.source_type == "query"
    assert "Requête sémantique : Créer 5 flashcards" in result.system_prompt
    assert "Top-K : 7 fragments" in result.user_prompt


def test_interpolate_step_jinja_syntax_error():
    """Vérifie la détection gracieuse d'une syntaxe Jinja2 erronée."""
    step = {
        "type": "LLM_PROMPT",
        "config": {
            "prompt_override": "Template avec balise non fermée {{ state.initial_prompt",
        },
    }

    result = PipelinePromptInterpolator.interpolate_step(step)

    assert result.is_valid is False
    assert result.error_message is not None
    assert "Erreur de syntaxe Jinja2" in result.system_prompt


def test_interpolate_step_map_reduce_item():
    """Vérifie la présence des variables d'itération Map-Reduce (item, index)."""
    step = {
        "type": "MAP_REDUCE",
        "config": {
            "prompt_override": "Élément {{ index }} : {{ item }}",
        },
    }

    result = PipelinePromptInterpolator.interpolate_step(step)

    assert result.is_valid is True
    assert "Élément 1 :" in result.system_prompt
    assert "Section 1 :" in result.system_prompt
