import pytest

from ankiforge.utils.anki_renderer import render_anki_card

pytestmark = pytest.mark.unit


def test_type_field_filter_recto_and_verso():
    """Vérifie la gestion des champs type: (taper la réponse) au recto et verso."""
    qfmt = "{{Front}}<br>{{type:Back}}"
    afmt = "{{FrontSide}}<hr id='answer'>{{type:Back}}"
    fields = {"Front": "Question", "Back": "Réponse attendue"}

    # 1. Rendu Recto : doit contenir une zone de saisie
    front_rendered = render_anki_card(
        raw_html=qfmt,
        css="",
        fields_dict=fields,
        is_recto=True,
    )
    assert "<input" in front_rendered
    assert "{{type:Back}}" not in front_rendered

    # 2. Rendu Verso :
    # - {{FrontSide}} ne doit PAS contenir le champ brut {{type:Back}}
    # - {{FrontSide}} ne doit PAS contenir la zone de saisie <input> résiduelle du recto
    # - Le verso avec {{type:Back}} doit afficher la réponse attendue (typeAns), PAS un <input> avec placeholder
    back_rendered = render_anki_card(
        raw_html=afmt,
        css="",
        fields_dict=fields,
        is_recto=False,
        front_html=qfmt,
    )
    assert "{{type:Back}}" not in back_rendered, "La balise {{type:Back}} ne doit pas rester brute dans FrontSide"
    assert "<input" not in back_rendered, "Le verso ne doit pas afficher de champ de saisie <input>"
    assert "typeAns" in back_rendered or "Réponse attendue" in back_rendered
    assert "typeAns" in back_rendered, "Le verso doit afficher la réponse typée avec la classe typeAns"


def test_anki_text_filter():
    """Vérifie le filtre standard Anki {{text:Champ}} qui dépouille le HTML."""
    raw_html = "{{text:Content}}"
    fields = {"Content": "<b>Texte en gras</b> et <i>italique</i>"}

    rendered = render_anki_card(
        raw_html=raw_html,
        css="",
        fields_dict=fields,
        is_recto=True,
    )
    assert "{{text:Content}}" not in rendered
    assert "<b>" not in rendered
    assert "Texte en gras et italique" in rendered


def test_anki_hint_filter():
    """Vérifie le filtre standard Anki {{hint:Champ}} qui génère un lien d'indice dépliable."""
    raw_html = "{{Front}}<br>{{hint:Indice}}"
    fields = {"Front": "Question", "Indice": "Un indice utile"}

    rendered = render_anki_card(
        raw_html=raw_html,
        css="",
        fields_dict=fields,
        is_recto=True,
    )
    assert "{{hint:Indice}}" not in rendered
    assert "Un indice utile" in rendered
    assert "hint" in rendered.lower()


def test_type_field_in_full_html_front_side():
    """Vérifie que {{FrontSide}} extrait correctement le contenu même si front_html est un document complet."""
    qfmt = "{{Front}}<br>{{type:Back}}"
    afmt = "{{FrontSide}}<hr id='answer'>{{type:Back}}"
    fields = {"Front": "Question Complète", "Back": "Réponse Finale"}

    # On simule un front_html qui est une page complète rendue par render_anki_card
    full_front_html = render_anki_card(raw_html=qfmt, css="", fields_dict=fields, is_recto=True)

    back_rendered = render_anki_card(
        raw_html=afmt,
        css="",
        fields_dict=fields,
        is_recto=False,
        front_html=full_front_html,
    )

    # Doit contenir la question, la réponse, et aucune duplication de <html> ou <!DOCTYPE
    assert "Question Complète" in back_rendered
    assert "Réponse Finale" in back_rendered
    assert back_rendered.count("<!DOCTYPE html>") == 1
    assert back_rendered.count("<html") == 1
    assert "{{type:Back}}" not in back_rendered
    assert "<input" not in back_rendered


def test_audio_sample_preview_renders_controls():
    """Vérifie que les balises de prévisualisation audio génèrent un élément <audio controls>."""
    raw_html = "{{Front}}<br>[sound:preview_sample.mp3]"
    fields = {"Front": "Écoutez le son"}

    rendered = render_anki_card(raw_html=raw_html, css="", fields_dict=fields, is_recto=True)
    assert "<audio controls" in rendered
    assert "preview_sample.mp3" not in rendered  # Remplacé par le lecteur HTML5


def test_generate_preview_mock_fields_heuristic():
    """Vérifie que la fonction de génération de champs factices identifie correctement les types de champs."""
    from ankiforge.ui.views.card_models_view.view import generate_preview_mock_fields

    fields = ["Front", "Back", "Audio", "Illustration", "MonScore", "Indice", "Texte"]
    mocks = generate_preview_mock_fields(fields)

    assert "Quelle est la capitale" in mocks["Front"]
    assert "Paris est la capitale" in mocks["Back"]
    assert mocks["Audio"] == "[sound:preview_sample.mp3]"
    assert "🖼️ Illustration" in mocks["Illustration"]
    assert mocks["MonScore"] == "42"
    assert "Indice utile" in mocks["Indice"]
    assert "{{c1::" in mocks["Texte"]
