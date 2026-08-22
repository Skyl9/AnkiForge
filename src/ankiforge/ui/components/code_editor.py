"""
Composant d'édition de code professionnel pour AnkiForge.
Intègre :
1. Gouttière native synchronisée (LineNumberArea) peinte avec QPainter au pixel près.
2. Pastilles de couleur interactives (Color Swatches) affichées en direct dans la gouttière à côté des codes couleurs hex/rgb.
3. Coloration syntaxique temps réel (HTML / Anki / Jinja2 & CSS moderne) connectée aux DesignTokens du thème.
4. Auto-fermeture automatique des balises standard ou personnalisées (<test> -> <test></test>) et accolades.
5. Formateur de code automatique (HTML / Anki & CSS moderne) avec raccourcis clavier (Ctrl+Alt+L / Ctrl+Shift+I / Shift+Alt+F) et bouton interactif.
6. Lintage en temps réel HTML/Anki et CSS moderne (variables, clamp, calc, nesting, at-rules) avec soulignement WaveUnderline et pastilles dans la gouttière.
7. Autocomplétion contextuelle (champs {{...}}, balises <...>, classes CSS et propriétés).
8. Barre d'état de linter compacte et interactive avec bouton de formatage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List, Optional, Set, Tuple

from PySide6.QtCore import QEvent, QRect, QRegularExpression, QSize, QStringListModel, Qt, QTimer, Signal, Slot
from PySide6.QtGui import (
    QColor,
    QFont,
    QHelpEvent,
    QPaintEvent,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QCompleter,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


# =============================================================================
# 1. STRUCTURES ET MOTEURS DE LINTAGE (HTML & CSS)
# =============================================================================


@dataclass
class LintIssue:
    """Représente une anomalie détectée par le linter dans le code source."""

    line: int  # 1-indexed
    column: int  # 1-indexed
    message: str
    severity: str  # "error" | "warning"
    rule_id: str


class HTMLLinter:
    """Moteur d'analyse statique et de lintage syntaxique pour gabarits HTML / Anki."""

    VOID_TAGS: Set[str] = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    @classmethod
    def lint(cls, code: str, known_fields: Optional[List[str]] = None) -> List[LintIssue]:
        issues: List[LintIssue] = []
        if not code or not code.strip():
            return issues

        lines = code.split("\n")
        tag_stack: List[tuple[str, int, int]] = []  # (tag_name, line_num, col_num)
        tag_pattern = re.compile(r"<\s*(/)?\s*([a-zA-Z0-9_\-]+)(\s+[^>]*)?(/)?>")

        for line_num, line in enumerate(lines, start=1):
            # A. Détection des accolades doubles Anki orphelines
            open_double = line.count("{{")
            close_double = line.count("}}")
            if open_double > close_double:
                issues.append(
                    LintIssue(
                        line=line_num,
                        column=line.rfind("{{") + 1,
                        message="Accolade double Anki non fermée « {{ » (il manque « }} »).",
                        severity="error",
                        rule_id="html-unclosed-anki-brace",
                    )
                )
            elif close_double > open_double:
                issues.append(
                    LintIssue(
                        line=line_num,
                        column=line.find("}}") + 1,
                        message="Accolade fermante orpheline « }} » sans ouverture « {{ ».",
                        severity="error",
                        rule_id="html-orphan-anki-brace",
                    )
                )

            # B. Validation des balises et champs Anki
            for match in re.finditer(r"\{\{([#\^/]?)([a-zA-Z0-9_:\s\-]+)\}\}", line):
                prefix = match.group(1)
                tag_content = match.group(2).strip()
                col = match.start() + 1
                if not tag_content:
                    issues.append(
                        LintIssue(
                            line=line_num,
                            column=col,
                            message="Balise Anki vide « {{}} ».",
                            severity="warning",
                            rule_id="html-empty-anki-tag",
                        )
                    )
                    continue

                if tag_content.startswith("cloze:"):
                    field_name = tag_content.split(":", 1)[1].strip()
                    if known_fields and field_name not in known_fields:
                        issues.append(
                            LintIssue(
                                line=line_num,
                                column=col,
                                message=f"Champ « {field_name} » dans « {{{{cloze:{field_name}}}}} » non défini dans le modèle.",
                                severity="warning",
                                rule_id="html-unknown-cloze-field",
                            )
                        )
                elif tag_content in ("FrontSide", "Tags", "Deck", "Card", "Subdeck", "Type"):
                    pass  # Balises Anki natives valides
                elif known_fields and prefix in ("", "#", "^", "/"):
                    clean_field = tag_content.split(":", 1)[-1].strip()
                    if clean_field not in known_fields:
                        issues.append(
                            LintIssue(
                                line=line_num,
                                column=col,
                                message=f"Champ « {clean_field} » non présent dans les champs du modèle ({', '.join(known_fields)}).",
                                severity="warning",
                                rule_id="html-unknown-field",
                            )
                        )

            # C. Analyse des balises HTML ouvrantes/fermantes
            for match in tag_pattern.finditer(line):
                is_closing = bool(match.group(1))
                tag_name = match.group(2).lower()
                is_self_closing = bool(match.group(4))
                col = match.start() + 1

                if tag_name in cls.VOID_TAGS or is_self_closing:
                    continue

                if not is_closing:
                    tag_stack.append((tag_name, line_num, col))
                else:
                    if not tag_stack:
                        issues.append(
                            LintIssue(
                                line=line_num,
                                column=col,
                                message=f"Balise fermante inattendue </{tag_name}> sans balise ouvrante.",
                                severity="error",
                                rule_id="html-orphan-closing-tag",
                            )
                        )
                    else:
                        top_tag, top_line, top_col = tag_stack[-1]
                        if top_tag == tag_name:
                            tag_stack.pop()
                        else:
                            # Recherche plus profonde dans la pile
                            found_idx = -1
                            for idx in range(len(tag_stack) - 1, -1, -1):
                                if tag_stack[idx][0] == tag_name:
                                    found_idx = idx
                                    break
                            if found_idx != -1:
                                while len(tag_stack) > found_idx:
                                    unclosed, u_line, u_col = tag_stack.pop()
                                    if unclosed != tag_name:
                                        issues.append(
                                            LintIssue(
                                                line=u_line,
                                                column=u_col,
                                                message=f"Balise <{unclosed}> non fermée (fermée par </{tag_name}> à la ligne {line_num}).",
                                                severity="error",
                                                rule_id="html-unclosed-tag",
                                            )
                                        )
                            else:
                                issues.append(
                                    LintIssue(
                                        line=line_num,
                                        column=col,
                                        message=f"Balise fermante </{tag_name}> ne correspond pas à la balise ouvrante <{top_tag}> (ligne {top_line}).",
                                        severity="error",
                                        rule_id="html-mismatched-tag",
                                    )
                                )

        # Balises orphelines restantes en fin de document
        while tag_stack:
            unclosed, u_line, u_col = tag_stack.pop()
            issues.append(
                LintIssue(
                    line=u_line,
                    column=u_col,
                    message=f"Balise <{unclosed}> ouverte mais non fermée.",
                    severity="error",
                    rule_id="html-unclosed-tag",
                )
            )

        return issues


