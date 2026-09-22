"""Tests unitaires du pipeline d'import web (WebImporter) — réseau 100 % mocké."""

from types import SimpleNamespace

import pytest
import requests

from ankiforge.services.parsing.web_importer import (
    DEFAULT_MAX_BYTES,
    WebImporter,
    WebImportError,
    WebImportRequest,
    WebImportResult,
    payload_to_result,
    result_to_payload,
)

pytestmark = pytest.mark.unit


STATIC_HTML = "<html><head><title>Mon Titre</title></head><body><article><p>Contenu de test.</p></article></body></html>"


class FakeResp:
    """Réponse HTTP simulée utilisée par requests.get."""

    def __init__(
        self,
        status_code: int = 200,
        html: str = STATIC_HTML,
        url: str = "https://blog.example.com/article-1",
        content_type: str = "text/html; charset=utf-8",
        body: bytes | None = None,
    ) -> None:
        self.status_code = status_code
        self.url = url
        self.headers = {"Content-Type": content_type}
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"
        self._html = html
        self._body = body if body is not None else html.encode("utf-8")

    @property
    def text(self) -> str:
        return self._html

    def iter_content(self, chunk_size: int = 65536):
        yield self._body

    def close(self) -> None:
        pass


def _fake_get_routing(*, responses: dict[str, FakeResp], default: FakeResp):
    def fake_get(url, headers=None, timeout=None, stream=False, allow_redirects=True):
        if url.startswith("https://cdn.example.com/"):
            return responses.get(url, default)
        if url in responses:
            return responses[url]
        return default

    return fake_get


@pytest.fixture
def importer(monkeypatch) -> WebImporter:
    """WebImporter isolé : requests.get + trafilatura.extract mockés."""

    def fake_extract(html, output_format="markdown", include_links=False, include_images=False, url=""):
        if "ARTICLE_MARKER" in html:
            return "# Article\n\nContenu principal extrait."
        if "PAGE2_MARKER" in html:
            return "# Page 2\n\nContenu de la page suivante."
        return ""

    monkeypatch.setattr("ankiforge.services.parsing.web_importer.trafilatura.extract", fake_extract)
    return WebImporter()


def _patch_get(monkeypatch, responses: dict[str, FakeResp], default: FakeResp | None = None) -> None:
    fake = _fake_get_routing(responses=responses, default=default or FakeResp())
    monkeypatch.setattr("ankiforge.services.parsing.web_importer.requests.get", fake)
    monkeypatch.setattr(requests.Session, "get", fake)


# ── Normalisation d'URL ──────────────────────────────────────────────────────


def test_normalize_url_prepends_https() -> None:
    assert WebImporter._normalize_url("example.com/article") == "https://example.com/article"


def test_normalize_url_keeps_explicit_http() -> None:
    assert WebImporter._normalize_url("http://example.com/x") == "http://example.com/x"


def test_normalize_url_rejects_other_schemes() -> None:
    with pytest.raises(WebImportError) as exc:
        WebImporter._normalize_url("ftp://example.com/x")
    assert exc.value.category == "invalid_url"


def test_normalize_url_rejects_missing_host() -> None:
    with pytest.raises(WebImportError):
        WebImporter._normalize_url("https:///path")


def test_normalize_url_rejects_empty() -> None:
    with pytest.raises(WebImportError) as exc:
        WebImporter._normalize_url("   ")
    assert exc.value.category == "invalid_url"


def test_detect_kind_routing() -> None:
    assert WebImporter._detect_kind("https://www.youtube.com/watch?v=abc") == "youtube"
    assert WebImporter._detect_kind("https://youtu.be/abc") == "youtube"
    assert WebImporter._detect_kind("https://fr.wikipedia.org/wiki/Oracle") == "wikipedia"
    assert WebImporter._detect_kind("https://blog.example.com/x") == "web"


# ── Cas d'erreur réseau / HTTP ───────────────────────────────────────────────


