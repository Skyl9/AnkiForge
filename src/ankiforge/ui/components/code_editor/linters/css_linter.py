from typing import List, Optional

from ankiforge.ui.components.code_editor.models import LintIssue


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
