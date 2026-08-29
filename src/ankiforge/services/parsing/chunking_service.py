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
    HEADING_REGEX = re.compile(r"^(#{1,6})\s+(.*)", re.MULTILINE)

    @classmethod
    def hash_content(cls, text: str) -> str:
        """Génère un hash MD5 du texte pour la déduplication et le suivi."""
        return hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()

    @classmethod
    def extract_chunks(cls, content: str, file_type: str | None = None) -> list[dict[str, Any]]:
        """Découpe un document en chunks cohérents et exploitables pour la Forge et le RAG.

        Si le document est paginé (PDF, PPTX, ou marqueurs de page présents),
        le découpage s'effectue par page.
        Sinon (Markdown brut, Web, texte), le découpage s'effectue par section logique (Titre + Corps).

        Args:
            content (str): Le contenu Markdown brut du document.
            file_type (str | None): Extension/type du fichier ('pdf', 'pptx', 'md', etc.).

        Returns:
            List[Dict[str, Any]]: Liste des fragments avec :
            - index: int
            - content: str (texte complet de la page ou de la section)
            - page_number: int | None
            - heading_path: str | None
            - content_hash: str
        """
        if not content or not content.strip():
            return []

        markers = list(cls.PAGE_MARKER_REGEX.finditer(content))
        is_paginated = bool(markers) or (file_type is not None and file_type.lower() in ("pdf", "pptx"))

        logger.debug(
            "Extraction de chunks pour document (%d caractères, file_type=%s, paginé=%s)",
            len(content),
            file_type,
            is_paginated,
        )

        result = cls._extract_by_page(content, markers) if is_paginated and markers else cls._extract_by_section(content)

        logger.info("Extraction de chunks achevée : %d fragments créés", len(result))
        return result

    @classmethod
    def _extract_by_page(cls, content: str, markers: list[re.Match]) -> list[dict[str, Any]]:
        """Découpe un document page par page à partir des marqueurs détectés."""
        chunks: list[dict[str, Any]] = []
        pages: list[tuple[int, str]] = []

        # Si du texte précède le premier marqueur
        if markers[0].start() > 0:
            prefix = content[: markers[0].start()].strip()
            if prefix:
                pages.append((1, prefix))

        for i, m in enumerate(markers):
            start = m.end()
            end = markers[i + 1].start() if i + 1 < len(markers) else len(content)
            page_text = content[start:end].strip()
            page_num = int(m.group(1) or m.group(2)) if (m.group(1) or m.group(2)) else (i + 1)
            pages.append((page_num, page_text))

        current_heading_stack: list[str] = []
        chunk_idx = 0

        for p_num, p_text in pages:
            clean_text = cls.PAGE_MARKER_REGEX.sub("", p_text).strip()
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
            if text and len(text) >= 15:
                chunks.append(
                    {
                        "index": chunk_idx,
                        "content": text,
                        "page_number": None,
                        "heading_path": current_heading_path or "Introduction",
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

                if has_substantive_text and level <= 3:
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
