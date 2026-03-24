import re


def render_anki_card(raw_html: str, css: str, fields_dict: dict, is_recto: bool = True, front_html: str = "") -> str:
    """Moteur de rendu natif Anki (Conditionnels, Champs, MathJax)."""

    # 0. SÉCURITÉ : On s'assure que tout est bien au format "string" (Texte)
    safe_fields = {}
    for k, v in fields_dict.items():
        if isinstance(v, list):
            # Si l'IA a fait une liste, on la transforme en texte avec des retours à la ligne
            safe_fields[k] = "<br>".join([str(item) for item in v])
        else:
            safe_fields[k] = str(v) if v is not None else ""

    # 1. Fonction pour vérifier si un champ est VRAIMENT vide
    def is_empty(html_str):
        clean_text = re.sub(r'<[^>]+>', '', str(html_str)).replace('&nbsp;', '').strip()
        return len(clean_text) == 0

    html = raw_html

    # 2. Gestion des blocs conditionnels {{#Champ}} et {{^Champ}}
    for field, val in safe_fields.items():
        empty = is_empty(val)

        # Bloc positif {{#Champ}}...{{/Champ}} : S'affiche SI le champ N'EST PAS vide
        pos_pattern = r"\{\{#" + re.escape(field) + r"\}\}(.*?)\{\{/" + re.escape(field) + r"\}\}"
        html = re.sub(pos_pattern, r"\1" if not empty else "", html, flags=re.DOTALL)

        # Bloc négatif {{^Champ}}...{{/Champ}} : S'affiche SI le champ EST vide
        neg_pattern = r"\{\{\^" + re.escape(field) + r"\}\}(.*?)\{\{/" + re.escape(field) + r"\}\}"
        html = re.sub(neg_pattern, "" if not empty else r"\1", html, flags=re.DOTALL)

    # 3. Remplacement standard {{Champ}}
    for field, val in safe_fields.items():
        html = html.replace(f"{{{{{field}}}}}", val)
        # Support du {{type:Champ}}
        html = html.replace(f"{{{{type:{field}}}}}",
                            f"<br><input type='text' placeholder='{field}' disabled style='width:100%; padding:5px;'><br>")

    # 4. Remplacement du {{FrontSide}} sur le Verso
    if not is_recto and "{{FrontSide}}" in html:
        front_rendered = front_html
        for field, val in fields_dict.items():
            front_rendered = front_rendered.replace(f"{{{{{field}}}}}", val)
        # Nettoyage grossier des tags non remplacés sur le FrontSide
        front_rendered = re.sub(r"\{\{[#^/][^}]+\}\}", "", front_rendered)
        html = html.replace("{{FrontSide}}", front_rendered)

    # 5. Injection de MathJax pour LaTeX
    mathjax_script = r"""
    <script>
    MathJax = {
      tex: { inlineMath: [['\\(', '\\)']], displayMath: [['\\[', '\\]']] },
      svg: { fontCache: 'global' }
    };
    </script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    """

    # 6. Assemblage final
    final_html = f"""
    <html>
    <head>
        <meta charset="utf-8">
        {mathjax_script}
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