class CSSLinter:
    """
    Moteur d'analyse statique et de lintage syntaxique pour feuilles de style CSS modernes.
    Supporte les variables CSS (--var: val), les fonctions (clamp, calc, color-mix),
    les sélecteurs multi-lignes, les pseudo-classes, les at-rules (@media, @keyframes)
    et les blocs imbriqués (CSS nesting).
    """

    @classmethod
    def lint(cls, code: str) -> List[LintIssue]:
        issues: List[LintIssue] = []
        if not code or not code.strip():
            return issues

        brace_stack: List[tuple[int, int]] = []
        in_comment = False
        comment_start = (1, 1)

        in_string: Optional[str] = None
        string_start = (1, 1)

        line_num = 1
        col_num = 0

        current_token: List[str] = []
        token_start_line = 1
        token_start_col = 1

        i = 0
        n = len(code)

        while i < n:
            ch = code[i]
            col_num += 1

            if ch == "\n":
                line_num += 1
                col_num = 0
                i += 1
                continue

            # Gestion des commentaires CSS /* ... */
            if in_comment:
                if ch == "*" and i + 1 < n and code[i + 1] == "/":
                    in_comment = False
                    i += 2
                    col_num += 1
                    continue
                i += 1
                continue

            if ch == "/" and i + 1 < n and code[i + 1] == "*":
                in_comment = True
                comment_start = (line_num, col_num)
                i += 2
                col_num += 1
                continue

            if ch == "*" and i + 1 < n and code[i + 1] == "/":
                issues.append(
                    LintIssue(
                        line=line_num,
                        column=col_num,
                        message="Fin de commentaire « */ » orpheline sans début « /* ».",
                        severity="error",
                        rule_id="css-orphan-comment-end",
                    )
                )
                i += 2
                col_num += 1
                continue

            # Gestion des chaînes de caractères "..." ou '...'
            if in_string:
                if ch == "\\" and i + 1 < n:
                    i += 2
                    col_num += 1
                    continue
                elif ch == in_string:
                    in_string = None
                current_token.append(ch)
                i += 1
                continue

            if ch in ('"', "'"):
                in_string = ch
                string_start = (line_num, col_num)
                current_token.append(ch)
                i += 1
                continue

            # Gestion des accolades ouvrantes {
            if ch == "{":
                stmt = "".join(current_token).strip()
                current_token = []
                brace_stack.append((line_num, col_num))
                token_start_line = line_num
                token_start_col = col_num + 1
                i += 1
                continue

            # Gestion des accolades fermantes }
            elif ch == "}":
                stmt = "".join(current_token).strip()
                current_token = []
                if stmt and brace_stack:
                    cls._validate_declaration(stmt, token_start_line, token_start_col, issues)

                if not brace_stack:
                    issues.append(
                        LintIssue(
                            line=line_num,
                            column=col_num,
                            message="Accolade fermante « } » inattendue sans bloc ouvert.",
                            severity="error",
                            rule_id="css-orphan-closing-brace",
                        )
                    )
                else:
                    brace_stack.pop()
                token_start_line = line_num
                token_start_col = col_num + 1
                i += 1
                continue

            # Gestion des points-virgules ; (fin d'une déclaration)
            elif ch == ";":
                stmt = "".join(current_token).strip()
                current_token = []
                if stmt and brace_stack:
                    cls._validate_declaration(stmt, token_start_line, token_start_col, issues)
                token_start_line = line_num
                token_start_col = col_num + 1
                i += 1
                continue

            if not current_token and ch.strip():
                token_start_line = line_num
                token_start_col = col_num

            current_token.append(ch)
            i += 1

        if in_comment:
            issues.append(
                LintIssue(
                    line=comment_start[0],
                    column=comment_start[1],
                    message="Commentaire CSS « /* » non fermé.",
                    severity="error",
                    rule_id="css-unclosed-comment",
                )
            )

        if in_string:
            issues.append(
                LintIssue(
                    line=string_start[0],
                    column=string_start[1],
                    message=f"Chaîne de caractères {in_string} non fermée.",
                    severity="error",
                    rule_id="css-unclosed-string",
                )
            )

        while brace_stack:
            b_line, b_col = brace_stack.pop()
            issues.append(
                LintIssue(
                    line=b_line,
                    column=b_col,
                    message="Accolade ouvrante « { » non fermée.",
                    severity="error",
                    rule_id="css-unclosed-brace",
                )
            )

        return issues

    @classmethod
    def _validate_declaration(cls, stmt: str, line: int, col: int, issues: List[LintIssue]) -> None:
        # Ignorer les at-rules globales comme @import, @charset
        if stmt.startswith("@"):
            return

        if ":" not in stmt:
            if not stmt.startswith(("/", "*", "<!--", "-->")):
                issues.append(
                    LintIssue(
                        line=line,
                        column=col,
                        message=f"Déclaration CSS « {stmt[:30]} » invalide : séparateur « : » manquant.",
                        severity="warning",
                        rule_id="css-missing-colon",
                    )
                )
            return

        prop_part, val_part = stmt.split(":", 1)
        prop_clean = prop_part.strip()
        val_clean = val_part.strip()

        if not prop_clean:
            issues.append(
                LintIssue(
                    line=line,
                    column=col,
                    message="Nom de propriété CSS vide avant « : ».",
                    severity="error",
                    rule_id="css-empty-property",
                )
            )
        elif not val_clean:
            issues.append(
                LintIssue(
                    line=line,
                    column=col,
                    message=f"Valeur vide pour la propriété « {prop_clean} ».",
                    severity="warning",
                    rule_id="css-empty-value",
                )
            )
        else:
            # Vérifier l'équilibre des parenthèses dans les expressions CSS (clamp, var, calc, etc.)
            if val_clean.count("(") != val_clean.count(")"):
                issues.append(
                    LintIssue(
                        line=line,
                        column=col,
                        message=f"Parenthèses non équilibrées dans la valeur de « {prop_clean} ».",
                        severity="error",
                        rule_id="css-unbalanced-parens",
                    )
                )


