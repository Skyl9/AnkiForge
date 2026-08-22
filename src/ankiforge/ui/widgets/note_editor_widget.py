"""
Éditeur de Champ de Note Natif Qt avec IntelliSense (LaTeX, HTML, Jinja2/Cloze),
Coloration syntaxique temps réel, gouttière de numéros de ligne et auto-complétion.
100% Conforme aux spécifications du ticket Obsidian et de GEMINI.md.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import qtawesome
from PySide6.QtCore import QRect, QRegularExpression, QSize, QStringListModel, Qt, QTimer, Signal, Slot
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QPainter,
    QPaintEvent,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel, NoteVersionModel, db
from ankiforge.services.cards.note_manager import NoteManager
from ankiforge.ui.components.components import ActionButton, PrimaryButton, RoundedPanel
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.drop_image_text_edit import DropImageTextEdit
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.anki_renderer import get_max_cloze_index

logger = logging.getLogger(__name__)

# =============================================================================
# 1. CATALOGUES D'AUTOCOMPLÉTION INTELLISENSE
# =============================================================================

LATEX_MACROS: List[Tuple[str, str]] = [
    (r"\frac{}{}", "Fraction : \\frac{num}{den}"),
    (r"\sqrt{}", "Racine carrée : \\sqrt{x}"),
    (r"\sum_{}^{}", "Somme : \\sum_{i=0}^{n}"),
    (r"\int_{}^{}", "Intégrale : \\int_{a}^{b}"),
    (r"\prod_{}^{}", "Produit : \\prod_{i=1}^{n}"),
    (r"\lim_{}", "Limite : \\lim_{x \\to \\infty}"),
    (r"\alpha", "Lettre grecque Alpha : α"),
    (r"\beta", "Lettre grecque Beta : β"),
    (r"\gamma", "Lettre grecque Gamma : γ"),
    (r"\delta", "Lettre grecque Delta : δ"),
    (r"\theta", "Lettre grecque Theta : θ"),
    (r"\lambda", "Lettre grecque Lambda : λ"),
    (r"\pi", "Nombre Pi : π"),
    (r"\sigma", "Lettre grecque Sigma : σ"),
    (r"\omega", "Lettre grecque Omega : ω"),
    (r"\infty", "Infini : ∞"),
    (r"\partial", "Dérivée partielle : ∂"),
    (r"\nabla", "Opérateur Nabla : ∇"),
    (r"\pm", "Plus ou moins : ±"),
    (r"\times", "Multiplication : ×"),
    (r"\div", "Division : ÷"),
    (r"\neq", "Différent de : ≠"),
    (r"\leq", "Inférieur ou égal : ≤"),
    (r"\geq", "Supérieur ou égal : ≥"),
    (r"\approx", "Approximativement : ≈"),
    (r"\in", "Appartient à : ∈"),
    (r"\subset", "Sous-ensemble : ⊂"),
    (r"\forall", "Pour tout : ∀"),
    (r"\exists", "Il existe : ∃"),
    (r"\mathbf{}", "Texte mathématique gras"),
    (r"\mathit{}", "Texte mathématique italique"),
    (r"\text{}", "Texte standard dans formule"),
    (r"\begin{matrix}\end{matrix}", "Matrice simple"),
    (r"\begin{pmatrix}\end{pmatrix}", "Matrice parenthèses"),
]

HTML_TAGS: List[Tuple[str, str]] = [
    ("<b></b>", "Gras : <b>texte</b>"),
    ("<i></i>", "Italique : <i>texte</i>"),
    ("<u></u>", "Souligné : <u>texte</u>"),
    ("<s></s>", "Barré : <s>texte</s>"),
    ("<code></code>", "Code en ligne : <code>cmd</code>"),
    ("<pre><code></code></pre>", "Bloc de code préformaté"),
    ('<span class=""></span>', "Conteneur stylé Span"),
    ('<div class=""></div>', "Bloc Division"),
    ("<br>", "Saut de ligne HTML"),
    ("<hr>", "Ligne de séparation horizontale"),
    ("<ul>\n  <li></li>\n</ul>", "Liste à puces non ordonnée"),
    ("<ol>\n  <li></li>\n</ol>", "Liste ordonnée numérotée"),
    ("<li></li>", "Élément de liste"),
    ("<p></p>", "Paragraphe"),
    ("<blockquote></blockquote>", "Citation en bloc"),
    ('<a href=""></a>', "Lien hypertexte"),
    ('<img src="">', "Image embarquée"),
    ("<table>\n  <tr><th></th></tr>\n  <tr><td></td></tr>\n</table>", "Tableau HTML"),
]

STANDARD_JINJA: List[Tuple[str, str]] = [
    ("{{c1::}}", "Trou Cloze n°1 : {{c1::mot}}"),
    ("{{c2::}}", "Trou Cloze n°2 : {{c2::mot}}"),
    ("{{FrontSide}}", "Contenu du recto (au verso)"),
    ("{{Tags}}", "Liste des tags de la carte"),
    ("{{Deck}}", "Nom du paquet Anki"),
]


# =============================================================================
# 2. COLORATION SYNTAXIQUE (KaTeXHighlighter)
# =============================================================================


class NoteKaTeXHighlighter(QSyntaxHighlighter):
    """
    Surligneur syntaxique haute performance pour champs de notes Anki :
    - HTML (Bleu)
    - Math KaTeX / LaTeX ($..$, $$..$$, \\(..\\), \\[..\\]) (Vert / Émeraude)
    - Variables Jinja2 / Champs de modèle (Orange / Jaune)
    - Cloze Deletions {{cN::...}} (Violet / Accent)
    """

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.rules: List[Tuple[QRegularExpression, QTextCharFormat]] = []
        self._setup_rules()

    def _setup_rules(self) -> None:
        self.rules.clear()

        # 1. Balises HTML : Cyan / Bleu
        html_fmt = QTextCharFormat()
        html_fmt.setForeground(QColor("#38bdf8" if DesignTokens.is_dark_mode() else "#0284c7"))
        self.rules.append((QRegularExpression(r"</?[a-zA-Z0-9_-]+(\s+[^>]*)?/?>"), html_fmt))

        # 2. LaTeX inline & display : Vert Émeraude
        latex_fmt = QTextCharFormat()
        latex_fmt.setForeground(QColor("#34d399" if DesignTokens.is_dark_mode() else "#059669"))
        self.rules.append((QRegularExpression(r"\$[^$]+\$"), latex_fmt))
        self.rules.append((QRegularExpression(r"\$\$[\s\S]*?\$\$"), latex_fmt))
        self.rules.append((QRegularExpression(r"\\\([^\)]+\\\)"), latex_fmt))
        self.rules.append((QRegularExpression(r"\\\[[\s\S]*?\\\]"), latex_fmt))

        # 3. Macros LaTeX isolées (\\frac, \\alpha...)
        macro_fmt = QTextCharFormat()
        macro_fmt.setForeground(QColor("#a7f3d0" if DesignTokens.is_dark_mode() else "#047857"))
        macro_fmt.setFontWeight(QFont.Weight.DemiBold)
        self.rules.append((QRegularExpression(r"\\[a-zA-Z]+"), macro_fmt))

        # 4. Variables Jinja2 standards : Orange / Ambre
        jinja_fmt = QTextCharFormat()
        jinja_fmt.setForeground(QColor("#fbbf24" if DesignTokens.is_dark_mode() else "#d97706"))
        self.rules.append((QRegularExpression(r"\{\{[^c\d][^}]*\}\}"), jinja_fmt))
        self.rules.append((QRegularExpression(r"\{%[\s\S]*?%\}"), jinja_fmt))

        # 5. Cloze deletions : Violet / Pourpre éclatant
        cloze_fmt = QTextCharFormat()
        cloze_fmt.setForeground(QColor("#c084fc" if DesignTokens.is_dark_mode() else "#7c3aed"))
        cloze_fmt.setFontWeight(QFont.Weight.Bold)
        self.rules.append((QRegularExpression(r"\{\{c\d+::[\s\S]*?\}\}"), cloze_fmt))

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self.rules:
            iterator = pattern.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)


# =============================================================================
# 3. INTELLISENSE COMPLETER (KaTeXCompleter)
# =============================================================================


class NoteKaTeXCompleter(QCompleter):
    """
    IntelliSense flottant contextuel pour macros LaTeX, balises HTML et champs du modèle.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.list_model = QStringListModel(self)
        self.setModel(self.list_model)
        self._current_items: List[Tuple[str, str]] = []
        self._known_fields: List[str] = []

    def set_known_fields(self, fields: List[str]) -> None:
        self._known_fields = list(fields)

    def update_model_for_prefix(self, prefix: str) -> None:
        items: List[Tuple[str, str]] = []

        if prefix.startswith("\\"):
            items = list(LATEX_MACROS)
        elif prefix.startswith("<"):
            items = list(HTML_TAGS)
        elif prefix.startswith("{"):
            items = list(STANDARD_JINJA)
            # Ajout des champs du modèle actif en tête de liste
            for f in self._known_fields:
                items.insert(0, (f"{{{{{f}}}}}", f"Champ du modèle : {f}"))
                items.append((f"{{{{cloze:{f}}}}}", f"Filtre Cloze pour : {f}"))
        else:
            items = []

        self._current_items = items
        display_list = [f"{item[0]}   —   {item[1]}" for item in items]
        self.list_model.setStringList(display_list)

    def get_actual_completion(self, display_text: str) -> str:
        for item in self._current_items:
            if display_text.startswith(item[0]):
                return item[0]
        # Fallback si texte direct
        if "   —   " in display_text:
            return display_text.split("   —   ")[0].strip()
        return display_text


