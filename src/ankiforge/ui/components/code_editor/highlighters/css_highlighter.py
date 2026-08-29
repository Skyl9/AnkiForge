from typing import Any, List
from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
)

from ankiforge.ui.theme import DesignTokens


class CSSSyntaxHighlighter(QSyntaxHighlighter):
    """Coloration syntaxique temps réel pour feuilles de style CSS."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.rules: List[tuple[QRegularExpression, QTextCharFormat]] = []
        self.comment_format = QTextCharFormat()
        self.comment_start_expression = QRegularExpression(r"/\*")
        self.comment_end_expression = QRegularExpression(r"\*/")
        self.update_formats()

    def update_formats(self) -> None:
        self.rules.clear()

        # Sélecteurs / Classes
        tag_fmt = QTextCharFormat()
        tag_fmt.setForeground(QColor(DesignTokens.SYNTAX_TAG))
        tag_fmt.setFontWeight(QFont.Weight.Bold)

        # Propriétés CSS & Variables
        prop_fmt = QTextCharFormat()
        prop_fmt.setForeground(QColor(DesignTokens.SYNTAX_ATTR))

        # Chaînes
        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor(DesignTokens.SYNTAX_STRING))

        # Mots-clés @media, !important, pseudo-classes, fonctions
        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor(DesignTokens.SYNTAX_KEYWORD))
        kw_fmt.setFontWeight(QFont.Weight.Bold)

        # Nombres, unités, couleurs hex
        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor(DesignTokens.SYNTAX_NUMBER))

        # Variables / IDs
        var_fmt = QTextCharFormat()
        var_fmt.setForeground(QColor(DesignTokens.SYNTAX_VARIABLE))

        # Commentaires
        self.comment_format.setForeground(QColor(DesignTokens.SYNTAX_COMMENT))
        self.comment_format.setFontItalic(True)

        # 1. Propriétés & Variables CSS avant ':'
        self.rules.append((QRegularExpression(r"\b(--[a-zA-Z0-9_\-]+|[a-zA-Z\-]+)(?=\s*:)"), prop_fmt))
        # 2. Chaînes
        self.rules.append((QRegularExpression(r'"[^"\\]*(\\.[^"\\]*)*"'), str_fmt))
        self.rules.append((QRegularExpression(r"'[^'\\]*(\\.[^'\\]*)*'"), str_fmt))
        # 3. Nombres et unités (px, em, rem, %, vh, vw, s, ms, deg, fr, ch, dvh, dvw)
        self.rules.append((QRegularExpression(r"\b[0-9]+(\.[0-9]+)?(px|em|rem|%|vh|vw|s|ms|deg|fr|ch|dvh|dvw)?\b"), num_fmt))
        # 4. Couleurs Hex
        self.rules.append((QRegularExpression(r"#[0-9a-fA-F]{3,8}\b"), num_fmt))
        # 5. Variables CSS dans les valeurs (ex: var(--border-color))
        self.rules.append((QRegularExpression(r"--[a-zA-Z0-9_\-]+"), var_fmt))
        # 6. Sélecteurs de classe
        self.rules.append((QRegularExpression(r"\.[a-zA-Z0-9_\-]+"), tag_fmt))
        # 7. Sélecteurs d'ID
        self.rules.append((QRegularExpression(r"#[a-zA-Z0-9_\-]+"), tag_fmt))
        # 8. At-rules (@media, @keyframes, @supports, @layer, @container, @font-face)
        self.rules.append((QRegularExpression(r"@[a-zA-Z_\-]+"), kw_fmt))
        # 9. Pseudo-éléments et pseudo-classes (:root, ::before, :hover, etc.)
        self.rules.append((QRegularExpression(r"::?[a-zA-Z0-9_\-]+(\([^\)]*\))?"), kw_fmt))
        # 10. !important
        self.rules.append((QRegularExpression(r"!important"), kw_fmt))
        # 11. Fonctions CSS modernes
        self.rules.append((QRegularExpression(r"\b(clamp|var|calc|color-mix|linear-gradient|radial-gradient|min|max|url|rgba?|hsla?)\b"), kw_fmt))

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self.rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                match = it.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)

        # Commentaires CSS multi-lignes
        self.setCurrentBlockState(0)
        start_index = 0
        if self.previousBlockState() != 1:
            match = self.comment_start_expression.match(text)
            start_index = match.capturedStart() if match.hasMatch() else -1

        while start_index >= 0:
            end_match = self.comment_end_expression.match(text, start_index)
            end_index = end_match.capturedStart() if end_match.hasMatch() else -1
            if end_index == -1:
                self.setCurrentBlockState(1)
                comment_length = len(text) - start_index
            else:
                comment_length = end_index - start_index + end_match.capturedLength()

            self.setFormat(start_index, comment_length, self.comment_format)
            start_match = self.comment_start_expression.match(text, start_index + comment_length)
            start_index = start_match.capturedStart() if start_match.hasMatch() else -1
