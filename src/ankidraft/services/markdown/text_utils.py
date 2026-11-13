"""Primitives de texte partagées par le structurateur et le détecteur de sommaire.

Ces fonctions sont volontairement sans état et sans dépendance : elles vivent dans
une feuille du graphe d'imports pour que `table_of_contents` (détection) et
`structurer` (outline, sections) puissent tous deux les utiliser sans créer de cycle.
"""

import re

# Balises de page générées par les parseurs (Marker notamment) : <span class="page">N</span>,
# <span id="page-X-Y">…</span>, ou équivalents <div>. Retirées INTÉGRALEMENT des titres
# (contenu inclus) pour ne pas faire fuiter un numéro de page dans le nom d'un chapitre.
_PAGE_ELEMENT_RE = re.compile(
    r"<\s*(?:span|div)\b[^>]*\bpage\b[^>]*>.*?<\s*/\s*(?:span|div)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MD_LINK_RE = re.compile(r"\[(.*?)\]\(.*?\)")
_INLINE_DELIM_RE = re.compile(r"[*_`]")
_INLINE_MATH_RE = re.compile(r"\$([^$]+)\$")
_SPACES_RE = re.compile(r"\s+")
_SLUG_STRIP_RE = re.compile(r"[^\w\s\-]", re.IGNORECASE)
_SLUG_DASH_RE = re.compile(r"[\s_]+")
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")


def clean_heading_title(text: str) -> str:
    """Nettoie un titre de ses balises HTML, ancres, formatages Markdown et KaTeX."""
    if not text:
        return ""
    # 0. Supprime intégralement les éléments de page HTML (span/div page) ET leur contenu
    cleaned = _PAGE_ELEMENT_RE.sub("", text)
    # 1. Supprime les balises HTML (<span id="...">...</span>, <span ...>, <br>, etc.)
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    # 2. Supprime les liens Markdown [texte](url) -> texte
    cleaned = _MD_LINK_RE.sub(r"\1", cleaned)
    # 3. Supprime les délimiteurs Markdown inline (gras, italique, code: *, _, `)
    cleaned = _INLINE_DELIM_RE.sub("", cleaned)
    # 4. Supprime les délimiteurs mathématiques inline ($...$)
    cleaned = _INLINE_MATH_RE.sub(r"\1", cleaned)
    # 5. Normalise les espaces
    return _SPACES_RE.sub(" ", cleaned).strip()


def slugify(text: str) -> str:
    """Génère un slug d'ancre standardisé compatible GitHub Markdown sans balises HTML résiduelles."""
    cleaned = clean_heading_title(text).lower()
    # Conserve les lettres, chiffres, tirets et espaces (supporte l'unicode/accents)
    cleaned = _SLUG_STRIP_RE.sub("", cleaned)
    # Remplace les espaces et underscores par des tirets
    return _SLUG_DASH_RE.sub("-", cleaned).strip("-") or "section"


def code_fence_lines(lines: list[str]) -> set[int]:
    """Identifie les index de lignes (0-indexés) situés à l'intérieur de blocs de code."""
    fence_lines: set[int] = set()
    in_fence = False
    fence_char = ""
    fence_len = 0

    for idx, line in enumerate(lines):
        stripped = line.strip()
        m = _FENCE_RE.match(stripped)
        if m:
            char = m.group(1)[0]
            length = len(m.group(1))
            fence_lines.add(idx)
            if not in_fence:
                in_fence = True
                fence_char = char
                fence_len = length
            elif char == fence_char and length >= fence_len:
                in_fence = False
        elif in_fence:
            fence_lines.add(idx)

    return fence_lines
