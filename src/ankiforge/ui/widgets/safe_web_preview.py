"""
Composant de prévisualisation web durci et optimisé pour PySide6 QtWebEngine.
Intègre SafeWebEnginePage pour bloquer les alertes/prompts JavaScript (anti-XSS)
et SafeWebEngineView pour prévenir les fuites de mémoire (Memory Leaks).
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


class SafeWebEnginePage(QWebEnginePage):
    """
    Page WebEngine durcie contre les attaques XSS et les dialogues JavaScript bloquants.
    Intercepte et neutralise alert(), confirm() et prompt() sans bloquer l'Event Loop Qt.
    """

    def javaScriptAlert(self, securityOrigin: QUrl | str, msg: str) -> None:
        """Intercepte et bloque silencieusement les boîtes de dialogue alert()."""
        origin_str = securityOrigin.toString() if isinstance(securityOrigin, QUrl) else str(securityOrigin)
        logger.warning(
            "Boîte de dialogue JavaScript alert() interceptée et bloquée (origine: %s) : %s",
            origin_str,
            msg,
        )

    def javaScriptConfirm(self, securityOrigin: QUrl | str, msg: str) -> bool:
        """Intercepte et bloque les boîtes confirm() en renvoyant toujours False."""
        origin_str = securityOrigin.toString() if isinstance(securityOrigin, QUrl) else str(securityOrigin)
        logger.warning(
            "Boîte de dialogue JavaScript confirm() interceptée et bloquée (origine: %s) : %s",
            origin_str,
            msg,
        )
        return False

    def javaScriptPrompt(self, securityOrigin: QUrl | str, msg: str, defaultValue: str) -> tuple[bool, str]:
        """Intercepte et bloque les boîtes prompt() en renvoyant (False, '')."""
        origin_str = securityOrigin.toString() if isinstance(securityOrigin, QUrl) else str(securityOrigin)
        logger.warning(
            "Boîte de dialogue JavaScript prompt() interceptée et bloquée (origine: %s) : %s",
            origin_str,
            msg,
        )
        return (False, "")


class SafeWebEngineView(QWebEngineView):
    """
    Un QWebEngineView optimisé pour éviter les fuites de mémoire (Memory Leaks)
    lors des appels répétés à setHtml() (notamment avec MathJax/KaTeX)
    et protégé contre l'exécution de pop-ups intrusives.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._load_count = 0
        self._refresh_threshold = 20

        # Utilisation systématique de la page durcie
        initial_page = SafeWebEnginePage(self)
        self._configure_page(initial_page)
        self.setPage(initial_page)

    def _configure_page(self, page: QWebEnginePage | None) -> None:
        if page is not None:
            page.setBackgroundColor(Qt.GlobalColor.transparent)
            settings = page.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, False)

    def _setup_new_page(self) -> None:
        """Crée une nouvelle page propre et détruit l'ancienne pour libérer la RAM."""
        old_page = self.page()
        new_page = SafeWebEnginePage(self)
        self._configure_page(new_page)
        self.setPage(new_page)

        if old_page is not None and old_page != new_page:
            try:
                old_page.deleteLater()
            except RuntimeError:
                pass  # Nosec B110: PySide6 setPage may already delete old C++ page

    def setHtmlSafe(self, html: str, base_url: QUrl | None = None) -> None:
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

    def cleanup(self) -> None:
        """Arrête proprement les chargements WebEngine lors du démontage du composant."""
        try:
            self.stop()
        except Exception:
            pass  # nosec B110

    def closeEvent(self, event: Any) -> None:
        self.cleanup()
        super().closeEvent(event)
