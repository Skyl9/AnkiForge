import re
import io
import base64
from typing import Optional

from PySide6.QtWidgets import QWidget, QPlainTextEdit, QTextBrowser, QSplitter, QVBoxLayout, QCompleter
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QKeyEvent, QTextCursor
from PySide6.QtCore import Qt, QRegularExpression, Signal, QStringListModel, QTimer

from ankiforge.ui.theme import DesignTokens, is_dark_mode

# Optional mathtext import
try:
    from matplotlib.mathtext import math_to_image

    HAS_MATHTEXT = True
except ImportError:
    HAS_MATHTEXT = False


LATEX_MACROS = [
    ("\\frac{}{}", "Fraction"),
    ("\\sum_{}", "Somme"),
    ("\\int_{}", "Intégrale"),
    ("\\alpha", "Alpha"),
    ("\\beta", "Beta"),
    ("\\gamma", "Gamma"),
    ("\\sqrt{}", "Racine carrée"),
    ("\\overline{}", "Barre"),
    ("\\text{}", "Texte"),
    ("\\textbf{}", "Texte gras"),
    ("\\textit{}", "Texte italique"),
    ("\\underbrace{}", "Accolade sous"),
    ("\\begin{matrix}\\end{matrix}", "Matrice"),
]

HTML_TAGS = [
    ("<b></b>", "Gras"),
    ("<i></i>", "Italique"),
    ("<u></u>", "Souligné"),
    ("<br>", "Saut de ligne"),
    ("<div></div>", "Division"),
    ("<span></span>", "Span"),
    ('<img src="">', "Image"),
]

JINJA_TAGS = [
    ("{{ }}", "Variable"),
    ("{% %}", "Bloc de code"),
    ("{{c1::}}", "Texte à trous (Cloze)"),
]


class KaTeXHighlighter(QSyntaxHighlighter):
    """Coloration syntaxique pour HTML + LaTeX + Jinja2."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []

        # 1. HTML tags : bleu
        html_format = QTextCharFormat()
        html_format.setForeground(QColor(DesignTokens.COLOR_BLUE))
        self.rules.append((QRegularExpression(r"<[^>]+>"), html_format))

        # 2. LaTeX : vert
        latex_format = QTextCharFormat()
        latex_format.setForeground(QColor(DesignTokens.COLOR_GREEN))
        self.rules.append((QRegularExpression(r"\$.*?\$"), latex_format))
        self.rules.append((QRegularExpression(r"\\\([^)]+\\\)"), latex_format))
        self.rules.append((QRegularExpression(r"\\\[.*?\\\]"), latex_format))
        self.rules.append((QRegularExpression(r"\$\$.*?\$\$"), latex_format))

        # 3. Jinja2 : orange
        jinja_format = QTextCharFormat()
        jinja_format.setForeground(QColor(DesignTokens.COLOR_YELLOW))
        self.rules.append((QRegularExpression(r"\{\{.*?\}\}"), jinja_format))
        self.rules.append((QRegularExpression(r"\{%.*?%\}"), jinja_format))

        # 4. Cloze : violet (sera appliqué par-dessus Jinja2 si ça matche)
        cloze_format = QTextCharFormat()
        cloze_format.setForeground(QColor(DesignTokens.COLOR_PURPLE))
        cloze_format.setFontWeight(QFont.Weight.Bold)
        self.rules.append((QRegularExpression(r"\{\{c\d+::.*?\}\}"), cloze_format))

    def highlightBlock(self, text: str):
        for pattern, fmt in self.rules:
            iterator = pattern.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)


class KaTeXCompleter(QCompleter):
    """IntelliSense pour macros LaTeX, HTML, Jinja2."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.list_model = QStringListModel()
        self.setModel(self.list_model)
        self._current_items = []

    def update_model(self, prefix: str):
        if prefix.startswith("\\"):
            self._current_items = LATEX_MACROS
        elif prefix.startswith("<"):
            self._current_items = HTML_TAGS
        elif prefix.startswith("{"):
            self._current_items = JINJA_TAGS
        else:
            self._current_items = []

        display_list = [f"{item[0]}  -  {item[1]}" for item in self._current_items]
        self.list_model.setStringList(display_list)

    def get_actual_completion(self, display_text: str) -> str:
        for item in self._current_items:
            if display_text.startswith(item[0]):
                return item[0]
        return display_text


