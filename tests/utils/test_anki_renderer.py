# ruff: noqa: SLF001
# noinspection PyProtectedMember

import pytest

from ankiforge.utils.anki_renderer import (
    _is_empty,
    _process_conditionals,
    _process_front_side,
    _sanitize_fields,
    render_anki_card,
)

pytestmark = pytest.mark.unit


def test_is_empty():
    """Vérifie la détection de champs HTML considérés comme 'vides' par Anki."""
    assert _is_empty("")
    assert _is_empty("   ")
    assert _is_empty("<br>")
    assert _is_empty("<div>&nbsp;</div>")

    assert not _is_empty("Texte")
    assert not _is_empty("<b>Gras</b>")


def test_sanitize_fields():
    """Vérifie la conversion des listes et des None pour le moteur."""
    raw: dict[str, str | list[str]] = {"Texte": "Normal", "Liste": ["A", "B"], "Vide": ""}
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
    fields: dict[str, str | list[str]] = {"Recto": "Q?", "Verso": "R!"}

    result = render_anki_card(raw_html=raw_html, css=css, fields_dict=fields, is_recto=True)

    # Vérifications de structure HTML
    assert "<html>" in result
    assert ".card { color: red; }" in result
    assert "katex" in result

    # Vérifications des données
    assert "<b>Q?</b><br>R!" in result


def test_process_media_references_images_and_sounds(tmp_path, monkeypatch):
    """Vérifie la réécriture des balises d'images et de son [sound:...] dans le HTML."""
    from ankiforge.utils.anki_renderer import _process_media_references

    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("ankiforge.utils.paths.get_media_dir", lambda *_: media_dir)

    # Création d'une fausse image et d'un faux fichier audio
    test_img = media_dir / "carte_france.png"
    test_img.write_bytes(b"image content")
    test_audio = media_dir / "prononciation.mp3"
    test_audio.write_bytes(b"audio content")

    raw_html = '<div><img src="carte_france.png" alt="France"><img src="https://example.com/logo.png">[sound:prononciation.mp3][sound:introuvable.mp3]</div>'

    processed = _process_media_references(raw_html)

    # 1. Image locale résolue en URL file://
    assert 'src="file://' in processed
    assert "carte_france.png" in processed

    # 2. Image distante non modifiée
    assert 'src="https://example.com/logo.png"' in processed

    # 3. Audio existant converti en lecteur HTML5 <audio>
    assert "<audio controls" in processed
    assert "prononciation.mp3" in processed

    # 4. Audio manquant avec repli visuel propre
    assert "🔊 introuvable.mp3" in processed
