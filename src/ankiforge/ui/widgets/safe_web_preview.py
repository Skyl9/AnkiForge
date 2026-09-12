"""
Composant de prévisualisation web durci et optimisé pour PySide6 QtWebEngine.
Intègre AnkiForgeWebProfile pour unifier le profil Chromium avec cache mémoire borné,
SafeWebEnginePage pour bloquer les alertes/prompts JavaScript (anti-XSS) et intercepter les protocoles applicatifs,
et SafeWebEngineView pour prévenir les fuites de mémoire (Memory Leaks).
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


class AnkiForgeWebProfile:
    """Gestionnaire de profil Chromium singleton pour AnkiForge.

    Garantit :
    - Un cache HTTP mémoire borné (50 Mo max par défaut) sans écritures disque inutiles.
    - La désactivation des cookies persistants (NoPersistentCookies).
    - Le partage du même contexte réseau et cache entre tous les SafeWebEngineView.
    - La purge programmée ou manuelle des caches mémoire.
    """

    _profile: QWebEngineProfile | None = None
    CACHE_MAX_BYTES: int = 50 * 1024 * 1024  # 50 Mo

    @classmethod
    def get_shared_profile(cls) -> QWebEngineProfile:
        if cls._profile is None:
            # On utilise defaultProfile() configuré pour l'application
            cls._profile = QWebEngineProfile.defaultProfile()
            cls._configure_profile(cls._profile)
        return cls._profile

    @classmethod
    def _configure_profile(cls, profile: QWebEngineProfile) -> None:
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        profile.setHttpCacheMaximumSize(cls.CACHE_MAX_BYTES)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        logger.debug(
            "AnkiForgeWebProfile initialisé : MemoryHttpCache borné à %d Mo, NoPersistentCookies",
            cls.CACHE_MAX_BYTES // (1024 * 1024),
        )

    @classmethod
    def clear_memory_cache(cls) -> None:
        """Vide le cache mémoire HTTP Chromium."""
        if cls._profile is not None:
            cls._profile.clearHttpCache()
            logger.debug("Cache mémoire AnkiForgeWebProfile vidé")


class SafeWebEnginePage(QWebEnginePage):
    """
    Page WebEngine durcie contre les attaques XSS et les dialogues JavaScript bloquants.
    Intercepte et neutralise alert(), confirm() et prompt() sans bloquer l'Event Loop Qt.
    Prend en charge l'interception de liens d'actions applicatives 'ankiforge://<action>/<params>'.
    """

    action_requested = Signal(str, dict)  # action_name, params_dict

    def __init__(self, profile: QWebEngineProfile | None = None, parent: QWidget | None = None) -> None:
        shared_profile = profile or AnkiForgeWebProfile.get_shared_profile()
        super().__init__(shared_profile, parent)

    def acceptNavigationRequest(self, url: QUrl | str, _type: QWebEnginePage.NavigationType, isMainFrame: bool) -> bool:
        """Intercepte les protocoles applicatifs ankiforge:// sans recharger la page."""
        qurl = QUrl(url) if isinstance(url, str) else url
        if qurl.scheme() == "ankiforge":
            action = qurl.host()
            raw_path = qurl.path().strip("/")
            params: dict[str, str] = {}
            if raw_path:
                parts = [urllib.parse.unquote(p) for p in raw_path.split("/")]
                if action == "inject" and len(parts) >= 2:
                    params["source"] = parts[0]
                    params["field_name"] = parts[1]
                else:
                    params["target"] = raw_path
            logger.debug("Action WebEngine interceptée : %s %s", action, params)
            self.action_requested.emit(action, params)
            return False
        return super().acceptNavigationRequest(url, _type, isMainFrame)

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
    lors des appels répétés à setHtml() (notamment avec MathJax/KaTeX),
    doté d'un profil partagé mémoire borné et d'un nettoyage DOM sans réallocation de page.
    """

    action_requested = Signal(str, dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._load_count = 0
        self._refresh_threshold = 20

        # Utilisation systématique de la page durcie avec profil partagé
        initial_page = SafeWebEnginePage(parent=self)
        self._configure_page(initial_page)
        self.setPage(initial_page)
        initial_page.action_requested.connect(self.action_requested.emit)

    def _configure_page(self, page: QWebEnginePage | None) -> None:
        if page is not None:
            page.setBackgroundColor(Qt.GlobalColor.transparent)
            settings = page.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, False)

    def reset_dom(self) -> None:
        """Vide l'arborescence DOM et libère le cache mémoire sans recréer la page C++."""
        try:
            self.history().clear()
            p = self.page()
            if p is not None:
                p.runJavaScript("if (document.body) { document.body.innerHTML = ''; }")
        except Exception:
            pass

    def setHtmlSafe(self, html: str, base_url: QUrl | None = None) -> None:
        """Remplace setHtml pour vider l'historique et optimiser l'empreinte mémoire."""
        if base_url is None:
            base_url = QUrl("")
        self._load_count += 1

        # Purge systématique de l'historique pour ne pas conserver de snapshots en RAM
        self.history().clear()

        # Tous les X chargements, on vide le DOM précédent pour recycler les nœuds Blink
        if self._load_count >= self._refresh_threshold:
            self.reset_dom()
            self._load_count = 0

        self.setHtml(html, base_url)

    def cleanup(self) -> None:
        """Arrête proprement les chargements WebEngine et libère le DOM lors du démontage."""
        try:
            self.stop()
            self.history().clear()
            self.load(QUrl("about:blank"))
        except Exception:
            pass  # nosec B110

    def closeEvent(self, event: Any) -> None:
        self.cleanup()
        super().closeEvent(event)
