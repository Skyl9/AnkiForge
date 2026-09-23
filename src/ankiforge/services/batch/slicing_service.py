"""Service de découpage et de partitionnement de documents pour la Batch Factory."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ankiforge.services.markdown.structurer import MarkdownStructurer

logger = logging.getLogger(__name__)


class SlicingMode(StrEnum):
    """Modes de découpage disponibles pour un document long."""

    HEADINGS = "headings"
    TOKENS = "tokens"
    PAGES = "pages"


class GranularityLevel(StrEnum):
    """Niveaux de granularité pour le découpage automatique."""

    COARSE = "coarse"  # Large / Macro (Grands chapitres H1, ~3 500 tks, 10 pages)
    BALANCED = "balanced"  # Équilibré / Standard (Recommandé : H1-H2, ~2 000 tks, 5 pages)
    FINE = "fine"  # Fin / Atomique (Sous-sections H1-H3, ~1 000 tks, 1 page)
    CUSTOM = "custom"  # Personnalisé (Réglages libres de profondeur/tokens/pages)


@dataclass(frozen=True, slots=True)
class SliceUnit:
    """Représente une unité textuelle découpée, prête pour la file d'attente Batch."""

    index: int
    title: str
    heading_path: str
    content: str
    page_number: int | None = None
    start_page: int | None = None
    end_page: int | None = None
    tokens_estimate: int = 0
    words_estimate: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Convertit l'unité en dictionnaire pour les structures de queue et snapshots."""
        return {
            "index": self.index,
            "title": self.title,
            "heading_path": self.heading_path,
            "content": self.content,
            "page_number": self.page_number,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "tokens_estimate": self.tokens_estimate,
            "words_estimate": self.words_estimate,
        }