# =============================================================================
# 2. FORMATEURS DE CODE (HTML & CSS BEAUTIFIERS)
# =============================================================================


class CSSFormatter:
    """Formateur de code CSS moderne pour harmoniser l'indentation, les sauts de lignes et espacements."""

    @classmethod
    def format(cls, css_text: str, indent_size: int = 2) -> str:
        if not css_text or not css_text.strip():
            return css_text

        indent_str = " " * indent_size
        raw = css_text.replace("\r\n", "\n").strip()

        i = 0
        n = len(raw)
        in_comment = False
        in_string = None
        current_token: List[str] = []
        tokens: List[Tuple[str, str]] = []

        while i < n:
            ch = raw[i]

            if in_comment:
                current_token.append(ch)
                if ch == "*" and i + 1 < n and raw[i + 1] == "/":
                    current_token.append("/")
                    tokens.append(("comment", "".join(current_token)))
                    current_token = []
                    in_comment = False
                    i += 2
                    continue
                i += 1
                continue

            if ch == "/" and i + 1 < n and raw[i + 1] == "*":
                if current_token:
                    stmt = "".join(current_token).strip()
                    if stmt:
                        tokens.append(("stmt", stmt))
                    current_token = []
                in_comment = True
                current_token.append("/*")
                i += 2
                continue

            if in_string:
                current_token.append(ch)
                if ch == "\\" and i + 1 < n:
                    current_token.append(raw[i + 1])
                    i += 2
                    continue
                elif ch == in_string:
                    in_string = None
                i += 1
                continue

            if ch in ('"', "'"):
                in_string = ch
                current_token.append(ch)
                i += 1
                continue

            if ch == "{":
                selector = "".join(current_token).strip()
                current_token = []
                if selector:
                    tokens.append(("selector", selector))
                tokens.append(("open_brace", "{"))
                i += 1
                continue
            elif ch == "}":
                stmt = "".join(current_token).strip()
                current_token = []
                if stmt:
                    tokens.append(("stmt", stmt))
                tokens.append(("close_brace", "}"))
                i += 1
                continue
            elif ch == ";":
                current_token.append(";")
                stmt = "".join(current_token).strip()
                current_token = []
                if stmt:
                    tokens.append(("stmt", stmt))
                i += 1
                continue

            current_token.append(ch)
            i += 1

        if current_token:
            stmt = "".join(current_token).strip()
            if stmt:
                tokens.append(("stmt", stmt))

        result_lines: List[str] = []
        indent = 0

        for ttype, content in tokens:
            if ttype == "comment":
                comm_lines = content.split("\n")
                if result_lines and result_lines[-1].strip() != "":
                    result_lines.append("")
                for c_l in comm_lines:
                    result_lines.append((indent_str * indent) + c_l.strip())
            elif ttype == "selector":
                if result_lines and result_lines[-1].strip() != "" and not result_lines[-1].endswith("{"):
                    result_lines.append("")
                sel_parts = [p.strip() for p in content.split(",") if p.strip()]
                if len(sel_parts) > 1:
                    for s_idx, part in enumerate(sel_parts):
                        suffix = "," if s_idx < len(sel_parts) - 1 else " {"
                        result_lines.append((indent_str * indent) + part + suffix)
                else:
                    result_lines.append((indent_str * indent) + content + " {")
            elif ttype == "open_brace":
                if not result_lines or not result_lines[-1].endswith("{"):
                    if result_lines:
                        result_lines[-1] = result_lines[-1] + " {"
                    else:
                        result_lines.append("{")
                indent += 1
            elif ttype == "close_brace":
                indent = max(0, indent - 1)
                result_lines.append((indent_str * indent) + "}")
                if indent == 0:
                    result_lines.append("")
            elif ttype == "stmt":
                clean_stmt = content
                if ":" in clean_stmt:
                    pname, pval = clean_stmt.split(":", 1)
                    pname = pname.strip()
                    pval = pval.strip()
                    if not pval.endswith(";") and not pval.endswith("}"):
                        pval += ";"
                    clean_stmt = f"{pname}: {pval}"
                result_lines.append((indent_str * indent) + clean_stmt)

        final_lines: List[str] = []
        prev_blank = False
        for li in result_lines:
            if not li.strip():
                if not prev_blank and final_lines:
                    final_lines.append("")
                prev_blank = True
            else:
                final_lines.append(li)
                prev_blank = False

        return "\n".join(final_lines).strip() + "\n"


