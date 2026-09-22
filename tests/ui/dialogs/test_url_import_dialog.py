"""Tests du dialogue d'import web (UrlImportDialog) — réseau et WebEngine mockés.

Les workers réels sont exercés (QThread) mais le réseau est simulé via
requests.get / trafilatura.extract mockés, et le rendu JS via
web_js_renderer.render_page_to_html mocké.
"""

import pytest
import requests

from ankiforge.database.models import DocumentModel
from ankiforge.ui.dialogs.url_import_dialog import UrlImportDialog

pytestmark = pytest.mark.ui


STATIC_HTML_OK = "<html><head><title>Article Rendu</title></head><body>ARTICLE_MARKER</body></html>"
SPA_HTML = '<html><head><title>SPA</title></head><body><div id="app"></div></body></html>'
RENDERED_HTML = "<html><head><title>SPA Rendue</title></head><body>RENDERED_MARKER</body></html>"


class FakeResp:
    def __init__(self, html: str | None = None, content_type: str = "text/html; charset=utf-8") -> None:
        self.status_code = 200
        self.url = "https://blog.example.com/article-1"
        self.headers = {"Content-Type": content_type}
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"
        self._html = html or STATIC_HTML_OK

    @property
    def text(self) -> str:
        return self._html

    def iter_content(self, chunk_size: int = 65536):
        yield self._html.encode("utf-8")

    def close(self) -> None:
        pass


def _patch_transport(monkeypatch, html_by_url: dict[str, str] | None = None) -> None:
    """Mocke le réseau : requests.get + trafilatura.extract consommés par le worker."""

    def fake_get(url, headers=None, timeout=None, stream=False, allow_redirects=True):
        return FakeResp(html=(html_by_url or {}).get(url, STATIC_HTML_OK))

    def fake_extract(html, output_format="markdown", include_links=False, include_images=False, url=""):
        if "ARTICLE_MARKER" in html:
            return "# Article rendu\n\nContenu principal."
        if "RENDERED_MARKER" in html:
            return "# Rendu JS\n\nContenu dynamique extrait."
        return ""

    monkeypatch.setattr("ankiforge.services.parsing.web_importer.requests.get", fake_get)
    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr("ankiforge.services.parsing.web_importer.trafilatura.extract", fake_extract)


def _run_analysis(qtbot, dialog: UrlImportDialog) -> None:
    dialog._on_analyze()
    qtbot.waitUntil(lambda: dialog._worker is None, timeout=8000)


def test_dialog_invalid_and_pagination_option(qtbot, monkeypatch) -> None:
    _patch_transport(monkeypatch)
    dialog = UrlImportDialog()
    qtbot.addWidget(dialog)

    assert not dialog.spin_max_pages.isEnabled()
    dialog.chk_pagination.setChecked(True)
    assert dialog.spin_max_pages.isEnabled()

    dialog.url_editor.setPlainText("https://blog.example.com/article-1\nftp://example.com/x")
    _run_analysis(qtbot, dialog)

    assert dialog.table.rowCount() == 2
    assert dialog.table.item(0, 2).text().startswith("Prêt à importer")
    assert "URL invalide" in dialog.table.item(1, 2).text()


def test_dialog_analyze_then_import_emits_signal(qtbot, monkeypatch) -> None:
    _patch_transport(monkeypatch)
    dialog = UrlImportDialog()
    qtbot.addWidget(dialog)
    emitted = []
    dialog.import_completed.connect(emitted.append)

    dialog.url_editor.setPlainText("https://blog.example.com/article-1")
    _run_analysis(qtbot, dialog)

    assert dialog.table.item(0, 2).text().startswith("Prêt à importer")
    assert dialog.btn_import.isEnabled()

    dialog.btn_import.click()
    qtbot.waitUntil(lambda: dialog._rows[0].get("saved_doc_id") is not None, timeout=5000)

    assert emitted and emitted[0]
    assert dialog.btn_cards.isEnabled()
    doc = DocumentModel.get_by_id(dialog._rows[0]["saved_doc_id"])
    assert doc.file_type == "web"
    assert doc.source_url == "https://blog.example.com/article-1"
    assert doc.content


