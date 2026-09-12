"""Tests unitaires pour SafeWebEngineView, SafeWebEnginePage et AnkiForgeWebProfile."""

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from pytestqt.qtbot import QtBot

from ankiforge.ui.widgets.safe_web_preview import (
    AnkiForgeWebProfile,
    SafeWebEnginePage,
    SafeWebEngineView,
)


def test_ankiforge_web_profile_configuration(qtbot: QtBot) -> None:
    profile = AnkiForgeWebProfile.get_shared_profile()
    assert profile is not None
    assert profile.httpCacheType() == QWebEngineProfile.HttpCacheType.MemoryHttpCache
    assert profile.httpCacheMaximumSize() == 50 * 1024 * 1024
    assert profile.persistentCookiesPolicy() == QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies

    # Test purge cache
    AnkiForgeWebProfile.clear_memory_cache()


def test_safe_web_engine_page_security_and_actions(qtbot: QtBot) -> None:
    page = SafeWebEnginePage()

    # 1. Sécurité anti-XSS : alert, confirm, prompt ne doivent pas bloquer
    page.javaScriptAlert(QUrl("https://example.com"), "Test alert")
    assert page.javaScriptConfirm(QUrl("https://example.com"), "Test confirm") is False
    assert page.javaScriptPrompt(QUrl("https://example.com"), "Test prompt", "default") == (False, "")

    # 2. Interception du protocole applicatif ankiforge://
    actions_received: list[tuple[str, dict]] = []
    page.action_requested.connect(lambda action, params: actions_received.append((action, params)))

    test_url = QUrl("ankiforge://inject/A/Recto")
    handled = page.acceptNavigationRequest(test_url, QWebEnginePage.NavigationType.NavigationTypeLinkClicked, True)

    assert handled is False  # La navigation Chromium normale doit être annulée
    assert len(actions_received) == 1
    action, params = actions_received[0]
    assert action == "inject"
    assert params["source"] == "A"
    assert params["field_name"] == "Recto"


def test_safe_web_engine_view_lifecycle_and_dom_recycling(qtbot: QtBot) -> None:
    view = SafeWebEngineView()
    qtbot.addWidget(view)

    # Vérification que le profil est bien le profil partagé
    assert view.page().profile() == AnkiForgeWebProfile.get_shared_profile()

    # Test chargement HTML sécurisé
    view.setHtmlSafe("<h2>Formule mathématique</h2><p>$E = mc^2$</p>")
    assert view._load_count == 1

    # Test propagation du signal d'action
    actions_received: list[tuple[str, dict]] = []
    view.action_requested.connect(lambda action, params: actions_received.append((action, params)))
    view.page().action_requested.emit("inject", {"source": "B", "field_name": "Verso"})

    assert len(actions_received) == 1
    assert actions_received[0] == ("inject", {"source": "B", "field_name": "Verso"})

    # Test reset DOM sans recréer la page
    old_page = view.page()
    view.reset_dom()
    assert view.page() == old_page  # La page C++ sous-jacente reste inchangée

    # Test seuil de rafraîchissement
    view._load_count = view._refresh_threshold - 1
    view.setHtmlSafe("<p>Reload</p>")
    assert view._load_count == 0
    assert view.page() == old_page

    # Test cleanup
    view.cleanup()
