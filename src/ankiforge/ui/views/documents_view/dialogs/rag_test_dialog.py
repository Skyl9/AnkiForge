import html
import re
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DocumentModel
from ankiforge.services.ai.rag_service import RAGService
from ankiforge.services.cards.media_manager import MediaManager
from ankiforge.ui.components import GlowLineEdit, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon
from ankiforge.utils.paths import resolve_media_path


def _highlight_snippet(content: str, query: str, limit: int = 240) -> str:
    """Return a short HTML-safe excerpt with query terms highlighted."""
    text = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL).strip()
    escaped = html.escape(text)
    terms = sorted({term for term in query.split() if len(term) > 1}, key=len, reverse=True)
    if len(text) > limit:
        match = re.search("|".join(re.escape(term) for term in terms), text, re.IGNORECASE) if terms else None
        start = max(0, (match.start() if match else 0) - limit // 3)
        text = f"{'...' if start else ''}{text[start : start + limit].strip()}{'...' if start + limit < len(text) else ''}"
        escaped = html.escape(text)
    if not terms:
        return escaped
    pattern = re.compile("|".join(re.escape(term) for term in terms), re.IGNORECASE)
    return pattern.sub(lambda match: f"<mark>{html.escape(match.group(0))}</mark>", escaped)


class _RAGResultWidget(QWidget):
    """Rich result presentation shared by text and visual retrieval results."""

    def __init__(self, result: dict, query: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        location = result.get("heading_path") or (f"Page {result.get('page_number')}" if result.get("page_number") else f"Section #{result.get('chunk_index', 0) + 1}")
        channel = result.get("channel", "hybrid")
        score = result.get("rrf_score", result.get("score", 0.0))
        header = QLabel(f"<b>📍 {html.escape(str(location))}</b> · Pertinence : {result.get('relevance_pct', 0)}% · Score : {float(score):.6f}")
        header.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")
        layout.addWidget(header)

        confidence = QProgressBar()
        confidence.setRange(0, 100)
        confidence.setValue(int(result.get("relevance_pct", 0)))
        confidence.setFormat("Confiance %p%")
        confidence.setFixedHeight(16)
        layout.addWidget(confidence)

        snippet = QTextBrowser()
        snippet.setOpenExternalLinks(False)
        snippet.setMaximumHeight(72)
        snippet.setHtml(_highlight_snippet(str(result.get("content", "")), query))
        snippet.setStyleSheet(f"QTextBrowser {{ background: transparent; border: 0; color: {DesignTokens.TEXT_PRIMARY}; }}")
        layout.addWidget(snippet)

        details = QLabel()
        if channel == "hybrid":
            details.setText(f"🧬 RRF {float(result.get('rrf_score', 0.0)):.6f} · FAISS #{result.get('dense_rank', '-')} · BM25 #{result.get('sparse_rank', '-')}")
        elif channel == "dense_only":
            details.setText(f"🌌 FAISS #{result.get('dense_rank', '-')} · score {float(result.get('dense_score', 0.0)):.4f}")
        elif channel == "sparse_only":
            details.setText(f"🔤 BM25 #{result.get('sparse_rank', '-')} · score {float(result.get('sparse_score', 0.0)):.4f}")
        else:
            details.setText("📄 BDD Directe")
        details.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 10px;")
        layout.addWidget(details)

        media_filename = result.get("media_filename")
        if media_filename:
            image_path = Path(MediaManager().media_dir) / str(media_filename)
            if not image_path.exists():
                image_path = resolve_media_path(str(media_filename))
            if image_path.exists():
                preview = QLabel()
                pixmap = QPixmap(str(image_path))
                if not pixmap.isNull():
                    preview.setPixmap(pixmap.scaled(96, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    preview.setToolTip("Image d'origine")
                    layout.addWidget(preview)
                open_button = SecondaryButton("Ouvrir l'image d'origine")
                open_button.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_PRIMARY))
                open_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(image_path))))
                layout.addWidget(open_button)


