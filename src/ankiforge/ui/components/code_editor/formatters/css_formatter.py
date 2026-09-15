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
        current_token: list[str] = []
        tokens: list[tuple[str, str]] = []

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

        result_lines: list[str] = []
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

        final_lines: list[str] = []
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
