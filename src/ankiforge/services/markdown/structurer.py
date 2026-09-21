"""Moteur d'analyse structurelle AST, Table des Matières et découpage sémantique Markdown."""

import logging
import re

from markdown_it import MarkdownIt

from ankiforge.services.markdown.models import (
    DocumentSection,
    HeadingNode,
    HeadingRepairItem,
    OutlineItem,
)

logger = logging.getLogger(__name__)


class MarkdownStructurer:
    """Service d'analyse AST CommonMark, navigation hiérarchique et découpage sémantique.

    Caractéristiques :
    - Extraction rapide de l'arborescence (Outline) avec numéros de lignes et breadcrumbs.
    - Génération de Table des Matières (TOC) avec ancres compatibles GitHub/KaTeX.
    - Réparation intelligente des sauts de hiérarchie (ex: H1 suivi directement de H3).
    - Découpage en sections sémantiques enrichies avec breadcrumbs pour le RAG et la Forge.
    """

    _parser: MarkdownIt | None = None

    @classmethod
    def get_parser(cls) -> MarkdownIt:
        """Fournit une instance partagée du parseur CommonMark avec support des tables."""
        if cls._parser is None:
            cls._parser = MarkdownIt().enable("table")
        return cls._parser

    @classmethod
    def clean_heading_title(cls, text: str) -> str:
        """Nettoie un titre de ses balises HTML, ancres, formatages Markdown et KaTeX."""
        if not text:
            return ""
        # 1. Supprime les balises HTML (<span id="...">...</span>, <span ...>, <br>, etc.)
        cleaned = re.sub(r"<[^>]+>", "", text)
        # 2. Supprime les liens Markdown [texte](url) -> texte
        cleaned = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", cleaned)
        # 3. Supprime les délimiteurs Markdown inline (gras, italique, code: *, _, `)
        cleaned = re.sub(r"[*_`]", "", cleaned)
        # 4. Supprime les délimiteurs mathématiques inline ($...$)
        cleaned = re.sub(r"\$([^$]+)\$", r"\1", cleaned)
        # 5. Normalise les espaces
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @classmethod
    def slugify(cls, text: str) -> str:
        """Génère un slug d'ancre standardisé compatible GitHub Markdown sans balises HTML résiduelles."""
        cleaned = cls.clean_heading_title(text).lower()
        # Conserve les lettres, chiffres, tirets et espaces (supporte l'unicode/accents)
        cleaned = re.sub(r"[^\w\s\-]", "", cleaned)
        # Remplace les espaces et underscores par des tirets
        cleaned = re.sub(r"[\s_]+", "-", cleaned)
        return cleaned.strip("-") or "section"

    @classmethod
    def get_outline(cls, text: str) -> list[OutlineItem]:
        """Extrait la liste ordonnée des titres avec leur niveau, ligne et fil d'Ariane."""
        if not text or not text.strip():
            return []

        tokens = cls.get_parser().parse(text)
        outline: list[OutlineItem] = []
        heading_stack: list[str] = []

        for i, token in enumerate(tokens):
            if token.type == "heading_open":
                level = int(token.tag[1:]) if len(token.tag) > 1 and token.tag[1:].isdigit() else 1
                line_number = (token.map[0] + 1) if token.map else 1

                # Le contenu du titre se trouve dans le token inline suivant.
                # On nettoie les balises HTML/Markdown résiduelles (spans de page Marker,
                # formatage inline laissé par markdownify, etc.).
                title = ""
                if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                    title = cls.clean_heading_title(tokens[i + 1].content)

                if not title:
                    title = f"Section {line_number}"

                # Mise à jour de la pile hiérarchique
                heading_stack = heading_stack[: level - 1]
                while len(heading_stack) < level - 1:
                    heading_stack.append("Section")
                heading_stack.append(title)

                breadcrumb = " > ".join(heading_stack)
                slug = cls.slugify(title)

                outline.append(
                    OutlineItem(
                        level=level,
                        title=title,
                        slug=slug,
                        line_number=line_number,
                        breadcrumb=breadcrumb,
                    )
                )

        return outline

    @classmethod
    def get_outline_tree(cls, text: str) -> list[HeadingNode]:
        """Construit l'arbre hiérarchique imbriqué des titres avec calcul de mots et lignes."""
        outline = cls.get_outline(text)
        if not outline:
            return []

        lines = text.split("\n")
        total_lines = len(lines)

        # Création des nœuds
        nodes: list[HeadingNode] = [
            HeadingNode(
                level=item.level,
                title=item.title,
                slug=item.slug,
                line_number=item.line_number,
            )
            for item in outline
        ]

        # Calcul des lignes de fin et comptage des mots
        for i, node in enumerate(nodes):
            if i + 1 < len(nodes):
                node.end_line = max(node.line_number, nodes[i + 1].line_number - 1)
            else:
                node.end_line = total_lines

            # Comptage des mots dans la plage de lignes
            section_lines = lines[node.line_number - 1 : node.end_line]
            section_text = "\n".join(section_lines)
            node.word_count = len(section_text.split())

        # Assemblage récursif de l'arbre
        root_nodes: list[HeadingNode] = []
        stack: list[HeadingNode] = []

        for node in nodes:
            while stack and stack[-1].level >= node.level:
                stack.pop()

            if not stack:
                root_nodes.append(node)
            else:
                stack[-1].children.append(node)

            stack.append(node)

        return root_nodes

    @staticmethod
    def _get_code_fence_lines(lines: list[str]) -> set[int]:
        """Identifie les index de lignes (0-indexés) situés à l'intérieur de blocs de code."""
        fence_lines: set[int] = set()
        in_fence = False
        fence_char = ""
        fence_len = 0

        for idx, line in enumerate(lines):
            stripped = line.strip()
            m = re.match(r"^(`{3,}|~{3,})", stripped)
            if m:
                char = m.group(1)[0]
                length = len(m.group(1))
                if not in_fence:
                    in_fence = True
                    fence_char = char
                    fence_len = length
                    fence_lines.add(idx)
                elif char == fence_char and length >= fence_len:
                    in_fence = False
                    fence_lines.add(idx)
                else:
                    fence_lines.add(idx)
            elif in_fence:
                fence_lines.add(idx)

        return fence_lines

    @classmethod
    def detect_heading_hierarchy_issues(cls, text: str) -> list[HeadingRepairItem]:
        """Détecte les sauts anormaux de hiérarchie (ex: H1 -> H3) en ignorant les blocs de code."""
        if not text or not text.strip():
            return []

        lines = text.split("\n")
        fence_lines = cls._get_code_fence_lines(lines)
        outline = cls.get_outline(text)
        if not outline:
            return []

        repairs: list[HeadingRepairItem] = []
        current_depth = 0

        for item in outline:
            line_idx = item.line_number - 1
            if line_idx in fence_lines:
                continue

            if current_depth == 0:
                # Premier titre : tolère un démarrage en H1 ou H2
                current_depth = item.level
                continue

            if item.level > current_depth + 1:
                target_level = current_depth + 1
                reason = f"Saut de niveau anormal (H{current_depth} ➔ H{item.level})"
                raw_line = lines[line_idx] if 0 <= line_idx < len(lines) else f"{'#' * item.level} {item.title}"
                clean_title = cls.clean_heading_title(item.title)
                repairs.append(
                    HeadingRepairItem(
                        line_number=item.line_number,
                        raw_line=raw_line,
                        title=clean_title,
                        old_level=item.level,
                        new_level=target_level,
                        reason=reason,
                    )
                )
                current_depth = target_level
            else:
                current_depth = item.level

        return repairs

    @classmethod
    def apply_heading_repairs(cls, text: str, repairs: list[HeadingRepairItem]) -> str:
        """Applique les corrections sélectionnées sur les titres du document."""
        if not repairs or not text:
            return text

        lines = text.split("\n")
        repair_map = {r.line_number - 1: r.new_level for r in repairs}

        for idx, new_level in repair_map.items():
            if 0 <= idx < len(lines):
                old_line = lines[idx]
                m = re.match(r"^(#{1,6})\s*(.*)$", old_line)
                if m:
                    content_part = m.group(2)
                    lines[idx] = f"{'#' * new_level} {content_part}"

        return "\n".join(lines)

    @classmethod
    def repair_heading_hierarchy(cls, text: str) -> tuple[str, list[str]]:
        """Détecte et répare automatiquement tous les sauts de niveau illégaux."""
        repairs = cls.detect_heading_hierarchy_issues(text)
        if not repairs:
            return text, []

        repaired_text = cls.apply_heading_repairs(text, repairs)
        changes = [f"Ligne {r.line_number}: Titre '{r.title}' ajusté de H{r.old_level} à H{r.new_level} ({r.reason})" for r in repairs]
        return repaired_text, changes

    @classmethod
    def generate_toc(cls, text: str, max_depth: int = 3, ordered: bool = False) -> str:
        """Génère une Table des Matières (TOC) standardisée, délimitée et propre."""
        outline = cls.get_outline(text)
        if not outline:
            return ""

        ignored_names = {"table des matières", "table des matieres", "sommaire", "table of contents", "toc"}

        filtered: list[tuple[int, str, str]] = []
        for item in outline:
            clean_title = cls.clean_heading_title(item.title)
            if clean_title.lower() in ignored_names:
                continue
            if item.level <= max_depth:
                filtered.append((item.level, clean_title, item.slug or cls.slugify(clean_title)))

        if not filtered:
            return ""

        min_level = min(level for level, _, _ in filtered)
        toc_lines: list[str] = [
            "<!-- toc -->",
            "## Table des Matières",
            "",
        ]

        counters = [0] * 7

        for level, title, slug in filtered:
            indent_level = level - min_level
            indent = "  " * indent_level

            if ordered:
                counters[level] += 1
                for deeper in range(level + 1, 7):
                    counters[deeper] = 0
                prefix = f"{counters[level]}."
            else:
                prefix = "-"

            toc_lines.append(f"{indent}{prefix} [{title}](#{slug})")

        toc_lines.append("<!-- /toc -->")
        return "\n".join(toc_lines)

    @classmethod
    def insert_or_update_toc(cls, text: str, max_depth: int = 3, ordered: bool = False) -> tuple[str, bool]:
        """Insère ou met à jour in-place la Table des Matières dans le document Markdown.

        Returns:
            Tuple (nouveau_texte, modifie_ou_non)
        """
        if not text or not text.strip():
            return text, False

        toc_block = cls.generate_toc(text, max_depth=max_depth, ordered=ordered)
        if not toc_block:
            return text, False

        # 1. Remplacement si un bloc <!-- toc --> ... <!-- /toc --> existe déjà
        toc_marker_pattern = re.compile(r"<!--\s*toc\s*-->[\s\S]*?<!--\s*/toc\s*-->\n*", re.IGNORECASE)
        if toc_marker_pattern.search(text):
            updated = toc_marker_pattern.sub(f"{toc_block}\n\n", text, count=1)
            return updated, True

        # 2. Remplacement si une section '## Table des Matières' non balisée existe
        existing_toc_pattern = re.compile(
            r"^#{1,3}\s+(?:Table des Matières|Table des matieres|Sommaire|TOC|Table of contents)\b[\s\S]*?(?=\n#{1,3}\s|\Z)",
            re.MULTILINE | re.IGNORECASE,
        )
        if existing_toc_pattern.search(text):
            updated = existing_toc_pattern.sub(f"{toc_block}\n\n", text, count=1)
            return updated, True

        # 3. Insertion intelligente si aucun sommaire n'existe
        # A. Après frontmatter YAML si présent
        frontmatter_pattern = re.compile(r"^---\n[\s\S]*?\n---\n*", re.MULTILINE)
        fm_match = frontmatter_pattern.match(text)
        if fm_match:
            insert_pos = fm_match.end()
            remainder = text[insert_pos:].lstrip("\n")
            new_text = f"{text[:insert_pos].rstrip()}\n\n{toc_block}\n\n{remainder}"
            return new_text, True

        # B. Après premier séparateur de page OCR {0}-------- si au tout début
        page_pattern = re.compile(r"^(?:\{\d+\}-+\s*\n*)", re.MULTILINE)
        page_match = page_pattern.match(text)
        prefix_len = page_match.end() if page_match else 0

        # C. Après le premier titre H1 du document
        h1_pattern = re.compile(r"^(#\s+[^\n]+(?:\n\n[^\n#][^\n]*)?)", re.MULTILINE)
        h1_match = h1_pattern.search(text[prefix_len:])
        if h1_match:
            insert_pos = prefix_len + h1_match.end()
            remainder = text[insert_pos:].lstrip("\n")
            new_text = f"{text[:insert_pos].rstrip()}\n\n{toc_block}\n\n{remainder}"
            return new_text, True

        # D. Sinon, insère après le séparateur de page initial ou en début
        if prefix_len > 0:
            remainder = text[prefix_len:].lstrip("\n")
            new_text = f"{text[:prefix_len].rstrip()}\n\n{toc_block}\n\n{remainder}"
        else:
            remainder = text.lstrip("\n")
            new_text = f"{toc_block}\n\n{remainder}"
        return new_text, True

    @classmethod
    def extract_sections(cls, text: str, max_tokens: int | None = None) -> list[DocumentSection]:
        """Découpe un document Markdown en sections sémantiques autonomes avec fil d'Ariane.

        Chaque section regroupe le titre et son corps jusqu'au titre suivant de niveau équivalent ou supérieur.
        Si max_tokens est spécifié et qu'une section dépasse ce seuil, elle est scindée
        en sous-blocs sans perdre son heading_path.

        Args:
            text: Contenu Markdown brut.
            max_tokens: Seuil optionnel de tokens maximum par chunk (1 token ~= 4 caractères).

        Returns:
            Liste ordonnée de DocumentSection.
        """
        if not text or not text.strip():
            return []

        outline = cls.get_outline(text)
        lines = text.split("\n")
        total_lines = len(lines)

        # Si le document ne comporte aucun titre, retourne une section unique ou découpe par paragraphes
        if not outline:
            return cls._fallback_sections(text, max_tokens)

        sections: list[DocumentSection] = []

        for i, item in enumerate(outline):
            start_line = item.line_number
            end_line = max(start_line, outline[i + 1].line_number - 1) if i + 1 < len(outline) else total_lines

            section_lines = lines[start_line - 1 : end_line]
            section_content = "\n".join(section_lines).strip()
            word_count = len(section_content.split())
            token_estimate = max(1, int(len(section_content) / 4))

            # Si la section est trop grande et que max_tokens est spécifié
            if max_tokens and token_estimate > max_tokens:
                sub_sections = cls._split_large_section(
                    item.breadcrumb,
                    item.level,
                    item.title,
                    section_content,
                    start_line,
                    max_tokens,
                )
                sections.extend(sub_sections)
            else:
                sections.append(
                    DocumentSection(
                        heading_path=item.breadcrumb,
                        level=item.level,
                        title=item.title,
                        content=section_content,
                        start_line=start_line,
                        end_line=end_line,
                        word_count=word_count,
                        token_estimate=token_estimate,
                    )
                )

        return sections

    @classmethod
    def _split_large_section(
        cls,
        heading_path: str,
        level: int,
        title: str,
        content: str,
        base_line: int,
        max_tokens: int,
    ) -> list[DocumentSection]:
        """Scinde une section volumineuse en préservant le fil d'Ariane."""
        paragraphs = content.split("\n\n")
        sub_sections: list[DocumentSection] = []
        current_parts: list[str] = []
        current_len = 0
        part_idx = 1
        current_start_line = base_line

        for p in paragraphs:
            p_strip = p.strip()
            if not p_strip:
                continue

            p_tokens = max(1, int(len(p_strip) / 4))
            if current_parts and (current_len + p_tokens > max_tokens):
                chunk_text = "\n\n".join(current_parts)
                line_span = chunk_text.count("\n") + 1
                sub_sections.append(
                    DocumentSection(
                        heading_path=f"{heading_path} (Partie {part_idx})",
                        level=level,
                        title=f"{title} ({part_idx})",
                        content=chunk_text,
                        start_line=current_start_line,
                        end_line=current_start_line + line_span - 1,
                        word_count=len(chunk_text.split()),
                        token_estimate=max(1, int(len(chunk_text) / 4)),
                    )
                )
                part_idx += 1
                current_start_line += line_span
                current_parts = [p_strip]
                current_len = p_tokens
            else:
                current_parts.append(p_strip)
                current_len += p_tokens

        if current_parts:
            chunk_text = "\n\n".join(current_parts)
            line_span = chunk_text.count("\n") + 1
            path_label = f"{heading_path} (Partie {part_idx})" if part_idx > 1 else heading_path
            title_label = f"{title} ({part_idx})" if part_idx > 1 else title
            sub_sections.append(
                DocumentSection(
                    heading_path=path_label,
                    level=level,
                    title=title_label,
                    content=chunk_text,
                    start_line=current_start_line,
                    end_line=current_start_line + line_span - 1,
                    word_count=len(chunk_text.split()),
                    token_estimate=max(1, int(len(chunk_text) / 4)),
                )
            )

        return sub_sections

    @classmethod
    def _fallback_sections(cls, text: str, max_tokens: int | None) -> list[DocumentSection]:
        """Découpe un texte sans titres structurés."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            return []

        if not max_tokens:
            word_count = len(text.split())
            return [
                DocumentSection(
                    heading_path="Document",
                    level=1,
                    title="Document",
                    content=text.strip(),
                    start_line=1,
                    end_line=text.count("\n") + 1,
                    word_count=word_count,
                    token_estimate=max(1, int(len(text) / 4)),
                )
            ]

        sections: list[DocumentSection] = []
        current_parts: list[str] = []
        current_len = 0
        part_idx = 1
        line_counter = 1

        for p in paragraphs:
            p_tokens = max(1, int(len(p) / 4))
            if current_parts and (current_len + p_tokens > max_tokens):
                chunk_text = "\n\n".join(current_parts)
                span = chunk_text.count("\n") + 1
                sections.append(
                    DocumentSection(
                        heading_path=f"Document (Partie {part_idx})",
                        level=1,
                        title=f"Section {part_idx}",
                        content=chunk_text,
                        start_line=line_counter,
                        end_line=line_counter + span - 1,
                        word_count=len(chunk_text.split()),
                        token_estimate=max(1, int(len(chunk_text) / 4)),
                    )
                )
                part_idx += 1
                line_counter += span
                current_parts = [p]
                current_len = p_tokens
            else:
                current_parts.append(p)
                current_len += p_tokens

        if current_parts:
            chunk_text = "\n\n".join(current_parts)
            span = chunk_text.count("\n") + 1
            sections.append(
                DocumentSection(
                    heading_path=f"Document (Partie {part_idx})",
                    level=1,
                    title=f"Section {part_idx}",
                    content=chunk_text,
                    start_line=line_counter,
                    end_line=line_counter + span - 1,
                    word_count=len(chunk_text.split()),
                    token_estimate=max(1, int(len(chunk_text) / 4)),
                )
            )

        return sections