class HTMLFormatter:
    """Formateur de code HTML / Jinja2 / Anki pour harmoniser la structure et l'indentation."""

    VOID_TAGS: Set[str] = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    @classmethod
    def format(cls, html_text: str, indent_size: int = 2) -> str:
        if not html_text or not html_text.strip():
            return html_text

        indent_str = " " * indent_size
        raw = html_text.replace("\r\n", "\n").strip()

        token_pattern = re.compile(
            r"(<!--.*?-->|" r"\{\{[#\^/][a-zA-Z0-9_\-]+\}\}|" r"\{\{[a-zA-Z0-9_:\s\-]+\}\}|" r"</?[a-zA-Z0-9_\-]+(?:\s+[^>]*)?/?>|" r"[^<]+)",
            re.DOTALL,
        )

        raw_tokens = token_pattern.findall(raw)
        result_lines: List[str] = []
        indent = 0

        for raw_tok in raw_tokens:
            tok = raw_tok.strip()
            if not tok:
                continue

            if tok.startswith("<!--"):
                result_lines.append((indent_str * indent) + tok)
            elif tok.startswith("{{/"):
                indent = max(0, indent - 1)
                result_lines.append((indent_str * indent) + tok)
            elif tok.startswith("{{#") or tok.startswith("{{^"):
                result_lines.append((indent_str * indent) + tok)
                indent += 1
            elif tok.startswith("</"):
                indent = max(0, indent - 1)
                result_lines.append((indent_str * indent) + tok)
            elif tok.startswith("<"):
                tag_name_match = re.match(r"<([a-zA-Z0-9_\-]+)", tok)
                t_name = tag_name_match.group(1).lower() if tag_name_match else ""
                is_void = t_name in cls.VOID_TAGS or tok.endswith("/>")
                result_lines.append((indent_str * indent) + tok)
                if not is_void:
                    indent += 1
            else:
                lines = [li.strip() for li in tok.split("\n") if li.strip()]
                for li in lines:
                    result_lines.append((indent_str * indent) + li)

        return "\n".join(result_lines).strip() + "\n"


