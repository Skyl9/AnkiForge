def parse_page_ranges(scope_str: str, max_pages: int = 9999, max_page: int | None = None) -> list[int]:
    """Parse une chaîne de portée de pages (ex: '1-5, 8, 12-15') en liste d'entiers triés."""
    if max_page is not None:
        max_pages = max_page
    if not scope_str or not scope_str.strip():
        return []

    clean_str = scope_str.strip().lower()
    if clean_str in ("all", "tout", "*"):
        return list(range(1, max_pages + 1))

    pages: set[int] = set()
    parts = clean_str.replace(";", ",").split(",")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "-" in part or "à" in part or ".." in part:
            separator = "-" if "-" in part else ("à" if "à" in part else "..")
            sub_parts = part.split(separator)
            if len(sub_parts) == 2:
                try:
                    p_start = int(sub_parts[0].strip())
                    p_end = int(sub_parts[1].strip())
                    if p_start <= p_end:
                        for p in range(p_start, min(p_end, max_pages) + 1):
                            if p >= 1:
                                pages.add(p)
                    else:
                        for p in range(p_end, min(p_start, max_pages) + 1):
                            if p >= 1:
                                pages.add(p)
                except ValueError:
                    continue
        else:
            try:
                p = int(part)
                if 1 <= p <= max_pages:
                    pages.add(p)
            except ValueError:
                continue

    return sorted(list(pages))


def format_page_ranges(pages: list[int] | set[int]) -> str:
    """Formate une collection de numéros de pages en chaîne canonique condensée (ex: '1-5, 8, 12-15')."""
    if not pages:
        return ""
    sorted_p = sorted(set(pages))
    intervals: list[tuple[int, int]] = []
    start = sorted_p[0]
    end = sorted_p[0]
    for p in sorted_p[1:]:
        if p == end + 1:
            end = p
        else:
            intervals.append((start, end))
            start = p
            end = p
    intervals.append((start, end))
    parts: list[str] = []
    for s, e in intervals:
        if s == e:
            parts.append(str(s))
        else:
            parts.append(f"{s}-{e}")
    return ", ".join(parts)
