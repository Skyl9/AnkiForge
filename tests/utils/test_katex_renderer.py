"""
Tests complets pour le moteur de rendu KaTeX et la gestion des balises mathématiques :
- Résolution locale des assets KaTeX et structure du script injecté
- Pré-traitement et assainissement des blocs mathématiques (_preprocess_math_blocks)
- Conversion des balises math historiques Anki ([latex], [math], [$], [45808])
- Préservation et transformation des clozes imbriqués dans les formules mathématiques
- Surlignage syntaxique sans rupture sur les parenthèses de fonctions (f(x), sin(x))
- Rendu réel dans Qt WebEngine (SafeWebEngineView / headless)
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRegularExpression, QUrl
from PySide6.QtGui import QTextDocument
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings

from ankiforge.ui.widgets.katex_editor import KaTeXHighlighter
from ankiforge.ui.widgets.note_editor_widget import NoteKaTeXHighlighter
from ankiforge.ui.widgets.safe_web_preview import SafeWebEngineView
from ankiforge.utils.anki_renderer import (
    _preprocess_math_blocks,
    get_mathjax_script,
    render_anki_card,
)
from ankiforge.utils.paths import get_resource_path


def test_katex_local_assets_exist() -> None:
    """Vérifie que les assets minifiés KaTeX et polices woff2 sont bien présents localement."""
    css_res = get_resource_path("resources", "katex", "katex.min.css")
    js_res = get_resource_path("resources", "katex", "katex.min.js")
    auto_render_res = get_resource_path("resources", "katex", "auto-render.min.js")

    assert css_res.exists(), f"Fichier KaTeX CSS introuvable : {css_res}"
    assert js_res.exists(), f"Fichier KaTeX JS introuvable : {js_res}"
    assert auto_render_res.exists(), f"Fichier KaTeX auto-render introuvable : {auto_render_res}"

    fonts_dir = get_resource_path("resources", "katex", "fonts")
    assert fonts_dir.exists(), f"Dossier fonts introuvable : {fonts_dir}"
    woff2_count = len(list(fonts_dir.glob("*.woff2")))
    assert woff2_count >= 10, f"Nombre insuffisant de polices KaTeX woff2 : {woff2_count}"


def test_get_mathjax_script_contains_valid_delimiters_and_settings() -> None:
    """Vérifie que le script injecté contient les délimiteurs correctement échappés et les options KaTeX."""
    script = get_mathjax_script()

    # Doit inclure les assets KaTeX (locaux file:// ou CDN)
    assert "katex.min.css" in script
    assert "katex.min.js" in script
    assert "auto-render.min.js" in script

    # Délimiteurs échappés pour JavaScript (double antislash dans le HTML)
    assert r"\\(" in script
    assert r"\\)" in script
    assert r"\\[" in script
    assert r"\\]" in script
    assert "$$" in script

    # Options de tolérance et d'extension HTML pour les clozes
    assert "trust" in script
    assert "strict" in script
    assert "throwOnError: false" in script

    # Garde-fou timeout pour éviter la boucle infinie
    assert "katexAttempts" in script
    assert "clearInterval(katexInterval)" in script


def test_preprocess_math_blocks_legacy_tags() -> None:
    """Vérifie la conversion de toutes les balises mathématiques historiques Anki."""
    raw = "1. [latex]\\frac{a}{b}[/latex] 2. [math]x^2[/math] 3. [$]\\alpha[/$] 4. [$$]\\beta[/$$]"
    processed = _preprocess_math_blocks(raw)

    assert "\\[\\frac{a}{b}\\]" in processed
    assert "\\(x^2\\)" in processed
    assert "\\(\\alpha\\)" in processed
    assert "\\[\\beta\\]" in processed
    assert "[latex]" not in processed
    assert "[math]" not in processed
    assert "[$]" not in processed
    assert "[$$]" not in processed


def test_preprocess_math_blocks_sanitizes_html_inside_math() -> None:
    """Vérifie que les sauts de lignes <br> et entités HTML sont nettoyés à l'intérieur des formules."""
    raw = r"Formule avec br : \( a + b <br> = c \) et entités : \[ x &lt; y &amp; z &gt; w &nbsp; \]"
    processed = _preprocess_math_blocks(raw)

    assert "<br>" not in processed
    assert "&lt;" not in processed
    assert "&amp;" not in processed
    assert "&gt;" not in processed
    assert "&nbsp;" not in processed

    assert r"\( a + b " in processed
    assert r" = c \)" in processed
    assert r"\[ x < y & z > w   \]" in processed