# =============================================================================
# 3. EXTRACTION ET GESTION DES COULEURS (Color Extraction & Swatches)
# =============================================================================

COLOR_PATTERN = re.compile(r"(#[0-9a-fA-F]{3,8}\b|" r"rgba?\s*\(\s*\d+\s*,\s*\d+\s*,\s*\d+(?:\s*,\s*[\d\.]+)?\s*\)|" r"hsla?\s*\(\s*\d+\s*,\s*\d+%\s*,\s*\d+%(?:\s*,\s*[\d\.]+)?\s*\))")


def extract_colors_from_text(line_text: str) -> List[Tuple[str, QColor]]:
    """Extrait tous les codes couleurs hexadécimaux, rgb/rgba ou hsl/hsla d'une ligne de code."""
    colors: List[Tuple[str, QColor]] = []
    for match in COLOR_PATTERN.finditer(line_text):
        col_str = match.group(0)
        c = QColor(col_str)
        if not c.isValid():
            m = re.match(r"rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d\.]+))?\s*\)", col_str)
            if m:
                r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
                a = float(m.group(4)) if m.group(4) is not None else 1.0
                c = QColor(r, g, b, int(a * 255))
        if c.isValid():
            colors.append((col_str, c))
    return colors


# =============================================================================
# 4. COLORATION SYNTAXIQUE (QSyntaxHighlighter)
# =============================================================================


