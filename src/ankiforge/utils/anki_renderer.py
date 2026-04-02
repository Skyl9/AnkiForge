import re

AnkiFields = dict[str, str | list[str]]


def _is_empty(html_str: str) -> bool:
    """Vérifie si une chaîne HTML est vide de contenu texte."""
    clean_text = re.sub(r'<[^>]+>', '', str(html_str)).replace('&nbsp;', '').strip()
    return len(clean_text) == 0


def _sanitize_fields(fields_dict: AnkiFields) -> dict[str, str]:
    """Convertit tous les champs en chaînes de caractères (gère les listes)."""
    safe_fields = {}
    for k, v in fields_dict.items():
        if isinstance(v, list):
            safe_fields[k] = "<br>".join([str(item) for item in v])
        else:
            safe_fields[k] = str(v) if v is not None else ""
    return safe_fields


def _process_conditionals(html: str, safe_fields: dict[str, str]) -> str:
    """Gère les blocs conditionnels {{#Champ}} et {{^Champ}}."""
    for field, val in safe_fields.items():
        empty = _is_empty(val)

        # Bloc positif {{#Champ}}...{{/Champ}}
        pos_pattern = r"\{\{#" + re.escape(field) + r"\}\}(.*?)\{\{/" + re.escape(field) + r"\}\}"
        html = re.sub(pos_pattern, r"\1" if not empty else "", html, flags=re.DOTALL)

        # Bloc négatif {{^Champ}}...{{/Champ}}
        neg_pattern = r"\{\{\^" + re.escape(field) + r"\}\}(.*?)\{\{/" + re.escape(field) + r"\}\}"
        html = re.sub(neg_pattern, "" if not empty else r"\1", html, flags=re.DOTALL)

    return html


def _process_standard_fields(html: str, safe_fields: dict[str, str]) -> str:
    """Remplace les variables standards {{Champ}} et {{type:Champ}}."""
    for field, val in safe_fields.items():
        html = html.replace(f"{{{{{field}}}}}", val)
        html = html.replace(
            f"{{{{type:{field}}}}}",
            f"<br><input type='text' placeholder='{field}' disabled style='width:100%; padding:5px;'><br>"
        )
    return html


def _process_front_side(html: str, front_html: str, safe_fields: dict[str, str]) -> str:
    """Gère l'injection du verso avec {{FrontSide}}."""
    if "{{FrontSide}}" not in html:
        return html

    front_rendered = front_html
    # 🐛 CORRECTION DU BUG : On itère sur safe_fields et non fields_dict
    for field, val in safe_fields.items():
        front_rendered = front_rendered.replace(f"{{{{{field}}}}}", val)

    # Nettoyage grossier des tags non remplacés sur le FrontSide
    front_rendered = re.sub(r"\{\{[#^/][^}]+\}\}", "", front_rendered)
    return html.replace("{{FrontSide}}", front_rendered)


def _get_mathjax_script() -> str:
    """Retourne le script d'injection pour MathJax."""
    return r"""
    <script>
        window.MathJax = {
            tex: {
                inlineMath: [['\\(', '\\)']],
                displayMath: [['\\[', '\\]'], ['$$', '$$']],
                processEnvironments: true 
            },
            options: {
                skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code']
            },
            chtml: {
                scale: 1.0 
            }
        };
    </script>
    <script type="text/javascript" id="MathJax-script" async
            src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js">
    </script>
    """


def render_anki_card(
        raw_html: str,
        css: str,
        fields_dict: AnkiFields,
        is_recto: bool = True,
        front_html: str = ""
) -> str:
    """Moteur de rendu natif Anki (Conditionnels, Champs, MathJax)."""

    # 1. Sécurisation des données
    safe_fields = _sanitize_fields(fields_dict)

    # 2. Pipeline de rendu du HTML
    html = raw_html
    html = _process_conditionals(html, safe_fields)
    html = _process_standard_fields(html, safe_fields)

    # 3. Traitement spécifique du Verso
    if not is_recto:
        html = _process_front_side(html, front_html, safe_fields)

    # 4. Assemblage final avec le template de base
    final_html = f"""
    <html>
    <head>
        <meta charset="utf-8">
        {_get_mathjax_script()}
        <style>
            body {{ background-color: #ffffff; margin: 20px; }}
            {css}
        </style>
    </head>
    <body>
        <div class="card">
            {html}
        </div>
    </body>
    </html>
    """
    return final_html