def test_analyze_url_timeout(importer, monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr("ankiforge.services.parsing.web_importer.requests.get", boom)
    with pytest.raises(WebImportError) as exc:
        importer.analyze_url(WebImportRequest(url="https://example.com/slow"))
    assert exc.value.category == "timeout"


def test_analyze_url_connection_error(importer, monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise requests.exceptions.ConnectionError()

    monkeypatch.setattr("ankiforge.services.parsing.web_importer.requests.get", boom)
    with pytest.raises(WebImportError) as exc:
        importer.analyze_url(WebImportRequest(url="https://example.com/dns"))
    assert exc.value.category == "network"


def test_analyze_url_403_is_anti_bot(importer, monkeypatch) -> None:
    _patch_get(monkeypatch, responses={"https://example.com/x": FakeResp(status_code=403)})
    with pytest.raises(WebImportError) as exc:
        importer.analyze_url(WebImportRequest(url="https://example.com/x"))
    assert exc.value.category == "anti_bot"
    assert exc.value.http_status == 403


def test_analyze_url_404_is_http(importer, monkeypatch) -> None:
    _patch_get(monkeypatch, responses={"https://example.com/x": FakeResp(status_code=404)})
    with pytest.raises(WebImportError) as exc:
        importer.analyze_url(WebImportRequest(url="https://example.com/x"))
    assert exc.value.category == "http"
    assert exc.value.http_status == 404


def test_analyze_url_500_generic_server_message(importer, monkeypatch) -> None:
    _patch_get(monkeypatch, responses={"https://example.com/x": FakeResp(status_code=502)})
    with pytest.raises(WebImportError) as exc:
        importer.analyze_url(WebImportRequest(url="https://example.com/x"))
    assert exc.value.category == "http"


def test_analyze_url_non_html_content_type_rejected(importer, monkeypatch) -> None:
    _patch_get(monkeypatch, responses={"https://example.com/doc.pdf": FakeResp(content_type="application/pdf")})
    with pytest.raises(WebImportError) as exc:
        importer.analyze_url(WebImportRequest(url="https://example.com/doc.pdf"))
    assert exc.value.category == "unsupported"


def test_analyze_url_page_too_large(importer, monkeypatch) -> None:
    big = FakeResp(body=b"x" * (DEFAULT_MAX_BYTES + 1))
    _patch_get(monkeypatch, responses={"https://example.com/big": big})
    with pytest.raises(WebImportError) as exc:
        importer.analyze_url(WebImportRequest(url="https://example.com/big"))
    assert exc.value.category == "size"


def test_analyze_url_render_js_flag_requires_webengine(importer) -> None:
    with pytest.raises(WebImportError) as exc:
        importer.analyze_url(WebImportRequest(url="https://example.com/spa", render_js=True))
    assert exc.value.category == "render_js_required"


# ── Cas de succès ────────────────────────────────────────────────────────────


def test_analyze_url_success(importer, monkeypatch) -> None:
    html = f"{STATIC_HTML.split('<body>')[0]}<body>ARTICLE_MARKER{STATIC_HTML.split('<body>')[1]}"
    _patch_get(monkeypatch, responses={"https://blog.example.com/article-1": FakeResp(html=html)})
    result = importer.analyze_url(WebImportRequest(url="https://blog.example.com/article-1"))
    assert result.ok
    assert "Contenu principal extrait." in result.content
    assert result.title == "Mon Titre"
    assert result.doc_type == "web"
    assert result.final_url == "https://blog.example.com/article-1"


def test_analyze_url_empty_html_after_fetch(importer, monkeypatch) -> None:
    _patch_get(monkeypatch, responses={"https://example.com/empty": FakeResp(html="<html></html>")}, default=FakeResp(html="<html></html>"))
    with pytest.raises(WebImportError) as exc:
        importer.analyze_url(WebImportRequest(url="https://example.com/empty"))
    assert exc.value.category == "empty"


def test_analyze_html_spa_detection_and_empty_dynamic(importer) -> None:
    spa_html = '<html><head><title>SPA</title></head><body><div id="app"></div></body></html>'
    with pytest.raises(WebImportError) as exc:
        importer.analyze_html(spa_html, WebImportRequest(url="https://example.com/spa"))
    assert exc.value.category == "empty_dynamic"


def test_analyze_html_mathml_converted_to_latex(importer) -> None:
    from ankiforge.services.parsing.web_importer import trafilatura

    trafilatura.extract = lambda *a, **k: "Formule : <annotation encoding='application/x-tex'>E = mc^2</annotation>"
    request = WebImportRequest(url="https://example.com/math")
    result = importer.analyze_html("<html><p>x</p></html>", request)
    assert "$$" in result.content
    assert "E = mc^2" in result.content


def test_analyze_html_download_images(importer, monkeypatch) -> None:
    seen = {"store_called": 0}

    class FakeMediaManager:
        def store_media_bytes(self, data: bytes, original_name: str, mime_type: str | None = None):
            seen["store_called"] += 1
            return SimpleNamespace(filename=f"web_image_{seen['store_called']}.png")

    from ankiforge.services.parsing.web_importer import trafilatura

    trafilatura.extract = lambda *a, **k: "![alt](https://cdn.example.com/img.jpg)"
    img = FakeResp(html="", content_type="image/jpeg", body=b"\x89PNG\r\n\x1a\n fake data")
    _patch_get(monkeypatch, responses={"https://cdn.example.com/img.jpg": img})

    importer.media_manager = FakeMediaManager()  # type: ignore[assignment]  # duck-typing : contrat MediaManager partiel volontaire
    request = WebImportRequest(url="https://example.com/article", download_images=True)
    result = importer.analyze_html("<html><p>x</p></html>", request, base_url="https://example.com/")
    assert 'src="web_image_1.png"' in result.content
    assert seen["store_called"] == 1


def test_analyze_url_pagination_merges_pages(importer, monkeypatch) -> None:
    page1 = '<html><head><link rel="next" href="https://blog.example.com/article-2"></head><body>ARTICLE_MARKER</body></html>'
    page2 = "<html><head><title>Page 2</title></head><body>PAGE2_MARKER</body></html>"
    _patch_get(
        monkeypatch,
        responses={
            "https://blog.example.com/article-1": FakeResp(html=page1),
            "https://blog.example.com/article-2": FakeResp(html=page2),
        },
    )
    request = WebImportRequest(url="https://blog.example.com/article-1", follow_pagination=True, max_pages=3)
    result = importer.analyze_url(request)
    assert result.flags.get("paginated")
    assert "[SPLIT]" in result.content
    assert "Contenu principal extrait." in result.content
    assert "Contenu de la page suivante." in result.content
    assert any("multi-pages" in w for w in result.warnings)


# ── Sérialisation ────────────────────────────────────────────────────────────


def test_result_to_payload_and_back() -> None:
    result = result_to_payload(
        type(
            "R",
            (),
            {
                "url": "https://example.com/x",
                "title": "T",
                "content": "C",
                "doc_type": "web",
                "final_url": "https://example.com/x",
                "http_status": 200,
                "content_type": "text/html",
                "warnings": ["w"],
                "flags": {"dynamic": True},
                "ok": True,
            },
        )(),
    )
    restored = payload_to_result(result)
    assert restored.url == "https://example.com/x"
    assert restored.content == "C"
    assert restored.flags["dynamic"]
    assert restored.warnings == ["w"]


def test_webimporterror_carries_category_and_status() -> None:
    err = WebImportError("msg", category="http", http_status=503)
    assert err.message == "msg"
    assert err.category == "http"
    assert err.http_status == 503


# ── Tableaux ignorés par trafilatura (cas Oracle-like) ───────────────────────


def test_analyze_html_recovers_tables_dropped_by_trafilatura(importer, monkeypatch) -> None:
    from ankiforge.services.parsing.web_importer import trafilatura

    trafilatura.extract = lambda *a, **k: "Java Software uses the following file suffixes:\n\nFrequently used file names include:"
    html = (
        "<html><body>"
        "<h4>2.1 File Suffixes</h4>"
        "<table><thead><tr><th>File Type</th><th>Suffix</th></tr></thead><tbody>"
        "<tr><td>Java source</td><td><code>.java</code></td></tr>"
        "<tr><td>Java bytecode</td><td><code>.class</code></td></tr>"
        "</tbody></table>"
        "</body></html>"
    )
    result = importer.analyze_html(html, WebImportRequest(url="https://example.com/oracle"))
    assert "| File Type | Suffix |" in result.content
    assert "| Java source | .java |" in result.content
    assert "| Java bytecode | .class |" in result.content


def test_analyze_html_inserts_tables_in_reading_order(importer, monkeypatch) -> None:
    from ankiforge.services.parsing.web_importer import trafilatura

    trafilatura.extract = lambda *a, **k: "This section lists commonly used file suffixes and names.\n\nJava Software uses the following file suffixes:\n\nFrequently used file names include:"
    html = (
        "<html><body>"
        "<h4>2.1 File Suffixes</h4>"
        "<p>This section lists commonly used file suffixes and names.</p>"
        "<p>Java Software uses the following file suffixes:</p>"
        "<table><thead><tr><th>File Type</th><th>Suffix</th></tr></thead><tbody>"
        "<tr><td>Java source</td><td>.java</td></tr>"
        "</tbody></table>"
        "<p>Frequently used file names include:</p>"
        "<table><thead><tr><th>File Name</th><th>Use</th></tr></thead><tbody>"
        "<tr><td>GNUmakefile</td><td>The preferred name for makefiles.</td></tr>"
        "</tbody></table>"
        "</body></html>"
    )
    result = importer.analyze_html(html, WebImportRequest(url="https://example.com"))

    assert (
        result.content.index("This section lists commonly used file suffixes and names.")
        < result.content.index("Java Software uses the following file suffixes:")
        < result.content.index("| File Type | Suffix |")
        < result.content.index("Frequently used file names include:")
        < result.content.index("| File Name | Use |")
    )


def test_analyze_html_does_not_duplicate_tables_already_extracted(importer, monkeypatch) -> None:
    from ankiforge.services.parsing.web_importer import trafilatura

    trafilatura.extract = lambda *a, **k: "| File Type | Suffix |\n| --- | --- |\n| Java source | .java |"
    html = "<html><body><table><thead><tr><th>File Type</th><th>Suffix</th></tr></thead><tbody><tr><td>Java source</td><td>.java</td></tr></tbody></table></body></html>"
    result = importer.analyze_html(html, WebImportRequest(url="https://example.com"))
    assert result.content.count("File Type") == 1
    assert result.content.count(".java") == 1


# ── Détection des murs (éviter les faux positifs du chrome des sites) ────────


def test_walls_no_false_positive_on_site_chrome() -> None:
    result = WebImportResult(url="https://example.com")
    html = (
        "<html><body>"
        "<header><button>Sign in</button><form><input name='q' placeholder='search'></form></header>"
        "<div>Le contenu de l'article.</div>"
        "<footer>Subscribe to our newsletter · Premium support</footer>"
        "<script>var u = 'login'; document.write('signin');</script>"
        "</body></html>"
    )
    WebImporter._detect_walls(html, result)
    assert not result.flags.get("paywall")
    assert not result.flags.get("login")
    assert not result.flags.get("cookie_wall")
    assert result.warnings == []


def test_walls_detects_password_field() -> None:
    result = WebImportResult(url="https://example.com")
    html = "<html><body><form><input type='password' name='p'></form></body></html>"
    WebImporter._detect_walls(html, result)
    assert result.flags.get("login")
    assert any("connexion" in w for w in result.warnings)


def test_walls_detects_strong_paywall_signal() -> None:
    result = WebImportResult(url="https://example.com")
    html = "<html><body><p>Continue reading: subscription required for this article.</p></body></html>"
    WebImporter._detect_walls(html, result)
    assert result.flags.get("paywall")


def test_walls_ignores_subscribe_in_footer() -> None:
    result = WebImportResult(url="https://example.com")
    html = "<html><body><footer>Subscribe to updates and premium support</footer></body></html>"
    WebImporter._detect_walls(html, result)
    assert not result.flags.get("paywall")
    assert not result.flags.get("login")
