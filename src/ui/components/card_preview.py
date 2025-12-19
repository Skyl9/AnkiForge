# src/ui/components/card_preview.py
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl

class CardPreview(QWebEngineView):
    def __init__(self):
        super().__init__()
        # HTML de base avec CDN MathJax pour le rendu
        self.html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
            <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; text-align: center; }
                .card { border: 1px solid #ddd; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                .label { font-size: 0.8em; color: #666; text-transform: uppercase; margin-bottom: 5px; }
                hr { margin: 20px 0; border: 0; border-top: 1px solid #eee; }
            </style>
        </head>
        <body>
            <div class="card">
                <div class="label">Recto</div>
                <div>{{ front }}</div>
            </div>
            <br>
            <div class="card">
                <div class="label">Verso</div>
                <div>{{ back }}</div>
            </div>
        </body>
        </html>
        """
        self.setHtml("<h3>En attente de contenu...</h3>")

    def update_content(self, front: str, back: str):
        # Injection du contenu dans le template
        # Note: Dans une vraie appli, utilisez jinja2 ici aussi
        html = self.html_template.replace("{{ front }}", front).replace("{{ back }}", back)
        self.setHtml(html)