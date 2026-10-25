"""Rendu et assainissement des modèles de cartes Anki (champs, médias, mathématiques KaTeX)."""

import html
import json
import logging
import re
from collections.abc import Mapping
from typing import Any

from ankiforge.utils.paths import get_resource_path

logger = logging.getLogger(__name__)

_SORT_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SORT_BLOCK_TAG_RE = re.compile(r"<(?:br|/p|/div|/li|tr|/tr)[^>]*>", re.IGNORECASE)
_SORT_IMG_RE = re.compile(r'<img[^>]+src=["\']?([^"\'>\s]+)["\']?[^>]*>', re.IGNORECASE)
_SORT_SOUND_RE = re.compile(r"\[sound:([^\]]+)\]", re.IGNORECASE)


def strip_html_for_sort(text: Any) -> str:
    """Épure le balisage HTML d'une chaîne pour indexation et tri déterministe (sfld Anki)."""
    if text is None:
        return ""
    s = str(text)
    s = _SORT_IMG_RE.sub(r"\1", s)
    s = _SORT_SOUND_RE.sub(r"\1", s)
    s = _SORT_BLOCK_TAG_RE.sub(" ", s)
    s = _SORT_HTML_TAG_RE.sub("", s)
    s = html.unescape(s)
    return " ".join(s.split()).strip()


def compute_sort_field(content: dict[str, Any] | list[Any] | str | None) -> str:
    """Calcule la valeur canonique du champ de tri d'une note (sort_field / sfld).

    Retourne la valeur épurée de HTML du premier champ non vide (ou le premier champ si tous sont vides),
    tronquée à 512 caractères.
    """
    if not content:
        return ""
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, (dict, list)):
                content = parsed
            else:
                return strip_html_for_sort(content)[:512]
        except Exception:
            return strip_html_for_sort(content)[:512]

    if isinstance(content, dict):
        vals = [str(v) for k, v in content.items() if not str(k).startswith("_")]
    elif isinstance(content, (list, tuple)):
        vals = [str(v) for v in content]
    else:
        vals = [str(content)]

    for val in vals:
        cleaned = strip_html_for_sort(val)
        if cleaned:
            return cleaned[:512]

    if vals:
        return strip_html_for_sort(vals[0])[:512]
    return ""


class AnkiFields(dict[str, Any]):
    """Dictionnaire typé représentant les champs d'une note Anki."""

    pass


