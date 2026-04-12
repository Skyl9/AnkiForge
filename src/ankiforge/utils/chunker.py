import logging
import re

logger = logging.getLogger(__name__)


def _get_protected_intervals(text: str) -> list[tuple[int, int]]:
    """Identifie les blocs LaTeX et Markdown à ne JAMAIS scinder."""
    intervals = []

    # Blocs de code Markdown (```...```)
    for m in re.finditer(r"```.*?```", text, re.DOTALL):
        intervals.append((m.start(), m.end()))

    # Blocs LaTeX Display ($$...$$)
    for m in re.finditer(r"\$\$.*?\$\$", text, re.DOTALL):
        intervals.append((m.start(), m.end()))

    # Blocs LaTeX alternatifs (\[...\])
    for m in re.finditer(r"\\\[.*?\\\]", text, re.DOTALL):
        intervals.append((m.start(), m.end()))

    return intervals


def _is_safe_split(idx: int, protected_intervals: list[tuple[int, int]]) -> bool:
    """Vérifie si un index ne tombe pas au milieu d'un bloc protégé."""
    for start, end in protected_intervals:
        if start < idx < end:
            return False
    return True


def _find_best_split(text: str, start: int, max_end: int, protected_intervals: list[tuple[int, int]]) -> int:
    """Trouve le meilleur endroit pour couper, en respectant les zones protégées."""
    if max_end >= len(text):
        return len(text)

    # Ordre de préférence des séparateurs
    separators = ["\n\n", "\n", ". ", " "]

    for sep in separators:
        split_idx = text.rfind(sep, start, max_end)

        while split_idx != -1:
            if _is_safe_split(split_idx, protected_intervals):
                return split_idx + len(sep) if sep.strip() else split_idx
            # S'il est protégé, on cherche le précédent
            split_idx = text.rfind(sep, start, split_idx)

    return max_end


def smart_chunk_text(text: str, strategy: str, max_chars: int = 6000, overlap: int = 1000) -> list[str]:
    """
    Le moteur de découpage intelligent et sécurisé.
    Empêche la coupure au milieu des formules mathématiques et des blocs de code.
    """
    if strategy == "Aucun (Document entier)" or len(text) <= max_chars:
        return [text]

    chunks = []
    protected_intervals = _get_protected_intervals(text)

    if strategy == "Sémantique (Titres)":
        # On trouve tous les débuts de titres
        splits = [0] + [m.start() for m in re.finditer(r"(^|\n)(#{1,3})\s", text)] + [len(text)]
        splits = sorted(list(set(splits)))

        semantic_chunks = []
        for i in range(len(splits) - 1):
            part = text[splits[i] : splits[i + 1]].strip()
            if len(part) > 50:
                semantic_chunks.append(part)

        # RÈGLE VITALE : On vérifie si un chapitre ne dépasse pas la limite
        for chunk in semantic_chunks:
            if len(chunk) > max_chars:
                logger.debug(f"Chapitre trop long ({len(chunk)} chars), sous-découpage activé.")
                # Appel récursif !
                sub_chunks = smart_chunk_text(chunk, "Chevauchement (Overlap)", max_chars, overlap)
                chunks.extend(sub_chunks)
            else:
                chunks.append(chunk)

        if not chunks:
            return smart_chunk_text(text, "Chevauchement (Overlap)", max_chars, overlap)

        return chunks

    elif strategy in ("Chevauchement (Overlap)", "Classique"):
        start = 0
        while start < len(text):
            max_end = start + max_chars

            split_idx = _find_best_split(text, start, max_end, protected_intervals)

            if split_idx <= start:
                logger.warning(f"Tronçonnage forcé à l'index {start + max_chars} (aucun espace trouvé).")
                split_idx = start + max_chars

            chunks.append(text[start:split_idx].strip())

            if split_idx >= len(text):
                break

            if strategy == "Chevauchement (Overlap)":
                overlap_target = split_idx - overlap
                if overlap_target <= start:
                    next_start = split_idx
                else:
                    next_start = _find_best_split(text, start, overlap_target, protected_intervals)

                if next_start <= start:
                    start = split_idx
                else:
                    start = next_start
            else:
                start = split_idx

        return chunks

    return [text]
