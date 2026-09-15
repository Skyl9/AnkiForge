"""
Tests de sécurité anti-XSS pour KaTeXEditor et SafeWebEnginePage.
Vérifie la neutralisation des balises <script>, des gestionnaires d'événements inline,
et l'interception silencieuse des boîtes alert(), confirm() et prompt().
"""

from __future__ import annotations

import sys
from typing import Any

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QWidget

from ankiforge.ui.widgets.katex_editor import sanitize_user_markdown_html
from ankiforge.ui.widgets.safe_web_preview import SafeWebEnginePage, SafeWebEngineView

LINUX_QTWEBENGINE_UNSTABLE = pytest.mark.skipif(
    sys.platform.startswith("linux"),
    reason="QtWebEngine 6.11 segfaults during pytest-qt teardown on Linux CI",
)


def test_sanitize_user_markdown_html_script_tags() -> None:
    """Vérifie que <script>alert('coucou')</script> est transformé en bloc de code inoffensif."""
    raw_html = "<p>Exemple de test : <script>alert('coucou')</script></p>"
    sanitized = sanitize_user_markdown_html(raw_html)

    # Ne doit plus contenir de balise script exécutable
    assert "<script>" not in sanitized
    assert "</script>" not in sanitized
    assert "<script" not in sanitized

    # Doit être affiché sous forme de code échappé lisible pour l'étudiant
    assert "&lt;script&gt;alert(&#x27;coucou&#x27;)&lt;/script&gt;" in sanitized
    assert "xss-neutralized" in sanitized


def test_sanitize_user_markdown_html_inline_event_handlers() -> None:
    """Vérifie que les attributs onerror/onload/onclick sont neutralisés."""
    raw_html = '<img src="invalid.jpg" onerror="alert(\'coucou\')" onclick="evil()">'
    sanitized = sanitize_user_markdown_html(raw_html)

    assert " onerror=" not in sanitized
    assert " onclick=" not in sanitized
    assert "data-blocked-onerror=" in sanitized
    assert "data-blocked-onclick=" in sanitized


def test_sanitize_user_markdown_html_javascript_protocol() -> None:
    """Vérifie que les liens javascript:... sont désactivés."""
    raw_html = "<a href=\"javascript:alert('coucou')\">Cliquez ici</a>"
    sanitized = sanitize_user_markdown_html(raw_html)

    assert 'href="javascript:' not in sanitized
    assert 'href="#"' in sanitized


@LINUX_QTWEBENGINE_UNSTABLE
def test_safe_web_engine_page_dialog_interception(qtbot: Any) -> None:
    """Vérifie que SafeWebEnginePage bloque silencieusement alert(), confirm() et prompt()."""
    dummy = QWidget()
    qtbot.addWidget(dummy)
    page = SafeWebEnginePage(parent=dummy)
    origin = QUrl("https://localhost")

    # 1. alert() ne doit pas bloquer ni lever d'exception
    page.javaScriptAlert(origin, "coucou")

    # 2. confirm() renvoie False
    res_confirm = page.javaScriptConfirm(origin, "Voulez-vous continuer ?")
    assert res_confirm is False

    # 3. prompt() renvoie (False, "")
    res_prompt = page.javaScriptPrompt(origin, "Entrez votre mot de passe", "def")
    assert res_prompt == (False, "")


@LINUX_QTWEBENGINE_UNSTABLE
def test_safe_web_engine_view_uses_safe_page(qtbot: Any) -> None:
    """Vérifie que SafeWebEngineView instancie bien une SafeWebEnginePage."""
    view = SafeWebEngineView()
    qtbot.addWidget(view)

    assert isinstance(view.page(), SafeWebEnginePage)
    view.cleanup()
