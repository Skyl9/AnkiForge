"""Widget d'édition des champs LaTeX (latex_pre, latex_post, latex_svg) pour un type de note."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankidraft.ui.components.code_editor.widgets.composite_editor import CodeEditorWithGutter
from ankidraft.ui.theme import DesignTokens
from ankidraft.utils.i18n import tr


class LatexModelEditorWidget(QWidget):
    """Widget composite pour éditer latex_pre, latex_post et latex_svg d'un NoteTypeModel."""

    textChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _apply_checkbox_style(self) -> None:
        """Applique le style thématisé à la case à cocher latex_svg."""
        self.chk_latex_svg.setStyleSheet(
            f"""
            QCheckBox {{
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 11px;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 3px;
                background-color: {DesignTokens.BG_INPUT};
            }}
            QCheckBox::indicator:checked {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """
        )

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # latex_pre (préambule)
        lbl_pre = QLabel(tr("Préambule LaTeX (latex_pre)"))
        lbl_pre.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        layout.addWidget(lbl_pre)

        self.latex_pre_editor = CodeEditorWithGutter(
            placeholder=tr("\\documentclass{article}\n\\usepackage{amsmath}\n\\begin{document}"),
            mode="html",
        )
        layout.addWidget(self.latex_pre_editor, 1)

        # latex_post (postambule)
        lbl_post = QLabel(tr("Postambule LaTeX (latex_post)"))
        lbl_post.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        layout.addWidget(lbl_post)

        self.latex_post_editor = CodeEditorWithGutter(
            placeholder=tr("\\end{document}"),
            mode="html",
        )
        layout.addWidget(self.latex_post_editor, 1)

        # latex_svg checkbox
        svg_row = QHBoxLayout()
        svg_row.setSpacing(8)
        self.chk_latex_svg = QCheckBox(tr("Activer le rendu vectoriel SVG (latex_svg)"))
        self.chk_latex_svg.setChecked(True)
        self._apply_checkbox_style()
        svg_row.addWidget(self.chk_latex_svg)
        svg_row.addStretch()
        layout.addLayout(svg_row)

    def _connect_signals(self) -> None:
        self.latex_pre_editor.textChanged.connect(self.textChanged.emit)
        self.latex_post_editor.textChanged.connect(self.textChanged.emit)
        self.chk_latex_svg.stateChanged.connect(self.textChanged.emit)

    def set_model_values(self, latex_pre: str, latex_post: str, latex_svg: bool) -> None:
        """Remplit les éditeurs avec les valeurs d'un NoteTypeModel."""
        self.latex_pre_editor.setPlainText(latex_pre or "")
        self.latex_post_editor.setPlainText(latex_post or "")
        self.chk_latex_svg.setChecked(bool(latex_svg))

    def get_model_values(self) -> tuple[str, str, bool]:
        """Retourne (latex_pre, latex_post, latex_svg) saisis dans le widget."""
        return (
            self.latex_pre_editor.toPlainText(),
            self.latex_post_editor.toPlainText(),
            self.chk_latex_svg.isChecked(),
        )

    def refresh_theme(self) -> None:
        """Rafraîchit les styles à chaud lors d'un changement de thème."""
        self.latex_pre_editor.refresh_theme()
        self.latex_post_editor.refresh_theme()
        self._apply_checkbox_style()
