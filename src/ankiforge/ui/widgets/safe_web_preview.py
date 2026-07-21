from PySide6.QtCore import Qt, QUrl
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView


class SafeWebEngineView(QWebEngineView):
    """
    Un QWebEngineView optimisé pour éviter les fuites de mémoire (Memory Leaks)
    lors des appels répétés à setHtml() (notamment avec MathJax).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._load_count = 0
        self._refresh_threshold = 20
        self._setup_new_page()

    def _setup_new_page(self):
        """Crée une nouvelle page propre et détruit l'ancienne pour libérer la RAM."""
        new_page = QWebEnginePage(self)
        new_page.setBackgroundColor(Qt.GlobalColor.transparent)
        self.setPage(new_page)

        # On autorise le chargement des images locales (dossier media)
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

    def setHtmlSafe(self, html: str, base_url: QUrl | None = None):
        """Remplace setHtml pour inclure une gestion agressive de la mémoire."""
        if base_url is None:
            base_url = QUrl("")
        self._load_count += 1

        # Tous les X chargements, on recrée complètement la page pour vider le cache MathJax/Chromium
        if self._load_count >= self._refresh_threshold:
            self._setup_new_page()
            self._load_count = 0
        else:
            # Sinon, on vide juste l'historique pour ne pas empiler les pages invisibles
            self.history().clear()

        self.setHtml(html, base_url)

    def clear_memory(self):
        """À appeler quand on quitte la vue ou qu'on n'a plus besoin de l'aperçu."""
        self.setHtmlSafe("<html><body style='background: transparent;'></body></html>")
        self._setup_new_page()
