import re

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

    def cloze_replacer(match):
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


def get_mathjax_script() -> str:
    return r"""
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css" crossorigin="anonymous">
    <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js" crossorigin="anonymous"></script>
    <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js" crossorigin="anonymous"></script>
    <script>
        var katexInterval = setInterval(function() {
            if (window.renderMathInElement) {
                clearInterval(katexInterval);
                renderMathInElement(document.body, {
                    delimiters: [
                        {left: '$$', right: '$$', display: true},
                        {left: '\\[', right: '\\]', display: true},
                        {left: '\\(', right: '\\)', display: false}
                    ],
                    throwOnError: false
                });
            }
        }, 50);
    </script>
    """


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
    (cloze deletion), le mode nuit et l'injection de MathJax pour le rendu LaTeX.

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
    safe_fields = _sanitize_fields(fields_dict)

    html = raw_html
    html = _process_conditionals(html, safe_fields)
    html = _process_cloze_fields(html, safe_fields, template_index, is_recto)
    html = _process_standard_fields(html, safe_fields)

    if not is_recto:
        html = _process_front_side(html, front_html, safe_fields)

    # Conversion des balises math Anki historiques
    html = html.replace("[$]", "\\(").replace("[/$]", "\\)")
    html = html.replace("[$$]", "\\[").replace("[/$$]", "\\]")

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
