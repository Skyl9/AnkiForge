import re


class HTMLFormatter:
    """Formateur de code HTML / Jinja2 / Anki pour harmoniser la structure et l'indentation."""

    VOID_TAGS: set[str] = {
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
        result_lines: list[str] = []
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
