import dataclasses

import pytest

from ankiforge.services.ai.utils import AIReponseParser

pytestmark = pytest.mark.unit


# On génère le fameux symbole Markdown dynamiquement via son code ASCII (96)
# Cela permet d'écrire les tests sans jamais casser l'affichage de l'éditeur !
MARKDOWN_CODE_BLOCK = chr(96) * 3


def test_parse_pure_json():
    """Test 1: L'IA est disciplinée et renvoie uniquement le JSON brut."""
    raw_response = """{"notes": [{"Recto": "Question", "Verso": "Réponse"}]}"""

    result = AIReponseParser.parse(raw_response)

    assert isinstance(result, dict)
    assert "notes" in result
    assert result["notes"][0]["Recto"] == "Question"


def test_parse_markdown_json_with_text():
    """Test 2: L'IA est bavarde et entoure le JSON de texte et de balises Markdown (très fréquent)."""

    raw_response = (
        """Voici vos flashcards générées avec succès !\n\n"""
        + MARKDOWN_CODE_BLOCK
        + """json\n"""
        + """{\n    "notes": [\n        {"Recto": "M1", "Verso": "M2"}\n    ]\n}\n"""
        + MARKDOWN_CODE_BLOCK
        + """\n\n"""
        """N'hésitez pas si vous en voulez d'autres."""
    )

    result = AIReponseParser.parse(raw_response)

    assert "notes" in result
    assert len(result["notes"]) == 1
    assert result["notes"][0]["Recto"] == "M1"


def test_parse_markdown_without_language_specifier():
    """Test 3: L'IA met la balise de code mais oublie de préciser le mot 'json'."""
    raw_response = """\n""" + MARKDOWN_CODE_BLOCK + """\n""" + """{"notes": [{"Test": "OK"}]}\n""" + MARKDOWN_CODE_BLOCK + """\n"""

    result = AIReponseParser.parse(raw_response)

    assert isinstance(result, dict)
    assert result["notes"][0]["Test"] == "OK"


def test_parse_json_with_leading_and_trailing_spaces():
    """Test 4: L'IA renvoie du JSON pur mais avec des sauts de ligne ou des espaces inutiles."""
    raw_response = """\n\n   {"notes": []}   \n"""

    result = AIReponseParser.parse(raw_response)

    assert isinstance(result, dict)
    assert result["notes"] == []


def test_parse_invalid_broken_json():
    """Test 5: L'IA a cassé la syntaxe JSON (oubli de guillemets, virgule en trop, etc.)."""
    # Ici on oublie volontairement les guillemets autour de la clé Front pour simuler une erreur
    raw_response = MARKDOWN_CODE_BLOCK + """json { "notes": [ { Front: "Cassé" } ] } """ + MARKDOWN_CODE_BLOCK

    # On vérifie que notre fonction attrape l'erreur et lève une ValueError propre
    with pytest.raises(ValueError) as exc_info:
        AIReponseParser.parse(raw_response)

    assert "Impossible de lire le JSON" in str(exc_info.value)
    assert "L'IA a généré un format invalide" in str(exc_info.value)


@dataclasses.dataclass
class Flashcard:
    Recto: str
    Verso: str


@dataclasses.dataclass
class DeckResponse:
    notes: list[Flashcard]


def test_parse_with_dataclass():
    raw_response = """{"notes": [{"Recto": "Q1", "Verso": "A1"}, {"Recto": "Q2", "Verso": "A2"}]}"""
    result = AIReponseParser.parse(raw_response, target_model=DeckResponse)

    assert isinstance(result, DeckResponse)
    assert len(result.notes) == 2
    assert isinstance(result.notes[0], Flashcard)
    assert result.notes[0].Recto == "Q1"


def test_parse_with_list_dataclass():
    raw_response = """[{"Recto": "Q1", "Verso": "A1"}]"""
    result = AIReponseParser.parse(raw_response, target_model=list[Flashcard])

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], Flashcard)
    assert result[0].Recto == "Q1"


