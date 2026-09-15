"""Moteur de formatage et de nettoyage Markdown haute fidélité pour AnkiForge."""

import logging
import re
from typing import Literal

from ankiforge.services.markdown.models import FormatOptions, FormatResult

logger = logging.getLogger(__name__)


class MarkdownFormatter:
    """Service de nettoyage, normalisation et formatage de documents Markdown.

    Caractéristiques :
    - Dé-césure intelligente des césures OCR de fin de ligne.
    - Normalisation des équations KaTeX (\\( ... \\) -> $...$, \\[ ... \\] -> $$...$$).
    - Alignement visuel parfait des tableaux GFM.
    - Normalisation des titres ATX et blocs de code.
    - Nettoyage rigoureux des espaces sans détruire les hard breaks Markdown.
    - Préservation garantie du contenu dans les code fences.
    """

    CODE_BLOCK_PATTERN = re.compile(
        r"(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]+`)",
        re.MULTILINE,
    )
    OCR_HYPHEN_PATTERN = re.compile(
        r"(\b[A-Za-zÀ-ÿ]{2,})-(?:\r?\n)[ \t]*([a-zà-ÿ]{2,}\b)",
    )
    KATEX_DISPLAY_PATTERN = re.compile(r"(?<!\\)\\\[([\s\S]*?)\\\]")
    KATEX_INLINE_PATTERN = re.compile(r"(?<!\\)\\\(([\s\S]*?)\\\)")
    ATX_MISSING_SPACE_PATTERN = re.compile(r"^(#{1,6})([^# \t\n].*)$", re.MULTILINE)
    ATX_TRAILING_HASHES_PATTERN = re.compile(r"^(#{1,6}[ \t]+.*?)[ \t]+#+[ \t]*$", re.MULTILINE)
    FENCE_TILDE_PATTERN = re.compile(r"^~~~([a-zA-Z0-9_\-]*)[ \t]*$", re.MULTILINE)
    FENCE_BACKTICK_CLEAN_PATTERN = re.compile(r"^```([a-zA-Z0-9_\-]*)[ \t]+$", re.MULTILINE)
    TABLE_SEPARATOR_PATTERN = re.compile(r"^[ \t]*\|?([ \t]*:?-+:?[ \t]*\|)+[ \t]*:?-+:?[ \t]*\|?[ \t]*$")

    @classmethod
    def format(cls, text: str, options: FormatOptions | None = None) -> FormatResult:
        """Applique l'ensemble des règles de formatage selon les options spécifiées.

        Args:
            text: Texte Markdown source.
            options: Configuration des étapes à exécuter (par défaut toutes actives).

        Returns:
            FormatResult contenant le texte nettoyé, l'indicateur de changement et le résumé.
        """
        if not text:
            return FormatResult(formatted_text="", changed=False, changes_summary=[])

        opts = options or FormatOptions()
        current_text = text
        changes_summary: list[str] = []

        # 1. Masquage des blocs de code pour éviter d'altérer du code ou des exemples
        masked_text, placeholders = cls._mask_code(current_text)

        # 2. Dé-césure des artefacts OCR
        if opts.dehyphenate_ocr:
            masked_text, count = cls._dehyphenate_ocr(masked_text)
            if count > 0:
                changes_summary.append(f"{count} césure(s) OCR réparée(s)")

        # 3. Normalisation KaTeX
        if opts.normalize_katex:
            masked_text, count = cls._normalize_katex(masked_text)
            if count > 0:
                changes_summary.append(f"{count} formule(s) KaTeX harmonisée(s)")

        # 4. Normalisation des titres ATX
        if opts.normalize_headings:
            masked_text, count = cls._normalize_headings(masked_text)
            if count > 0:
                changes_summary.append(f"{count} titre(s) ATX normalisé(s)")

        # 5. Alignement des tableaux GFM
        if opts.align_tables:
            masked_text, count = cls._align_tables(masked_text)
            if count > 0:
                changes_summary.append(f"{count} tableau(x) GFM aligné(s)")

        # 6. Démasquage du code
        current_text = cls._unmask_code(masked_text, placeholders)

        # 7. Normalisation des code fences
        if opts.normalize_code_fences:
            current_text, count = cls._normalize_code_fences(current_text)
            if count > 0:
                changes_summary.append(f"{count} bloc(s) de code normalisé(s)")

        # 8. Nettoyage des espaces et lignes vides
        if opts.clean_whitespace:
            current_text, count = cls._clean_whitespace(current_text)
            if count > 0:
                changes_summary.append("Espaces et lignes vides nettoyés")

        changed = current_text != text
        return FormatResult(
            formatted_text=current_text,
            changed=changed,
            changes_summary=changes_summary,
        )

    @classmethod
    def _mask_code(cls, text: str) -> tuple[str, dict[str, str]]:
        """Remplace temporairement les blocs de code par des jetons neutres."""
        placeholders: dict[str, str] = {}
        idx = 0

        def replacer(match: re.Match[str]) -> str:
            nonlocal idx
            token = f"«AF_CODE_TOKEN_{idx}»"
            placeholders[token] = match.group(0)
            idx += 1
            return token

        masked = cls.CODE_BLOCK_PATTERN.sub(replacer, text)
        return masked, placeholders

    @classmethod
    def _unmask_code(cls, text: str, placeholders: dict[str, str]) -> str:
        """Restaure les blocs de code d'origine."""
        result = text
        for token, original in placeholders.items():
            result = result.replace(token, original)
        return result

    @classmethod
    def _dehyphenate_ocr(cls, text: str) -> tuple[str, int]:
        """Supprime les traits d'union en fin de ligne introduits par l'OCR."""
        count = len(cls.OCR_HYPHEN_PATTERN.findall(text))
        if count == 0:
            return text, 0
        cleaned = cls.OCR_HYPHEN_PATTERN.sub(r"\1\2", text)
        return cleaned, count

    @classmethod
    def _normalize_katex(cls, text: str) -> tuple[str, int]:
        """Harmonise les syntaxes LaTeX \\( ... \\) et \\[ ... \\] vers $ et $$."""
        count = 0

        def repl_display(m: re.Match[str]) -> str:
            nonlocal count
            count += 1
            inner = m.group(1).strip()
            return f"$$\n{inner}\n$$"

        def repl_inline(m: re.Match[str]) -> str:
            nonlocal count
            count += 1
            inner = m.group(1).strip()
            return f"${inner}$"

        res = cls.KATEX_DISPLAY_PATTERN.sub(repl_display, text)
        res = cls.KATEX_INLINE_PATTERN.sub(repl_inline, res)
        return res, count

    @classmethod
    def _normalize_headings(cls, text: str) -> tuple[str, int]:
        """Garantit l'espace après '#' et supprime les hashes fermants superflus."""
        count = 0
        missing_matches = len(cls.ATX_MISSING_SPACE_PATTERN.findall(text))
        trailing_matches = len(cls.ATX_TRAILING_HASHES_PATTERN.findall(text))
        count = missing_matches + trailing_matches

        res = cls.ATX_MISSING_SPACE_PATTERN.sub(r"\1 \2", text)
        res = cls.ATX_TRAILING_HASHES_PATTERN.sub(r"\1", res)
        return res, count

    @classmethod
    def _normalize_code_fences(cls, text: str) -> tuple[str, int]:
        """Normalise ~~~ vers ``` et supprime les espaces en fin d'étiquette de langue."""
        tilde_count = len(cls.FENCE_TILDE_PATTERN.findall(text))
        backtick_clean_count = len(cls.FENCE_BACKTICK_CLEAN_PATTERN.findall(text))
        total = tilde_count + backtick_clean_count

        res = cls.FENCE_TILDE_PATTERN.sub(r"```\1", text)
        res = cls.FENCE_BACKTICK_CLEAN_PATTERN.sub(r"```\1", res)
        return res, total

    @classmethod
    def _align_tables(cls, text: str) -> tuple[str, int]:
        """Détecte et aligne esthétiquement les tableaux Markdown (GFM)."""
        lines = text.split("\n")
        aligned_lines: list[str] = []
        i = 0
        table_count = 0

        while i < len(lines):
            line = lines[i]

            # Vérifie si la ligne courante et suivante forment l'en-tête d'un tableau
            if "|" in line and i + 1 < len(lines) and cls.TABLE_SEPARATOR_PATTERN.match(lines[i + 1]):
                # Début d'un tableau
                table_lines = [line, lines[i + 1]]
                i += 2

                # Collecte toutes les lignes du corps du tableau
                while i < len(lines) and "|" in lines[i] and lines[i].strip():
                    table_lines.append(lines[i])
                    i += 1

                # Aligne le tableau collecté
                formatted_table = cls._format_single_table(table_lines)
                aligned_lines.extend(formatted_table)
                table_count += 1
            else:
                aligned_lines.append(line)
                i += 1

        return "\n".join(aligned_lines), table_count

    @classmethod
    def _split_table_row(cls, row_str: str) -> list[str]:
        """Découpe une ligne de tableau en cellules en ignorant les barres d'extrémité."""
        s = row_str.strip()
        if s.startswith("|"):
            s = s[1:]
        if s.endswith("|"):
            s = s[:-1]
        return [cell.strip() for cell in s.split("|")]

    @classmethod
    def _format_single_table(cls, raw_rows: list[str]) -> list[str]:
        """Aligne les colonnes d'un tableau unique avec séparateurs et marges."""
        if len(raw_rows) < 2:
            return raw_rows

        parsed_rows = [cls._split_table_row(r) for r in raw_rows]
        num_cols = max(len(r) for r in parsed_rows)
        if num_cols == 0:
            return raw_rows

        # Complète les lignes avec des cellules vides si nécessaire
        for r in parsed_rows:
            while len(r) < num_cols:
                r.append("")

        # Analyse les alignements à partir de la 2e ligne (séparateurs)
        sep_cells = parsed_rows[1]
        alignments: list[Literal["left", "center", "right"]] = []
        for cell in sep_cells:
            c = cell.strip()
            has_start = c.startswith(":")
            has_end = c.endswith(":")
            if has_start and has_end:
                alignments.append("center")
            elif has_end:
                alignments.append("right")
            else:
                alignments.append("left")
        while len(alignments) < num_cols:
            alignments.append("left")

        # Calcule la largeur maximale par colonne (minimum 3 caractères)
        col_widths = [3] * num_cols
        for row_idx, r in enumerate(parsed_rows):
            if row_idx == 1:
                continue  # Ligne de séparation
            for c_idx, cell in enumerate(r):
                col_widths[c_idx] = max(col_widths[c_idx], len(cell))

        # Reconstruit les lignes
        formatted: list[str] = []

        # 1. En-tête
        header_cells = [parsed_rows[0][col_idx].ljust(col_widths[col_idx]) for col_idx in range(num_cols)]
        formatted.append(f"| {' | '.join(header_cells)} |")

        # 2. Séparateur
        sep_row: list[str] = []
        for col_idx in range(num_cols):
            w = col_widths[col_idx]
            align = alignments[col_idx]
            if align == "center":
                sep_row.append(f":{'-' * max(1, w - 2)}:")
            elif align == "right":
                sep_row.append(f"{'-' * max(2, w - 1)}:")
            else:
                sep_row.append(f":{'-' * max(2, w - 1)}")
        formatted.append(f"| {' | '.join(sep_row)} |")

        # 3. Lignes de données
        for r in parsed_rows[2:]:
            data_cells: list[str] = []
            for col_idx in range(num_cols):
                val = r[col_idx]
                w = col_widths[col_idx]
                align = alignments[col_idx]
                if align == "center":
                    data_cells.append(val.center(w))
                elif align == "right":
                    data_cells.append(val.rjust(w))
                else:
                    data_cells.append(val.ljust(w))
            formatted.append(f"| {' | '.join(data_cells)} |")

        return formatted

    @classmethod
    def _clean_whitespace(cls, text: str) -> tuple[str, int]:
        """Nettoie les espaces de fin de ligne et fusionne les lignes vides excédentaires."""
        lines = text.split("\n")
        cleaned_lines: list[str] = []
        count = 0

        for line in lines:
            # Préserve les deux espaces finaux (hard break CommonMark)
            stripped = line.rstrip() + "  " if line.endswith("  ") and not line.endswith("   ") else line.rstrip()
            if stripped != line:
                count += 1
            cleaned_lines.append(stripped)

        intermediate = "\n".join(cleaned_lines)
        # Réduit 3 sauts de ligne ou plus à 2 (une seule ligne vide entre blocs)
        multi_newlines = re.compile(r"\n{3,}")
        if multi_newlines.search(intermediate):
            count += 1
            intermediate = multi_newlines.sub("\n\n", intermediate)

        # Assure un unique saut de ligne final si le document n'est pas vide
        if intermediate and not intermediate.endswith("\n"):
            intermediate += "\n"
            count += 1

        return intermediate, count
