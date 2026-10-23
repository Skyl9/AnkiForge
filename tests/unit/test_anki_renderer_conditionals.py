"""Tests unitaires pour le moteur de parser conditionnel récursif et la règle de génération Anki (ADR 0037).

Vérifie :
1. Les conditionnels simples {{#Champ}} et {{^Champ}}.
2. Les conditionnels imbriqués {{#A}}...{{#B}}...{{/B}}...{{/A}}.
3. Le traitement des champs absents du dictionnaire de valeurs.
4. Le respect de la règle de génération de carte Anki (should_generate_card).
"""

import pytest

from ankiforge.utils.anki_renderer import (
    _process_conditionals,
    _sanitize_fields,
    should_generate_card,
)

pytestmark = pytest.mark.unit


def test_process_conditionals_simple():
    """Vérifie l'évaluation des conditionnels simples positifs et négatifs."""
    fields = _sanitize_fields({"Front": "Bonjour", "Extra": ""})

    # Champ rempli : positif conservé, négatif supprimé
    html = "{{#Front}}Contenu Présent{{/Front}}"
    assert _process_conditionals(html, fields) == "Contenu Présent"

    html_neg = "{{^Front}}Contenu Absent{{/Front}}"
    assert _process_conditionals(html_neg, fields) == ""

    # Champ vide : positif supprimé, négatif conservé
    html_empty = "{{#Extra}}Contenu Extra{{/Extra}}"
    assert _process_conditionals(html_empty, fields) == ""

    html_empty_neg = "{{^Extra}}Pas d'Extra{{/Extra}}"
    assert _process_conditionals(html_empty_neg, fields) == "Pas d'Extra"


def test_process_conditionals_absent_field():
    """Vérifie qu'un champ absent du dictionnaire est évalué comme falsy (vide)."""
    fields = _sanitize_fields({"Front": "Bonjour"})

    # Le champ 'Inconnu' n'est pas dans fields
    html_pos = "{{#Inconnu}}Ne doit pas s'afficher{{/Inconnu}}"
    assert _process_conditionals(html_pos, fields) == ""

    html_neg = "{{^Inconnu}}Champ Absent Détecté{{/Inconnu}}"
    assert _process_conditionals(html_neg, fields) == "Champ Absent Détecté"


def test_process_conditionals_nested():
    """Vérifie l'évaluation récursive de conditionnels imbriqués."""
    fields_both = _sanitize_fields({"A": "ValA", "B": "ValB"})
    fields_only_a = _sanitize_fields({"A": "ValA", "B": ""})
    fields_none = _sanitize_fields({"A": "", "B": ""})

    template = "{{#A}}A est là [{{#B}}B aussi{{/B}}]{{/A}}"

    assert _process_conditionals(template, fields_both) == "A est là [B aussi]"
    assert _process_conditionals(template, fields_only_a) == "A est là []"
    assert _process_conditionals(template, fields_none) == ""

    # Imbrication inversée : si pas de A mais B est là
    template_inv = "{{^A}}Pas de A mais {{#B}}B est là{{/B}}{{/A}}"
    assert _process_conditionals(template_inv, fields_only_a) == ""
    assert _process_conditionals(template_inv, _sanitize_fields({"A": "", "B": "Oui"})) == "Pas de A mais B est là"


def test_should_generate_card_basic():
    """Vérifie la règle de génération pour un modèle basique."""
    qfmt = "{{Front}}"

    assert should_generate_card(qfmt, {"Front": "Question non vide"}) is True
    assert should_generate_card(qfmt, {"Front": "   "}) is False
    assert should_generate_card(qfmt, {"Front": ""}) is False
    assert should_generate_card(qfmt, {}) is False


def test_should_generate_card_optional_reversed():
    """Vérifie le cas classique du modèle 'Basique (carte inversée optionnelle)'.

    Carte 1 : Front={{Front}}
    Carte 2 : Front={{#Add Reverse}}{{Back}}{{/Add Reverse}}
    """
    qfmt_card2 = "{{#Add Reverse}}{{Back}}{{/Add Reverse}}"

    # Si Add Reverse est vide : pas de carte 2
    assert should_generate_card(qfmt_card2, {"Front": "Q", "Back": "A", "Add Reverse": ""}) is False

    # Si Add Reverse est présent mais Back est vide : pas de carte 2
    assert should_generate_card(qfmt_card2, {"Front": "Q", "Back": "", "Add Reverse": "y"}) is False

    # Si Add Reverse et Back sont présents : carte 2 générée !
    assert should_generate_card(qfmt_card2, {"Front": "Q", "Back": "A", "Add Reverse": "y"}) is True


def test_should_generate_card_with_html_and_media():
    """Vérifie la génération avec balises HTML et éléments médias.

    Un recto avec seulement des balises vides (ex: <br>, <div></div>) ne génère pas de carte,
    mais une image <img> ou un tag audio génère une carte.
    """
    qfmt = "{{#Front}}{{Front}}{{/Front}}"

    assert should_generate_card(qfmt, {"Front": "<br>&nbsp;<div>  </div>"}) is False
    assert should_generate_card(qfmt, {"Front": "<img src='image.png'>"}) is True
    assert should_generate_card(qfmt, {"Front": "[sound:audio.mp3]"}) is True