def test_extract_cards_from_data():
    from ankiforge.services.ai.utils import extract_cards_from_data

    # Format 1: dict with "notes"
    d1 = {"notes": [{"Front": "Q1", "Back": "A1"}]}
    assert extract_cards_from_data(d1) == [{"Front": "Q1", "Back": "A1"}]

    # Format 2: dict with "cards"
    d2 = {"cards": [{"Front": "Q2", "Back": "A2"}]}
    assert extract_cards_from_data(d2) == [{"Front": "Q2", "Back": "A2"}]

    # Format 3: raw list of dicts
    d3 = [{"Front": "Q3", "Back": "A3"}]
    assert extract_cards_from_data(d3) == [{"Front": "Q3", "Back": "A3"}]

    # Format 4: string JSON
    d4 = '{"notes": [{"Front": "Q4", "Back": "A4"}]}'
    assert extract_cards_from_data(d4) == [{"Front": "Q4", "Back": "A4"}]

    # Format 5: single card dict
    d5 = {"Front": "Q5", "Back": "A5"}
    assert extract_cards_from_data(d5) == [{"Front": "Q5", "Back": "A5"}]

    # Format 6: empty or invalid
    assert extract_cards_from_data([]) == []
    assert extract_cards_from_data("invalid text") == []
    assert extract_cards_from_data(None) == []


def test_parse_json_with_unescaped_html_quotes():
    """Vérifie que AIReponseParser répare les guillemets HTML non échappés."""
    raw = """{
      "notes": [
        {
          "Front": "Qu'est-ce que \\( E = mc^2 \\)?",
          "Back": "<div class=\\"important\\">Énergie de masse</div>"
        }
      ]
    }"""
    parsed = AIReponseParser.parse(raw)
    assert isinstance(parsed, dict)
    assert "notes" in parsed
    assert len(parsed["notes"]) == 1
    assert "Énergie de masse" in parsed["notes"][0]["Back"]


def test_parse_json_with_trailing_commas():
    """Vérifie la suppression automatique des virgules traînantes."""
    raw = """{
      "notes": [
        {"Front": "Q1", "Back": "A1",},
      ],
    }"""
    parsed = AIReponseParser.parse(raw)
    assert isinstance(parsed, dict)
    assert len(parsed["notes"]) == 1
    assert parsed["notes"][0]["Front"] == "Q1"


def test_parse_partial_broken_json_recovery():
    """Vérifie la récupération partielle d'objets JSON même si la racine est tronquée."""
    raw = """Voici les cartes :
    {"Front": "Q1", "Back": "A1"}
    {"Front": "Q2", "Back": "A2"}
    Fin de génération.
    """
    parsed = AIReponseParser.parse(raw)
    assert isinstance(parsed, dict)
    assert "notes" in parsed
    assert len(parsed["notes"]) == 2


def test_extract_cards_multi_model():
    """Vérifie la prise en charge des sorties multi-modèles structurées."""
    from ankiforge.services.ai.utils import extract_cards_from_data

    # Format multi-modèles standard avec clé "fields"
    multi_data = {
        "notes": [
            {
                "model": "Basique",
                "fields": {"Front": "Capitale France", "Back": "Paris"},
            },
            {
                "model": "Texte à trous (Cloze)",
                "fields": {"Texte": "La capitale de l'Italie est {{c1::Rome}}.", "Remarques extra": "Europe"},
            },
        ]
    }
    extracted = extract_cards_from_data(multi_data)
    assert len(extracted) == 2
    assert extracted[0]["model"] == "Basique"
    assert extracted[0]["Front"] == "Capitale France"
    assert extracted[0]["Back"] == "Paris"
    assert extracted[1]["model"] == "Texte à trous (Cloze)"
    assert "{{c1::Rome}}" in extracted[1]["Texte"]

    # Format multi-modèles plat
    flat_multi = {
        "notes": [
            {"model": "Basique", "Front": "Q1", "Back": "A1"},
            {"note_type": "Cloze", "Texte": "{{c1::Test}}", "Remarques extra": "Note"},
        ]
    }
    extracted_flat = extract_cards_from_data(flat_multi)
    assert len(extracted_flat) == 2
    assert extracted_flat[0]["model"] == "Basique"
    assert extracted_flat[1]["model"] == "Cloze"


def test_format_available_card_models_prompt():
    """Vérifie le formatage des directives de modèles de cartes pour le prompt Jinja."""
    from ankiforge.services.ai.utils import format_available_card_models_prompt

    mock_models = [
        {"name": "Basique", "description": "Questions simples Q/R", "fields_schema": '["Front", "Back"]'},
        {"name": "Cloze", "description": "Phrases à trous", "fields_schema": ["Texte", "Remarques extra"]},
    ]
    catalog = format_available_card_models_prompt(mock_models)
    assert "MODÈLES DE CARTES AUTORISÉS" in catalog
    assert 'Modèle : "Basique"' in catalog
    assert "Questions simples Q/R" in catalog
    assert '"Front": "..."' in catalog
    assert 'Modèle : "Cloze"' in catalog
    assert "Phrases à trous" in catalog
    assert "FORMAT JSON DE SORTIE" in catalog