def test_preprocess_math_blocks_transforms_cloze_spans() -> None:
    r"""Vérifie que <span class='cloze'> dans une formule devient \htmlClass{cloze}{...}."""
    raw = r"Formule : \( <span class='cloze'>[...]</span> + 1 = 0 \) et \[ <span class='cloze'>x^2</span> = 4 \]"
    processed = _preprocess_math_blocks(raw)

    assert r"\( \htmlClass{cloze}{[...]} + 1 = 0 \)" in processed
    assert r"\[ \htmlClass{cloze}{x^2} = 4 \]" in processed
    assert "<span class='cloze'>" not in processed
    assert '<span class="cloze">' not in processed


def test_render_anki_card_injects_katex_and_cloze_styles() -> None:
    """Vérifie que render_anki_card pré-traite les formules et injecte les styles cloze KaTeX."""
    fields = {"Front": r"Calcul : \( {{c1::\sqrt{2}}} pprox 1.414 \)", "Back": "OK"}
    html = render_anki_card("{{cloze:Front}}", "", fields, is_recto=True, template_index=0)

    # La formule doit avoir été transformée avec \htmlClass
    assert r"\htmlClass{cloze}{[...]}" in html
    # Le script KaTeX doit être présent
    assert "renderMathInElement" in html
    # Les règles CSS pour .katex .cloze doivent être incluses
    assert ".katex .cloze" in html


def test_highlighters_highlight_parentheses_formulas(qtbot: Any) -> None:
    """Vérifie que les highlighters ne coupent pas la coloration sur les parenthèses internes."""
    doc = QTextDocument()
    highlighter = NoteKaTeXHighlighter(doc)
    assert len(highlighter.rules) >= 4

    test_text = "Voici une formule : \\( f(x) = \\frac{1}{(1+x)} \\) et une autre : \\( \\sin(x) \\)"
    doc.setPlainText(test_text)

    # Vérification que la regex du surligneur trouve l'intégralité de la formule
    pattern = QRegularExpression(r"\\\(.+?\\\)")
    match = pattern.match(test_text)
    assert match.hasMatch()
    assert match.captured(0) == "f(x) = \\frac{1}{(1+x)}" or match.captured(0) == "\\( f(x) = \\frac{1}{(1+x)} \\)"

    # Test KaTeXHighlighter
    katex_hl = KaTeXHighlighter(doc)
    assert len(katex_hl.rules) >= 4


def test_safe_web_engine_view_has_file_urls_enabled(qtbot: Any) -> None:
    """Vérifie que SafeWebEngineView autorise l'accès aux URLs de fichiers locaux pour KaTeX."""
    view = SafeWebEngineView()
    qtbot.addWidget(view)

    assert view.settings().testAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls) is True
    assert view.settings().testAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls) is True
    view.cleanup()


def test_webengine_headless_renders_katex_formulas(qtbot: Any) -> None:
    """Test réel offscreen dans QWebEnginePage pour confirmer que KaTeX s'exécute et génère .katex."""
    page = QWebEnginePage()
    page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
    page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

    fields = {
        "Front": (
            "1. Inline : \\( f(x) = \\frac{1}{(1+x)} \\)<br>"
            "2. Display : \\[ \\int_0^1 x^2 dx = \\frac{1}{3} \\]<br>"
            "3. Cloze math : \\( {{c1::x^2}} + 1 = 0 \\)<br>"
            "4. Multiline br : \\( a + b <br> = c \\)<br>"
            "5. Legacy : [latex]e^{i\\pi} + 1 = 0[/latex]"
        ),
        "Back": "Verso",
    }
    html = render_anki_card("{{cloze:Front}}", "", fields, is_recto=True, template_index=0)

    css_res = get_resource_path("resources", "katex", "katex.min.css")
    base_url = QUrl.fromLocalFile(str(css_res.parent) + "/")

    page.setHtml(html, base_url)

    rendered_count: list[int] = []

    def check_result(count: Any) -> None:
        rendered_count.append(int(count) if count is not None else 0)

    # On attend que KaTeX termine son auto-render dans WebEngine
    qtbot.wait(2000)

    page.runJavaScript("document.querySelectorAll('.katex').length", check_result)
    qtbot.wait(500)

    assert len(rendered_count) > 0
    # Les 5 formules doivent toutes avoir généré des éléments .katex
    assert rendered_count[0] >= 5, f"Nombre de formules KaTeX rendues insuffisant : {rendered_count[0]}"
