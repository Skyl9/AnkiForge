"""Moteur d'analyse structurelle AST, Table des Matières et découpage sémantique Markdown."""

import logging
import re

from markdown_it import MarkdownIt

from ankiforge.services.markdown.models import (
    DocumentSection,
    HeadingNode,
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
    def slugify(cls, text: str) -> str:
        """Génère un slug d'ancre standardisé compatible GitHub Markdown."""
        # Supprime le balisage inline résiduel (gras, italique, code, liens)
        cleaned = re.sub(r"[*_`]", "", text)
        cleaned = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", cleaned)
        cleaned = cleaned.strip().lower()
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

                # Le contenu du titre se trouve dans le token inline suivant
                title = ""
                if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                    title = tokens[i + 1].content.strip()

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

    @classmethod
    def repair_heading_hierarchy(cls, text: str) -> tuple[str, list[str]]:
        """Détecte et répare les sauts de niveau illégaux (ex: H1 -> H3).

        Ajuste les niveaux relatifs pour rétablir une progression logique continue
        sans rompre la subordination des sous-sections.

        Returns:
            Tuple (texte_modifié, liste_des_modifications_effectuées).
        """
        if not text or not text.strip():
            return text, []

        changes: list[str] = []
        # Normalise les éventuels `#Titre` sans espace avant analyse CommonMark
        missing_spaces = re.compile(r"^(#{1,6})([^# \t\n].*)$", re.MULTILINE)
        if missing_spaces.search(text):
            text = missing_spaces.sub(r"\1 \2", text)
            changes.append("Espaces ajoutés après '#' sur les titres ATX")

        outline = cls.get_outline(text)
        if not outline:
            return text, changes

        lines = text.split("\n")
        replacements: dict[int, str] = {}  # 0-indexed line -> new line string

        # Algorithme d'ajustement hiérarchique
        current_max_depth = 0
        target_levels: list[int] = []

        for item in outline:
            current_level = item.level
            corrected_level = current_max_depth + 1 if current_level > current_max_depth + 1 else current_level
            current_max_depth = corrected_level
            target_levels.append(corrected_level)

        # Applique les corrections si des niveaux ont été modifiés
        for item, corrected_level in zip(outline, target_levels, strict=False):
            if corrected_level != item.level:
                line_idx = item.line_number - 1
                if 0 <= line_idx < len(lines):
                    old_line = lines[line_idx]
                    # Remplacement des '#' au début de la ligne
                    m = re.match(r"^(#{1,6})\s*(.*)$", old_line)
                    if m:
                        content_part = m.group(2)
                        new_line = f"{'#' * corrected_level} {content_part}"
                        replacements[line_idx] = new_line
                        changes.append(f"Ligne {item.line_number}: Titre '{item.title}' ajusté de H{item.level} à H{corrected_level}")

        if not replacements:
            return text, []

        for line_idx, new_line in replacements.items():
            lines[line_idx] = new_line

        return "\n".join(lines), changes

    @classmethod
    def generate_toc(cls, text: str, max_depth: int = 3, ordered: bool = False) -> str:
        """Génère une Table des Matières (TOC) Markdown avec liens ancrés.

        Args:
            text: Contenu Markdown source.
            max_depth: Profondeur maximale des titres inclus (1 à 6).
            ordered: Si True, numérotation ordonnée (1., 1.1...), sinon puces '-'

        Returns:
            Chaîne Markdown représentant le sommaire formaté.
        """
        outline = cls.get_outline(text)
        if not outline:
            return ""

        filtered = [item for item in outline if item.level <= max_depth]
        if not filtered:
            return ""

        min_level = min(item.level for item in filtered)
        toc_lines: list[str] = ["## Table des Matières\n"]

        # Suivi de la numérotation ordonnée
        counters = [0] * 7

        for item in filtered:
            indent_level = item.level - min_level
            indent = "  " * indent_level

            if ordered:
                counters[item.level] += 1
                # Réinitialise les compteurs plus profonds
                for deeper in range(item.level + 1, 7):
                    counters[deeper] = 0
                prefix = f"{counters[item.level]}."
            else:
                prefix = "-"

            toc_lines.append(f"{indent}{prefix} [{item.title}](#{item.slug})")

        return "\n".join(toc_lines) + "\n"

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
