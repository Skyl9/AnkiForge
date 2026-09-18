import hashlib
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class ChunkingService:
    """Service de découpage documentaire intelligent et sémantique.

    Prend en charge :
    - Découpage par page pour les PDFs et documents paginés (Marker, PyMuPDF, PPTX).
    - Découpage par section hiérarchique pour les documents Markdown / Web / Textes.
    - Élimination garantie des fragments orphelins (titres isolés sans contenu).
    """

    PAGE_MARKER_REGEX = re.compile(
        r"<!--\s*PAGE:\s*(\d+)\s*-->|\{(\d+)\}-{5,}|\x0c|\[SPLIT\]",
        re.IGNORECASE,
    )
    TIME_MARKER_REGEX = re.compile(
        r"<!--\s*TIME:\s*([\d.]+)\s*-\s*([\d.]+)\s*-->",
        re.IGNORECASE,
    )
    HEADING_REGEX = re.compile(r"^(#{1,6})\s+(.*)", re.MULTILINE)

    STRATEGY_DEFAULT = "default"
    STRATEGY_MARKDOWN_AST = "markdown_ast"

    # Version de la stratégie de structuration. Incrémentée à chaque changement
    # de découpage pour détecter les documents indexés avec une ancienne version
    # et déclencher une re-indexation automatique.
    # v1 = ancien (H3 seul, pas de markdown_ast), v2 = nouveau (H1→H6 AST)
    # v3 = PDFs Marker détectés par contenu → découpage AST avec conservation des pages
    CHUNKING_VERSION: int = 3

    CONTINUOUS_FILE_TYPES = ("md", "markdown", "txt", "text", "web", "youtube", "yt", "ipynb", "py")

    # Regex pour détecter les titres avec page-span HTML residuels (Marker)
    _SPAN_PAGE_HEADING_RE = re.compile(r'<span\s+id="page-\d+-\d+"></span>', re.IGNORECASE)

    # Regex pour extraire les balises de page Marker numérotées {N}
    _MARKER_PAGE_RE = re.compile(r"\{(\d+)\}-{5,}")

    @classmethod
    def preferred_strategy(cls, file_type: str | None) -> str | None:
        """Retourne la stratégie de découpage la plus fine pour un type de document.

        Les documents continus (Markdown, Web, texte) sont découpés via l'AST
        MarkdownStructurer (un fragment par titre H1→H6, fil d'Ariane complet).
        Les documents paginés et audio conservent leur découpage natif
        (pages / marqueurs temporels).
        """
        ft = (file_type or "").lower().strip()
        if ft in cls.CONTINUOUS_FILE_TYPES:
            return cls.STRATEGY_MARKDOWN_AST
        return None

    @classmethod
    def hash_content(cls, text: str) -> str:
        """Génère un hash MD5 du texte pour la déduplication et le suivi."""
        return hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()

    @classmethod
    def extract_chunks(
        cls,
        content: str,
        file_type: str | None = None,
        strategy: str | None = None,
    ) -> list[dict[str, Any]]:
        """Découpe un document en chunks cohérents et exploitables pour la Forge et le RAG.

        Si strategy == 'markdown_ast', le découpage s'appuie sur l'analyseur AST MarkdownStructurer.
        Si le document est paginé (PDF, PPTX, ou marqueurs de page présents),
        le découpage s'effectue par page.
        Sinon (Markdown brut, Web, texte), le découpage s'effectue par section logique (Titre + Corps).

        Args:
            content (str): Le contenu Markdown brut du document.
            file_type (str | None): Extension/type du fichier ('pdf', 'pptx', 'md', etc.).
            strategy (str | None): Stratégie optionnelle ('markdown_ast', etc.).

        Returns:
            list[dict[str, Any]]: Liste des fragments avec :
            - index: int
            - content: str (texte complet de la page ou de la section)
            - page_number: int | None
            - heading_path: str | None
            - start_time: float | None
            - end_time: float | None
            - content_hash: str
        """
        if not content or not content.strip():
            return []

        markers = list(cls.PAGE_MARKER_REGEX.finditer(content))
        is_paginated = bool(markers) or (file_type is not None and file_type.lower() in ("pdf", "pptx", "epub", "audio", "mp3", "m4a", "wav", "ogg", "flac", "aac"))
        ft = (file_type or "").lower().strip()

        # Les PDFs traités par Marker possèdent un Markdown riche (titres, tables,
        # LaTeX, images) plus fin que le simple découpage page par page.
        # On le détecte au contenu : au moins un marqueur {N}--- ET une structure
        # de titres réelle (headings autres que "## Page N" de PyMuPDF natif).
        if ft in ("pdf",) and markers:
            marker_nums = [int(mm.group(1)) for m in markers if (mm := cls._MARKER_PAGE_RE.match(m.group(0)))]
            num_heading_matches = list(cls.HEADING_REGEX.finditer(content))
            has_real_headings = any(not re.match(r"^##\s+Page\s+\d+$", m.group(2).strip()) for m in num_heading_matches)
            if marker_nums and has_real_headings and strategy is None:
                strategy = cls.STRATEGY_MARKDOWN_AST

        logger.debug(
            "Extraction de chunks pour document (%d caractères, file_type=%s, paginé=%s, strategy=%s)",
            len(content),
            file_type,
            is_paginated,
            strategy,
        )

        if strategy == cls.STRATEGY_MARKDOWN_AST:
            result = cls.extract_chunks_markdown_ast(content)
            logger.info("Extraction AST Markdown achevée : %d fragments créés", len(result))
            return result

        result = cls._extract_by_page(content, markers) if is_paginated and markers else cls._extract_by_section(content)

        logger.info("Extraction de chunks achevée : %d fragments créés", len(result))
        return result

    @classmethod
    def _clean_heading_text(cls, text: str) -> str:
        """Nettoie un titre de heading : retire les spans HTML de page (Marker),
        les résidus de balisage gras/italique et les liens."""
        cleaned = cls._SPAN_PAGE_HEADING_RE.sub("", text)
        cleaned = re.sub(r"(?<!\*)\*\*(?!\*)(.*?)\*\*(?!\*)", r"\1", cleaned)
        cleaned = re.sub(r"(?<!\*)\*(?!\*)(.*?)\*(?!\*)", r"\1", cleaned)
        cleaned = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", cleaned)
        return cleaned.strip()

    @classmethod
    def _build_line_to_page_map(cls, content: str) -> dict[int, int | None]:
        """Construit {numero_ligne: page} à partir des marqueurs de page du contenu."""
        line_to_page: dict[int, int | None] = {}
        lines = content.split("\n")
        explicit_pages: list[int] = []
        for m in cls._MARKER_PAGE_RE.finditer(content):
            explicit_pages.append(int(m.group(1)))
        offset = 1 if explicit_pages and min(explicit_pages) == 0 else 0

        current_page: int | None = None
        for i, line in enumerate(lines, start=1):
            hit = cls._MARKER_PAGE_RE.search(line)
            if hit:
                current_page = int(hit.group(1)) + offset
            line_to_page[i] = current_page
        return line_to_page if any(p is not None for p in line_to_page.values()) else {}

    @classmethod
    def _assign_pages_to_sections(cls, sections: list[Any], line_to_page: dict[int, int | None]) -> list[int | None]:
        """Attribue une page à chaque section à partir de sa ligne de début."""
        pages: list[int | None] = []
        for sec in sections:
            start_line = getattr(sec, "start_line", None) or 1
            page = None
            for line_no in range(start_line, 0, -1):
                if line_no in line_to_page and line_to_page[line_no] is not None:
                    page = line_to_page[line_no]
                    break
            pages.append(page)
        return pages

    @classmethod
    def extract_chunks_markdown_ast(cls, content: str, max_tokens: int | None = None) -> list[dict[str, Any]]:
        """Découpe un document Markdown en utilisant l'analyseur structurel AST MarkdownStructurer.

        Garantit la préservation rigoureuse du fil d'Ariane (heading_path) pour chaque section,
        idéal pour le RAG vectoriel et la Forge documentaire.

        Quand des marqueurs de page Marker ({N}---) sont présents, chaque section conserve
        son numéro de page d'origine (utile pour la couverture des PDF paginés).
        """
        from ankiforge.services.markdown.structurer import MarkdownStructurer

        if not content or not content.strip():
            return []

        line_to_page = cls._build_line_to_page_map(content)
        sections = MarkdownStructurer.extract_sections(content, max_tokens=max_tokens)
        sec_pages = cls._assign_pages_to_sections(sections, line_to_page)
        chunks: list[dict[str, Any]] = []
        for idx, sec in enumerate(sections):
            clean_path = " > ".join(cls._clean_heading_text(part) for part in sec.heading_path.split(" > "))
            chunks.append(
                {
                    "index": idx,
                    "content": sec.content,
                    "page_number": sec_pages[idx],
                    "heading_path": clean_path,
                    "start_time": None,
                    "end_time": None,
                    "content_hash": cls.hash_content(sec.content),
                }
            )
        return chunks

    @classmethod
    def _extract_by_page(cls, content: str, markers: list[re.Match]) -> list[dict[str, Any]]:
        """Découpe un document page par page à partir des marqueurs détectés."""
        chunks: list[dict[str, Any]] = []
        pages: list[tuple[int, str]] = []
        explicit_page_numbers = [int(match.group(1) or match.group(2)) for match in markers if match.group(1) or match.group(2)]
        page_number_offset = 1 if explicit_page_numbers and min(explicit_page_numbers) == 0 else 0

        # Si du texte précède le premier marqueur
        if markers[0].start() > 0:
            prefix = content[: markers[0].start()].strip()
            if prefix:
                first_page = explicit_page_numbers[0] + page_number_offset if explicit_page_numbers else 1
                pages.append((max(1, first_page - 1), prefix))

        for i, m in enumerate(markers):
            start = m.end()
            end = markers[i + 1].start() if i + 1 < len(markers) else len(content)
            page_text = content[start:end].strip()
            page_num = int(m.group(1) or m.group(2)) + page_number_offset if (m.group(1) or m.group(2)) else (i + 1)
            pages.append((page_num, page_text))

        current_heading_stack: list[str] = []
        chunk_idx = 0

        for p_num, p_text in pages:
            clean_text = cls.PAGE_MARKER_REGEX.sub("", p_text).strip()
            time_match = cls.TIME_MARKER_REGEX.search(clean_text)
            start_time = float(time_match.group(1)) if time_match else None
            end_time = float(time_match.group(2)) if time_match else None
            if time_match:
                clean_text = cls.TIME_MARKER_REGEX.sub("", clean_text).strip()

            if not clean_text or len(clean_text) < 15:
                continue

            # Mettre à jour la hiérarchie des titres trouvés sur cette page
            heading_matches = list(cls.HEADING_REGEX.finditer(clean_text))
            for h_match in heading_matches:
                level = len(h_match.group(1))
                title = h_match.group(2).strip()
                current_heading_stack = current_heading_stack[: level - 1]
                while len(current_heading_stack) < level - 1:
                    current_heading_stack.append("Section")
                current_heading_stack.append(title)

            heading_path_str = " > ".join(current_heading_stack) if current_heading_stack else f"Page {p_num}"

            chunks.append(
                {
                    "index": chunk_idx,
                    "content": clean_text,
                    "page_number": p_num,
                    "heading_path": heading_path_str,
                    "start_time": start_time,
                    "end_time": end_time,
                    "content_hash": cls.hash_content(clean_text),
                }
            )
            chunk_idx += 1

        if not chunks:
            return cls._extract_by_section(content)

        return chunks

    @classmethod
    def _extract_by_section(cls, content: str) -> list[dict[str, Any]]:
        """Découpe un document Markdown par section hiérarchique (Titre + Corps)."""
        chunks: list[dict[str, Any]] = []
        lines = content.split("\n")

        current_heading_stack: list[str] = []
        current_section_lines: list[str] = []
        current_heading_path: str | None = None
        chunk_idx = 0

        def flush_section() -> None:
            nonlocal chunk_idx, current_section_lines, current_heading_path
            text = "\n".join(current_section_lines).strip()
            text = cls.PAGE_MARKER_REGEX.sub("", text).strip()
            time_match = cls.TIME_MARKER_REGEX.search(text)
            start_time = float(time_match.group(1)) if time_match else None
            end_time = float(time_match.group(2)) if time_match else None
            if time_match:
                text = cls.TIME_MARKER_REGEX.sub("", text).strip()
            if text and len(text) >= 15:
                chunks.append(
                    {
                        "index": chunk_idx,
                        "content": text,
                        "page_number": None,
                        "heading_path": current_heading_path or "Introduction",
                        "start_time": start_time,
                        "end_time": end_time,
                        "content_hash": cls.hash_content(text),
                    }
                )
                chunk_idx += 1
            current_section_lines = []

        for line in lines:
            h_match = cls.HEADING_REGEX.match(line)
            if h_match:
                level = len(h_match.group(1))
                title = h_match.group(2).strip()

                has_substantive_text = any(line_item.strip() and not cls.HEADING_REGEX.match(line_item) for line_item in current_section_lines)

                if has_substantive_text and level <= 6:
                    flush_section()

                current_heading_stack = current_heading_stack[: level - 1]
                while len(current_heading_stack) < level - 1:
                    current_heading_stack.append("Section")
                current_heading_stack.append(title)
                current_heading_path = " > ".join(current_heading_stack)

                current_section_lines.append(line)
            else:
                current_section_lines.append(line)

        flush_section()

        # Si le document n'avait pas de titres structurés (texte au kilomètre)
        if not chunks:
            raw_blocks = content.split("\n\n")
            accumulated: list[str] = []
            for block in raw_blocks:
                b_clean = block.strip()
                if not b_clean:
                    continue
                accumulated.append(b_clean)
                combined = "\n\n".join(accumulated)
                if len(combined) >= 250:
                    chunks.append(
                        {
                            "index": chunk_idx,
                            "content": combined,
                            "page_number": None,
                            "heading_path": "Document",
                            "content_hash": cls.hash_content(combined),
                        }
                    )
                    chunk_idx += 1
                    accumulated = []
            if accumulated:
                combined = "\n\n".join(accumulated)
                if len(combined) >= 15:
                    chunks.append(
                        {
                            "index": chunk_idx,
                            "content": combined,
                            "page_number": None,
                            "heading_path": "Document",
                            "content_hash": cls.hash_content(combined),
                        }
                    )

        return chunks

    @classmethod
    def extract_heading_tree_with_pages(
        cls,
        content: str,
        total_pages: int | None = None,
        file_type: str | None = None,
    ) -> list["HeadingTreeNode"]:
        """Extrait l'arbre hiérarchique des titres (H1, H2, H3...) en associant à chaque titre sa plage de pages physiques.

        Pour les documents convertis en Markdown (PDF avec marqueurs <!-- PAGE: X --> ou documents purs),
        permet une navigation et une sélection sémantique de chapitres complète.

        Returns:
            list[HeadingTreeNode]: Liste des nœuds racines (H1) contenant leurs enfants récursifs (H2, H3).
        """
        if not content or not content.strip():
            return []

        # 1. Repérage des marqueurs de pages et de leurs positions en caractères
        page_positions: list[tuple[int, int]] = []
        for m in cls.PAGE_MARKER_REGEX.finditer(content):
            p_str = m.group(1) or m.group(2)
            p_num = int(p_str) if p_str and p_str.isdigit() else None
            if p_num is not None:
                page_positions.append((m.start(), p_num))

        def find_page_for_offset(offset: int) -> int | None:
            if not page_positions:
                return None
            current_page = page_positions[0][1]
            for char_pos, p_num in page_positions:
                if char_pos <= offset:
                    current_page = p_num
                else:
                    break
            return current_page

        # 2. Détection de tous les titres Markdown ATX (#, ##, ###)
        heading_matches = list(cls.HEADING_REGEX.finditer(content))
        if not heading_matches:
            return []

        flat_nodes: list[HeadingTreeNode] = []
        current_heading_stack: list[str] = []

        for idx, h_match in enumerate(heading_matches):
            level = len(h_match.group(1))
            title = h_match.group(2).strip()
            start_offset = h_match.start()
            end_offset = heading_matches[idx + 1].start() if idx + 1 < len(heading_matches) else len(content)

            raw_body = content[h_match.end() : end_offset]
            trailing_markers = list(cls.PAGE_MARKER_REGEX.finditer(raw_body))
            content_end_offset = end_offset
            if trailing_markers:
                last_m = trailing_markers[-1]
                # Si le marqueur de page est à la fin du bloc (juste avant le titre suivant)
                if not raw_body[last_m.end() :].strip():
                    content_end_offset = h_match.end() + last_m.start()

            clean_body = content[h_match.end() : content_end_offset].rstrip()
            word_count = len(clean_body.split()) if clean_body else 0
            token_count = max(1, int(round(word_count * 1.33))) if word_count else 0

            start_p = find_page_for_offset(start_offset)
            last_content_offset = h_match.end() + len(clean_body) - 1 if clean_body else start_offset
            end_p = find_page_for_offset(last_content_offset) if last_content_offset >= start_offset else start_p
            if start_p is not None and end_p is not None and end_p < start_p:
                end_p = start_p
            if total_pages and end_p and end_p > total_pages:
                end_p = total_pages

            # Construction du fil d'Ariane
            current_heading_stack = current_heading_stack[: level - 1]
            while len(current_heading_stack) < level - 1:
                current_heading_stack.append("Section")
            current_heading_stack.append(title)
            heading_path = " > ".join(current_heading_stack)

            node = HeadingTreeNode(
                title=title,
                level=level,
                slug=re.sub(r"[^\w\s-]", "", title).strip().lower().replace(" ", "-"),
                start_page=start_p,
                end_page=end_p,
                word_count=word_count,
                token_count=token_count,
                heading_path=heading_path,
                chunk_index=idx,
            )
            flat_nodes.append(node)

        # 3. Assemblage arborescent H1 -> H2 -> H3
        root_nodes: list[HeadingTreeNode] = []
        stack: list[HeadingTreeNode] = []

        for node in flat_nodes:
            while stack and stack[-1].level >= node.level:
                stack.pop()

            if not stack:
                root_nodes.append(node)
            else:
                stack[-1].children.append(node)

            stack.append(node)

        # 4. Propagation récursive des plages de pages et volumes aux nœuds parents
        def propagate_bounds(n: HeadingTreeNode) -> tuple[int | None, int | None, int, int]:
            sub_min_p = n.start_page
            sub_max_p = n.end_page
            total_words = n.word_count
            total_tokens = n.token_count

            for child in n.children:
                c_min, c_max, c_words, c_tokens = propagate_bounds(child)
                if c_min is not None:
                    sub_min_p = c_min if sub_min_p is None else min(sub_min_p, c_min)
                if c_max is not None:
                    sub_max_p = c_max if sub_max_p is None else max(sub_max_p, c_max)
                total_words += c_words
                total_tokens += c_tokens

            n.start_page = sub_min_p
            n.end_page = sub_max_p
            n.word_count = total_words
            n.token_count = total_tokens
            return sub_min_p, sub_max_p, total_words, total_tokens

        for root in root_nodes:
            propagate_bounds(root)

        return root_nodes

    @classmethod
    def build_tree_from_chunks(cls, chunks: list[dict[str, Any]]) -> list["HeadingTreeNode"]:
        """Construit un arbre HeadingTreeNode à partir d'une liste de dictionnaires de chunks."""
        if not chunks:
            return []

        has_headings = any(bool(c.get("heading_path")) for c in chunks)
        if not has_headings:
            nodes: list[HeadingTreeNode] = []
            for idx, c in enumerate(chunks):
                p = c.get("page_number")
                title = f"Page {p}" if p else f"Section #{idx + 1}"
                content = str(c.get("content") or "")
                words = len(content.split())
                nodes.append(
                    HeadingTreeNode(
                        title=title,
                        level=1,
                        start_page=p,
                        end_page=p,
                        word_count=words,
                        token_count=max(1, int(round(words * 1.33))),
                        heading_path=title,
                        chunk_index=c.get("index", idx),
                    )
                )
            return nodes

        root_nodes: list[HeadingTreeNode] = []
        node_cache: dict[str, HeadingTreeNode] = {}

        for idx, c in enumerate(chunks):
            h_path = (c.get("heading_path") or "").strip()
            p = c.get("page_number")
            content = str(c.get("content") or "")
            words = len(content.split())
            tokens = max(1, int(round(words * 1.33))) if words else 0

            if not h_path:
                h_path = f"Page {p}" if p else f"Section #{idx + 1}"

            parts = [part.strip() for part in h_path.split(" > ") if part.strip()]
            if not parts:
                parts = [h_path]

            curr_path = ""
            parent_node: HeadingTreeNode | None = None

            for lvl, part in enumerate(parts, start=1):
                curr_path = f"{curr_path} > {part}" if curr_path else part
                if curr_path in node_cache:
                    existing = node_cache[curr_path]
                    if p is not None:
                        existing.start_page = p if existing.start_page is None else min(existing.start_page, p)
                        existing.end_page = p if existing.end_page is None else max(existing.end_page, p)
                    existing.word_count += words
                    existing.token_count += tokens
                    parent_node = existing
                else:
                    new_node = HeadingTreeNode(
                        title=part,
                        level=lvl,
                        start_page=p,
                        end_page=p,
                        word_count=words if lvl == len(parts) else 0,
                        token_count=tokens if lvl == len(parts) else 0,
                        heading_path=curr_path,
                        chunk_index=c.get("index", idx) if lvl == len(parts) else None,
                    )
                    node_cache[curr_path] = new_node
                    if parent_node is None:
                        root_nodes.append(new_node)
                    else:
                        parent_node.children.append(new_node)
                    parent_node = new_node

        return root_nodes


class HeadingTreeNode:
    """Nœud hiérarchique représentant un titre et sa section, avec correspondance de pages physiques et statistiques."""

    def __init__(
        self,
        title: str,
        level: int = 1,
        slug: str = "",
        start_page: int | None = None,
        end_page: int | None = None,
        word_count: int = 0,
        token_count: int = 0,
        cards_count: int = 0,
        heading_path: str = "",
        chunk_index: int | None = None,
        children: list["HeadingTreeNode"] | None = None,
    ) -> None:
        self.title = title
        self.level = level
        self.slug = slug
        self.start_page = start_page
        self.end_page = end_page
        self.word_count = word_count
        self.token_count = token_count
        self.cards_count = cards_count
        self.heading_path = heading_path or title
        self.chunk_index = chunk_index
        self.children: list[HeadingTreeNode] = children if children is not None else []

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "level": self.level,
            "slug": self.slug,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "word_count": self.word_count,
            "token_count": self.token_count,
            "cards_count": self.cards_count,
            "heading_path": self.heading_path,
            "chunk_index": self.chunk_index,
            "children": [child.to_dict() for child in self.children],
        }
