"""Lecteur de documentation applicatif autonome pour AnkiForge (DocReaderDialog).

Permet de consulter les guides et documentations de l'application hors-ligne,
avec rendu natif des illustrations vectorielles SVG locales via QTextBrowser,
recherche textuelle incrémentale en surbrillance et zoom typographique.
Conforme à l'ADR 0038.
"""

from __future__ import annotations

import logging
from pathlib import Path

import markdown
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components import IconButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.paths import get_docs_path

logger = logging.getLogger(__name__)


class DocReaderDialog(QDialog):
    """Boîte de dialogue autonome pour la lecture de guides et documentations intégrées."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DocReaderDialog")
        self.setWindowTitle(self.tr("Documentation & Guides AnkiForge"))
        self.setMinimumSize(820, 560)
        self.resize(920, 680)
        self.setModal(False)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinMaxButtonsHint)

        self._current_zoom_level: int = 0
        self._current_search_query: str = ""
        self._match_count: int = 0
        self._base_dir: Path = get_docs_path()

        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 1. Header Bar ────────────────────────────────────────────────────
        self.header_bar = QWidget()
        self.header_bar.setObjectName("DocReaderHeaderBar")
        self.header_bar.setStyleSheet(f"""
            QWidget#DocReaderHeaderBar {{
                background-color: {DesignTokens.BG_PANEL};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.setSpacing(10)

        self.lbl_header_icon = QLabel()
        icon = load_phosphor_icon("ph.book-open", color=DesignTokens.ACCENT_PRIMARY)
        if not icon.isNull():
            self.lbl_header_icon.setPixmap(icon.pixmap(20, 20))
        header_layout.addWidget(self.lbl_header_icon)

        self.lbl_title = QLabel(self.tr("Guide Utilisateur"))
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 15px; font-weight: bold;")
        header_layout.addWidget(self.lbl_title)

        header_layout.addStretch()

        self.btn_close = IconButton("ph.x", tooltip=self.tr("Fermer la fenêtre (Échap)"), size=26)
        self.btn_close.setAutoDefault(False)
        self.btn_close.clicked.connect(self.close)
        header_layout.addWidget(self.btn_close)

        main_layout.addWidget(self.header_bar)

        # ── 2. Toolbar (Recherche & Zoom) ────────────────────────────────────
        self.toolbar = QWidget()
        self.toolbar.setObjectName("DocReaderToolbar")
        self.toolbar.setStyleSheet(f"""
            QWidget#DocReaderToolbar {{
                background-color: {DesignTokens.BG_MAIN};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        toolbar_layout = QHBoxLayout(self.toolbar)
        toolbar_layout.setContentsMargins(16, 6, 16, 6)
        toolbar_layout.setSpacing(8)

        # Champ de recherche
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.tr("Rechercher dans ce guide..."))
        self.search_input.setFixedWidth(240)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 8px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._find_next)
        toolbar_layout.addWidget(self.search_input)

        self.lbl_match_count = QLabel("")
        self.lbl_match_count.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        toolbar_layout.addWidget(self.lbl_match_count)

        self.btn_find_prev = IconButton("ph.caret-up", tooltip=self.tr("Occurrence précédente"), size=24)
        self.btn_find_prev.setAutoDefault(False)
        self.btn_find_prev.clicked.connect(self._find_prev)
        toolbar_layout.addWidget(self.btn_find_prev)

        self.btn_find_next = IconButton("ph.caret-down", tooltip=self.tr("Occurrence suivante (Entrée)"), size=24)
        self.btn_find_next.setAutoDefault(False)
        self.btn_find_next.clicked.connect(self._find_next)
        toolbar_layout.addWidget(self.btn_find_next)

        toolbar_layout.addStretch()

        # Contrôles de zoom typographique
        self.btn_zoom_out = IconButton("ph.magnifying-glass-minus", tooltip=self.tr("Réduire la taille du texte"), size=24)
        self.btn_zoom_out.setAutoDefault(False)
        self.btn_zoom_out.clicked.connect(self._zoom_out)
        toolbar_layout.addWidget(self.btn_zoom_out)

        self.btn_zoom_reset = IconButton("ph.arrows-counter-clockwise", tooltip=self.tr("Taille normale (100%)"), size=24)
        self.btn_zoom_reset.setAutoDefault(False)
        self.btn_zoom_reset.clicked.connect(self._zoom_reset)
        toolbar_layout.addWidget(self.btn_zoom_reset)

        self.btn_zoom_in = IconButton("ph.magnifying-glass-plus", tooltip=self.tr("Agrandir la taille du texte"), size=24)
        self.btn_zoom_in.setAutoDefault(False)
        self.btn_zoom_in.clicked.connect(self._zoom_in)
        toolbar_layout.addWidget(self.btn_zoom_in)

        main_layout.addWidget(self.toolbar)

        # ── 3. Corps Central (QTextBrowser) ──────────────────────────────────
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setFrameShape(QFrame.Shape.NoFrame)
        self.text_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
                border: none;
                padding: 24px 32px;
                selection-background-color: {DesignTokens.ACCENT_PRIMARY};
                selection-color: {DesignTokens.TEXT_ON_ACCENT};
            }}
        """)
        main_layout.addWidget(self.text_browser, 1)

    def load_markdown(self, markdown_text: str, base_dir: Path | None = None, title: str = "") -> None:
        """Parse le Markdown, résout les ressources locales et injecte le HTML stylisé."""
        self._base_dir = base_dir or get_docs_path()
        if title:
            self.lbl_title.setText(title)
            self.setWindowTitle(title)

        # Conversion Markdown vers HTML avec extensions de tables et blocs de code
        html_body = markdown.markdown(
            markdown_text,
            extensions=["tables", "fenced_code", "nl2br"],
        )

        full_html = self._wrap_in_document_template(html_body)

        # Positionnement de la base URL pour la résolution automatique des SVG et images relatives
        doc = self.text_browser.document()
        doc.setBaseUrl(QUrl.fromLocalFile(str(self._base_dir) + "/"))
        self.text_browser.setHtml(full_html)
        self.text_browser.moveCursor(QTextCursor.MoveOperation.Start)

    def _wrap_in_document_template(self, html_body: str) -> str:
        """Enveloppe le fragment HTML avec les styles CSS dérivés des DesignTokens."""
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-size: 13.5px;
        line-height: 1.6;
        color: {DesignTokens.TEXT_PRIMARY};
        background-color: {DesignTokens.BG_MAIN};
        margin: 0;
        padding: 0 10px 40px 10px;
    }}
    h1 {{
        color: {DesignTokens.TEXT_PRIMARY};
        font-size: 22px;
        font-weight: 700;
        margin-top: 10px;
        margin-bottom: 14px;
        border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
        padding-bottom: 8px;
    }}
    h2 {{
        color: {DesignTokens.TEXT_PRIMARY};
        font-size: 17px;
        font-weight: 700;
        margin-top: 24px;
        margin-bottom: 10px;
        border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
        padding-bottom: 6px;
    }}
    h3 {{
        color: {DesignTokens.TEXT_PRIMARY};
        font-size: 14.5px;
        font-weight: 600;
        margin-top: 18px;
        margin-bottom: 8px;
    }}
    p {{
        margin-top: 6px;
        margin-bottom: 12px;
    }}
    ul, ol {{
        margin-top: 4px;
        margin-bottom: 12px;
        padding-left: 24px;
    }}
    li {{
        margin-bottom: 4px;
    }}
    img {{
        max-width: 100%;
        height: auto;
        border-radius: {DesignTokens.RADIUS_MD}px;
        margin: 14px 0;
        border: 1px solid {DesignTokens.BORDER_COLOR};
        background-color: {DesignTokens.BG_PANEL};
    }}
    table {{
        border-collapse: collapse;
        width: 100%;
        margin: 16px 0;
        font-size: 12.5px;
    }}
    th, td {{
        border: 1px solid {DesignTokens.BORDER_COLOR};
        padding: 8px 12px;
        text-align: left;
    }}
    th {{
        background-color: {DesignTokens.BG_PANEL};
        color: {DesignTokens.TEXT_PRIMARY};
        font-weight: 600;
    }}
    tr:nth-child(even) {{
        background-color: {DesignTokens.BG_HOVER};
    }}
    blockquote {{
        border-left: 4px solid {DesignTokens.ACCENT_PRIMARY};
        background-color: {DesignTokens.BG_PANEL};
        margin: 14px 0;
        padding: 10px 14px;
        border-radius: {DesignTokens.RADIUS_SM}px;
    }}
    code {{
        background-color: {DesignTokens.BG_INPUT};
        color: {DesignTokens.ACCENT_PRIMARY};
        font-family: "{DesignTokens.FONT_CODE}", monospace;
        font-size: 12px;
        padding: 2px 5px;
        border-radius: 4px;
    }}
    kbd {{
        background-color: {DesignTokens.BG_HOVER};
        color: {DesignTokens.TEXT_PRIMARY};
        border: 1px solid {DesignTokens.BORDER_COLOR};
        border-radius: 4px;
        padding: 2px 6px;
        font-family: "{DesignTokens.FONT_CODE}", monospace;
        font-size: 11px;
    }}
    a {{
        color: {DesignTokens.ACCENT_PRIMARY};
        text-decoration: none;
    }}
    a:hover {{
        text-decoration: underline;
    }}
    hr {{
        border: none;
        border-top: 1px solid {DesignTokens.BORDER_COLOR};
        margin: 24px 0;
    }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""

    # ── Recherche textuelle ──────────────────────────────────────────────────

    def _on_search_text_changed(self, text: str) -> None:
        self._current_search_query = text.strip()
        if not self._current_search_query:
            self.lbl_match_count.setText("")
            self._match_count = 0
            return

        # Compte approximatif des occurrences
        raw_text = self.text_browser.toPlainText()
        self._match_count = raw_text.lower().count(self._current_search_query.lower())
        if self._match_count > 0:
            self.lbl_match_count.setText(tr("%1 résultat(s)", self._match_count))
            self._find_next()
        else:
            self.lbl_match_count.setText(self.tr("0 résultat"))

    def _find_next(self) -> None:
        if not self._current_search_query:
            return
        found = self.text_browser.find(self._current_search_query)
        if not found:
            # Rebouclage depuis le début
            self.text_browser.moveCursor(QTextCursor.MoveOperation.Start)
            self.text_browser.find(self._current_search_query)

    def _find_prev(self) -> None:
        if not self._current_search_query:
            return
        found = self.text_browser.find(self._current_search_query, QTextDocument.FindFlag.FindBackward)
        if not found:
            # Rebouclage depuis la fin
            self.text_browser.moveCursor(QTextCursor.MoveOperation.End)
            self.text_browser.find(self._current_search_query, QTextDocument.FindFlag.FindBackward)

    # ── Zoom typographique ───────────────────────────────────────────────────

    def _zoom_in(self) -> None:
        self.text_browser.zoomIn(1)
        self._current_zoom_level += 1

    def _zoom_out(self) -> None:
        self.text_browser.zoomOut(1)
        self._current_zoom_level -= 1

    def _zoom_reset(self) -> None:
        if self._current_zoom_level > 0:
            self.text_browser.zoomOut(self._current_zoom_level)
        elif self._current_zoom_level < 0:
            self.text_browser.zoomIn(-self._current_zoom_level)
        self._current_zoom_level = 0

    # ── Fabriques de commodité ───────────────────────────────────────────────

    @classmethod
    def open_guide(cls, guide_name: str = "cycle_de_vie_distribue.md", parent: QWidget | None = None) -> DocReaderDialog:
        """Instancie et charge un guide stocké dans docs/guides/."""
        dlg = cls(parent=parent)
        docs_path = get_docs_path()
        guide_file = docs_path / "guides" / guide_name
        if not guide_file.is_file():
            guide_file = docs_path / guide_name

        if guide_file.is_file():
            content = guide_file.read_text(encoding="utf-8", errors="replace")
            # Extraction du titre du premier H1
            title = guide_name.replace("_", " ").replace(".md", "").title()
            for line in content.splitlines():
                if line.startswith("# "):
                    title = line.replace("# ", "").strip()
                    break
            dlg.load_markdown(content, base_dir=guide_file.parent, title=title)
        else:
            logger.warning("Fichier de guide introuvable : %s", guide_file)
            dlg.load_markdown(
                tr("# Guide Introuvable\n\nLe document `%1` n'a pas pu être chargé.", guide_name),
                base_dir=docs_path,
                title=cls.tr("Erreur"),
            )
        return dlg