def test_dialog_dedup_detects_existing_and_updates(qtbot, monkeypatch) -> None:
    _patch_transport(monkeypatch)
    dialog = UrlImportDialog()
    qtbot.addWidget(dialog)

    dialog.url_editor.setPlainText("https://blog.example.com/article-1")
    _run_analysis(qtbot, dialog)
    dialog.btn_import.click()
    qtbot.waitUntil(lambda: dialog._rows[0].get("saved_doc_id") is not None, timeout=5000)
    first_id = dialog._rows[0]["saved_doc_id"]

    monkeypatch.setattr(
        "ankiforge.ui.dialogs.url_import_dialog.QMessageBox.question",
        lambda *a, **k: 0x00004000,  # Yes
    )

    dialog.url_editor.setPlainText("https://blog.example.com/article-1")
    _run_analysis(qtbot, dialog)
    assert dialog._rows[0].get("existing_doc_id") == first_id

    dialog.btn_import.click()
    qtbot.waitUntil(lambda: dialog._rows[0].get("saved_doc_id") is not None, timeout=5000)
    doc = DocumentModel.get_by_id(first_id)
    assert "Contenu principal." in doc.content
    assert DocumentModel.select().count() == 1


def test_dialog_js_retry_for_spa(qtbot, monkeypatch) -> None:
    _patch_transport(monkeypatch, html_by_url={"https://blog.example.com/article-1": SPA_HTML})

    def fake_render(url, timeout_ms=20000):
        return RENDERED_HTML, "https://blog.example.com/article-1"

    monkeypatch.setattr("ankiforge.services.parsing.web_js_renderer.render_page_to_html", fake_render)

    dialog = UrlImportDialog()
    qtbot.addWidget(dialog)
    dialog.chk_js.setChecked(True)

    dialog.url_editor.setPlainText("https://blog.example.com/article-1")
    _run_analysis(qtbot, dialog)

    qtbot.waitUntil(lambda: dialog._rows[0].get("status") == "ok", timeout=8000)
    assert "Contenu dynamique extrait." in dialog._rows[0]["result"].content


def test_dialog_missing_webengine_keeps_error_state(qtbot, monkeypatch) -> None:
    _patch_transport(monkeypatch, html_by_url={"https://blog.example.com/article-1": SPA_HTML})
    dialog = UrlImportDialog()
    qtbot.addWidget(dialog)
    dialog.chk_js.setChecked(False)

    dialog.url_editor.setPlainText("https://blog.example.com/article-1")
    _run_analysis(qtbot, dialog)

    assert dialog._rows[0].get("status") == "error"
    assert "dynamique" in dialog.table.item(0, 2).text().lower()
    hint_row = dialog.table.item(0, 3)
    assert "rendu js" in hint_row.text().lower()


def test_dialog_create_cards_emits_request(qtbot, monkeypatch) -> None:
    _patch_transport(monkeypatch)
    dialog = UrlImportDialog()
    qtbot.addWidget(dialog)
    requested = []
    dialog.cards_requested.connect(requested.append)

    dialog.url_editor.setPlainText("https://blog.example.com/article-1")
    _run_analysis(qtbot, dialog)
    dialog.btn_import.click()
    qtbot.waitUntil(lambda: dialog._rows[0].get("saved_doc_id") is not None, timeout=5000)

    dialog.btn_cards.click()
    assert len(requested) == 1
    assert requested[0] == dialog._rows[0]["saved_doc_id"]


def test_dialog_preview_updates_on_selection(qtbot, monkeypatch) -> None:
    _patch_transport(monkeypatch)
    dialog = UrlImportDialog()
    qtbot.addWidget(dialog)

    dialog.url_editor.setPlainText("https://blog.example.com/article-1\nhttps://blog.example.com/article-2")
    _run_analysis(qtbot, dialog)

    dialog.table.selectRow(1)
    assert dialog.txt_title.text() == "Article Rendu"
    assert "Contenu principal." in dialog.preview_edit.toPlainText()


def test_dialog_cleanup_cancels_running_worker(qtbot, monkeypatch) -> None:
    _patch_transport(monkeypatch)
    dialog = UrlImportDialog()
    qtbot.addWidget(dialog)
    dialog.url_editor.setPlainText("https://blog.example.com/article-1")
    dialog._on_analyze()
    assert dialog._worker is not None
    dialog._cancel_running_worker()
    dialog._worker.wait(2000)
    dialog.close()
    assert dialog._worker is None or not dialog._worker.isRunning()
