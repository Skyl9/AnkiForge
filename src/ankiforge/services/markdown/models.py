"""Modèles de données pour les services de formatage et structuration Markdown."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FormatOptions:
    """Options de configuration pour le formatage d'un document Markdown."""

    dehyphenate_ocr: bool = True
    normalize_katex: bool = True
    align_tables: bool = True
    normalize_headings: bool = True
    clean_whitespace: bool = True
    normalize_code_fences: bool = True


@dataclass
class HeadingNode:
    """Nœud d'arborescence hiérarchique d'un titre de document."""

    level: int
    title: str
    slug: str
    line_number: int  # 1-indexé
    end_line: int | None = None  # 1-indexé
    word_count: int = 0
    children: list["HeadingNode"] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Convertit le nœud et ses enfants en dictionnaire sérialisable."""
        return {
            "level": self.level,
            "title": self.title,
            "slug": self.slug,
            "line_number": self.line_number,
            "end_line": self.end_line,
            "word_count": self.word_count,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass(frozen=True)
class OutlineItem:
    """Élément plat d'arborescence pour navigation rapide."""

    level: int
    title: str
    slug: str
    line_number: int  # 1-indexé
    breadcrumb: str

    def to_dict(self) -> dict[str, object]:
        """Convertit l'élément en dictionnaire sérialisable."""
        return {
            "level": self.level,
            "title": self.title,
            "slug": self.slug,
            "line_number": self.line_number,
            "breadcrumb": self.breadcrumb,
        }


@dataclass
class DocumentSection:
    """Section sémantique découpée selon les titres pour le RAG et la Forge."""

    heading_path: str
    level: int
    title: str
    content: str
    start_line: int  # 1-indexé
    end_line: int  # 1-indexé
    word_count: int
    token_estimate: int

    def to_dict(self) -> dict[str, object]:
        """Convertit la section en dictionnaire sérialisable."""
        return {
            "heading_path": self.heading_path,
            "level": self.level,
            "title": self.title,
            "content": self.content,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "word_count": self.word_count,
            "token_estimate": self.token_estimate,
        }


@dataclass(frozen=True)
class FormatResult:
    """Résultat d'une opération de formatage Markdown."""

    formatted_text: str
    changed: bool
    changes_summary: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Convertit le résultat en dictionnaire sérialisable."""
        return {
            "formatted_text": self.formatted_text,
            "changed": self.changed,
            "changes_summary": list(self.changes_summary),
        }