class SlicingService:
    """Moteur de découpage intelligent pour documents longs (PDF, Markdown, Web)."""

    PAGE_MARKER_REGEX = re.compile(
        r"<!--\s*PAGE:\s*(\d+)\s*-->|\{(\d+)\}-{5,}|\x0c|\[SPLIT\]",
        re.IGNORECASE,
    )
    _MARKER_PAGE_RE = re.compile(r"\{(\d+)\}-{5,}")
    _SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9À-ÖØ-ß])")

    @classmethod
    def get_headings_preset(cls, level: GranularityLevel | str) -> tuple[int, int]:
        """Retourne (max_depth, min_words) pour un palier de granularité."""
        lvl = str(level).lower()
        if lvl == GranularityLevel.COARSE.value:
            return 1, 100
        if lvl == GranularityLevel.FINE.value:
            return 3, 30
        return 2, 50

    @classmethod
    def get_tokens_preset(cls, level: GranularityLevel | str) -> tuple[int, int]:
        """Retourne (target_tokens, overlap_tokens) pour un palier de granularité."""
        lvl = str(level).lower()
        if lvl == GranularityLevel.COARSE.value:
            return 3500, 200
        if lvl == GranularityLevel.FINE.value:
            return 1000, 100
        return 2000, 150

    @classmethod
    def get_pages_preset(cls, level: GranularityLevel | str) -> int:
        """Retourne pages_per_slice pour un palier de granularité."""
        lvl = str(level).lower()
        if lvl == GranularityLevel.COARSE.value:
            return 10
        if lvl == GranularityLevel.FINE.value:
            return 1
        return 5

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """Estime le nombre de tokens pour un texte (ratio moyen de 1.3 par mot)."""
        words = len(text.split())
        return int(words * 1.3) if words > 0 else 0

    @classmethod
    def estimate_words(cls, text: str) -> int:
        """Compte le nombre de mots du texte."""
        return len(text.split())

    @classmethod
    def slice_document(
        cls,
        content: str,
        mode: SlicingMode | str = SlicingMode.HEADINGS,
        **kwargs: Any,
    ) -> list[SliceUnit]:
        """Point d'entrée universel pour découper un document selon le mode spécifié."""
        mode_str = str(mode).lower()
        granularity = kwargs.get("granularity")
        if granularity and isinstance(granularity, GranularityLevel | str) and str(granularity).lower() != GranularityLevel.CUSTOM.value:
            if mode_str == SlicingMode.HEADINGS.value:
                default_depth, default_min_words = cls.get_headings_preset(granularity)
                kwargs.setdefault("max_depth", default_depth)
                kwargs.setdefault("min_words", default_min_words)
            elif mode_str == SlicingMode.TOKENS.value:
                default_target, default_overlap = cls.get_tokens_preset(granularity)
                kwargs.setdefault("target_tokens", default_target)
                kwargs.setdefault("overlap_tokens", default_overlap)
            elif mode_str == SlicingMode.PAGES.value:
                kwargs.setdefault("pages_per_slice", cls.get_pages_preset(granularity))

        if mode_str == SlicingMode.HEADINGS.value:
            max_depth = int(kwargs.get("max_depth", 2))
            min_words = int(kwargs.get("min_words", 50))
            return cls.slice_by_headings(content, max_depth=max_depth, min_words=min_words)
        if mode_str == SlicingMode.TOKENS.value:
            target_tokens = int(kwargs.get("target_tokens", 2000))
            overlap_tokens = int(kwargs.get("overlap_tokens", 150))
            return cls.slice_by_tokens(content, target_tokens=target_tokens, overlap_tokens=overlap_tokens)
        if mode_str == SlicingMode.PAGES.value:
            pages_per_slice = int(kwargs.get("pages_per_slice", 5))
            return cls.slice_by_pages(content, pages_per_slice=pages_per_slice)
        # Fallback par défaut sur les titres
        return cls.slice_by_headings(content)

    @classmethod
    def slice_by_headings(
        cls,
        content: str,
        max_depth: int = 2,
        min_words: int = 50,
    ) -> list[SliceUnit]:
        """Découpe un document en sections hiérarchiques basées sur les titres (H1→H{max_depth}).

        - Agrégation hiérarchique réelle : les sous-sections plus profondes que max_depth
          sont intégralement incorporées dans le contenu de la section parente.
        - Fusion des micro-sections : les blocs inférieurs à min_words sont fusionnés
          pour préserver la densité pédagogique.
        """
        if not content or not content.strip():
            return []

        line_to_page = cls._build_line_to_page_map(content)
        outline = MarkdownStructurer.get_outline(content)

        if not outline:
            words = cls.estimate_words(content)
            tokens = cls.estimate_tokens(content)
            return [
                SliceUnit(
                    index=0,
                    title="Document Complet",
                    heading_path="Document Complet",
                    content=content.strip(),
                    page_number=1,
                    start_page=1,
                    end_page=1,
                    tokens_estimate=tokens,
                    words_estimate=words,
                )
            ]

        lines = content.split("\n")
        total_lines = len(lines)

        # Calcul du niveau maximal effectif relatif au niveau minimal existant
        min_level = min(item.level for item in outline)
        effective_max_level = min_level + max(0, max_depth - 1)

        # Repérage des titres de coupure (ceux dont le niveau <= effective_max_level)
        cutting_indices = [i for i, it in enumerate(outline) if it.level <= effective_max_level]
        if not cutting_indices:
            cutting_indices = [i for i, it in enumerate(outline) if it.level == min_level]

        raw_units: list[dict[str, Any]] = []
        for pos, k in enumerate(cutting_indices):
            item = outline[k]
            start_line = item.line_number
            # Si premier titre de coupure, englober le préambule initial si existant
            slice_start_line = 1 if pos == 0 else start_line

            if pos + 1 < len(cutting_indices):
                next_k = cutting_indices[pos + 1]
                slice_end_line = max(slice_start_line, outline[next_k].line_number - 1)
            else:
                slice_end_line = total_lines

            slice_text = "\n".join(lines[slice_start_line - 1 : slice_end_line]).strip()
            clean_path = " > ".join(MarkdownStructurer.clean_heading_title(p) for p in item.breadcrumb.split(" > ") if p.strip())
            leaf_title = clean_path.split(" > ")[-1] if clean_path else MarkdownStructurer.clean_heading_title(item.title)
            sec_words = cls.estimate_words(slice_text)
            page_num = cls._resolve_page_for_line(start_line, line_to_page)

            raw_units.append(
                {
                    "title": leaf_title,
                    "heading_path": clean_path,
                    "content": slice_text,
                    "page_number": page_num,
                    "words": sec_words,
                }
            )

        # Fusion des sections trop courtes (< min_words)
        merged_units: list[dict[str, Any]] = []
        if min_words > 0:
            for unit in raw_units:
                if not merged_units:
                    merged_units.append(unit)
                    continue

                prev = merged_units[-1]
                if unit["words"] < min_words:
                    prev["content"] = f"{prev['content']}\n\n{unit['content']}".strip()
                    prev["words"] = cls.estimate_words(prev["content"])
                else:
                    merged_units.append(unit)

            if len(merged_units) > 1 and merged_units[0]["words"] < min_words:
                first = merged_units.pop(0)
                merged_units[0]["content"] = f"{first['content']}\n\n{merged_units[0]['content']}".strip()
                merged_units[0]["words"] = cls.estimate_words(merged_units[0]["content"])
        else:
            merged_units = raw_units

        result: list[SliceUnit] = []
        for idx, u in enumerate(merged_units):
            cnt = u["content"].strip()
            words = cls.estimate_words(cnt)
            tokens = cls.estimate_tokens(cnt)
            p_num = u.get("page_number")
            result.append(
                SliceUnit(
                    index=idx,
                    title=u["title"],
                    heading_path=u["heading_path"],
                    content=cnt,
                    page_number=p_num,
                    start_page=p_num,
                    end_page=p_num,
                    tokens_estimate=tokens,
                    words_estimate=words,
                )
            )

        return result

    @classmethod
    def slice_by_tokens(
        cls,
        content: str,
        target_tokens: int = 2000,
        overlap_tokens: int = 150,
    ) -> list[SliceUnit]:
        """Découpe un texte en blocs d'environ target_tokens avec coupure douce et chevauchement."""
        clean_text = content.strip()
        if not clean_text:
            return []

        target_words = max(100, int(target_tokens / 1.3))
        overlap_words = max(0, int(overlap_tokens / 1.3))

        # Découpage initial en paragraphes pour respecter les blocs naturels
        paragraphs = [p.strip() for p in clean_text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [clean_text]

        chunks_text: list[str] = []
        current_paras: list[str] = []
        current_word_count = 0

        for p in paragraphs:
            p_words = len(p.split())
            if current_word_count + p_words > target_words and current_paras:
                # Émission de la tranche courante
                block_content = "\n\n".join(current_paras)
                chunks_text.append(block_content)

                # Calcul du recouvrement : reprendre les derniers mots
                if overlap_words > 0:
                    words = block_content.split()
                    tail = " ".join(words[-overlap_words:])
                    current_paras = [f"... {tail}", p]
                    current_word_count = len(current_paras[0].split()) + p_words
                else:
                    current_paras = [p]
                    current_word_count = p_words
            else:
                current_paras.append(p)
                current_word_count += p_words

        if current_paras:
            chunks_text.append("\n\n".join(current_paras))

        # Construction des SliceUnit
        slices: list[SliceUnit] = []
        for idx, text in enumerate(chunks_text):
            word_count_est = cls.estimate_words(text)
            tokens = cls.estimate_tokens(text)
            title = f"Tranche {idx + 1} (~{word_count_est} mots)"
            slices.append(
                SliceUnit(
                    index=idx,
                    title=title,
                    heading_path=title,
                    content=text,
                    page_number=None,
                    start_page=None,
                    end_page=None,
                    tokens_estimate=tokens,
                    words_estimate=word_count_est,
                )
            )

        return slices

    @classmethod
    def slice_by_pages(
        cls,
        content: str,
        pages_per_slice: int = 5,
    ) -> list[SliceUnit]:
        """Découpe un document paginé (PDF/PPTX) en tranches de pages_per_slice pages."""
        if not content or not content.strip():
            return []

        markers = list(cls.PAGE_MARKER_REGEX.finditer(content))
        if not markers:
            # Fallback en blocs de tokens si aucune pagination détectée
            return cls.slice_by_tokens(content, target_tokens=pages_per_slice * 400)

        # Extraction des pages individuelles
        pages: list[tuple[int, str]] = []
        for i, m in enumerate(markers):
            start = m.end()
            end = markers[i + 1].start() if i + 1 < len(markers) else len(content)
            page_text = content[start:end].strip()
            num_str = m.group(1) or m.group(2)
            page_num = int(num_str) if num_str and num_str.isdigit() else (i + 1)
            pages.append((page_num, page_text))

        if not pages:
            return cls.slice_by_headings(content)

        # Regroupement par paquets de pages_per_slice
        slices: list[SliceUnit] = []
        step = max(1, pages_per_slice)
        slice_idx = 0

        for i in range(0, len(pages), step):
            group = pages[i : i + step]
            if not group:
                continue

            start_p = group[0][0]
            end_p = group[-1][0]
            combined_text = "\n\n".join(p[1] for p in group if p[1].strip()).strip()
            if not combined_text:
                continue

            words = cls.estimate_words(combined_text)
            tokens = cls.estimate_tokens(combined_text)
            title = f"Pages {start_p} à {end_p}" if start_p != end_p else f"Page {start_p}"
            slices.append(
                SliceUnit(
                    index=slice_idx,
                    title=title,
                    heading_path=title,
                    content=combined_text,
                    page_number=start_p,
                    start_page=start_p,
                    end_page=end_p,
                    tokens_estimate=tokens,
                    words_estimate=words,
                )
            )
            slice_idx += 1

        return slices

    @classmethod
    def get_outline_tree(cls, content: str) -> list[dict[str, Any]]:
        """Extrait l'arborescence hiérarchique du document pour l'assistant interactif (Wizard)."""
        if not content or not content.strip():
            return []

        outline = MarkdownStructurer.get_outline(content)
        line_to_page = cls._build_line_to_page_map(content)

        result: list[dict[str, Any]] = []
        for item in outline:
            p_num = cls._resolve_page_for_line(item.line_number, line_to_page)
            result.append(
                {
                    "title": item.title,
                    "level": item.level,
                    "line_number": item.line_number,
                    "page_number": p_num,
                    "breadcrumb": item.breadcrumb,
                    "slug": item.slug,
                }
            )
        return result

    @classmethod
    def _build_line_to_page_map(cls, content: str) -> dict[int, int | None]:
        """Associe chaque ligne à son numéro de page correspondant si des marqueurs existent."""
        line_to_page: dict[int, int | None] = {}
        lines = content.split("\n")
        current_page: int | None = 1

        has_markers = False
        for i, line in enumerate(lines, start=1):
            hit = cls._MARKER_PAGE_RE.search(line)
            if hit:
                has_markers = True
                current_page = int(hit.group(1))
            line_to_page[i] = current_page

        return line_to_page if has_markers else {}

    @classmethod
    def _resolve_page_for_line(cls, line_no: int, line_to_page: dict[int, int | None]) -> int | None:
        """Trouve la page correspondante à une ligne donnée."""
        if not line_to_page:
            return None
        for l_num in range(line_no, 0, -1):
            if l_num in line_to_page and line_to_page[l_num] is not None:
                return line_to_page[l_num]
        return None
