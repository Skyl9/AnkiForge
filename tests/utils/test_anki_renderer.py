# tests/utils/test_anki_renderer.py
import pytest

from ankiforge.utils.anki_renderer import (
    _is_empty, _sanitize_fields, _process_conditionals,
    _process_standard_fields, _process_front_side, render_anki_card
)


def test_is_empty():
    """Vérifie la détection de champs HTML considérés comme 'vides' par Anki."""
    assert _is_empty("") == True
    assert _is_empty("   ") == True
    assert _is_empty("<br>") == True
    assert _is_empty("<div>&nbsp;</div>") == True

    assert _is_empty("Texte") == False
    assert _is_empty("<b>Gras</b>") == False


def test_sanitize_fields():
    """Vérifie la conversion des listes et des None pour le moteur."""
    raw = {
        "Texte": "Normal",
        "Liste": ["A", "B"],
        "Vide": None
    }
    safe = _sanitize_fields(raw)

    assert safe["Texte"] == "Normal"
    assert safe["Liste"] == "A<br>B"
    assert safe["Vide"] == ""


def test_process_conditionals():
    """Vérifie les blocs {{#Champ}} (si plein) et {{^Champ}} (si vide)."""
    fields = {"Plein": "Info", "Vide": ""}

    # 1. Condition Positive (Le texte doit rester)
    html_pos = "Début {{#Plein}}Le champ est plein{{/Plein}} Fin"
    assert _process_conditionals(html_pos, fields) == "Début Le champ est plein Fin"

    # 2. Condition Positive sur champ vide (Le texte doit disparaître)
    html_pos_empty = "Début {{#Vide}}Invisible{{/Vide}} Fin"
    assert _process_conditionals(html_pos_empty, fields) == "Début  Fin"

    # 3. Condition Négative (S'affiche uniquement si vide)
    html_neg = "Début {{^Vide}}Le champ est vide !{{/Vide}} Fin"
    assert _process_conditionals(html_neg, fields) == "Début Le champ est vide ! Fin"


def test_process_front_side():
    """Vérifie que la balise {{FrontSide}} injecte bien le recto sans les balises orphelines."""
    fields = {"Recto": "Question1"}

    # Le Recto d'origine (avec un bloc conditionnel vide qui devrait être nettoyé)
    front_html = "{{Recto}} {{#Inconnu}}Texte{{/Inconnu}}"

    # Le Verso qui demande l'injection du Recto
    back_html = "Voici la réponse. Rappel : {{FrontSide}}"

    result = _process_front_side(back_html, front_html, fields)

    assert "Question1" in result
    assert "{{#Inconnu}}" not in result  # Nettoyage réussi


def test_render_anki_card_integration():
    """Test global du rendu final."""
    raw_html = "<b>{{Recto}}</b><br>{{Verso}}"
    css = ".card { color: red; }"
    fields = {"Recto": "Q?", "Verso": "R!"}

    result = render_anki_card(
        raw_html=raw_html,
        css=css,
        fields_dict=fields,
        is_recto=True
    )

    # Vérifications de structure HTML
    assert "<html>" in result
    assert ".card { color: red; }" in result
    assert "MathJax" in result
    assert "tex-svg.js" in result

    # Vérifications des données
    assert "<b>Q?</b><br>R!" in result