"""Service d'import web fonctionnel pour AnkiForge.

Remplace l'extraction web minimale (trafilatura.fetch_url) par un pipeline
robuste qui prend en charge un large éventail de cas utilisateur :

- URLs invalides, protocoles non supportés, erreurs DNS/connexion/timeout.
- Erreurs HTTP (404, 403 anti-bot/Cloudflare, 5xx) traduites en messages clairs.
- Pages générées dynamiquement via JavaScript (SPA) — détection + repli rendu JS.
- Paywall, murs de connexion et cookies — heuristique + avertissement.
- Téléchargements non-HTML (PDF, image, JSON...) — signalés pour un import adapté.
- Limites de taille (octets / images), articles multi-pages (rel=next),
  MathML → LaTeX, téléchargement optionnel des images.
- YouTube et Wikipédia routés vers les parseurs dédiés existants.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
import trafilatura
from bs4 import BeautifulSoup

from ankiforge.services.cards.media_manager import MediaManager

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) AnkiForge/1.1"
DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 Mo
DEFAULT_MAX_IMAGES = 30
DEFAULT_MAX_IMAGES_BYTES = 5 * 1024 * 1024  # 5 Mo par image
DEFAULT_MAX_PAGES = 3

ProgressCallback = Callable[[str], None]

_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_DYNAMIC_HINTS_RE = re.compile(
    r'<div[^>]+id=["\'](?:app|root|__next|__nuxt|main-app|app-root)["\']'
    r"|data-reactroot|ng-app|vite|webpack|bundle\.js|_nuxt|__NEXT_DATA__|data-nuxt-route",
    re.IGNORECASE,
)
_PAYWALL_HINTS_RE = re.compile(
    r"\bpaywall\b|\bsubscription required\b|\bsubscriber-only\b|\bfor subscribers\b|\bmetered\b|\bpremium content\b|\b(?:article|content) behind\b",
    re.IGNORECASE,
)
_ROBOTS_NOINDEX_RE = re.compile(r"<meta[^>]+robots[^>]+noindex", re.IGNORECASE)
_COOKIE_WALL_RE = re.compile(r"onetrust|qc-cmp2|sp_message|cookieconsent", re.IGNORECASE)
_MATHML_ANNOTATION_RE = re.compile(
    r"<annotation\b[^>]*encoding=['\"]application/x-tex['\"][^>]*>(.*?)</annotation>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")

_STATUS_MESSAGES: dict[int, str] = {
    401: "Le site demande une authentification (HTTP 401).",
    402: "Paiement requis (HTTP 402) — il s'agit probablement d'un article payant.",
    403: "Le site a refusé l'accès (HTTP 403). Il est probablement protégé contre les robots (Cloudflare, connexion requise...).",
    404: "Page introuvable (HTTP 404) — l'URL est peut-être erronée ou l'article a été déplacé.",
    410: "Ce contenu a été supprimé (HTTP 410).",
    429: "Trop de requêtes (HTTP 429) — le site limite le débit. Réessayez dans quelques minutes.",
}

_CONTENT_TYPE_EXT: dict[str, str] = {
    "application/pdf": "PDF",
    "application/x-pdf": "PDF",
    "application/epub+zip": "EPUB",
    "application/epub": "EPUB",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word (.docx)",
    "application/msword": "Word (.doc)",
    "application/json": "JSON",
    "application/xml": "XML",
    "text/xml": "XML",
    "application/zip": "archive ZIP",
    "application/vnd.anki": "paquet Anki (.apkg)",
}


class WebImportError(Exception):
    """Erreur d'import web catégorisée pour un message utilisateur lisible."""

    def __init__(self, message: str, category: str = "general", http_status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.category = category
        self.http_status = http_status


@dataclass
class WebImportRequest:
    """Paramètres d'une importation de page web (statique de préférence)."""

    url: str
    render_js: bool = False
    download_images: bool = False
    follow_pagination: bool = False
    max_pages: int = DEFAULT_MAX_PAGES
    max_bytes: int = DEFAULT_MAX_BYTES
    max_images: int = DEFAULT_MAX_IMAGES
    timeout: float = DEFAULT_TIMEOUT


@dataclass
class WebImportResult:
    """Résultat d'analyse d'une URL (aucune écriture en base de données)."""

    url: str
    title: str = ""
    content: str = ""
    doc_type: str = "web"  # web, youtube, wikipedia
    final_url: str = ""
    http_status: int | None = None
    content_type: str = ""
    warnings: list[str] = field(default_factory=list)
    flags: dict[str, bool] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.content.strip())