# =============================================================================
# 4. GOUTTIÈRE DE NUMÉROS DE LIGNES (NoteLineNumberArea)
# =============================================================================


class NoteLineNumberArea(QWidget):
    """Gouttière native peinte avec QPainter pour l'éditeur de notes."""

    def __init__(self, editor: NoteFieldTextEdit) -> None:
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event: QPaintEvent) -> None:
        self.code_editor.line_number_area_paint_event(event)


# =============================================================================
# 5. ÉDITEUR TEXTE NATIF ENRICHI (NoteFieldTextEdit)
# =============================================================================


class NoteFieldTextEdit(QPlainTextEdit):
    """
    QPlainTextEdit natif avec gouttière, autocomplétion flottante,
    coloration syntaxique KaTeX/HTML/Cloze et fermeture automatique des délimiteurs.
    """

    focus_changed = Signal(bool)
    save_requested = Signal()
    history_requested = Signal()
    shortcut_action_triggered = Signal(str)  # bold, italic, underline, cloze, math, link, etc.

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # Typographie & Rendu
        font = QFont(DesignTokens.FONT_CODE, 12)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)

        # Gouttière
        self.line_number_area = NoteLineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_number_area_width(0)

        # Coloration
        self.highlighter = NoteKaTeXHighlighter(self.document())

        # IntelliSense
        self.completer = NoteKaTeXCompleter(self)
        self.completer.setWidget(self)
        self.completer.activated.connect(self._insert_completion)

        self._apply_style()

    def _apply_style(self) -> None:
        bg_editor = DesignTokens.BG_INPUT
        text_primary = DesignTokens.TEXT_PRIMARY
        border_color = DesignTokens.BORDER_COLOR
        radius = DesignTokens.RADIUS_SM

        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {bg_editor};
                color: {text_primary};
                border: 1px solid {border_color};
                border-top: none;
                border-bottom-left-radius: {radius}px;
                border-bottom-right-radius: {radius}px;
                padding: 6px;
                selection-background-color: {DesignTokens.ACCENT_PRIMARY};
                selection-color: #ffffff;
            }}
        """)

    def set_known_fields(self, fields: List[str]) -> None:
        self.completer.set_known_fields(fields)

    # --- Gestion de la Gouttière ---

    def line_number_area_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        char_width = self.fontMetrics().horizontalAdvance("9")
        return 14 + char_width * max(2, digits)

    def _update_line_number_area_width(self, _: int = 0) -> None:
        new_width = self.line_number_area_width()
        margins = self.viewportMargins()
        if margins.left() != new_width:
            self.setViewportMargins(new_width, 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event: QPaintEvent) -> None:
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(DesignTokens.BG_PANEL))

        painter.setPen(QColor(DesignTokens.BORDER_COLOR))
        painter.drawLine(
            self.line_number_area.width() - 1,
            event.rect().top(),
            self.line_number_area.width() - 1,
            event.rect().bottom(),
        )

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        current_block_num = self.textCursor().blockNumber()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number_str = str(block_number + 1)
                is_current = block_number == current_block_num
                color = QColor(DesignTokens.ACCENT_PRIMARY if is_current else DesignTokens.TEXT_MUTED)
                painter.setPen(color)
                painter.setFont(self.font())
                painter.drawText(
                    0,
                    top + 2,
                    self.line_number_area.width() - 6,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number_str,
                )

            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def _highlight_current_line(self) -> None:
        self.line_number_area.update()

    # --- Actions Clavier & IntelliSense ---

    def focusInEvent(self, event: Any) -> None:
        super().focusInEvent(event)
        self.focus_changed.emit(True)

    def focusOutEvent(self, event: Any) -> None:
        super().focusOutEvent(event)
        self.focus_changed.emit(False)

    def _text_under_cursor(self) -> str:
        tc = self.textCursor()
        block_text = tc.block().text()
        block_pos = tc.positionInBlock()

        start = block_pos
        while start > 0 and block_text[start - 1] not in [" ", "\t", "\n"]:
            start -= 1
        return block_text[start:block_pos]

    def _insert_completion(self, completion_text: str) -> None:
        if self.completer.widget() is not self:
            return

        actual = self.completer.get_actual_completion(completion_text)
        tc = self.textCursor()
        prefix = self._text_under_cursor()

        extra = len(actual) - len(prefix)
        if extra > 0:
            tc.insertText(actual[-extra:])
        else:
            for _ in range(len(prefix)):
                tc.deletePreviousChar()
            tc.insertText(actual)

        if "{}{}" in actual:
            tc.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 3)
        elif actual.endswith("::}}"):
            tc.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 2)
        elif "><" in actual:
            offset = len(actual) - actual.find("><") - 1
            tc.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, offset)
        elif "{}" in actual or "{{ }}" in actual or "{% %}" in actual:
            offset = 1 if "{}" in actual else 3
            tc.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, offset)

        self.setTextCursor(tc)

    def wrap_selection(self, prefix: str, suffix: str) -> None:
        cursor = self.textCursor()
        selected = cursor.selectedText()
        cursor.insertText(f"{prefix}{selected}{suffix}")
        if not selected:
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, len(suffix))
            self.setTextCursor(cursor)

    def insert_at_cursor(self, text: str) -> None:
        self.textCursor().insertText(text)

    def keyPressEvent(self, e: QKeyEvent) -> None:
        popup = self.completer.popup()
        if popup is not None and popup.isVisible():
            if e.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape, Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                e.ignore()
                return

        modifiers = e.modifiers()
        is_ctrl_or_cmd = bool(modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
        is_shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if is_ctrl_or_cmd and e.key() == Qt.Key.Key_S:
            self.save_requested.emit()
            e.accept()
            return
        if is_ctrl_or_cmd and e.key() == Qt.Key.Key_H:
            self.history_requested.emit()
            e.accept()
            return
        if is_ctrl_or_cmd and not is_shift:
            if e.key() == Qt.Key.Key_B:
                self.shortcut_action_triggered.emit("bold")
                e.accept()
                return
            if e.key() == Qt.Key.Key_I:
                self.shortcut_action_triggered.emit("italic")
                e.accept()
                return
            if e.key() == Qt.Key.Key_U:
                self.shortcut_action_triggered.emit("underline")
                e.accept()
                return
            if e.key() == Qt.Key.Key_K:
                self.shortcut_action_triggered.emit("link")
                e.accept()
                return
            if e.key() == Qt.Key.Key_M:
                self.shortcut_action_triggered.emit("math")
                e.accept()
                return
        if is_ctrl_or_cmd and is_shift and e.key() == Qt.Key.Key_C:
            self.shortcut_action_triggered.emit("cloze")
            e.accept()
            return

        key_char = e.text()
        pairs = {
            "(": ")",
            "[": "]",
            "{": "}",
            '"': '"',
            "'": "'",
            "$": "$",
        }

        if key_char in pairs:
            cursor = self.textCursor()
            selected = cursor.selectedText()
            closing = pairs[key_char]

            if selected:
                cursor.insertText(f"{key_char}{selected}{closing}")
                e.accept()
                return
            else:
                super().keyPressEvent(e)
                pos = self.textCursor().position()
                cursor.insertText(closing)
                cursor.setPosition(pos)
                self.setTextCursor(cursor)
                e.accept()
                return

        if key_char == ">":
            cursor = self.textCursor()
            block_text = cursor.block().text()
            block_pos = cursor.positionInBlock()

            match = re.search(r"<([a-zA-Z0-9_-]+)(?:\s+[^>]*)?$", block_text[:block_pos])
            super().keyPressEvent(e)

            if match:
                tag_name = match.group(1).lower()
                self_closing = {"br", "hr", "img", "input", "meta", "link", "source", "col", "base"}
                if tag_name not in self_closing and not block_text[block_pos - 1] == "/":
                    closing_tag = f"</{tag_name}>"
                    insert_cursor = self.textCursor()
                    cur_pos = insert_cursor.position()
                    insert_cursor.insertText(closing_tag)
                    insert_cursor.setPosition(cur_pos)
                    self.setTextCursor(insert_cursor)
            return

        super().keyPressEvent(e)

        prefix = self._text_under_cursor()
        if prefix and (prefix.startswith("\\") or prefix.startswith("<") or prefix.startswith("{")):
            self.completer.update_model_for_prefix(prefix)
            self.completer.setCompletionPrefix(prefix)

            popup = self.completer.popup()
            if popup is not None:
                popup.setCurrentIndex(self.completer.completionModel().index(0, 0))
                cr = self.cursorRect()
                scroll_bar = popup.verticalScrollBar()
                scroll_w = scroll_bar.sizeHint().width() if scroll_bar else 0
                cr.setWidth(max(240, popup.sizeHintForColumn(0) + scroll_w + 20))
                self.completer.complete(cr)
        else:
            popup = self.completer.popup()
            if popup is not None and popup.isVisible():
                popup.hide()


# =============================================================================
# 6. CONTENEUR DE CHAMP AVEC EN-TÊTE DÉPLIABLE (NoteFieldEditorWidget)
# =============================================================================


class NoteFieldEditorWidget(QWidget):
    """
    Widget complet de champ de note :
    - En-tête cliquable avec chevron animé et badge de nom
    - Éditeur natif `NoteFieldTextEdit` avec IntelliSense & KaTeX
    - Signalement des changements de contenu et de focus
    """

    content_changed = Signal(str)  # field_name
    focus_received = Signal(object)  # self
    save_requested = Signal()
    history_requested = Signal()

    def __init__(
        self,
        field_name: str,
        initial_value: str = "",
        is_first: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.field_name = field_name
        self._is_first = is_first
        self._is_collapsed = False

        self._setup_ui(initial_value)

    def _setup_ui(self, initial_value: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)

        self.btn_header = QPushButton()
        self.btn_header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_header_text()

        accent_color = DesignTokens.ACCENT_PRIMARY if self._is_first else DesignTokens.TEXT_PRIMARY
        radius = DesignTokens.RADIUS_SM

        self.btn_header.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                color: {accent_color};
                text-align: left;
                font-size: 11px;
                font-weight: bold;
                padding: 6px 12px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-top-left-radius: {radius}px;
                border-top-right-radius: {radius}px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        self.btn_header.clicked.connect(self.toggle_collapsed)
        layout.addWidget(self.btn_header)

        self.editor = NoteFieldTextEdit(self)
        self.editor.setPlainText(initial_value)
        self.editor.setMinimumHeight(75)

        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.focus_changed.connect(self._on_focus_changed)
        self.editor.save_requested.connect(self.save_requested)
        self.editor.history_requested.connect(self.history_requested)

        layout.addWidget(self.editor)

    def _update_header_text(self) -> None:
        icon_arrow = "▶" if self._is_collapsed else "▼"
        self.btn_header.setText(f"{icon_arrow}  {self.field_name.upper()}")

    def toggle_collapsed(self) -> None:
        self._is_collapsed = not self._is_collapsed
        self.editor.setVisible(not self._is_collapsed)
        self._update_header_text()

        radius = DesignTokens.RADIUS_SM
        if self._is_collapsed:
            self.btn_header.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_PANEL};
                    color: {DesignTokens.TEXT_MUTED};
                    text-align: left;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 6px 12px;
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {radius}px;
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                }}
            """)
        else:
            accent_color = DesignTokens.ACCENT_PRIMARY if self._is_first else DesignTokens.TEXT_PRIMARY
            self.btn_header.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_PANEL};
                    color: {accent_color};
                    text-align: left;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 6px 12px;
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-top-left-radius: {radius}px;
                    border-top-right-radius: {radius}px;
                    border-bottom-left-radius: 0px;
                    border-bottom-right-radius: 0px;
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                }}
            """)

    def _on_text_changed(self) -> None:
        self.content_changed.emit(self.field_name)

    def _on_focus_changed(self, has_focus: bool) -> None:
        if has_focus:
            self.focus_received.emit(self)

    def get_text(self) -> str:
        return self.editor.toPlainText()

    def set_text(self, text: str) -> None:
        self.editor.setPlainText(text)

    def set_known_fields(self, fields: List[str]) -> None:
        self.editor.set_known_fields(fields)


# =============================================================================
# 7. COMPOSANT RÉTRO-COMPATIBLE (NoteEditorWidget)
# =============================================================================


class NoteEditorWidget(QWidget):
    """
    Composant d'édition complet pour compatibilité ascendante.
    """

    note_updated = Signal(int, dict, int)
    note_created = Signal(int)
    history_requested = Signal(int)
    creation_mode_exited = Signal(bool, object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current_note: Optional[NoteModel] = None
        self.current_deck_id: Optional[int] = None
        self.field_editors: Dict[str, QTextEdit] = {}
        self.is_creating = False
        self.creation_model_cb: Optional[QComboBox] = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(10)

        editor_panel = RoundedPanel()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(15, 15, 15, 15)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 10)

        btn_bold = ActionButton("fa5s.bold", "")
        btn_italic = ActionButton("fa5s.italic", "")
        btn_h2 = ActionButton("fa5s.heading", "")
        btn_latex = ActionButton("fa5s.square-root-alt", "")

        toolbar_layout.addWidget(btn_bold)
        toolbar_layout.addWidget(btn_italic)
        toolbar_layout.addWidget(btn_h2)
        toolbar_layout.addWidget(btn_latex)
        toolbar_layout.addStretch()

        editor_layout.addLayout(toolbar_layout)

        self.details_scroll = QScrollArea()
        self.details_scroll.setWidgetResizable(True)
        self.details_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.details_widget = QWidget()
        self.details_widget.setStyleSheet("background: transparent;")
        self.details_layout = QVBoxLayout(self.details_widget)
        self.details_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.details_scroll.setWidget(self.details_widget)

        editor_layout.addWidget(self.details_scroll)

        buttons_layout = QHBoxLayout()
        self.btn_history = ActionButton("fa5s.history", " Historique")
        self.btn_history.setEnabled(False)

        self.btn_save_edits = PrimaryButton(qtawesome.icon("fa5s.save", color="white"), " Sauvegarder modifications")
        self.btn_save_edits.setEnabled(False)

        buttons_layout.addWidget(self.btn_history)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.btn_save_edits)

        editor_layout.addLayout(buttons_layout)
        self.splitter.addWidget(editor_panel)

        preview_panel = RoundedPanel()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(15, 15, 15, 15)

        self.preview_widget = CardPreviewWidget(show_header=True)

        preview_tools_layout = QHBoxLayout()
        self.btn_toggle_mobile = ActionButton("fa5s.mobile-alt", " Mobile")
        self.btn_toggle_mobile.setCheckable(True)
        self.btn_toggle_mobile.toggled.connect(self._toggle_mobile_preview)

        preview_tools_layout.addWidget(self.btn_toggle_mobile)
        preview_tools_layout.addStretch()

        preview_layout.addWidget(self.preview_widget)
        preview_layout.addLayout(preview_tools_layout)

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(500)

        self.splitter.addWidget(preview_panel)
        self.splitter.setSizes([350, 450])

        layout.addWidget(self.splitter)

    def _connect_signals(self) -> None:
        self.btn_history.clicked.connect(self._on_history_clicked)
        self.btn_save_edits.clicked.connect(self.save_note_edits)
        self.preview_timer.timeout.connect(self.update_preview)

    def _toggle_mobile_preview(self, checked: bool) -> None:
        if checked:
            self.preview_widget.setMaximumWidth(375)
            self.btn_toggle_mobile.setText(" Desktop")
            self.btn_toggle_mobile.setIcon(qtawesome.icon("fa5s.desktop", color="white"))
        else:
            self.preview_widget.setMaximumWidth(16777215)
            self.btn_toggle_mobile.setText(" Mobile")
            self.btn_toggle_mobile.setIcon(qtawesome.icon("fa5s.mobile-alt", color="white"))

    def set_current_deck(self, deck_id: Optional[int]) -> None:
        self.current_deck_id = deck_id

    def load_note(self, note_id: int) -> None:
        self._clear_editor()
        self.is_creating = False
        try:
            self.current_note = NoteModel.get_by_id(note_id)
            if not self.current_note or not self.current_note.note_type:
                return

            self.btn_save_edits.setText(" Sauvegarder modifications")
            self.btn_save_edits.setEnabled(True)
            self.btn_history.setEnabled(True)
            self.btn_history.setVisible(True)

            active_version = NoteVersionModel.get_or_none(note=self.current_note, is_active=True)
            content_dict = json.loads(active_version.content) if active_version else {}

            lbl_title = QLabel(f"<b>Édition (Modèle : {self.current_note.note_type.name})</b>")
            lbl_title.setStyleSheet("font-size: 16px;")
            self.details_layout.addWidget(lbl_title)
            self.details_layout.addSpacing(5)

            for field_name, field_value in content_dict.items():
                lbl = QLabel(field_name)
                lbl.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 10px; text-transform: uppercase; letter-spacing: 1px;")
                text_edit = DropImageTextEdit()

                clean_value = field_value.replace("<br>", "\n") if field_value else ""
                text_edit.setPlainText(clean_value)
                text_edit.setMinimumHeight(60)
                text_edit.textChanged.connect(self._on_text_changed)

                self.field_editors[field_name] = text_edit
                self.details_layout.addSpacing(15)
                self.details_layout.addWidget(lbl)
                self.details_layout.addSpacing(5)
                self.details_layout.addWidget(text_edit)

            self.update_preview()
        except Exception as e:
            logger.exception("Erreur lors du chargement de la note dans l'éditeur :")
            self.details_layout.addWidget(QLabel(f"Erreur : {e}"))

    def enter_creation_mode(self) -> None:
        self._clear_editor()
        self.is_creating = True
        self.current_note = None

        self.btn_save_edits.setText(" ✨ Créer la note")
        self.btn_save_edits.setEnabled(True)
        self.btn_history.setVisible(False)

        lbl_title = QLabel("<b>Création de Note</b>")
        lbl_title.setStyleSheet("font-size: 16px;")
        self.details_layout.addWidget(lbl_title)
        self.details_layout.addSpacing(5)

        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Modèle :"))
        self.creation_model_cb = QComboBox()
        models = NoteTypeModel.select()
        for m in models:
            self.creation_model_cb.addItem(m.name, m.id)

        self.creation_model_cb.currentIndexChanged.connect(self._render_creation_fields)
        model_layout.addWidget(self.creation_model_cb)
        model_layout.addStretch()

        model_widget = QWidget()
        model_widget.setLayout(model_layout)
        self.details_layout.addWidget(model_widget)

        self._render_creation_fields()

    def _render_creation_fields(self) -> None:
        if not self.is_creating or not self.creation_model_cb:
            return

        model_id = self.creation_model_cb.currentData()
        if not model_id:
            return

        note_type = NoteTypeModel.get_by_id(model_id)
        fields = json.loads(note_type.fields_schema) if note_type.fields_schema else []

        while self.details_layout.count() > 2:
            child = self.details_layout.takeAt(2)
            if child:
                w = child.widget()
                if w:
                    w.deleteLater()

        self.field_editors.clear()
        for field_name in fields:
            lbl = QLabel(f"<b>{field_name}</b>")
            text_edit = DropImageTextEdit()
            text_edit.setMinimumHeight(60)
            text_edit.textChanged.connect(self._on_text_changed)

            self.field_editors[field_name] = text_edit
            self.details_layout.addWidget(lbl)
            self.details_layout.addWidget(text_edit)

        self.update_preview()

    def _clear_editor(self) -> None:
        while self.details_layout.count():
            child = self.details_layout.takeAt(0)
            if child:
                w = child.widget()
                if w:
                    w.deleteLater()
        self.field_editors.clear()
        self.current_note = None

    @Slot()
    def _on_text_changed(self) -> None:
        self.preview_timer.start()

    @Slot()
    def _on_history_clicked(self) -> None:
        if self.current_note:
            self.history_requested.emit(self.current_note.id)

    @Slot()
    def save_note_edits(self) -> None:
        if self.is_creating:
            self._create_new_note()
            return
        if not self.current_note:
            return

        try:
            active_version = NoteVersionModel.get_or_none(note=self.current_note, is_active=True)
            content_dict = json.loads(active_version.content) if active_version else {}
            for field_name, editor in self.field_editors.items():
                content_dict[field_name] = editor.toPlainText().replace("\n", "<br>")

            with db.atomic():
                new_version = self.current_note.add_version(content_dict, source="manual")

                note_type = self.current_note.note_type
                templates = json.loads(note_type.templates) if note_type.templates else []
                is_cloze = any("{{cloze:" in t.get("qfmt", "") or "{{cloze:" in t.get("afmt", "") for t in templates)

                if is_cloze:
                    max_cloze = get_max_cloze_index(content_dict)
                    target_num_cards = max(1, max_cloze)
                    existing_cards = list(self.current_note.cards.order_by(CardModel.template_index))
                    current_num_cards = len(existing_cards)

                    if target_num_cards > current_num_cards:
                        deck = existing_cards[0].deck if existing_cards else DeckModel.get_by_id(self.current_deck_id)
                        for i in range(current_num_cards, target_num_cards):
                            CardModel.create(note=self.current_note, deck=deck, template_index=i)
                    elif target_num_cards < current_num_cards:
                        for card in existing_cards[target_num_cards:]:
                            card.delete_instance()

            self.note_updated.emit(self.current_note.id, content_dict, new_version.version_number)
            show_toast(self, "Note mise à jour !")
        except Exception as e:
            logger.exception("Erreur lors de la sauvegarde :")
            QMessageBox.critical(self, "Erreur", f"Impossible de sauvegarder : {e}")

    def _create_new_note(self) -> None:
        try:
            if not self.creation_model_cb or not self.current_deck_id:
                return

            model_id = self.creation_model_cb.currentData()
            note_type = NoteTypeModel.get_by_id(model_id)
            deck = DeckModel.get_by_id(self.current_deck_id)

            content_dict = {name: editor.toPlainText().replace("\n", "<br>") for name, editor in self.field_editors.items()}
            new_note = NoteManager.create_note(note_type=note_type, deck=deck, content_dict=content_dict, tags=[], status="new", source="manual")

            show_toast(self, "✨ Nouvelle note créée !")
            self._exit_creation_mode(refresh=True, select_note_id=new_note.id)
            self.note_created.emit(new_note.id)
        except Exception as e:
            logger.exception("Erreur lors de la création :")
            QMessageBox.critical(self, "Erreur", f"Impossible de créer la note : {e}")

    def _exit_creation_mode(self, refresh: bool = False, select_note_id: Optional[int] = None) -> None:
        self.is_creating = False
        self.btn_save_edits.setText(" Sauvegarder les modifications")
        self.btn_history.setVisible(True)
        self.creation_mode_exited.emit(refresh, select_note_id)
        if not refresh:
            self._clear_editor()
            self.btn_save_edits.setEnabled(False)
            self.btn_history.setEnabled(False)

    @Slot()
    def update_preview(self) -> None:
        note_type = None
        if self.is_creating:
            if not self.creation_model_cb:
                return
            model_id = self.creation_model_cb.currentData()
            note_type = NoteTypeModel.get_by_id(model_id)
        elif self.current_note:
            note_type = self.current_note.note_type

        if not note_type:
            self.preview_widget.set_empty_state("Sélectionnez une note pour la prévisualiser.")
            return

        current_fields = {name: editor.toPlainText().replace("\n", "<br>") for name, editor in self.field_editors.items()}
        self.preview_widget.update_preview(note_type, current_fields)