def get_max_cloze_index(fields_dict: dict) -> int:
    """Identifie l'index de trou de complétion (cloze) le plus élevé dans une note.

    Parcourt tous les champs pour trouver des motifs de type {{c1::...}}, {{c2::...}}, etc.

    Args:
        fields_dict: Dictionnaire des champs de la note.

    Returns:
        L'index maximum trouvé (ex: 3 pour c3). Retourne 0 si aucun n'est trouvé.
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
    if not html_str:
        return True
    s = str(html_str).strip()
    if not s:
        return True
    lower_s = s.lower()
    if "<img" in lower_s or "<svg" in lower_s or "[sound:" in lower_s or "<audio" in lower_s or "<video" in lower_s:
        return False
    clean_text = re.sub(r"<[^>]+>", "", s).replace("&nbsp;", "").strip()
    return len(clean_text) == 0


def _sanitize_fields(fields_dict: Mapping[str, Any]) -> dict[str, str]:
    safe_fields = {}
    for k, v in fields_dict.items():
        if isinstance(v, list):
            safe_fields[k] = "<br>".join([str(item) for item in v])
        else:
            s = str(v) if v is not None else ""
            if "\n" in s and "<br" not in s and "<p" not in s and "<div" not in s:
                s = s.replace("\r\n", "\n").replace("\n", "<br>")
            safe_fields[k] = s
    return safe_fields


def _process_conditionals(html: str, safe_fields: Mapping[str, str]) -> str:
    """Évalue de façon récursive les blocs conditionnels Anki {{#Champ}} et {{^Champ}}.

    - Supporte les balises imbriquées à n'importe quelle profondeur via un remplacement
      itératif ciblant à chaque passe le bloc conditionnel le plus interne.
    - Évalue tout champ absent de `safe_fields` ou ne contenant que du texte vide
      comme 'falsy' (vide).
    - Nettoie les balises conditionnelles orphelines ou mal formées.
    """
    if "{{#" not in html and "{{^" not in html:
        return html

    # Motif ciblant le bloc conditionnel le plus interne (ne contenant aucun {{# ou {{^ ou {{/)
    # Group 1: opérateur ('#' ou '^')
    # Group 2: nom du champ
    # Group 3: contenu du bloc
    inner_pattern = re.compile(
        r"\{\{([#^])([^}#/]+)\}\}((?:(?!\{\{[#^/]).)*?)\{\{/\2\}\}",
        flags=re.DOTALL,
    )

    max_passes = 50
    passes = 0
    while passes < max_passes:
        passes += 1
        matched = False

        def _replace_block(m: re.Match[str]) -> str:
            nonlocal matched
            matched = True
            op = m.group(1)
            field_name = m.group(2).strip()
            body = m.group(3)

            field_val = safe_fields.get(field_name, "")
            empty = _is_empty(field_val)

            if op == "#":
                return body if not empty else ""
            else:  # op == "^"
                return "" if not empty else body

        new_html = inner_pattern.sub(_replace_block, html)
        if not matched or new_html == html:
            break
        html = new_html

    # Nettoyage de sécurité pour d'éventuelles balises de conditionnels orphelines
    html = re.sub(r"\{\{[#^/][^}]+\}\}", "", html)
    return html


def should_generate_card(template_qfmt: str, fields_dict: Mapping[str, Any]) -> bool:
    """Détermine si un gabarit de carte Recto (qfmt) engendre une carte physique selon la règle officielle Anki.

    Règle officielle Anki :
    Une carte n'est créée pour une note que si :
    1. Le gabarit Recto, après résolution des conditionnels ({{#...}}, {{^...}}) et
       substitution des champs ({{Champ}}), produit du texte visible non vide ou du média
       (images <img>, <svg>, sons [sound:...]).
    2. Un recto ne contenant que des espaces ou des balises HTML vides (ex: <br>, <div></div>)
       n'engendre AUCUNE carte.
    """
    if not template_qfmt:
        return False

    safe_fields = _sanitize_fields(fields_dict)

    # 1. Évaluation des conditionnels imbriqués
    rendered = _process_conditionals(template_qfmt, safe_fields)

    # 2. Substitution des champs standards
    rendered = _process_standard_fields(rendered, safe_fields, is_recto=True)

    # 3. Retrait des balises spéciales (FrontSide, Tags, Deck, etc.)
    rendered = re.sub(r"\{\{(FrontSide|Tags|Deck|Subdeck|Card|Type)\}\}", "", rendered)

    # 4. Nettoyage de balises non substituées résiduelles
    rendered = re.sub(r"\{\{[^}]+\}\}", "", rendered)

    # 5. Détection de non-vacuité via _is_empty
    return not _is_empty(rendered)


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


def _process_standard_fields(html: str, safe_fields: dict[str, str], is_recto: bool = True) -> str:
    for field in sorted(safe_fields.keys(), key=len, reverse=True):
        val = safe_fields[field]

        # 1. Filtre Anki standard {{text:Champ}} : dépouille toutes les balises HTML
        text_val = re.sub(r"<[^>]+>", "", val).strip()
        html = html.replace(f"{{{{text:{field}}}}}", text_val)

        # 2. Filtre Anki standard {{hint:Champ}} : indice dépliable <details>
        if val.strip():
            hint_html = (
                f"<details class='hint' style='margin: 4px 0;'>"
                f"<summary style='cursor: pointer; font-weight: 500;'>{field}</summary>"
                f"<div class='hint-content' style='margin-top: 4px; padding: 4px 8px; border-radius: 4px;'>{val}</div>"
                f"</details>"
            )
            html = html.replace(f"{{{{hint:{field}}}}}", hint_html)
        else:
            html = html.replace(f"{{{{hint:{field}}}}}", "")

        # 3. Filtre Anki {{type:Champ}} : zone de saisie au recto, validation avec classe typeAns au verso
        if is_recto:
            type_html = (
                f"<br><input type='text' class='type-input' placeholder='{field}' disabled "
                f"style='width:100%; max-width: 320px; padding: 6px 10px; margin: 4px 0; border: 1px solid #94a3b8; border-radius: 4px; font-family: monospace;'><br>"
            )
        else:
            type_html = f"<code class='typeAns'><span class='typeGood'>{val}</span></code>" if val.strip() else f"<code class='typeAns'><span class='typeMissed'>({field} vide)</span></code>"
        html = html.replace(f"{{{{type:{field}}}}}", type_html)

        # 4. Substitution standard du champ {{Champ}}
        html = html.replace(f"{{{{{field}}}}}", val)

    return html


def _process_front_side(html: str, front_html: str, safe_fields: dict[str, str]) -> str:
    if "{{FrontSide}}" not in html or not front_html:
        return html

    front_rendered = front_html
    # Si un document HTML complet a été transmis (ex: par preview_card_render), extraire le corps de la carte
    card_match = re.search(r'<div class="card">(.*)</div>(?:\s*<link|\s*<script|\s*</body>|\s*$)', front_rendered, flags=re.DOTALL)
    if card_match:
        front_rendered = card_match.group(1)

    # Selon la spécification Anki, {{FrontSide}} au verso doit masquer les champs de saisie {{type:...}}
    for field in sorted(safe_fields.keys(), key=len, reverse=True):
        front_rendered = re.sub(r"\{\{type:" + re.escape(field) + r"\}\}", "", front_rendered)

    # Si front_html était déjà pré-rendu en HTML, retirer les balises <input> générées pour type:
    front_rendered = re.sub(r"<br>\s*<input\b[^>]*class=['\"]type-input['\"][^>]*>\s*<br>", "", front_rendered, flags=re.IGNORECASE)
    front_rendered = re.sub(r"<input\b[^>]*class=['\"]type-input['\"][^>]*>", "", front_rendered, flags=re.IGNORECASE)
    front_rendered = re.sub(r"<input\b[^>]*placeholder=['\"][^'\"]*['\"][^>]*>", "", front_rendered, flags=re.IGNORECASE)

    # Substitution des champs, filtres text/hint et conditionnels restants si front_html était un template brut
    front_rendered = _process_conditionals(front_rendered, safe_fields)
    front_rendered = _process_standard_fields(front_rendered, safe_fields, is_recto=True)
    front_rendered = re.sub(r"\{\{[#^/][^}]+\}\}", "", front_rendered)

    return html.replace("{{FrontSide}}", front_rendered)


def _preprocess_math_blocks(html: str) -> str:
    """Normalise et prépare les blocs mathématiques pour KaTeX.

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
    """Génère le script et les feuilles de style KaTeX à injecter dans le HTML d'une carte.

    Returns:
        Balises HTML complètes, ou chaîne vide si le bundle KaTeX local est introuvable.
    """
    css_res = get_resource_path("resources", "katex", "katex.min.css")
    js_res = get_resource_path("resources", "katex", "katex.min.js")
    auto_render_res = get_resource_path("resources", "katex", "auto-render.min.js")

    if css_res.exists() and js_res.exists() and auto_render_res.exists():
        css_url = css_res.as_uri()
        js_url = js_res.as_uri()
        auto_render_url = auto_render_res.as_uri()
    else:
        # Pas de fallback CDN : le rendu mathématique est purement local (hors-ligne
        # et confidentiel). Si le bundle KaTeX manque, on renonce à la syntaxe KaTeX
        # mais le contenu reste lisible.
        logger.error("Bundle KaTeX local introuvable (css/js/auto-render) : rendu mathématique désactivé.")
        return ""

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
    """Résout et réécrit les balises de médias dans le HTML d'une carte Anki.

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
        if audio_name.lower().startswith(("preview", "sample", "test")):
            return (
                '<span class="anki-audio-container" style="display: inline-block; margin: 4px 0;">'
                '<audio controls preload="none" style="height: 30px; vertical-align: middle; max-width: 280px;"></audio>'
                "</span>"
            )
        return f'<span class="anki-audio-missing" style="opacity: 0.7; font-size: 11px;">🔊 {audio_name}</span>'

    html = re.sub(r"\[sound:([^\]]+)\]", _replace_sound, html, flags=re.IGNORECASE)

    return html


def render_anki_card(
    raw_html: str,
    css: str,
    fields_dict: Mapping[str, Any],
    is_recto: bool = True,
    front_html: str = "",
    is_dark_mode: bool = False,
    template_index: int = 0,
) -> str:
    """Simule le rendu HTML d'une carte Anki.

    Gère les remplacements de champs, les sections conditionnelles, les trous de complétion
    (cloze deletion), le mode nuit et l'injection de MathJax/KaTeX pour le rendu LaTeX.

    Args:
        raw_html: Le template HTML brut (Recto ou Verso).
        css: Les styles CSS du modèle de note.
        fields_dict: Les données de la note (champs -> contenu).
        is_recto: Si True, affiche le recto. Sinon le verso.
        front_html: Le contenu rendu du recto (nécessaire pour {{FrontSide}} au verso).
        is_dark_mode: Active les styles de mode nuit.
        template_index: L'index de la carte physique (pour les notes à plusieurs cartes).

    Returns:
        Le code HTML complet, prêt à être affiché dans un QWebEngineView.
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
    html = _process_standard_fields(html, safe_fields, is_recto=is_recto)

    if not is_recto:
        html = _process_front_side(html, front_html, safe_fields)

    # Pré-traitement et normalisation des blocs mathématiques KaTeX / LaTeX
    html = _preprocess_math_blocks(html)

    # Résolution des médias (images et balises audio [sound:...])
    html = _process_media_references(html)

    cleaned_css = css.replace("palette(text)", "inherit") if css else ""
    body_class = "nightMode" if is_dark_mode else ""
    final_html = f"""<!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ background-color: #f8fafc; color: #1e293b; margin: 0; padding: 15px; }}
                    body.nightMode {{ background-color: #0f172a; color: #e2e8f0; }}
                    .card {{
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                        font-size: 18px;
                        line-height: 1.5;
                        background-color: #ffffff;
                        color: #1e293b;
                        padding: 16px;
                        border-radius: 8px;
                        box-sizing: border-box;
                    }}
                    .nightMode .card {{ background-color: #1e293b; color: #e2e8f0; }}
                    ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
                    ::-webkit-scrollbar-track {{ background: transparent; }}
                    ::-webkit-scrollbar-thumb {{ background: #555; border-radius: 5px; }}
                    ::-webkit-scrollbar-thumb:hover {{ background: #777; }}
                    .cloze {{ color: #38bdf8; font-weight: bold; }}
                    .katex .cloze {{ color: #38bdf8 !important; font-weight: bold; background: rgba(56, 189, 248, 0.15); border-radius: 3px; padding: 0 3px; }}
                    .typeAns {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; padding: 2px 6px; border-radius: 4px; background: rgba(16, 185, 129, 0.12); }}
                    .typeGood {{ color: #16a34a; font-weight: bold; }}
                    .nightMode .typeGood {{ color: #4ade80; }}
                    .typeBad {{ color: #dc2626; text-decoration: line-through; }}
                    .nightMode .typeBad {{ color: #f87171; }}
                    .typeMissed {{ color: #9333ea; font-style: italic; }}
                    .nightMode .typeMissed {{ color: #c084fc; }}
                    details.hint summary {{ color: #0284c7; font-weight: 500; cursor: pointer; user-select: none; }}
                    .nightMode details.hint summary {{ color: #38bdf8; }}
                    img {{ max-width: 100%; height: auto; }}
                    {cleaned_css}
                </style>
            </head>
            <body class="{body_class}">
                <div class="card">{html}</div>
                {get_mathjax_script()}
            </body>
            </html>
            """
    return final_html


def render_card_text(
    template_html: str,
    fields_dict: Mapping[str, Any],
    template_index: int = 0,
    is_recto: bool = True,
    front_raw_html: str = "",
) -> str:
    """Rend le texte lisible et épuré d'une carte (recto ou verso) pour l'affichage en tableau avec préservation des médias."""
    if not template_html:
        return ""
    safe_fields = _sanitize_fields(fields_dict)

    # Repli intelligent des champs si Front/Back absents dans le dictionnaire
    if "Front" not in safe_fields and len(safe_fields) > 0:
        safe_fields["Front"] = list(safe_fields.values())[0]
    if "Back" not in safe_fields and len(safe_fields) > 1:
        safe_fields["Back"] = list(safe_fields.values())[1]

    html = template_html
    html = _process_conditionals(html, safe_fields)
    html = _process_cloze_fields(html, safe_fields, template_index, is_recto)
    html = _process_standard_fields(html, safe_fields)
    if not is_recto and front_raw_html:
        html = _process_front_side(html, front_raw_html, safe_fields)

    # Préserver les médias sous une forme textuelle descriptive avant suppression du HTML structurel
    html = re.sub(r'<img[^>]*src=["\']?([^"\'>\s]+)["\']?[^>]*>', r"🖼️ [\1]", html, flags=re.IGNORECASE)
    html = re.sub(r"<svg[^>]*>.*?</svg>", r"🔲 [Masque d'occlusion]", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"\[sound:([^\]]+)\]", r"🔊 [\1]", html, flags=re.IGNORECASE)

    clean = re.sub(r"<[^>]+>", "", html)
    return clean.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()
