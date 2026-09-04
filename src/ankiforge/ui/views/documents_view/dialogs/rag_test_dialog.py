from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DocumentModel
from ankiforge.services.ai.rag_service import RAGService
from ankiforge.ui.components import GlowLineEdit, PrimaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


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
        btn_search.setIcon(load_phosphor_icon("ph.magnifying-glass", color="white"))
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

                if has_media and media_fn:
                    from pathlib import Path

                    from PySide6.QtGui import QIcon, QPixmap

                    from ankiforge.services.cards.media_manager import MediaManager

                    img_path = Path(MediaManager().media_dir) / media_fn
                    if img_path.exists():
                        pix = QPixmap(str(img_path))
                        if not pix.isNull():
                            item.setIcon(
                                QIcon(
                                    pix.scaled(
                                        36,
                                        36,
                                        Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation,
                                    )
                                )
                            )

                item.setData(Qt.ItemDataRole.UserRole, r)
                self.results_list.addItem(item)

        except Exception as e:
            self.results_list.addItem(QListWidgetItem(f"Erreur recherche RAG : {e}"))
