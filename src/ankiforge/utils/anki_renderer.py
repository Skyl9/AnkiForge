import logging
import re

from ankiforge.utils.paths import get_resource_path

logger = logging.getLogger(__name__)

AnkiFields = dict[str, str | list[str]]


def get_max_cloze_index(fields_dict: dict) -> int:
    """
    Identifie l'index de trou de complétion (cloze) le plus élevé dans une note.

    Parcourt tous les champs pour trouver des motifs de type {{c1::...}}, {{c2::...}}, etc.

    Args:
        fields_dict (dict): Dictionnaire des champs de la note.

    Returns:
        int: L'index maximum trouvé (ex: 3 pour c3). Retourne 0 si aucun n'est trouvé.
    """
    max_idx = 0
    pattern = re.compile(r"\{\{c(\d+)::", re.IGNORECASE)
    for val in fields_dict.values():
        if isinstance(val, str):
            for match in pattern.finditer(val):
                idx = int(match.group(1))
                if idx > max_idx:
                    max_idx = idx
    return max_idx


def _is_empty(html_str: str) -> bool:
    clean_text = re.sub(r"<[^>]+>", "", str(html_str)).replace("&nbsp;", "").strip()
    return len(clean_text) == 0


def _sanitize_fields(fields_dict: AnkiFields) -> dict[str, str]:
    safe_fields = {}
    for k, v in fields_dict.items():
        if isinstance(v, list):
            safe_fields[k] = "<br>".join([str(item) for item in v])
        else:
            safe_fields[k] = str(v) if v is not None else ""
    return safe_fields


def _process_conditionals(html: str, safe_fields: dict[str, str]) -> str:
    for field, val in safe_fields.items():
        empty = _is_empty(val)
        pos_pattern = r"\{\{#" + re.escape(field) + r"\}\}(.*?)\{\{/" + re.escape(field) + r"\}\}"
        html = re.sub(pos_pattern, r"\1" if not empty else "", html, flags=re.DOTALL)
        neg_pattern = r"\{\{\^" + re.escape(field) + r"\}\}(.*?)\{\{/" + re.escape(field) + r"\}\}"
        html = re.sub(neg_pattern, "" if not empty else r"\1", html, flags=re.DOTALL)
    return html


def _process_cloze_fields(html: str, safe_fields: dict[str, str], template_index: int, is_recto: bool) -> str:
    """Gère la syntaxe {{cloze:Champ}} et remplace les {{c1::texte::indice}}."""
    target_idx = template_index + 1  # L'index d'Anki commence à 1 (c1, c2...)
    # Accepte les sauts de lignes dans les trous avec re.DOTALL
    cloze_pattern = re.compile(r"\{\{c(\d+)::(.*?)(?:::([^}]*?))?\}\}", re.DOTALL | re.IGNORECASE)

    def cloze_replacer(match: re.Match[str]) -> str:
        c_idx = int(match.group(1))
        text = match.group(2)

        hint = match.group(3) if match.group(3) else "..."

        if c_idx == target_idx:
            if is_recto:
                return f"<span class='cloze'>[{hint}]</span>"
            else:
                return f"<span class='cloze'>{text}</span>"
        else:
            return text

    for field, val in safe_fields.items():
        cloze_tag = f"{{{{cloze:{field}}}}}"
        if cloze_tag in html:
            processed_val = cloze_pattern.sub(cloze_replacer, val)
            html = html.replace(cloze_tag, processed_val)

        # Si le champ n'a pas le préfixe cloze, on retire simplement la syntaxe et on affiche le texte
        safe_fields[field] = cloze_pattern.sub(r"\2", val)

    return html


def _process_standard_fields(html: str, safe_fields: dict[str, str]) -> str:
    for field, val in safe_fields.items():
        html = html.replace(f"{{{{{field}}}}}", val)
        html = html.replace(
            f"{{{{type:{field}}}}}",
            f"<br><input type='text' placeholder='{field}' disabled style='width:100%; padding:5px;'><br>",
        )
    return html


def _process_front_side(html: str, front_html: str, safe_fields: dict[str, str]) -> str:
    if "{{FrontSide}}" not in html:
        return html
    front_rendered = front_html
    for field, val in safe_fields.items():
        front_rendered = front_rendered.replace(f"{{{{{field}}}}}", val)
    front_rendered = re.sub(r"\{\{[#^/][^}]+\}\}", "", front_rendered)
    return html.replace("{{FrontSide}}", front_rendered)


