# noinspection PyProtectedMember

from unittest.mock import MagicMock, patch

import pytest

from ankiforge.database.models.cards import NoteTypeModel
from ankiforge.utils.anki_renderer import (
    _is_empty,
    _process_conditionals,
    _process_front_side,
    _process_latex_blocks,
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


def test_render_anki_card_theme_defaults_keep_preview_readable():
    """Le rendu applique un contraste de base dans les deux thèmes."""
    light = render_anki_card(raw_html="{{Recto}}", css="", fields_dict={"Recto": "Question"}, is_dark_mode=False)
    dark = render_anki_card(raw_html="{{Recto}}", css="", fields_dict={"Recto": "Question"}, is_dark_mode=True)

    assert "body { background-color: #f8fafc; color: #1e293b;" in light
    assert "body.nightMode { background-color: #1e2128; color: #e2e8f0;" in light
    assert '<body class="">' in light
    assert '<body class="nightMode">' in dark
    assert ".nightMode .card { background-color: #1e2128; color: #e2e8f0; }" in dark


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


def test_render_anki_card_newline_conversion_and_palette_cleaning() -> None:
    """Vérifie que render_anki_card remplace palette(text) et convertit \n en <br> pour les champs multilignes."""
    fields = {"Front": "Ligne 1\nLigne 2\nLigne 3", "Back": "Réponse directe"}
    css = ".card { color: palette(text); font-size: 20px; }"

    rendered = render_anki_card(
        raw_html="{{Front}}",
        css=css,
        fields_dict=fields,
        is_recto=True,
    )

    # Vérifier que palette(text) a été assaini
    assert "palette(text)" not in rendered
    assert "inherit" in rendered

    # Vérifier que les retours à la ligne \n ont été convertis en <br>
    assert "Ligne 1<br>Ligne 2<br>Ligne 3" in rendered


def _make_mock_compiler(ready: bool = True, filename: str = "latex-abc123.svg") -> MagicMock:
    """Crée un LatexCompilerService mock."""
    compiler = MagicMock()
    compiler.is_ready.return_value = ready
    compiler.compile_snippet_to_media.return_value = filename
    return compiler


def _make_mock_note_type(latex_pre: str = "", latex_post: str = "", latex_svg: bool = True) -> MagicMock:
    """Crée un NoteTypeModel mock avec les champs LaTeX."""
    mock = MagicMock(spec=NoteTypeModel)
    mock.latex_pre = latex_pre
    mock.latex_post = latex_post
    mock.latex_svg = latex_svg
    return mock


def test_process_latex_blocks_compiler_ready_replaces_with_img() -> None:
    """[latex]...[/latex] est remplacé par <img class="latex" src="..."> quand le compilateur est prêt."""
    html = "Texte avant [latex]\\frac{1}{2}[/latex] texte après"
    compiler = _make_mock_compiler(ready=True)
    note_type = _make_mock_note_type()

    result = _process_latex_blocks(html, note_type, compiler)

    assert '<img class="latex" src="latex-abc123.svg">' in result
    assert "[latex]" not in result
    assert "[/latex]" not in result
    compiler.compile_snippet_to_media.assert_called_once_with("\\frac{1}{2}", note_type)


def test_process_latex_blocks_compiler_not_ready_fallback_span() -> None:
    """Repli sur <span class="af-latex-uncompiled"> quand le compilateur n'est pas prêt."""
    html = "Formule [latex]E = mc^2[/latex] ici"
    compiler = _make_mock_compiler(ready=False)
    note_type = _make_mock_note_type()

    result = _process_latex_blocks(html, note_type, compiler)

    assert '<span class="af-latex-uncompiled"' in result
    assert "E = mc^2" in result
    assert "[latex]" not in result
    compiler.compile_snippet_to_media.assert_not_called()


def test_process_latex_blocks_dollar_variants() -> None:
    """Les variantes [$]...[/$] et [$$]...[/$$] sont aussi gérées."""
    html = "Inline [$]\\alpha[/$] et display [$$]\\sum_{i=1}^n x_i[/$$]"
    compiler = _make_mock_compiler(ready=True)
    note_type = _make_mock_note_type()

    result = _process_latex_blocks(html, note_type, compiler)

    assert '<img class="latex" src="latex-abc123.svg">' in result
    assert "[$]" not in result
    assert "[/$]" not in result
    assert "[$$]" not in result
    assert "[/$$]" not in result
    assert compiler.compile_snippet_to_media.call_count == 2


def test_process_latex_blocks_compiler_exception_fallback() -> None:
    """En cas d'exception de compilation, repli sur span de secours."""
    html = "Test [latex]\\undefined[/latex]"
    compiler = _make_mock_compiler(ready=True)
    compiler.compile_snippet_to_media.side_effect = Exception("Erreur compilation")
    note_type = _make_mock_note_type()

    result = _process_latex_blocks(html, note_type, compiler)

    assert '<span class="af-latex-uncompiled"' in result
    assert "\\undefined" in result


def test_process_latex_blocks_none_compiler_fallback() -> None:
    """Quand compiler_service est None, repli sur span."""
    html = "Test [latex]x^2[/latex]"
    result = _process_latex_blocks(html, None, None)

    assert '<span class="af-latex-uncompiled"' in result
    assert "x^2" in result


def test_render_anki_card_latex_with_compiler_ready() -> None:
    """render_anki_card remplace [latex] par une image SVG quand le compilateur est prêt."""
    raw_html = "Formule : [latex]\\frac{1}{2}[/latex]"
    css = ""
    fields = {}
    note_type = _make_mock_note_type()

    with patch("ankiforge.utils.anki_renderer.LatexCompilerService") as mock_compiler_cls:
        compiler_instance = _make_mock_compiler(ready=True)
        mock_compiler_cls.return_value = compiler_instance

        result = render_anki_card(
            raw_html=raw_html,
            css=css,
            fields_dict=fields,
            is_recto=True,
            note_type=note_type,
        )

        assert '<img class="latex" src="latex-abc123.svg">' in result
        assert "[latex]" not in result


def test_render_anki_card_latex_without_compiler_fallback() -> None:
    """render_anki_card utilise le span de repli quand aucun note_type n'est fourni."""
    raw_html = "Formule : [latex]\\frac{1}{2}[/latex]"
    css = ""
    fields = {}

    result = render_anki_card(
        raw_html=raw_html,
        css=css,
        fields_dict=fields,
        is_recto=True,
        note_type=None,
    )

    assert '<span class="af-latex-uncompiled"' in result
    assert "\\frac{1}{2}" in result
    assert "[latex]" not in result


def test_render_anki_card_katex_delimiters_preserved() -> None:
    """Les délimiteurs KaTeX $..$ et \\(..\\) sont préservés (non convertis en SVG)."""
    raw_html = "Math inline : $x^2$ et \\(\\alpha\\)"
    css = ""
    fields = {}
    note_type = _make_mock_note_type()

    result = render_anki_card(
        raw_html=raw_html,
        css=css,
        fields_dict=fields,
        is_recto=True,
        note_type=note_type,
    )

    assert "$x^2$" in result
    assert "\\(\\alpha\\)" in result