class RAGTestDialog(QDialog):
    """Permet de tester instantanément la recherche RAG Hybride (FAISS + BM25 avec RRF) sur le document."""

    def __init__(self, doc: DocumentModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.setWindowTitle(f"Recherche RAG Hybride — {doc.title}")
        self.resize(680, 540)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header_top = QHBoxLayout()
        ico = QLabel()
        ico.setPixmap(load_phosphor_icon("ph.database", color=DesignTokens.COLOR_GREEN).pixmap(20, 20))
        title_lbl = QLabel(f"Interroger l'index RAG : <b>{doc.title}</b>")
        title_lbl.setStyleSheet(f"font-size: 13px; color: {DesignTokens.TEXT_PRIMARY};")
        header_top.addWidget(ico)
        header_top.addWidget(title_lbl, 1)
        layout.addLayout(header_top)

        # Ligne de configuration de mode
        mode_row = QHBoxLayout()
        lbl_mode = QLabel("Canal de recherche :")
        lbl_mode.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: bold;")
        self.mode_cb = QComboBox()
        self.mode_cb.setFixedHeight(28)
        self.mode_cb.addItem("🧬 RAG Hybride (FAISS Dense + BM25 Sparse avec RRF)", "hybrid")
        self.mode_cb.addItem("🌌 Sémantique Dense Pure (FAISS L2)", "dense")
        self.mode_cb.addItem("🔤 Lexicale Exacte Pure (BM25 Okapi)", "sparse")
        self.mode_cb.setStyleSheet(f"""
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 2px 8px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 11px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 18px;
            }}
        """)
        mode_row.addWidget(lbl_mode)
        mode_row.addWidget(self.mode_cb, 1)
        layout.addLayout(mode_row)

        # Barre de recherche
        search_row = QHBoxLayout()
        self.search_input = GlowLineEdit()
        self.search_input.setPlaceholderText("Posez une question ou entrez des mots-clés techniques...")
        self.search_input.returnPressed.connect(self._on_search)

        btn_search = PrimaryButton("Rechercher")
        btn_search.setIcon(load_on_accent_icon("ph.magnifying-glass"))
        btn_search.clicked.connect(self._on_search)

        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(btn_search)
        layout.addLayout(search_row)

        self.results_list = QListWidget()
        self.results_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 6px;
            }}
            QListWidget::item {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                margin-bottom: 6px;
                padding: 8px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QListWidget::item:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        layout.addWidget(self.results_list, 1)

    def _on_search(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            return

        self.results_list.clear()
        try:
            mode = self.mode_cb.currentData() or "hybrid"
            rag = RAGService()
            results = rag.search(self.doc.id, query, top_k=4, mode=mode)
            if not results:
                self.results_list.addItem(QListWidgetItem("Aucun fragment pertinent trouvé pour cette requête."))
                return

            for r in results:
                loc = r.get("heading_path") or (f"Page {r.get('page_number')}" if r.get("page_number") else f"Section #{r.get('chunk_index', 0) + 1}")
                channel = r.get("channel", "hybrid")
                rel_pct = r.get("relevance_pct", 0)

                if channel == "hybrid":
                    badge_info = f"🧬 RRF: {r.get('rrf_score', 0.0):.5f} • FAISS: #{r.get('dense_rank', '-')} • BM25: #{r.get('sparse_rank', '-')}"
                elif channel == "dense_only":
                    badge_info = f"🌌 FAISS: #{r.get('dense_rank', '-')} (score: {r.get('dense_score', 0.0)})"
                elif channel == "sparse_only":
                    badge_info = f"🔤 BM25: #{r.get('sparse_rank', '-')} (score: {r.get('sparse_score', 0.0)})"
                else:
                    badge_info = "📄 BDD Directe"

                media_fn = r.get("media_filename")
                has_media = bool(media_fn)
                media_badge = " 🖼️ [Visuel]" if has_media else ""
                content_snippet = r.get("content", "")[:180] + "..." if len(r.get("content", "")) > 180 else r.get("content", "")
                item_txt = f"📍 {loc}{media_badge}  (Pertinence : {rel_pct}%)  [{badge_info}]\n{content_snippet}"
                item = QListWidgetItem(item_txt)

                item.setData(Qt.ItemDataRole.UserRole, r)
                self.results_list.addItem(item)
                self.results_list.setItemWidget(item, _RAGResultWidget(r, query))

        except Exception as e:
            self.results_list.addItem(QListWidgetItem(f"Erreur recherche RAG : {e}"))
