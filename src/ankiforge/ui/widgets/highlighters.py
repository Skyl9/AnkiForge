import re
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


class AnkiHtmlHighlighter(QSyntaxHighlighter):
    """
    Highlighter pour les templates Anki (HTML + Moustaches {{...}}).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []

        # Règle pour les balises HTML <...>
        html_tag_format = QTextCharFormat()
        html_tag_format.setForeground(QColor("#569CD6"))  # Bleu clair
        self.highlighting_rules.append((re.compile(r"<[^>]*>"), html_tag_format))

        # Règle pour les balises Anki {{...}}
        anki_tag_format = QTextCharFormat()
        anki_tag_format.setForeground(QColor("#CE9178"))  # Orange/Brun doux
        anki_tag_format.setFontWeight(QFont.Weight.Bold)
        # On peut simuler un fond semi-transparent si nécessaire,
        # mais le texte coloré en gras est déjà très efficace.
        # anki_tag_format.setBackground(QColor(230, 162, 60, 40))
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
        selector_format.setForeground(QColor("#DCDCAA"))  # Jaune
        self.highlighting_rules.append((re.compile(r"[.#][a-zA-Z0-9_-]+"), selector_format))

        # Propriétés (ex: font-family, color)
        property_format = QTextCharFormat()
        property_format.setForeground(QColor("#9CDCFE"))  # Bleu très clair
        self.highlighting_rules.append((re.compile(r"[a-zA-Z0-9_-]+(?=\s*:)"), property_format))

        # Valeurs (après le :)
        value_format = QTextCharFormat()
        value_format.setForeground(QColor("#CE9178"))
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

        # 1. Commentaires Jinja {# ... #} (Vert)
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6A9955"))
        comment_format.setFontItalic(True)
        self.highlighting_rules.append((re.compile(r"\{#.*?#\}"), comment_format))

        # 2. Blocs de contrôle Jinja {% ... %} (Violet)
        block_format = QTextCharFormat()
        block_format.setForeground(QColor("#C586C0"))
        block_format.setFontWeight(QFont.Weight.Bold)
        self.highlighting_rules.append((re.compile(r"\{%.*?%\}"), block_format))

        # 3. Variables Jinja {{ ... }} (Orange)
        var_format = QTextCharFormat()
        var_format.setForeground(QColor("#CE9178"))
        var_format.setFontWeight(QFont.Weight.Bold)
        self.highlighting_rules.append((re.compile(r"\{\{.*?\}\}"), var_format))

        # 4. Mots clés Markdown inline `code` (Vert d'eau)
        code_format = QTextCharFormat()
        code_format.setForeground(QColor("#4EC9B0"))
        self.highlighting_rules.append((re.compile(r"`[^`]+`"), code_format))

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), format)
