from ankiforge.services.ai.schemas import (
    GeneratedCardSchema,
    GeneratedCardsContainerSchema,
    SelfHealingValidator,
    WozniakAuditResultSchema,
)
from ankiforge.services.ai.utils import extract_cards_from_data


def test_generated_card_schema_normalization():
    # Direct field keys
    raw = {"Front": "Qu'est ce que Cauchy-Schwarz ?", "Back": "|<x,y>| <= ||x|| ||y||", "model": "Basique", "tags": ["math", "algebre"]}
    card = GeneratedCardSchema.model_validate(raw)
    assert card.model == "Basique"
    assert card.fields["Front"] == "Qu'est ce que Cauchy-Schwarz ?"
    assert "math" in card.tags

    # Nested fields key
    raw_nested = {"model": "Cloze", "fields": {"Texte": "{{c1::Python}} est un langage."}, "tags": "programmation informatique"}
    card_nested = GeneratedCardSchema.model_validate(raw_nested)
    assert card_nested.model == "Cloze"
    assert card_nested.fields["Texte"] == "{{c1::Python}} est un langage."
    assert "programmation" in card_nested.tags


def test_self_healing_validator_markdown_cleanup():
    markdown_json = """
    Voici les cartes générées :
    ```json
    {
        "notes": [
            {
                "model": "Basique",
                "fields": {
                    "Recto": "Définition de l'intégrale",
                    "Verso": "Aire sous la courbe.",
                }
            }
        ]
    }
    ```
    J'espère que cela vous convient !
    """
    container = SelfHealingValidator.parse_and_validate(markdown_json, GeneratedCardsContainerSchema)
    assert len(container.notes) == 1
    assert container.notes[0].fields["Recto"] == "Définition de l'intégrale"


def test_self_healing_validator_raw_list():
    raw_list = [
        {"Recto": "Q1", "Verso": "A1"},
        {"Recto": "Q2", "Verso": "A2"},
    ]
    container = SelfHealingValidator.parse_and_validate(raw_list, GeneratedCardsContainerSchema)
    assert len(container.notes) == 2
    assert container.notes[0].fields["Recto"] == "Q1"


def test_wozniak_audit_schema():
    raw = {
        "is_compliant": False,
        "violations": [
            {
                "rule_name": "Atomicité",
                "reason": "La carte contient deux concepts non reliés.",
                "suggestion": {"Front": "Q1", "Back": "R1"},
            }
        ],
        "global_score": 75,
    }
    audit = SelfHealingValidator.parse_and_validate(raw, WozniakAuditResultSchema)
    assert not audit.is_compliant
    assert len(audit.violations) == 1
    assert audit.violations[0].rule_name == "Atomicité"


def test_extract_cards_from_data_self_healing():
    dirty_json = '```json\n{"notes": [{"Front": "Hello", "Back": "World",}]}\n```'
    cards = extract_cards_from_data(dirty_json)
    assert len(cards) == 1
    assert cards[0]["Front"] == "Hello"
    assert cards[0]["Back"] == "World"