class KaTeXTextEdit(QPlainTextEdit):
    """QPlainTextEdit customisé avec QCompleter pour IntelliSense."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.completer = KaTeXCompleter(self)
        self.completer.setWidget(self)
        self.completer.activated.connect(self.insert_completion)

    def insert_completion(self, completion: str):
        if self.completer.widget() is not self:
            return

        actual_completion = self.completer.get_actual_completion(completion)

        tc = self.textCursor()
        # Find exactly the prefix typed so far
        prefix = self.completer.completionPrefix()
        extra = len(actual_completion) - len(prefix)
        if extra > 0:
            tc.insertText(actual_completion[-extra:])

        # Positionner le curseur judicieusement (ex: au milieu de \frac{}{})
        if "{}{}" in actual_completion:
            tc.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 3)
        elif "{}" in actual_completion or "><" in actual_completion or "{{ }}" in actual_completion or "{% %}" in actual_completion:
            offset = 1
            if "><" in actual_completion:
                offset = actual_completion[::-1].find(">") + 1
            elif "{{ }}" in actual_completion or "{% %}" in actual_completion:
                offset = 3
            tc.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, offset)
        elif actual_completion.endswith("::}}"):
            tc.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 2)

        self.setTextCursor(tc)

    def textUnderCursor(self) -> str:
        tc = self.textCursor()
        tc.select(QTextCursor.SelectionType.WordUnderCursor)
        pos = tc.position()
        block_text = tc.block().text()
        start = pos
        # On remonte jusqu'au début du mot ou jusqu'au caractère déclencheur
        while start > 0 and block_text[start - 1] not in [" ", "\t", "\n"]:
            start -= 1
        return block_text[start:pos]

    def keyPressEvent(self, e: QKeyEvent):
        popup = self.completer.popup()
        if popup is not None and popup.isVisible():
            if e.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape, Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                e.ignore()
                return

        # Let the editor handle the key first, except if it's the trigger character
        super().keyPressEvent(e)

        cr = self.cursorRect()
        completion_prefix = self.textUnderCursor()

        if completion_prefix and (completion_prefix.startswith("\\") or completion_prefix.startswith("<") or completion_prefix.startswith("{")):
            self.completer.update_model(completion_prefix)
            self.completer.setCompletionPrefix(completion_prefix)

            popup = self.completer.popup()
            if popup is not None:
                popup.setCurrentIndex(self.completer.completionModel().index(0, 0))

                scroll_bar = popup.verticalScrollBar()
                scroll_width = scroll_bar.sizeHint().width() if scroll_bar else 0
                cr.setWidth(popup.sizeHintForColumn(0) + scroll_width)
            self.completer.complete(cr)
        else:
            popup = self.completer.popup()
            if popup is not None:
                popup.hide()


class KaTeXEditor(QWidget):
    """Éditeur de notes 100% natif Qt avec rendu LaTeX live."""

    content_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self._setup_connections()
        self.math_cache: dict[str, str] = {}

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Éditeur
        self.editor = KaTeXTextEdit()
        font = QFont(DesignTokens.FONT_CODE, DesignTokens.FONT_SIZE_CODE)
        self.editor.setFont(font)

        # Highlighter
        self.highlighter = KaTeXHighlighter(self.editor.document())

        # Preview
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)

        self.splitter.addWidget(self.editor)
        self.splitter.addWidget(self.preview)
        self.splitter.setSizes([400, 400])

        layout.addWidget(self.splitter)

        # Timer pour le debouncing du rendu live
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(300)  # 300ms de debounce

    def _setup_connections(self):
        self.editor.textChanged.connect(self._on_text_changed)
        self.render_timer.timeout.connect(self._update_preview)

    def _on_text_changed(self):
        self.content_changed.emit()
        self.render_timer.start()

    def get_content(self) -> str:
        return self.editor.toPlainText()

    def set_content(self, html: str) -> None:
        self.editor.setPlainText(html)
        self._update_preview()

    def _render_math(self, math_str: str) -> str:
        if not HAS_MATHTEXT:
            return f"<i>{math_str}</i>"

        if math_str in self.math_cache:
            return self.math_cache[math_str]

        try:
            buf = io.BytesIO()
            color = "white" if is_dark_mode() else "black"
            # Utilisation de mathtext pour générer une image
            math_to_image(f"${math_str}$", buf, format="png", dpi=120, color=color)
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            img_tag = f'<img src="data:image/png;base64,{b64}" style="vertical-align: middle;">'
            self.math_cache[math_str] = img_tag
            return img_tag
        except Exception:
            # Fallback si erreur de parsing LaTeX
            return '<span style="color: red;">[Math Error]</span>'

    def _update_preview(self):
        text = self.editor.toPlainText()

        # On protège d'abord le HTML brut (basique)
        # Mais l'utilisateur peut entrer de vraies balises HTML.
        # On va éviter un échappement complet pour laisser passer <b>, <i>, etc.
        # Remplacement manuel basique pour les sauts de ligne
        text = text.replace("\n", "<br>")

        # On remplace les blocs LaTeX par les images
        # 1. $...$ (non-greedy)
        text = re.sub(r"\$(.*?)\$", lambda m: self._render_math(m.group(1)), text)
        # 2. \(...\)
        text = re.sub(r"\\\((.*?)\\\)", lambda m: self._render_math(m.group(1)), text)
        # 3. \[...\]
        text = re.sub(r"\\\[(.*?)\\\]", lambda m: f"<div align='center'>{self._render_math(m.group(1))}</div>", text)
        # 4. $$...$$
        text = re.sub(r"\$\$(.*?)\$\$", lambda m: f"<div align='center'>{self._render_math(m.group(1))}</div>", text)

        html_content = f"""
        <html>
        <body style="font-family: {DesignTokens.FONT_MAIN}; font-size: {DesignTokens.FONT_SIZE_BASE}px; color: {DesignTokens.TEXT_PRIMARY}; background-color: {DesignTokens.BG_MAIN}; margin: 10px;">
            {text}
        </body>
        </html>
        """
        self.preview.setHtml(html_content)