@dataclass
class FetchResult:
    """Réponse HTTP téléchargée en amont de l'extraction du contenu."""

    html: str
    final_url: str
    http_status: int | None
    content_type: str
    headers: dict[str, str]


class WebImporter:
    """Pipeline d'import web : téléchargement, extraction, détection des cas limites."""

    def __init__(self, media_manager: MediaManager | None = None) -> None:
        self.media_manager = media_manager or MediaManager()

    # ── API publique ──────────────────────────────────────────────────────────

    def analyze_url(self, request: WebImportRequest, progress_callback: ProgressCallback | None = None) -> WebImportResult:
        """Analyse une URL : téléchargement statique + extraction du contenu principal."""
        url = self._normalize_url(request.url)
        kind = self._detect_kind(url)

        if kind == "youtube":
            return self._analyze_youtube(url, progress_callback)
        if kind == "wikipedia":
            return self._analyze_wikipedia(url, progress_callback)

        if request.render_js:
            raise WebImportError(
                "L'URL est configurée pour un rendu JavaScript : utilisez le rendu WebEngine (page dynamique/SPA) puis analyze_html sur le HTML rendu.",
                category="render_js_required",
            )

        if progress_callback:
            progress_callback("Téléchargement de la page web...")
        fetch = self._fetch_static(url, request)
        if progress_callback:
            progress_callback("Extraction du contenu principal...")
        result = self.analyze_html(
            fetch.html,
            request,
            base_url=fetch.final_url,
            http_status=fetch.http_status,
            content_type=fetch.content_type,
            doc_type="web",
            progress_callback=progress_callback,
        )

        if request.follow_pagination and result.ok:
            pagination = self._follow_pagination(result, fetch, request, progress_callback)
            if pagination is not None:
                result = pagination
        return result

    def analyze_html(
        self,
        html: str,
        request: WebImportRequest,
        base_url: str = "",
        http_status: int | None = None,
        content_type: str = "text/html",
        doc_type: str = "web",
        progress_callback: ProgressCallback | None = None,
    ) -> WebImportResult:
        """Extrait le contenu principal d'un HTML déjà téléchargé (repli JS compris)."""
        result = WebImportResult(
            url=request.url,
            final_url=base_url or request.url,
            http_status=http_status,
            content_type=content_type,
            doc_type=doc_type,
        )

        if html:
            result.flags["dynamic"] = bool(_DYNAMIC_HINTS_RE.search(html))
            result.title = self._extract_title(html, base_url or request.url)
            self._detect_walls(html, result)

        ctype = (content_type or "").lower()
        detected_label = self._classify_content_type(ctype)
        if detected_label:
            raise WebImportError(
                f"Cette URL pointe vers un {detected_label}, pas vers une page web. Importez-le via le bouton 'Importer' local.",
                category="unsupported",
                http_status=http_status,
            )

        if not html.strip():
            raise WebImportError("Page vide : aucun contenu HTML reçu.", category="empty", http_status=http_status)

        markdown = self._extract_markdown(html, base_url or request.url)
        if not markdown.strip():
            if result.flags.get("dynamic"):
                raise WebImportError(
                    "Cette page est générée dynamiquement via JavaScript (site SPA). Activez l'option 'Rendre avec JavaScript' pour tenter l'extraction du rendu final.",
                    category="empty_dynamic",
                    http_status=http_status,
                )
            raise WebImportError(
                "Aucun contenu textuel principal détecté (page vide, murs anti-robots ou contenu en image).",
                category="empty",
                http_status=http_status,
            )

        markdown = self._mathml_to_latex(markdown)
        if request.download_images:
            if progress_callback:
                progress_callback("Téléchargement des images de la page...")
            markdown = self._download_images(markdown, result.final_url or base_url or request.url, request)
        result.content = markdown
        return result

    # ── Normalisation & routage ───────────────────────────────────────────────

    @staticmethod
    def _normalize_url(raw: str) -> str:
        url = raw.strip()
        if not url:
            raise WebImportError("URL vide : saisissez l'adresse d'une page web.", category="invalid_url")
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", url):
            url = f"https://{url}"
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise WebImportError(f"Protocole '{parsed.scheme}' non supporté : utilisez http:// ou https://.", category="invalid_url")
        if not parsed.netloc:
            raise WebImportError("URL invalide : l'hôte (nom de domaine) est manquant.", category="invalid_url")
        return url

    @staticmethod
    def _detect_kind(url: str) -> str:
        host = urlparse(url).netloc.lower()
        if "youtu.be" in host or host.endswith("youtube.com"):
            return "youtube"
        if "wikipedia.org" in host and "/wiki/" in urlparse(url).path:
            return "wikipedia"
        return "web"

    def _analyze_youtube(self, url: str, progress_callback: ProgressCallback | None = None) -> WebImportResult:
        from ankiforge.services.parsing.youtube_parser import YouTubeParser

        if progress_callback:
            progress_callback("Récupération des sous-titres YouTube...")
        try:
            parser = YouTubeParser()
            content = parser.parse(url, ai_manager=None)
            if not content:
                raise WebImportError("Impossible de récupérer les sous-titres pour cette vidéo (sous-titres absents ou vidéo privée).", category="youtube")
            return WebImportResult(url=url, title=self._youtube_title(url, content), content=content, doc_type="youtube", final_url=url)
        except WebImportError:
            raise
        except Exception as e:
            logger.exception("Erreur lors de l'extraction YouTube de %s", url)
            raise WebImportError(f"Erreur d'extraction YouTube : {e}", category="youtube") from e

    @staticmethod
    def _youtube_title(url: str, content: str) -> str:
        first_line = content.strip().splitlines()[0] if content.strip() else ""
        return (first_line.strip("# ").strip() or url)[:120]

    def _analyze_wikipedia(self, url: str, progress_callback: ProgressCallback | None = None) -> WebImportResult:
        from ankiforge.services.parsing.document_parser import DocumentParser

        if progress_callback:
            progress_callback("Extraction de l'article Wikipédia (formules LaTeX préservées)...")
        try:
            content = DocumentParser._parse_wikipedia(url)
        except Exception as e:
            logger.exception("Erreur lors de l'extraction Wikipédia de %s", url)
            raise WebImportError(str(e), category="wikipedia") from e
        title = content.strip().splitlines()[0].lstrip("# ").strip() if content.strip() else ""
        title = title or url
        return WebImportResult(url=url, title=title[:120], content=content, doc_type="web", final_url=url)

    # ── Téléchargement statique ───────────────────────────────────────────────

    @staticmethod
    def _is_private_host(url: str) -> bool:
        """Refuse les hôtes de réseaux privés/internes — anti-SSRF.

        Bloque les IP littérales privées (RFC1918, loopback, link-local, CGNAT,
        multicast) et les hôtes DNS qui résolvent vers ces plages, afin qu'un
        import web ne puisse pas être détourné pour sonder l'environnement interne.
        """
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            return False
        try:
            ip = ipaddress.ip_address(host.split("%")[0])
        except ValueError:
            ip = None
        if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved):
            return True
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            return False
        for _family, _, _, _, sockaddr in infos:
            addr = str(sockaddr[0]).split("%")[0]
            try:
                resolved = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if resolved.is_private or resolved.is_loopback or resolved.is_link_local or resolved.is_multicast or resolved.is_reserved:
                return True
        return False

    def _fetch_static(self, url: str, request: WebImportRequest) -> FetchResult:
        headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "fr,en-US;q=0.9,en;q=0.8"}
        current_url = url
        resp: requests.Response | None = None
        for _redirect in range(5):
            if self._is_private_host(current_url):
                raise WebImportError("Adresse réseau privé (environnement interne) refusée pour l'import web.", category="network")
            try:
                resp = requests.get(current_url, headers=headers, timeout=request.timeout, stream=True, allow_redirects=False)
            except requests.exceptions.Timeout:
                raise WebImportError("Le site met trop de temps à répondre (délai dépassé). Réessayez ou vérifiez votre connexion.", category="timeout") from None
            except requests.exceptions.SSLError:
                raise WebImportError("Connexion sécurisée (TLS/SSL) impossible avec ce site.", category="network") from None
            except requests.exceptions.ConnectionError:
                raise WebImportError("Site injoignable : nom de domaine introuvable (DNS) ou connexion refusée.", category="network") from None
            except requests.exceptions.RequestException:
                raise WebImportError("Erreur réseau inattendue pendant le téléchargement.", category="network") from None

            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                resp.close()
                resp = None
                if not location:
                    raise WebImportError("Redirection sans destination (en-tête Location manquant).", category="network") from None
                current_url = urljoin(current_url, location)
                continue
            break
        else:
            raise WebImportError("Trop de redirections enchaînées : le site boucle probablement sur des liens.", category="network")

        if resp is None:
            raise WebImportError("Page vide : le serveur n'a renvoyé aucun contenu.", category="empty", http_status=None)

        status = resp.status_code
        if status in _STATUS_MESSAGES:
            resp.close()
            category = "anti_bot" if status == 403 else "http"
            raise WebImportError(_STATUS_MESSAGES[status], category=category, http_status=status)
        if status >= 500:
            resp.close()
            raise WebImportError(f"Le serveur rencontre actuellement un problème (HTTP {status}). Réessayez plus tard.", category="http", http_status=status)
        if status >= 400:
            resp.close()
            raise WebImportError(f"Erreur HTTP {status} en récupérant la page.", category="http", http_status=status)

        try:
            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_content(chunk_size=65536):
                chunks.append(chunk)
                total += len(chunk)
                if total > request.max_bytes:
                    resp.close()
                    raise WebImportError(f"Cette page est trop volumineuse (plus de {request.max_bytes // (1024 * 1024)} Mo).", category="size", http_status=status)
            raw = b"".join(chunks)
        except requests.exceptions.RequestException:
            raise WebImportError("Connexion interrompue pendant le téléchargement de la page.", category="network", http_status=status) from None

        if not raw:
            raise WebImportError("Page vide : le serveur n'a renvoyé aucun contenu.", category="empty", http_status=status)

        resp.encoding = resp.encoding or resp.apparent_encoding or "utf-8"
        html = raw.decode(resp.encoding or "utf-8", errors="replace")
        return FetchResult(
            html=html,
            final_url=resp.url,
            http_status=status,
            content_type=resp.headers.get("Content-Type", "text/html"),
            headers={str(k): str(v) for k, v in resp.headers.items()},
        )

    # ── Extraction du contenu ─────────────────────────────────────────────────

    @staticmethod
    def _classify_content_type(content_type: str) -> str | None:
        """Retourne un libellé humain si le Content-Type n'est pas une page web."""
        if not content_type:
            return None
        mime = content_type.split(";")[0].strip().lower()
        if mime.startswith("text/html"):
            return None
        if mime.startswith("text/"):
            return None
        if mime.startswith("image/"):
            return "document image"
        return _CONTENT_TYPE_EXT.get(mime)

    @staticmethod
    def _extract_markdown(html: str, base_url: str) -> str:
        if trafilatura is None:
            raise RuntimeError("Le module trafilatura n'est pas installé. Lancez 'uv add trafilatura'")
        try:
            extracted = trafilatura.extract(html, output_format="markdown", include_links=False, include_images=False, url=base_url)
        except Exception as e:
            logger.warning("Échec de trafilatura.extract : %s", e)
            extracted = None
        markdown = str(extracted or "")
        return WebImporter._merge_tables_into_markdown(markdown, html)

    @staticmethod
    def _merge_tables_into_markdown(markdown: str, html: str) -> str:
        """Réinsère les <table> à la position lue (après le bloc qui les précède).

        trafilatura ignore parfois les tableaux : on les convertit en tables
        Markdown et on les insère dans l'ordre de lecture, après le paragraphe
        ou le titre précédent. Une table déjà présente dans le Markdown n'est
        pas dupliquée.
        """
        soup = BeautifulSoup(html, "html.parser")
        for table in soup.find_all("table"):
            block = WebImporter._table_to_markdown(table)
            if not block:
                continue
            first_cell = WebImporter._first_table_cell(block)
            if first_cell and first_cell in markdown:
                continue
            anchor = table.find_previous(["p", "li", "h1", "h2", "h3", "h4", "h5", "h6"])
            anchor_text = anchor.get_text(" ", strip=True) if anchor else ""
            markdown = WebImporter._insert_table(markdown, block, anchor_text)
        return markdown

    @staticmethod
    def _insert_table(markdown: str, block: str, anchor: str) -> str:
        """Insère une table après le paragraphe qui lui correspond (dans l'ordre de lecture)."""
        target = WebImporter._normalized(anchor)
        if target:
            paragraphs = markdown.split("\n\n")
            for i, paragraph in enumerate(paragraphs):
                normalized = WebImporter._normalized(paragraph)
                if normalized == target or normalized.startswith(target):
                    paragraphs.insert(i + 1, block)
                    return "\n\n".join(paragraphs)
        return f"{markdown}\n\n{block}" if markdown.strip() else block

    @staticmethod
    def _normalized(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _table_to_markdown(table: Any) -> str:
        """Convertit un élément <table> de BeautifulSoup en table Markdown."""
        rows: list[list[str]] = []
        for row in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True).replace("|", "\\|") for cell in row.find_all(["th", "td"])]
            if any(cells):
                rows.append(cells)
        if not rows:
            return ""
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        header = rows[0]
        lines = ["| " + " | ".join(header) + " |"]
        lines.append("| " + " | ".join("---" for _ in header) + " |")
        lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
        return "\n".join(lines)

    @staticmethod
    def _first_table_cell(block: str) -> str:
        """Première cellule d'une table Markdown (utilisée pour détecter les doublons)."""
        if not block:
            return ""
        first = block.splitlines()[0].strip()
        return first.lstrip("|").strip().split("|")[0].strip()

    @staticmethod
    def _extract_title(html: str, url: str) -> str:
        try:
            soup = BeautifulSoup(html, "html.parser")
            og_title = soup.find("meta", attrs={"property": "og:title"})
            if og_title and og_title.get("content"):
                return str(og_title["content"]).strip()[:120]
            title_tag = soup.find("title")
            if title_tag and title_tag.text.strip():
                return title_tag.text.strip()[:120]
        except Exception as err:
            logger.debug("Extraction du titre web ignorée : %s", err)
        parsed = urlparse(url)
        last = parsed.path.strip("/").split("/")[-1] if parsed.path.strip("/") else ""
        return (last or parsed.netloc)[:120]

    @staticmethod
    def _detect_walls(html: str, result: WebImportResult) -> None:
        soup: BeautifulSoup | None = None
        try:
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "noscript", "template"]):
                tag.decompose()
            visible = " " + soup.get_text(" ", strip=True).lower() + " "
        except Exception:
            visible = html

        if _ROBOTS_NOINDEX_RE.search(html):
            result.flags["paywall"] = True
            result.warnings.append("La page interdit son indexation (meta robots noindex).")
        elif _PAYWALL_HINTS_RE.search(visible):
            result.flags["paywall"] = True
            result.warnings.append("Cette page semble être derrière un paywall : le contenu extrait peut être partiel.")

        if soup is not None and soup.find("input", attrs={"type": "password"}) is not None:
            result.flags["login"] = True
            result.warnings.append("Un formulaire de connexion a été détecté : le contenu peut être restreint.")

        if _COOKIE_WALL_RE.search(html):
            result.flags["cookie_wall"] = True
            result.warnings.append("Un bandeau de consentement (cookie wall) a été détecté.")

    @staticmethod
    def _mathml_to_latex(markdown: str) -> str:
        def repl(match: re.Match) -> str:
            code = _HTML_TAG_RE.sub("", match.group(1)).strip()
            return f"\n\n $${code}$$ \n\n" if code else ""

        return _MATHML_ANNOTATION_RE.sub(repl, markdown)

    def _download_images(self, markdown: str, base_url: str, request: WebImportRequest) -> str:
        downloaded = 0

        def repl(match: re.Match) -> str:
            nonlocal downloaded
            if downloaded >= request.max_images:
                return match.group(0)
            alt, src = match.group(1), match.group(2)
            if src.startswith("data:"):
                return match.group(0)
            absolute = src if re.match(r"^https?://", src) else urljoin(base_url, src)
            if self._is_private_host(absolute):
                return match.group(0)
            content_type = ""
            data: bytes = b""
            image_timeout: float = min(request.timeout, 10.0)
            try:
                resp = requests.get(absolute, headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=image_timeout, stream=True)
                content_type = resp.headers.get("Content-Type", "") or ""
                if resp.status_code != 200 or "image/" not in content_type.lower():
                    resp.close()
                    return match.group(0)
                for chunk in resp.iter_content(chunk_size=65536):
                    data += chunk
                    if len(data) > DEFAULT_MAX_IMAGES_BYTES:
                        resp.close()
                        return match.group(0)
                resp.close()
            except requests.exceptions.RequestException:
                return match.group(0)
            if not data:
                return match.group(0)
            suffix = self._image_suffix(content_type, absolute)
            media = self.media_manager.store_media_bytes(data, f"web_image_{downloaded}{suffix}", content_type)
            if not media or not media.filename:
                return match.group(0)
            downloaded += 1
            return f'<img src="{media.filename}" alt="{alt}">'

        return _MD_IMAGE_RE.sub(repl, markdown)

    @staticmethod
    def _image_suffix(content_type: str, url: str) -> str:
        mappings = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp", "image/svg+xml": ".svg", "image/avif": ".avif"}
        mime = (content_type or "").split(";")[0].strip().lower()
        if mime in mappings:
            return mappings[mime]
        suffix = re.search(r"\.(jpe?g|png|gif|webp|svg|avif)(?:\?|$)", url, re.IGNORECASE)
        return suffix.group(1).lower() if suffix else ".png"

    # ── Articles multi-pages ──────────────────────────────────────────────────

    def _follow_pagination(
        self,
        result: WebImportResult,
        fetch: FetchResult,
        request: WebImportRequest,
        progress_callback: ProgressCallback | None = None,
    ) -> WebImportResult | None:
        visited: set[str] = {fetch.final_url}
        pages: list[str] = [result.content]
        current_url = fetch.final_url
        current_html = fetch.html
        for _ in range(request.max_pages):
            next_url = self._find_next_url(current_html, current_url)
            if not next_url or next_url in visited:
                break
            visited.add(next_url)
            try:
                next_fetch = self._fetch_static(next_url, request)
            except WebImportError as e:
                if progress_callback:
                    progress_callback(f"Pagination stoppée : {e.message}")
                break
            if progress_callback:
                progress_callback(f"Fusion de la page suivante : {next_url}")
            next_result = self.analyze_html(
                next_fetch.html,
                request,
                base_url=next_fetch.final_url,
                http_status=next_fetch.http_status,
                content_type=next_fetch.content_type,
                doc_type="web",
            )
            if not next_result.ok:
                break
            pages.append(next_result.content)
            current_html = next_fetch.html
            current_url = next_fetch.final_url

        if len(pages) == 1:
            return None
        result.content = "\n\n[SPLIT]\n\n".join(pages)
        if progress_callback:
            progress_callback(f"Article assemblé : {len(pages)} pages fusionnées.")
        result.flags["paginated"] = True
        result.warnings.append(f"Article multi-pages : {len(pages)} pages fusionnées.")
        return result

    @staticmethod
    def _find_next_url(html: str, base_url: str) -> str | None:
        try:
            soup = BeautifulSoup(html, "html.parser")
            link = soup.find("link", attrs={"rel": lambda v: bool(v) and "next" in str(v).lower().split()})
            if link and link.get("href"):
                return urljoin(base_url, str(link["href"]))
            anchor = soup.find("a", attrs={"rel": lambda v: bool(v) and "next" in str(v).lower().split()})
            if anchor and anchor.get("href"):
                return urljoin(base_url, str(anchor["href"]))
            for a in soup.find_all("a"):
                if not a.get("href"):
                    continue
                text = a.get_text(" ", strip=True).lower()
                cls = str(a.get("class", "")).lower()
                if text in ("suivant", "next", "page suivant", "→", "suivante") or "next" in cls:
                    href = str(a["href"])
                    if href != "#" and "page" in href.lower():
                        return urljoin(base_url, href)
        except Exception:
            return None
        return None


def result_to_payload(result: WebImportResult) -> dict[str, Any]:
    """Sérialise un WebImportResult pour le passage entre threads/workers Qt."""
    return {
        "url": result.url,
        "title": result.title,
        "content": result.content,
        "doc_type": result.doc_type,
        "final_url": result.final_url,
        "http_status": result.http_status,
        "content_type": result.content_type,
        "warnings": list(result.warnings),
        "flags": dict(result.flags),
        "ok": result.ok,
    }


def payload_to_result(payload: dict[str, Any]) -> WebImportResult:
    """Reconstruit un WebImportResult depuis un payload Qt (objet signal)."""
    return WebImportResult(
        url=payload["url"],
        title=payload.get("title", ""),
        content=payload.get("content", ""),
        doc_type=payload.get("doc_type", "web"),
        final_url=payload.get("final_url", ""),
        http_status=payload.get("http_status"),
        content_type=payload.get("content_type", ""),
        warnings=list(payload.get("warnings", [])),
        flags=dict(payload.get("flags", {})),
    )
