from typing import Any

from PySide6.QtCore import QRegularExpression, QStringListModel, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QCompleter, QFrame, QHBoxLayout, QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.safe_web_preview import SafeWebEngineView

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
        self.rules.append((QRegularExpression(r"\$\$.+?\$\$"), latex_format))
        self.rules.append((QRegularExpression(r"\\\[.+?\\\]"), latex_format))
        self.rules.append((QRegularExpression(r"\\\(.+?\\\)"), latex_format))
        self.rules.append((QRegularExpression(r"\$[^$\n]+\$"), latex_format))

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
        if popup is not None and popup.isVisible() and e.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape, Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self._setup_connections()
        self.math_cache: dict[str, str] = {}

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Slider stylisé (Toggle)

        self.mode_toggle_frame = QFrame()
        self.mode_toggle_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 16px;
            }}
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {DesignTokens.TEXT_MUTED};
                font-weight: bold;
                border-radius: 14px;
                padding: 6px 16px;
            }}
            QPushButton:checked {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                color: white;
            }}
        """)
        toggle_layout = QHBoxLayout(self.mode_toggle_frame)
        toggle_layout.setContentsMargins(2, 2, 2, 2)
        toggle_layout.setSpacing(0)

        self.btn_mode_raw = QPushButton("Texte Brut")
        self.btn_mode_raw.setCheckable(True)

        self.btn_mode_split = QPushButton("Mixte")
        self.btn_mode_split.setCheckable(True)
        self.btn_mode_split.setChecked(True)

        self.btn_mode_preview = QPushButton("Aperçu (KaTeX)")
        self.btn_mode_preview.setCheckable(True)

        toggle_layout.addWidget(self.btn_mode_raw)
        toggle_layout.addWidget(self.btn_mode_split)
        toggle_layout.addWidget(self.btn_mode_preview)

        self.btn_mode_raw.clicked.connect(lambda: self._on_mode_toggled("raw"))
        self.btn_mode_split.clicked.connect(lambda: self._on_mode_toggled("split"))
        self.btn_mode_preview.clicked.connect(lambda: self._on_mode_toggled("preview"))

        toggle_container = QWidget()
        tc_layout = QHBoxLayout(toggle_container)
        tc_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tc_layout.addWidget(self.mode_toggle_frame)
        tc_layout.setContentsMargins(0, 0, 0, 8)

        layout.addWidget(toggle_container)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Éditeur
        self.editor = KaTeXTextEdit()
        font = QFont(DesignTokens.FONT_CODE, DesignTokens.FONT_SIZE_CODE)
        self.editor.setFont(font)

        # Highlighter
        self.highlighter = KaTeXHighlighter(self.editor.document())

        # Preview
        self.preview = SafeWebEngineView()

        self.splitter.addWidget(self.editor)
        self.splitter.addWidget(self.preview)
        self.splitter.setSizes([400, 400])

        layout.addWidget(self.splitter, 1)

        # Timer pour le debouncing du rendu live
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(500)  # 500ms de debounce

    def _on_mode_toggled(self, mode: str):
        self.btn_mode_raw.setChecked(mode == "raw")
        self.btn_mode_split.setChecked(mode == "split")
        self.btn_mode_preview.setChecked(mode == "preview")

        if mode == "raw":
            self.splitter.setSizes([1, 0])
        elif mode == "preview":
            self.splitter.setSizes([0, 1])
        else:
            self.splitter.setSizes([400, 400])

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
        return f"\\({math_str}\\)"

    def _update_preview(self):
        import markdown

        from ankiforge.utils.anki_renderer import _preprocess_math_blocks, get_mathjax_script
        from ankiforge.utils.paths import get_media_dir

        text = self.editor.toPlainText()
        text = _preprocess_math_blocks(text)

        # Conversion Markdown vers HTML
        html_body = markdown.markdown(text, extensions=["tables", "fenced_code", "nl2br", "sane_lists"])

        html_content = f"""<!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: {DesignTokens.FONT_MAIN};
                font-size: {DesignTokens.FONT_SIZE_BASE}px;
                color: {DesignTokens.TEXT_PRIMARY};
                background-color: {DesignTokens.BG_MAIN};
                margin: 15px;
                line-height: 1.6;
            }}
            h1, h2, h3 {{ color: {DesignTokens.ACCENT_PRIMARY}; }}
            code {{ background-color: {DesignTokens.BG_HOVER}; padding: 2px 4px; border-radius: 4px; }}
            pre {{ background-color: {DesignTokens.BG_HOVER}; padding: 10px; border-radius: 6px; overflow-x: auto; }}
            blockquote {{ border-left: 4px solid {DesignTokens.ACCENT_PRIMARY}; margin: 0; padding-left: 10px; color: {DesignTokens.TEXT_MUTED}; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid {DesignTokens.BORDER_COLOR}; padding: 8px; text-align: left; }}
            th {{ background-color: {DesignTokens.BG_HOVER}; }}
            .cloze {{ color: #38bdf8; font-weight: bold; }}
            .katex .cloze {{ color: #38bdf8 !important; font-weight: bold; background: rgba(56, 189, 248, 0.15); border-radius: 3px; padding: 0 3px; }}
        </style>
        </head>
        <body>
            {html_body}
            {get_mathjax_script()}
        </body>
        </html>
        """
        media_dir = get_media_dir()
        media_dir.mkdir(exist_ok=True)
        base_url = QUrl.fromLocalFile(str(media_dir) + "/")
        self.preview.setHtmlSafe(html_content, base_url)

    def closeEvent(self, event: Any) -> None:
        if hasattr(self, "preview") and hasattr(self.preview, "cleanup"):
            self.preview.cleanup()
        super().closeEvent(event)