class HTMLSyntaxHighlighter(QSyntaxHighlighter):
    """Coloration syntaxique temps réel pour gabarits HTML et balises Anki/Jinja2."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.rules: List[tuple[QRegularExpression, QTextCharFormat]] = []
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


# =============================================================================
# 5. GOUTTIÈRE DE NUMÉROS DE LIGNES & PASTILLES DE COULEUR (LineNumberArea)
# =============================================================================


class LineNumberArea(QWidget):
    """Gouttière native peinte avec QPainter, incluant numéros de lignes, pastilles de couleur et alertes."""

    def __init__(self, editor: NativeCodeEditor) -> None:
        super().__init__(editor)
        self.code_editor = editor
        self.setMouseTracking(True)

    def sizeHint(self) -> QSize:
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event: QPaintEvent) -> None:
        self.code_editor.line_number_area_paint_event(event)

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            pos_y = event.pos().y()
            block = self.code_editor.firstVisibleBlock()
            top = int(self.code_editor.blockBoundingGeometry(block).translated(self.code_editor.contentOffset()).top())
            bottom = top + int(self.code_editor.blockBoundingRect(block).height())

            while block.isValid() and top <= self.height():
                if top <= pos_y <= bottom:
                    line_text = block.text()
                    colors = extract_colors_from_text(line_text)
                    if colors:
                        tip_parts = [f"🎨 Couleur : {c_str}" for c_str, _ in colors]
                        QToolTip.showText(event.globalPos(), "\n".join(tip_parts), self)
                        return True
                    break
                block = block.next()
                top = bottom
                bottom = top + int(self.code_editor.blockBoundingRect(block).height())

        return super().event(event)


# =============================================================================
# 6. ÉDITEUR DE CODE NATIF (NativeCodeEditor)
# =============================================================================


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

    def _update_line_number_area_width(self, _: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

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
            # Champs Anki
            for f in self._known_fields:
                words.append(f"{{{{{f}}}}}")
                words.append(f"{{{{cloze:{f}}}}}")
                words.append(f"{{{{#{f}}}}}{{{{/{f}}}}}")
            words.extend(["{{FrontSide}}", "{{Tags}}", "{{Deck}}", "{{Card}}"])
            # Balises HTML courantes
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
            # Classes
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
            # Propriétés CSS & Variables
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

        # 1. Anki Field trigger: {{...
        last_double = text_before.rfind("{{")
        if last_double != -1 and "}}" not in text_before[last_double:]:
            return "anki", text_before[last_double:]

        # 2. HTML Tag trigger: <...
        last_angle = text_before.rfind("<")
        if last_angle != -1 and ">" not in text_before[last_angle:]:
            return "html", text_before[last_angle:]

        # 3. CSS Class trigger: .class
        last_dot = text_before.rfind(".")
        if last_dot != -1 and not any(c in text_before[last_dot:] for c in (" ", "{", "}", ";", ":")):
            return "css_class", text_before[last_dot:]

        # 4. Word
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
        # A. Raccourcis de formatage : Ctrl+Alt+L, Ctrl+Shift+I, Shift+Alt+F
        is_ctrl_alt_l = event.modifiers() == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier) and event.key() == Qt.Key.Key_L
        is_ctrl_shift_i = event.modifiers() == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier) and event.key() == Qt.Key.Key_I
        is_shift_alt_f = event.modifiers() == (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier) and event.key() == Qt.Key.Key_F

        if is_ctrl_alt_l or is_ctrl_shift_i or is_shift_alt_f:
            event.accept()
            self.format_code()
            return

        # B. Navigation dans l'autocomplétion
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

        # C. Auto-fermeture automatique des balises HTML (<test> -> <test></test>)
        if event.text() == ">" and self.mode == "html":
            tc = self.textCursor()
            block_text = tc.block().text()
            pos = tc.positionInBlock()
            text_before = block_text[:pos]

            match = re.search(r"<([a-zA-Z0-9_\-]+)(\s+[^<>]*)?$", text_before)
            if match:
                tag_name = match.group(1).lower()
                full_match = match.group(0)
                # Ne pas auto-fermer les balises déjà fermantes </... ou auto-fermantes .../> ou les balises vides void
                if not full_match.startswith("</") and not full_match.rstrip().endswith("/") and tag_name not in HTMLLinter.VOID_TAGS:
                    tc.insertText(f"></{tag_name}>")
                    tc.movePosition(
                        QTextCursor.MoveOperation.Left,
                        QTextCursor.MoveMode.MoveAnchor,
                        len(f"</{tag_name}>"),
                    )
                    self.setTextCursor(tc)
                    return

        # D. Auto-fermeture des accolades Anki {{ -> {{}}
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

        # E. Déclenchement de l'autocomplétion
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


# =============================================================================
# 7. BARRE DE STATUT DE LINTAGE AVEC BOUTON FORMATER (LintStatusBar)
# =============================================================================


class LintStatusBar(QFrame):
    """Barre inférieure élégante affichant la synthèse du linter avec clic pour navigation et bouton formater."""

    def __init__(self, editor: NativeCodeEditor, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.editor = editor
        self.setObjectName("lintStatusBar")
        self.setFixedHeight(28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setStyleSheet(f"""
            QFrame#lintStatusBar {{
                background-color: {DesignTokens.BG_SIDEBAR};
                border-top: 1px solid {DesignTokens.BORDER_COLOR};
                border-bottom-left-radius: {DesignTokens.RADIUS_SM}px;
                border-bottom-right-radius: {DesignTokens.RADIUS_SM}px;
                padding: 2px 8px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(6)

        self.icon_lbl = QLabel()
        self.icon_lbl.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.icon_lbl)

        self.status_lbl = QLabel("Syntaxe valide")
        self.status_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        layout.addWidget(self.status_lbl, 1)

        # Bouton Formater le code (Ctrl+Alt+L)
        self.format_btn = QPushButton("Formater")
        self.format_btn.setIcon(load_phosphor_icon("ph.magic-wand", color=DesignTokens.TEXT_SECONDARY))
        self.format_btn.setIconSize(QSize(13, 13))
        self.format_btn.setToolTip("Formater le document (Ctrl+Alt+L / Ctrl+Shift+I)")
        self.format_btn.setFixedHeight(20)
        self.format_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.format_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_SECONDARY};
                font-size: 10px;
                font-weight: 500;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 1px 7px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.format_btn.clicked.connect(self.editor.format_code)
        layout.addWidget(self.format_btn)

        self.editor.lint_issues_changed.connect(self.update_status)
        self.update_status([])

    @Slot(list)
    def update_status(self, issues: List[LintIssue]) -> None:
        if not issues:
            self.icon_lbl.setPixmap(load_phosphor_icon("ph.check-circle", color=DesignTokens.COLOR_GREEN).pixmap(14, 14))
            self.status_lbl.setText("Syntaxe valide")
            self.status_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 11px; font-weight: 500;")
            self.setToolTip("Aucune anomalie détectée.")
        else:
            errors = [i for i in issues if i.severity == "error"]
            warnings = [i for i in issues if i.severity == "warning"]

            if errors:
                self.icon_lbl.setPixmap(load_phosphor_icon("ph.x-circle", color=DesignTokens.COLOR_RED).pixmap(14, 14))
                summary = f"{len(errors)} erreur{'s' if len(errors) > 1 else ''} : {errors[0].message}"
                self.status_lbl.setText(summary)
                self.status_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_RED}; font-size: 11px; font-weight: 500;")
            else:
                self.icon_lbl.setPixmap(load_phosphor_icon("ph.warning", color=DesignTokens.COLOR_YELLOW).pixmap(14, 14))
                summary = f"{len(warnings)} avertissement{'s' if len(warnings) > 1 else ''} : {warnings[0].message}"
                self.status_lbl.setText(summary)
                self.status_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; font-weight: 500;")

            tooltip_text = "\n".join(f"• Ligne {iss.line} : {iss.message}" for iss in issues)
            self.setToolTip(f"Cliquez pour aller à la première anomalie :\n{tooltip_text}")

    def mousePressEvent(self, event: Any) -> None:
        issues = self.editor.get_lint_issues()
        if issues:
            self.editor.jump_to_line(issues[0].line)
        super().mousePressEvent(event)


