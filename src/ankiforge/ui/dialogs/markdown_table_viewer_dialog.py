"""
Dialogue modal de visualisation et d'édition de tableaux Markdown pour le rôle IA d'un type de note.
"""

from __future__ import annotations

import markdown
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton, apply_compact_style
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class MarkdownTableViewerDialog(QDialog):
    """
    Dialogue modal permettant de visualiser le rendu visuel d'un tableau Markdown
    associé au rôle IA d'un type de note, et d'éditer son code source brut.
    """

    def __init__(self, markdown_text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Visualiseur & Éditeur de Tableau Markdown"))
        self.resize(880, 560)
        self.setMinimumSize(720, 420)
        self.setModal(True)

        self._raw_markdown = markdown_text
        self.result_markdown = markdown_text

        self._setup_ui()
        self._update_rendered_view()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(12)

        # En-tête
        header_frame = QFrame()
        header_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 8, 10, 8)
        header_layout.setSpacing(12)

        icon_label = QLabel()
        icon_label.setPixmap(load_phosphor_icon("ph.table", color=DesignTokens.ACCENT_PRIMARY).pixmap(26, 26))
        icon_label.setStyleSheet("border: none; background: transparent;")
        header_layout.addWidget(icon_label)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)

        title_lbl = QLabel(self.tr("Tableau Markdown du rôle IA"))
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: bold; border: none; background: transparent;")
        title_vbox.addWidget(title_lbl)

        sub_lbl = QLabel(self.tr("Consultez le tableau rendu ou modifiez directement la syntaxe Markdown transmise au moteur IA."))
        sub_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        title_vbox.addWidget(sub_lbl)

        header_layout.addLayout(title_vbox, 1)
        root_layout.addWidget(header_frame)

        # Onglets Rendu visuel / Éditeur brut
        self.tab_widget = QTabWidget()

        # Onglet 1 : Rendu visuel
        render_container = QWidget()
        render_layout = QVBoxLayout(render_container)
        render_layout.setContentsMargins(8, 8, 8, 8)

        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(False)
        self.text_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 10px;
            }}
        """)
        render_layout.addWidget(self.text_browser)
        self.tab_widget.addTab(render_container, self.tr("Rendu du tableau"))

        # Onglet 2 : Éditeur Markdown brut
        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(8, 8, 8, 8)

        self.raw_editor = QPlainTextEdit()
        mono_font = QFont("JetBrains Mono", 12)
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        self.raw_editor.setFont(mono_font)
        self.raw_editor.setPlainText(self._raw_markdown)
        self.raw_editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 10px;
                line-height: 1.4;
            }}
        """)
        self.raw_editor.textChanged.connect(self._on_text_changed)
        editor_layout.addWidget(self.raw_editor)
        self.tab_widget.addTab(editor_container, self.tr("Code Markdown brut"))

        root_layout.addWidget(self.tab_widget, 1)

        # Pied de page
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        bottom_layout.addStretch()

        btn_cancel = SecondaryButton(self.tr("Annuler"))
        apply_compact_style(btn_cancel, height=32)
        btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(btn_cancel)

        self.btn_apply = PrimaryButton(self.tr("Appliquer les modifications"))
        apply_compact_style(self.btn_apply, height=32)
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        bottom_layout.addWidget(self.btn_apply)

        root_layout.addLayout(bottom_layout)

    def _update_rendered_view(self) -> None:
        """Génère le HTML stylé à partir du Markdown brut et l'affiche dans le navigateur."""
        text = self.raw_editor.toPlainText().strip()
        if not text:
            html = f"<p style='color: {DesignTokens.TEXT_MUTED}; font-style: italic;'>{self.tr('Aucun contenu de tableau Markdown à afficher.')}</p>"
        else:
            rendered_table = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
            css = f"""
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                    background-color: transparent;
                    color: {DesignTokens.TEXT_PRIMARY};
                    margin: 8px;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 6px;
                    margin-bottom: 12px;
                    font-size: 13px;
                }}
                th {{
                    background-color: {DesignTokens.BG_PANEL};
                    color: {DesignTokens.TEXT_PRIMARY};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    padding: 8px 12px;
                    text-align: left;
                    font-weight: bold;
                }}
                td {{
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    padding: 8px 12px;
                    vertical-align: top;
                }}
                tr:nth-child(even) {{
                    background-color: {DesignTokens.BG_HOVER};
                }}
                code {{
                    background-color: {DesignTokens.BG_PANEL};
                    padding: 2px 5px;
                    border-radius: 4px;
                    font-family: monospace;
                    font-size: 11px;
                }}
            </style>
            """
            html = f"{css}<div>{rendered_table}</div>"

        self.text_browser.setHtml(html)

    def _on_text_changed(self) -> None:
        """Met à jour le rendu visuel lorsque le code Markdown est modifié."""
        self._update_rendered_view()

    def _on_apply_clicked(self) -> None:
        """Valide la saisie et ferme le dialogue."""
        self.result_markdown = self.raw_editor.toPlainText().strip()
        self.accept()
