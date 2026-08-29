import re
from typing import List, Optional, Set

from ankiforge.ui.components.code_editor.models import LintIssue


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
