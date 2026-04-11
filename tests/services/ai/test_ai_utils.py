import pytest

from ankiforge.services.ai.utils import parse_ai_json_response

# On génère le fameux symbole Markdown dynamiquement via son code ASCII (96)
# Cela permet d'écrire les tests sans jamais casser l'affichage de l'éditeur !
MARKDOWN_CODE_BLOCK = chr(96) * 3


def test_parse_pure_json():
    """Test 1: L'IA est disciplinée et renvoie uniquement le JSON brut."""
    raw_response = """{"notes": [{"Recto": "Question", "Verso": "Réponse"}]}"""

    result = parse_ai_json_response(raw_response)

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

    result = parse_ai_json_response(raw_response)

    assert "notes" in result
    assert len(result["notes"]) == 1
    assert result["notes"][0]["Recto"] == "M1"


def test_parse_markdown_without_language_specifier():
    """Test 3: L'IA met la balise de code mais oublie de préciser le mot 'json'."""
    raw_response = """\n""" + MARKDOWN_CODE_BLOCK + """\n""" + """{"notes": [{"Test": "OK"}]}\n""" + MARKDOWN_CODE_BLOCK + """\n"""

    result = parse_ai_json_response(raw_response)

    assert isinstance(result, dict)
    assert result["notes"][0]["Test"] == "OK"


def test_parse_json_with_leading_and_trailing_spaces():
    """Test 4: L'IA renvoie du JSON pur mais avec des sauts de ligne ou des espaces inutiles."""
    raw_response = """\n\n   {"notes": []}   \n"""

    result = parse_ai_json_response(raw_response)

    assert isinstance(result, dict)
    assert result["notes"] == []


def test_parse_invalid_broken_json():
    """Test 5: L'IA a cassé la syntaxe JSON (oubli de guillemets, virgule en trop, etc.)."""
    # Ici on oublie volontairement les guillemets autour de la clé Front pour simuler une erreur
    raw_response = MARKDOWN_CODE_BLOCK + """json { "notes": [ { Front: "Cassé" } ] } """ + MARKDOWN_CODE_BLOCK

    # On vérifie que notre fonction attrape l'erreur et lève une ValueError propre
    with pytest.raises(ValueError) as exc_info:
        parse_ai_json_response(raw_response)

    assert "Impossible de lire le JSON" in str(exc_info.value)
    assert "L'IA a généré un format invalide" in str(exc_info.value)