def _preprocess_math_blocks(html: str) -> str:
    """
    Normalise et prépare les blocs mathématiques pour KaTeX :
    - Convertit les balises Anki historiques [latex]...[/latex], [math]...[/math], [$]...[/$], [$$]...[/$$].
    - Nettoie les balises parasites (<br>, &nbsp;, &amp;, etc.) à l'intérieur des délimiteurs mathématiques.
    - Transforme les clozes imbriqués (<span class='cloze'>...</span>) en macro KaTeX \\htmlClass{cloze}{...}
      pour garantir un rendu KaTeX continu tout en conservant le style visuel de trou cloze.
    """
    # 1. Conversion des balises math Anki historiques et variantes
    html = re.sub(r"\[latex\](.*?)\[/latex\]", lambda m: r"\[" + m.group(1) + r"\]", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"\[math\](.*?)\[/math\]", lambda m: r"\(" + m.group(1) + r"\)", html, flags=re.DOTALL | re.IGNORECASE)
    html = html.replace("[$]", r"\(").replace("[/$]", r"\)")
    html = html.replace("[$$]", r"\[").replace("[/$$]", r"\]")

    # 2. Nettoyage interne des blocs mathématiques
    math_pattern = re.compile(r"(\\\[.*?\\\]|\\\(.*?\\\)|\$\$.*?\$\$)", flags=re.DOTALL)

    def _clean_block(m: re.Match[str]) -> str:
        block = m.group(0)
        # Cloze span dans la formule -> \htmlClass{cloze}{contenu}
        block = re.sub(
            r"<span class=[\"']cloze[\"'][^>]*>(.*?)</span>",
            lambda cm: r"\htmlClass{cloze}{" + cm.group(1) + r"}",
            block,
            flags=re.DOTALL | re.IGNORECASE,
        )
        # Balises de saut de ligne HTML -> \n
        block = re.sub(r"<br\s*/?>", "\n", block, flags=re.IGNORECASE)
        # Entités HTML courantes
        block = block.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        return block

    return math_pattern.sub(_clean_block, html)


def get_mathjax_script() -> str:
    css_res = get_resource_path("resources", "katex", "katex.min.css")
    js_res = get_resource_path("resources", "katex", "katex.min.js")
    auto_render_res = get_resource_path("resources", "katex", "auto-render.min.js")

    if css_res.exists() and js_res.exists() and auto_render_res.exists():
        css_url = css_res.as_uri()
        js_url = js_res.as_uri()
        auto_render_url = auto_render_res.as_uri()
    else:
        css_url = "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css"
        js_url = "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"
        auto_render_url = "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"

    return f"""
    <link rel="stylesheet" href="{css_url}" crossorigin="anonymous">
    <script src="{js_url}" crossorigin="anonymous"></script>
    <script src="{auto_render_url}" crossorigin="anonymous"></script>
    <script>
        var katexAttempts = 0;
        var katexInterval = setInterval(function() {{
            katexAttempts++;
            if (window.renderMathInElement) {{
                clearInterval(katexInterval);
                renderMathInElement(document.body, {{
                    delimiters: [
                        {{left: '$$', right: '$$', display: true}},
                        {{left: '\\\\[', right: '\\\\]', display: true}},
                        {{left: '\\\\(', right: '\\\\)', display: false}},
                        {{left: '\\\\begin{{equation}}', right: '\\\\end{{equation}}', display: true}},
                        {{left: '\\\\begin{{align}}', right: '\\\\end{{align}}', display: true}},
                        {{left: '\\\\begin{{aligned}}', right: '\\\\end{{aligned}}', display: true}},
                        {{left: '\\\\begin{{alignat}}', right: '\\\\end{{alignat}}', display: true}},
                        {{left: '\\\\begin{{gather}}', right: '\\\\end{{gather}}', display: true}},
                        {{left: '\\\\begin{{CD}}', right: '\\\\end{{CD}}', display: true}}
                    ],
                    trust: function(ctx) {{ return true; }},
                    strict: 'ignore',
                    throwOnError: false
                }});
            }} else if (katexAttempts >= 100) {{
                clearInterval(katexInterval);
            }}
        }}, 50);
    </script>
    """


