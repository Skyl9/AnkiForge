import re

from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from ankiforge.ui.theme import DesignTokens


class AnkiHtmlHighlighter(QSyntaxHighlighter):
    """
    Highlighter pour les templates Anki (HTML + Moustaches {{...}}).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []

        # Règle pour les balises HTML <...>
        html_tag_format = QTextCharFormat()
        html_tag_format.setForeground(QColor(DesignTokens.SYNTAX_TAG))
        self.highlighting_rules.append((re.compile(r"<[^>]*>"), html_tag_format))

        # Règle pour les balises Anki {{...}}
        anki_tag_format = QTextCharFormat()
        anki_tag_format.setForeground(QColor(DesignTokens.SYNTAX_VARIABLE))
        anki_tag_format.setFontWeight(QFont.Weight.Bold)
        self.highlighting_rules.append((re.compile(r"\{\{.*?\}\}"), anki_tag_format))

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), format)


class CssHighlighter(QSyntaxHighlighter):
    """
    Highlighter basique pour le CSS des modèles Anki.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []

        # Sélecteurs (ex: .card, #answer)
        selector_format = QTextCharFormat()
        selector_format.setForeground(QColor(DesignTokens.SYNTAX_TAG))
        self.highlighting_rules.append((re.compile(r"[.#][a-zA-Z0-9_-]+"), selector_format))

        # Propriétés (ex: font-family, color)
        property_format = QTextCharFormat()
        property_format.setForeground(QColor(DesignTokens.SYNTAX_ATTR))
        self.highlighting_rules.append((re.compile(r"[a-zA-Z0-9_-]+(?=\s*:)"), property_format))

        # Valeurs (après le :)
        value_format = QTextCharFormat()
        value_format.setForeground(QColor(DesignTokens.SYNTAX_STRING))
        self.highlighting_rules.append((re.compile(r"(?<=:)[^;]+"), value_format))

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), format)


class JinjaHighlighter(QSyntaxHighlighter):
    """
    Highlighter pour les prompts système utilisant la syntaxe Jinja2 et Markdown.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []

        # 1. Commentaires Jinja {# ... #}
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor(DesignTokens.SYNTAX_COMMENT))
        comment_format.setFontItalic(True)
        self.highlighting_rules.append((re.compile(r"\{#.*?#\}"), comment_format))

        # 2. Blocs de contrôle Jinja {% ... %}
        block_format = QTextCharFormat()
        block_format.setForeground(QColor(DesignTokens.SYNTAX_KEYWORD))
        block_format.setFontWeight(QFont.Weight.Bold)
        self.highlighting_rules.append((re.compile(r"\{%.*?%\}"), block_format))

        # 3. Variables Jinja {{ ... }}
        var_format = QTextCharFormat()
        var_format.setForeground(QColor(DesignTokens.SYNTAX_VARIABLE))
        var_format.setFontWeight(QFont.Weight.Bold)
        self.highlighting_rules.append((re.compile(r"\{\{.*?\}\}"), var_format))

        # 4. Mots clés Markdown inline `code`
        code_format = QTextCharFormat()
        code_format.setForeground(QColor(DesignTokens.SYNTAX_NUMBER))
        self.highlighting_rules.append((re.compile(r"`[^`]+`"), code_format))

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), format)


class SourceHighlighter(QSyntaxHighlighter):
    """Surligneur léger pour griser le HTML et colorer le Markdown."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []

        # 1. Balises HTML (ex: <span id="...">) -> Grisé
        html_format = QTextCharFormat()
        html_format.setForeground(QColor(DesignTokens.TEXT_MUTED))
        self.rules.append((re.compile(r"<[^>]+>"), html_format))

        # 2. Titres Markdown (# Titre) -> Couleur Accent + Gras
        h_format = QTextCharFormat()
        h_format.setForeground(QColor(DesignTokens.ACCENT_PRIMARY))
        h_format.setFontWeight(QFont.Weight.Bold)
        self.rules.append((re.compile(r"^#+\s+.*"), h_format))

    def highlightBlock(self, text):
        for pattern, format in self.rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), format)
