from typing import Any

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
)

from ankiforge.ui.theme import DesignTokens


class HTMLSyntaxHighlighter(QSyntaxHighlighter):
    """Coloration syntaxique temps réel pour gabarits HTML et balises Anki/Jinja2."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.rules: list[tuple[QRegularExpression, QTextCharFormat]] = []
        self.comment_format = QTextCharFormat()
        self.comment_start_expression = QRegularExpression(r"<!--")
        self.comment_end_expression = QRegularExpression(r"-->")
        self.update_formats()

    def update_formats(self) -> None:
        self.rules.clear()

        # Format balises HTML <tag>, </tag>, >
        tag_fmt = QTextCharFormat()
        tag_fmt.setForeground(QColor(DesignTokens.SYNTAX_TAG))
        tag_fmt.setFontWeight(QFont.Weight.Bold)

        # Format attributs HTML (class=, id=, style=)
        attr_fmt = QTextCharFormat()
        attr_fmt.setForeground(QColor(DesignTokens.SYNTAX_ATTR))

        # Format chaînes de caractères "..." ou '...'
        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor(DesignTokens.SYNTAX_STRING))

        # Format variables / champs Anki {{Champ}}
        var_fmt = QTextCharFormat()
        var_fmt.setForeground(QColor(DesignTokens.SYNTAX_VARIABLE))
        var_fmt.setFontWeight(QFont.Weight.DemiBold)

        # Format mots-clés Anki / conditionals / cloze
        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor(DesignTokens.SYNTAX_KEYWORD))
        kw_fmt.setFontWeight(QFont.Weight.Bold)

        # Format entités HTML &amp; etc.
        entity_fmt = QTextCharFormat()
        entity_fmt.setForeground(QColor(DesignTokens.SYNTAX_NUMBER))

        # Commentaires
        self.comment_format.setForeground(QColor(DesignTokens.SYNTAX_COMMENT))
        self.comment_format.setFontItalic(True)

        # Règles dans l'ordre de priorité
        self.rules.append((QRegularExpression(r"\b[a-zA-Z_\-:]+(?=\=)"), attr_fmt))
        self.rules.append((QRegularExpression(r'"[^"\\]*(\\.[^"\\]*)*"'), str_fmt))
        self.rules.append((QRegularExpression(r"'[^'\\]*(\\.[^'\\]*)*'"), str_fmt))
        self.rules.append((QRegularExpression(r"</?[a-zA-Z0-9_\-]+"), tag_fmt))
        self.rules.append((QRegularExpression(r"/?>"), tag_fmt))
        self.rules.append((QRegularExpression(r"&[a-zA-Z0-9#]+;"), entity_fmt))
        self.rules.append((QRegularExpression(r"\{\{[a-zA-Z0-9_:\s\-]+\}\}"), var_fmt))
        self.rules.append((QRegularExpression(r"\{\{[#\^/][a-zA-Z0-9_\-]+\}\}"), kw_fmt))
        self.rules.append((QRegularExpression(r"\{\{cloze:[a-zA-Z0-9_\-]+\}\}"), kw_fmt))
        self.rules.append((QRegularExpression(r"\{\{(FrontSide|Tags|Deck|Card|Subdeck|Type)\}\}"), kw_fmt))

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self.rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                match = it.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)

        # Commentaires HTML multi-lignes
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
