from __future__ import annotations

import re
from typing import Any, List, Optional
from PySide6.QtCore import QRect, QStringListModel, Qt, QTimer, Signal, Slot
from PySide6.QtGui import (
    QColor,
    QFont,
    QPaintEvent,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QCompleter,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

from ankiforge.ui.components.code_editor.color_utils import extract_colors_from_text
from ankiforge.ui.components.code_editor.formatters.css_formatter import CSSFormatter
from ankiforge.ui.components.code_editor.formatters.html_formatter import HTMLFormatter
from ankiforge.ui.components.code_editor.highlighters.css_highlighter import CSSSyntaxHighlighter
from ankiforge.ui.components.code_editor.highlighters.html_highlighter import HTMLSyntaxHighlighter
from ankiforge.ui.components.code_editor.linters.css_linter import CSSLinter
from ankiforge.ui.components.code_editor.linters.html_linter import HTMLLinter
from ankiforge.ui.components.code_editor.models import LintIssue
from ankiforge.ui.components.code_editor.widgets.gutter import LineNumberArea
from ankiforge.ui.theme import DesignTokens


class NativeCodeEditor(QPlainTextEdit):
    """
    Éditeur de code avec numéros de lignes natifs, pastilles de couleurs,
    coloration syntaxique temps réel, formatage de code et autocomplétion.
    """

    lint_issues_changed = Signal(list)

    def __init__(
        self,
        mode: str = "html",
        placeholder: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.mode = mode.lower()  # "html" | "css"
        self._known_fields: List[str] = []
        self._custom_classes: List[str] = []
        self._lint_issues: List[LintIssue] = []

        # Police et styles de base
        font = QFont(DesignTokens.FONT_CODE, 12)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setPlaceholderText(placeholder)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

        # Initialisation de la gouttière
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)

        self._update_line_number_area_width(0)

        # Coloration syntaxique temps réel
        self._init_highlighter()

        # Timer de debouncing pour le linter temps réel (150ms)
        self._lint_timer = QTimer(self)
        self._lint_timer.setSingleShot(True)
        self._lint_timer.setInterval(150)
        self._lint_timer.timeout.connect(self.run_linter)

        self.textChanged.connect(self._on_text_changed)

        # Autocomplétion
        self._init_completer()

        self._apply_base_style()
        self._highlight_current_line()

    def _init_highlighter(self) -> None:
        if self.mode == "html":
            self.highlighter: Optional[QSyntaxHighlighter] = HTMLSyntaxHighlighter(self.document())
        elif self.mode == "css":
            self.highlighter = CSSSyntaxHighlighter(self.document())
        else:
            self.highlighter = None

    def refresh_highlighter(self) -> None:
        """Met à jour les couleurs de la syntaxe suite à un changement de thème."""
        if hasattr(self, "highlighter") and self.highlighter is not None:
            if hasattr(self.highlighter, "update_formats"):
                self.highlighter.update_formats()
            self.highlighter.rehighlight()

    def _apply_base_style(self) -> None:
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 12px;
                line-height: 1.5;
                padding: 6px;
                border: none;
                border-top-right-radius: {DesignTokens.RADIUS_SM}px;
                border-bottom-right-radius: {DesignTokens.RADIUS_SM}px;
                selection-background-color: {DesignTokens.ACCENT_PRIMARY};
                selection-color: #ffffff;
            }}
        """)

    # --- Gestion de la Gouttière & Pastilles de Couleur ---
    def line_number_area_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        char_width = self.fontMetrics().horizontalAdvance("9")
        # 38px de base pour pastilles de couleur (10px) + puces d'alerte (6px) + marges
        return 38 + char_width * max(2, digits)

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
        painter.fillRect(event.rect(), QColor(DesignTokens.BG_SIDEBAR))

        # Ligne de séparation droite
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
                line_idx = block_number + 1
                number_str = str(line_idx)
                line_text = block.text()

                # A. Puces d'erreur / warning de linting (x = 5)
                line_issues = [iss for iss in self._lint_issues if iss.line == line_idx]
                if line_issues:
                    has_error = any(iss.severity == "error" for iss in line_issues)
                    dot_color = QColor(DesignTokens.COLOR_RED if has_error else DesignTokens.COLOR_YELLOW)
                    painter.setBrush(dot_color)
                    painter.setPen(Qt.PenStyle.NoPen)
                    dot_y = top + (self.fontMetrics().height() - 6) // 2 + 2
                    painter.drawEllipse(5, dot_y, 6, 6)

                # B. Pastilles de couleur interactives (x = 15)
                colors = extract_colors_from_text(line_text)
                if colors:
                    swatch_color = colors[0][1]
                    swatch_y = top + (self.fontMetrics().height() - 10) // 2 + 2
                    painter.setBrush(swatch_color)
                    # Bordure subtile pour détacher les couleurs sombres ou blanches du fond
                    border_c = QColor(255, 255, 255, 80) if DesignTokens.IS_DARK else QColor(0, 0, 0, 60)
                    painter.setPen(border_c)
                    painter.drawRoundedRect(14, swatch_y, 10, 10, 2.5, 2.5)

                # C. Numéro de ligne (aligné à droite)
                is_current = block_number == current_block_num
                color = QColor(DesignTokens.ACCENT_PRIMARY if is_current else DesignTokens.TEXT_MUTED)
                painter.setPen(color)
                painter.setFont(self.font())
                painter.drawText(
                    0,
                    top + 2,
                    self.line_number_area.width() - 8,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number_str,
                )

            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def _highlight_current_line(self) -> None:
        self._apply_extra_selections()

    # --- Formatage Automatique de Code (Beautify / Indentation) ---
    @Slot()
    def format_code(self) -> None:
        """Formate le document complet avec une indentation et un espacement propres."""
        raw_code = self.toPlainText()
        if not raw_code.strip():
            return

        cursor = self.textCursor()
        pos = cursor.position()

        if self.mode == "css":
            formatted = CSSFormatter.format(raw_code)
        elif self.mode == "html":
            formatted = HTMLFormatter.format(raw_code)
        else:
            formatted = raw_code

        if formatted != raw_code:
            self.setPlainText(formatted)
            cursor.setPosition(min(pos, len(formatted)))
            self.setTextCursor(cursor)
            self.run_linter()

    # --- Lintage Temps Réel & Visualisation ---
    def set_known_fields(self, fields: List[str]) -> None:
        self._known_fields = list(fields)
        self._update_autocomplete_model()
        self.run_linter()

    def set_custom_classes(self, classes: List[str]) -> None:
        self._custom_classes = list(classes)
        self._update_autocomplete_model()

    def get_lint_issues(self) -> List[LintIssue]:
        return list(self._lint_issues)

    def jump_to_line(self, line_num: int) -> None:
        block = self.document().findBlockByLineNumber(max(0, line_num - 1))
        if block.isValid():
            cursor = QTextCursor(block)
            self.setTextCursor(cursor)
            self.setFocus()

    def _on_text_changed(self) -> None:
        self._lint_timer.start()

    @Slot()
    def run_linter(self) -> None:
        code = self.toPlainText()
        if self.mode == "html":
            self._lint_issues = HTMLLinter.lint(code, known_fields=self._known_fields)
        elif self.mode == "css":
            self._lint_issues = CSSLinter.lint(code)
        else:
            self._lint_issues = []

        self.line_number_area.update()
        self._apply_extra_selections()
        self.lint_issues_changed.emit(self._lint_issues)

    def _apply_extra_selections(self) -> None:
        extra_selections: List[QTextEdit.ExtraSelection] = []

        # 1. Surlignage de la ligne courante
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(QColor(DesignTokens.BG_HOVER))
            selection.format.setProperty(int(QTextCharFormat.Property.FullWidthSelection), True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)

        # 2. Soulignement wavy sous les erreurs de linter
        for issue in self._lint_issues:
            block = self.document().findBlockByLineNumber(issue.line - 1)
            if block.isValid():
                sel = QTextEdit.ExtraSelection()
                sel.cursor = QTextCursor(block)
                sel.cursor.select(QTextCursor.SelectionType.LineUnderCursor)

                fmt = QTextCharFormat()
                color = QColor(DesignTokens.COLOR_RED if issue.severity == "error" else DesignTokens.COLOR_YELLOW)
                fmt.setUnderlineColor(color)
                fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
                fmt.setToolTip(issue.message)
                sel.format = fmt
                extra_selections.append(sel)

        self.setExtraSelections(extra_selections)

    # --- Autocomplétion Contextuelle (QCompleter) ---
    def _init_completer(self) -> None:
        self.completer = QCompleter(self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.activated.connect(self._insert_completion)

        popup = self.completer.popup()
        popup.setStyleSheet(f"""
            QListView {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px;
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 11px;
            }}
            QListView::item {{
                padding: 4px 8px;
                border-radius: 4px;
            }}
            QListView::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
                color: {DesignTokens.TEXT_PRIMARY};
                font-weight: bold;
            }}
        """)

        self._update_autocomplete_model()

    def _update_autocomplete_model(self) -> None:
        words: List[str] = []
        if self.mode == "html":
            for f in self._known_fields:
                words.append(f"{{{{{f}}}}}")
                words.append(f"{{{{cloze:{f}}}}}")
                words.append(f"{{{{#{f}}}}}{{{{/{f}}}}}")
            words.extend(["{{FrontSide}}", "{{Tags}}", "{{Deck}}", "{{Card}}"])
            words.extend(
                [
                    '<div class="card">',
                    '<span class="highlight">',
                    '<hr id="answer">',
                    "<br>",
                    "<p>",
                    "<b>",
                    "<i>",
                    "<code>",
                ]
            )
        elif self.mode == "css":
            words.extend(
                [
                    ".card",
                    ".af-callout-info",
                    ".af-callout-warning",
                    ".af-callout-danger",
                    ".af-callout-tip",
                    ".af-badge-diff",
                    ".cloze",
                    ".nightMode",
                ]
            )
            for c in self._custom_classes:
                clean_c = c if c.startswith(".") else f".{c}"
                if clean_c not in words:
                    words.append(clean_c)
            words.extend(
                [
                    "background-color: ",
                    "color: ",
                    "font-size: ",
                    "font-weight: bold;",
                    "font-family: ",
                    "border: ",
                    "border-radius: ",
                    "padding: ",
                    "margin: ",
                    "text-align: center;",
                    "display: flex;",
                    "box-shadow: ",
                    "var(--",
                    "clamp(",
                    "calc(",
                    "color-mix(",
                    "linear-gradient(",
                ]
            )

        model = QStringListModel(words, self.completer)
        self.completer.setModel(model)

    def _get_completion_prefix(self) -> tuple[str, str]:
        tc = self.textCursor()
        block_text = tc.block().text()
        pos = tc.positionInBlock()
        text_before = block_text[:pos]

        last_double = text_before.rfind("{{")
        if last_double != -1 and "}}" not in text_before[last_double:]:
            return "anki", text_before[last_double:]

        last_angle = text_before.rfind("<")
        if last_angle != -1 and ">" not in text_before[last_angle:]:
            return "html", text_before[last_angle:]

        last_dot = text_before.rfind(".")
        if last_dot != -1 and not any(c in text_before[last_dot:] for c in (" ", "{", "}", ";", ":")):
            return "css_class", text_before[last_dot:]

        tc.select(QTextCursor.SelectionType.WordUnderCursor)
        return "word", tc.selectedText()

    @Slot(str)
    def _insert_completion(self, completion: str) -> None:
        tc = self.textCursor()
        _, prefix = self._get_completion_prefix()
        if prefix:
            tc.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, len(prefix))
        tc.insertText(completion)
        self.setTextCursor(tc)

    def keyPressEvent(self, event: Any) -> None:
        is_ctrl_alt_l = event.modifiers() == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier) and event.key() == Qt.Key.Key_L
        is_ctrl_shift_i = event.modifiers() == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier) and event.key() == Qt.Key.Key_I
        is_shift_alt_f = event.modifiers() == (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier) and event.key() == Qt.Key.Key_F

        if is_ctrl_alt_l or is_ctrl_shift_i or is_shift_alt_f:
            event.accept()
            self.format_code()
            return

        if self.completer and self.completer.popup().isVisible():
            if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Tab):
                event.ignore()
                current_completion = self.completer.currentCompletion()
                if current_completion:
                    self._insert_completion(current_completion)
                self.completer.popup().hide()
                return
            elif event.key() == Qt.Key.Key_Escape:
                self.completer.popup().hide()
                event.ignore()
                return

        if event.text() == ">" and self.mode == "html":
            tc = self.textCursor()
            block_text = tc.block().text()
            pos = tc.positionInBlock()
            text_before = block_text[:pos]

            match = re.search(r"<([a-zA-Z0-9_\-]+)(\s+[^<>]*)?$", text_before)
            if match:
                tag_name = match.group(1).lower()
                full_match = match.group(0)
                if not full_match.startswith("</") and not full_match.rstrip().endswith("/") and tag_name not in HTMLLinter.VOID_TAGS:
                    tc.insertText(f"></{tag_name}>")
                    tc.movePosition(
                        QTextCursor.MoveOperation.Left,
                        QTextCursor.MoveMode.MoveAnchor,
                        len(f"</{tag_name}>"),
                    )
                    self.setTextCursor(tc)
                    return

        if event.text() == "{" and self.mode == "html":
            tc = self.textCursor()
            block_text = tc.block().text()
            pos = tc.positionInBlock()
            text_before = block_text[:pos]
            if text_before.endswith("{"):
                tc.insertText("{}}")
                tc.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 2)
                self.setTextCursor(tc)
                return

        super().keyPressEvent(event)

        _, prefix = self._get_completion_prefix()
        if prefix and len(prefix) >= 1:
            self.completer.setCompletionPrefix(prefix)
            popup = self.completer.popup()
            popup.setCurrentIndex(self.completer.completionModel().index(0, 0))
            cr = self.cursorRect()
            cr.setWidth(self.completer.popup().sizeHintForColumn(0) + self.completer.popup().verticalScrollBar().sizeHint().width() + 20)
            self.completer.complete(cr)
        elif self.completer:
            self.completer.popup().hide()
