import pytest

from ankiforge.services.cards.note_type_roles import (
    NoteTypeRoleArchetype,
    find_role_archetype_by_id,
    get_standard_role_archetypes,
)


@pytest.mark.unit
def test_get_standard_role_archetypes_count_and_types() -> None:
    archetypes = get_standard_role_archetypes()
    assert len(archetypes) == 6
    ids = [a.archetype_id for a in archetypes]
    assert "basic" in ids
    assert "cloze" in ids
    assert "medical_qcm" in ids
    assert "dev_code" in ids
    assert "math_katex" in ids
    assert "vocab_languages" in ids


@pytest.mark.unit
def test_archetype_attributes() -> None:
    archetypes = get_standard_role_archetypes()
    for a in archetypes:
        assert isinstance(a, NoteTypeRoleArchetype)
        assert bool(a.archetype_id)
        assert bool(a.name)
        assert bool(a.category)
        assert bool(a.use_case)
        assert len(a.suggested_fields) > 0
        assert bool(a.ai_heuristic_directive)


@pytest.mark.unit
def test_find_role_archetype_by_id() -> None:
    basic = find_role_archetype_by_id("basic")
    assert basic is not None
    assert basic.name.startswith("Basique")
    assert "Front" in basic.suggested_fields
    assert "Back" in basic.suggested_fields

    unknown = find_role_archetype_by_id("unknown_id")
    assert unknown is None


@pytest.mark.unit
def test_markdown_table_generation_and_detection() -> None:
    from ankiforge.services.cards.note_type_roles import (
        generate_markdown_table,
        is_markdown_table,
        parse_markdown_table,
    )

    rows = [
        {
            "concept": "Définition conceptuelle",
            "directive": "Formuler une question directe.",
            "fields": "Front, Back",
        },
        {
            "concept": "Formule KaTeX",
            "directive": "Théorème avec étapes.",
            "fields": "Theoreme, Demonstration",
        },
    ]

    md_table = generate_markdown_table(rows)
    assert is_markdown_table(md_table) is True
    assert "| Concept / Cas d'usage |" in md_table
    assert "| Définition conceptuelle |" in md_table
    assert "| Formule KaTeX |" in md_table

    headers, parsed_rows = parse_markdown_table(md_table)
    assert len(headers) == 3
    assert len(parsed_rows) == 2
    assert parsed_rows[0]["concept"] == "Définition conceptuelle"
    assert parsed_rows[1]["fields"] == "Theoreme, Demonstration"


@pytest.mark.unit
def test_is_markdown_table_negative() -> None:
    from ankiforge.services.cards.note_type_roles import is_markdown_table

    assert is_markdown_table("") is False
    assert is_markdown_table("Simple directive textuelle sans tableau") is False
    assert is_markdown_table("Texte avec un pipe | mais sans structure de table") is False


@pytest.mark.unit
def test_get_table_creation_templates() -> None:
    from ankiforge.services.cards.note_type_roles import get_table_creation_templates

    templates = get_table_creation_templates()
    assert len(templates) >= 5
    for tmpl in templates:
        assert "concept" in tmpl
        assert "directive" in tmpl
        assert "fields" in tmpl
        assert bool(tmpl["concept"])