# =============================================================================
# 8. CONTENEUR ÉDITEUR AVEC GOUTTIÈRE & LINT STATUS (CodeEditorWithGutter)
# =============================================================================


class CodeEditorWithGutter(QFrame):
    """
    Conteneur d'édition de code haut niveau encapsulant l'éditeur natif,
    la coloration syntaxique, la gouttière synchronisée avec pastilles de couleur,
    le linter temps réel, le formateur de code et la barre d'état.
    """

    textChanged = Signal()

    def __init__(
        self,
        placeholder: str = "",
        mode: str = "html",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("codeEditorWrapper")

        self.setStyleSheet(f"""
            QFrame#codeEditorWrapper {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-top: 1px solid {DesignTokens.BORDER_LIGHT};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QFrame#codeEditorWrapper:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Éditeur natif avec gouttière et coloration syntaxique
        self.native_editor = NativeCodeEditor(mode=mode, placeholder=placeholder, parent=self)
        self.native_editor.textChanged.connect(self.textChanged.emit)
        layout.addWidget(self.native_editor, 1)

        # Barre de statut de linter avec bouton de formatage
        self.lint_status_bar = LintStatusBar(self.native_editor, parent=self)
        layout.addWidget(self.lint_status_bar)

    @property
    def editor(self) -> NativeCodeEditor:
        """Permet l'accès transparent à l'instance NativeCodeEditor."""
        return self.native_editor

    def toPlainText(self) -> str:
        return self.native_editor.toPlainText()

    def setPlainText(self, text: str) -> None:
        self.native_editor.setPlainText(text)

    def insertPlainText(self, text: str) -> None:
        self.native_editor.insertPlainText(text)

    def clear(self) -> None:
        self.native_editor.clear()

    def set_known_fields(self, fields: List[str]) -> None:
        self.native_editor.set_known_fields(fields)

    def set_custom_classes(self, classes: List[str]) -> None:
        self.native_editor.set_custom_classes(classes)

    def get_lint_issues(self) -> List[LintIssue]:
        return self.native_editor.get_lint_issues()

    def jump_to_line(self, line_num: int) -> None:
        self.native_editor.jump_to_line(line_num)

    def format_code(self) -> None:
        self.native_editor.format_code()

    def refresh_theme(self) -> None:
        """Rafraîchit la coloration syntaxique et les styles lors d'un changement de thème."""
        self.native_editor.refresh_highlighter()
