"""Rendu JavaScript de pages web via QtWebEngine (repli pour les sites SPA).

Ce module ne doit être appelé QUE sur le thread principal Qt : Chromium/WebEngine
requiert la boucle d'événements GUI. Il est utilisé par le dialogue d'import web
lorsque l'extraction statique a échoué sur une page générée dynamiquement
(en JavaScript) ou lorsque l'utilisateur coche explicitement « Rendre avec JS ».

Le rendu utilise un profil mémoire partagé (AnkiForgeWebProfile) sans cookies
persistants, un délai borné et un cap de taille pour éviter les pages monstrueuses.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DEFAULT_RENDER_TIMEOUT_MS = 20000
DEFAULT_TO_HTML_TIMEOUT_MS = 5000
MAX_RENDER_BYTES = 30 * 1024 * 1024  # 30 Mo de HTML rendu : au-delà, on tronque


class JsRenderError(Exception):
    """Échec du rendu JavaScript (timeout, page vide, erreur du moteur)."""


def render_page_to_html(url: str, timeout_ms: int = DEFAULT_RENDER_TIMEOUT_MS) -> tuple[str, str]:
    """Rend une page JavaScript et retourne (html, final_url).

    Raises:
        JsRenderError: si le rendu échoue, expire ou ne produit aucun HTML.
    """
    from PySide6.QtCore import QEventLoop, QTimer, QUrl
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView

    from ankiforge.ui.widgets.safe_web_preview import AnkiForgeWebProfile

    profile = AnkiForgeWebProfile.configure_profile()
    if profile is not None:
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)

    view = QWebEngineView()
    view.setVisible(False)
    page: QWebEnginePage = QWebEnginePage(profile, view) if profile is not None else QWebEnginePage(view)
    view.setPage(page)

    html_holder: dict[str, str] = {"html": ""}
    current_url: dict[str, str] = {"url": url}
    load_loop: QEventLoop = QEventLoop()
    html_loop: QEventLoop = QEventLoop()
    timer: QTimer | None = None
    html_timer: QTimer | None = None

    def _on_load_finished(_ok: bool) -> None:
        load_loop.quit()

    def _on_url_changed(qurl: QUrl) -> None:
        current_url["url"] = qurl.toString()

    def _on_html(html_text: str) -> None:
        html_holder["html"] = html_text
        html_loop.quit()

    try:
        page.loadFinished.connect(_on_load_finished)
        page.urlChanged.connect(_on_url_changed)

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(load_loop.quit)
        timer.start(timeout_ms)

        page.load(QUrl(url))
        load_loop.exec()
        timer.stop()

        if not page.url().isEmpty():
            current_url["url"] = page.url().toString()

        html_timer = QTimer()
        html_timer.setSingleShot(True)
        html_timer.timeout.connect(html_loop.quit)
        html_timer.start(DEFAULT_TO_HTML_TIMEOUT_MS)

        page.toHtml(_on_html)
        html_loop.exec()
        html_timer.stop()
    finally:
        if timer is not None:
            timer.stop()
        if html_timer is not None:
            html_timer.stop()
        try:
            view.stop()
        except Exception as err:
            logger.debug("Arrêt de la vue web ignoré : %s", err)
        try:
            view.close()
        except Exception as err:
            logger.debug("Fermeture de la vue web ignorée : %s", err)
        try:
            view.deleteLater()
        except Exception as err:
            logger.debug("Suppression de la vue web ignorée : %s", err)

    final_url = current_url["url"]
    html = html_holder["html"]
    if not html or not html.strip():
        raise JsRenderError("Le rendu JavaScript n'a produit aucun contenu (page bloquée ou encore en chargement).")
    if len(html.encode("utf-8", errors="replace")) > MAX_RENDER_BYTES:
        html = html[: MAX_RENDER_BYTES // 4]
        logger.warning("HTML rendu tronqué pour %s (cap taille atteint)", url)
    return html, final_url
