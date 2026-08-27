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
        self._configure_page(self.page())

    def _configure_page(self, page: QWebEnginePage | None) -> None:
        if page is not None:
            page.setBackgroundColor(Qt.GlobalColor.transparent)
            self.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

    def _setup_new_page(self) -> None:
        """Crée une nouvelle page propre et détruit l'ancienne pour libérer la RAM."""
        old_page = self.page()
        new_page = QWebEnginePage(self)
        self._configure_page(new_page)
        self.setPage(new_page)

        if old_page is not None and old_page != new_page:
            try:
                old_page.deleteLater()
            except RuntimeError:
                pass  # Nosec B110: PySide6 setPage may already delete old C++ page

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

    def cleanup(self):
        """Arrête proprement les chargements WebEngine lors du démontage du composant."""
        try:
            self.stop()
        except Exception:
            pass  # nosec B110

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)
