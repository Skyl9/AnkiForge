import jinja2

from ankiforge.services.ai.persona_templates import (
    JINJA2_VARIABLE_DOCS,
    PERSONA_TEMPLATES,
    PROMPT_STARTER_FRAMEWORKS,
    SAMPLE_TEST_INPUTS,
    get_persona_template,
    get_templates_by_category,
)


def test_persona_templates_integrity():
    """Vérifie que tous les modèles ont un ID unique, des métadonnées valides et un prompt Jinja2 valide."""
    assert len(PERSONA_TEMPLATES) >= 8
    seen_ids = set()

    env = jinja2.Environment(loader=jinja2.BaseLoader(), autoescape=False)

    for tpl in PERSONA_TEMPLATES:
        assert tpl.id not in seen_ids, f"ID de modèle dupliqué : {tpl.id}"
        seen_ids.add(tpl.id)

        assert tpl.name
        assert tpl.icon.startswith("ph.")
        assert tpl.icon_color.startswith("#")
        assert tpl.category
        assert tpl.scope in ("pipeline", "mcp", "universal")
        assert tpl.output_format in ("json", "cloze", "markdown", "text")
        assert tpl.sample_test_input

        # Compilation et rendu Jinja2
        jinja_tpl = env.from_string(tpl.system_prompt)
        rendered = jinja_tpl.render(text_source="Test source text", fields=["Front", "Back"])
        assert "Test source text" in rendered or tpl.scope == "mcp" or "{{ text_source }}" not in tpl.system_prompt


def test_get_persona_template():
    """Vérifie la récupération unitaire par identifiant."""
    atomic = get_persona_template("wozniak_atomic")
    assert atomic is not None
    assert "Wozniak" in atomic.name
    assert atomic.output_format == "json"

    assert get_persona_template("non_existent_id") is None


def test_get_templates_by_category():
    """Vérifie le regroupement par catégorie."""
    by_cat = get_templates_by_category()
    assert "Pédagogie & SRS" in by_cat
    assert "Sciences & Médical" in by_cat
    assert len(by_cat["Pédagogie & SRS"]) >= 1


def test_prompt_starters_integrity():
    """Vérifie que tous les canevas de prompts sont valides et compilent."""
    assert len(PROMPT_STARTER_FRAMEWORKS) >= 5
    env = jinja2.Environment(loader=jinja2.BaseLoader(), autoescape=False)

    for starter in PROMPT_STARTER_FRAMEWORKS:
        assert starter.id
        assert starter.label
        assert starter.recommended_format in ("json", "cloze", "markdown", "text")
        j_tpl = env.from_string(starter.template_content)
        rendered = j_tpl.render(text_source="Sample text")
        assert rendered


def test_variable_docs_and_samples():
    """Vérifie la présence et la structure des variables et des échantillons."""
    assert len(JINJA2_VARIABLE_DOCS) >= 7
    for var in JINJA2_VARIABLE_DOCS:
        assert var.variable.startswith("{{")
        assert var.label
        assert var.description
        assert var.scope_availability

    assert len(SAMPLE_TEST_INPUTS) >= 5
    for title, text in SAMPLE_TEST_INPUTS:
        assert title
        assert len(text) > 30