def _process_media_references(html: str) -> str:
    """
    Résout et réécrit les balises de médias dans le HTML d'une carte Anki :
    - <img src="..."> : résout le chemin physique réel avec resolve_media_path (support des noms hachés,
      cross-profils, et décompression Zstandard automatique). Si l'image est résolue, utilise son URL
      locale absolue (file://...) pour garantir que WebEngine la charge sans ambiguïté.
    - [sound:...] : convertit la syntaxe audio standard d'Anki en lecteur HTML5 <audio controls>.
    """
    from PySide6.QtCore import QUrl

    from ankiforge.utils.paths import resolve_media_path

    # 1. Remplacement des balises <img src="...">
    def _replace_img(match: re.Match[str]) -> str:
        prefix = match.group(1)
        src = match.group(2)
        suffix = match.group(3)

        if src.startswith(("http://", "https://", "data:", "qrc:/")):
            return match.group(0)

        resolved = resolve_media_path(src)
        if resolved.exists():
            file_url = QUrl.fromLocalFile(str(resolved)).toString()
            return f'<img{prefix}src="{file_url}"{suffix}>'
        return match.group(0)

    html = re.sub(
        r'<img([^>]*?)\bsrc=["\']([^"\']+)["\']([^>]*?)>',
        _replace_img,
        html,
        flags=re.IGNORECASE,
    )

    # 2. Conversion des balises audio Anki [sound:nom_fichier.mp3]
    def _replace_sound(match: re.Match[str]) -> str:
        audio_name = match.group(1).strip()
        resolved = resolve_media_path(audio_name)
        if resolved.exists():
            audio_url = QUrl.fromLocalFile(str(resolved)).toString()
            return (
                f'<span class="anki-audio-container" style="display: inline-block; margin: 4px 0;">'
                f'<audio controls preload="none" src="{audio_url}" style="height: 30px; vertical-align: middle; max-width: 280px;"></audio>'
                f"</span>"
            )
        return f'<span class="anki-audio-missing" style="opacity: 0.7; font-size: 11px;">🔊 {audio_name}</span>'

    html = re.sub(r"\[sound:([^\]]+)\]", _replace_sound, html, flags=re.IGNORECASE)

    return html


def render_anki_card(
    raw_html: str,
    css: str,
    fields_dict: AnkiFields,
    is_recto: bool = True,
    front_html: str = "",
    is_dark_mode: bool = False,
    template_index: int = 0,
) -> str:
    """
    Simule le rendu HTML d'une carte Anki.

    Gère les remplacements de champs, les sections conditionnelles, les trous de complétion
    (cloze deletion), le mode nuit et l'injection de MathJax/KaTeX pour le rendu LaTeX.

    Args:
        raw_html (str): Le template HTML brut (Recto ou Verso).
        css (str): Les styles CSS du modèle de note.
        fields_dict (AnkiFields): Les données de la note (champs -> contenu).
        is_recto (bool): Si True, affiche le recto. Sinon le verso.
        front_html (str): Le contenu rendu du recto (nécessaire pour {{FrontSide}} au verso).
        is_dark_mode (bool): Active les styles de mode nuit.
        template_index (int): L'index de la carte physique (pour les notes à plusieurs cartes).

    Returns:
        str: Le code HTML complet, prêt à être affiché dans un QWebEngineView.
    """
    logger.debug(
        "Rendu de carte Anki (recto=%s, dark_mode=%s, template_index=%d, %d champs)",
        is_recto,
        is_dark_mode,
        template_index,
        len(fields_dict),
    )
    safe_fields = _sanitize_fields(fields_dict)

    html = raw_html
    html = _process_conditionals(html, safe_fields)
    html = _process_cloze_fields(html, safe_fields, template_index, is_recto)
    html = _process_standard_fields(html, safe_fields)

    if not is_recto:
        html = _process_front_side(html, front_html, safe_fields)

    # Pré-traitement et normalisation des blocs mathématiques KaTeX / LaTeX
    html = _preprocess_math_blocks(html)

    # Résolution des médias (images et balises audio [sound:...])
    html = _process_media_references(html)

    body_class = "nightMode" if is_dark_mode else ""
    final_html = f"""<!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ background-color: transparent; margin: 0; padding: 15px; }}
                    ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
                    ::-webkit-scrollbar-track {{ background: transparent; }}
                    ::-webkit-scrollbar-thumb {{ background: #555; border-radius: 5px; }}
                    ::-webkit-scrollbar-thumb:hover {{ background: #777; }}
                    .cloze {{ color: #38bdf8; font-weight: bold; }}
                    .katex .cloze {{ color: #38bdf8 !important; font-weight: bold; background: rgba(56, 189, 248, 0.15); border-radius: 3px; padding: 0 3px; }}
                    img {{ max-width: 100%; height: auto; }}
                    {css}
                </style>
            </head>
            <body class="{body_class}">
                <div class="card">{html}</div>
                {get_mathjax_script()}
            </body>
            </html>
            """
    return final_html
