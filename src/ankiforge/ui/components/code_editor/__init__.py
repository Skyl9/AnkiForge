"""
Package CodeEditor d'AnkiForge.
Re-exporte l'ensemble des linters, formatters, highlighters et widgets pour rétrocompatibilité 100%.
"""

from ankiforge.ui.components.code_editor.color_utils import (
    COLOR_PATTERN,
    extract_colors_from_text,
)
from ankiforge.ui.components.code_editor.formatters import (
    CSSFormatter,
    HTMLFormatter,
)
from ankiforge.ui.components.code_editor.highlighters import (
    CSSSyntaxHighlighter,
    HTMLSyntaxHighlighter,
)
from ankiforge.ui.components.code_editor.linters import (
    CSSLinter,
    HTMLLinter,
)
from ankiforge.ui.components.code_editor.models import LintIssue
from ankiforge.ui.components.code_editor.widgets import (
    CodeEditorWithGutter,
    LineNumberArea,
    LintStatusBar,
    NativeCodeEditor,
)

__all__ = [
    "LintIssue",
    "HTMLLinter",
    "CSSLinter",
    "HTMLFormatter",
    "CSSFormatter",
    "COLOR_PATTERN",
    "extract_colors_from_text",
    "HTMLSyntaxHighlighter",
    "CSSSyntaxHighlighter",
    "LineNumberArea",
    "NativeCodeEditor",
    "LintStatusBar",
    "CodeEditorWithGutter",
]
