from ankiforge.utils.chunker import (
    _get_protected_intervals,
    _is_safe_split,
    smart_chunk_text,
)


def test_protected_intervals_detection():
    """Vérifie que les blocs Markdown et LaTeX sont bien repérés."""
    text = "Voici du texte normal.\n" "```python\nprint('Hello')\n```\n" "Et une équation:\n" "$$\nE=mc^2\n$$\n" "Fin."
    intervals = _get_protected_intervals(text)

    assert len(intervals) == 2
    # On vérifie que la protection enveloppe bien tout le bloc code
    assert text[intervals[0][0] : intervals[0][1]].startswith("```python")
    # Et tout le bloc LaTeX
    assert text[intervals[1][0] : intervals[1][1]].startswith("$$")


def test_safe_split_logic():
    """Vérifie que l'algorithme refuse de couper au milieu d'un bloc protégé."""
    text = "0123456789 ```code``` 9876543210"
    intervals = _get_protected_intervals(text)

    # L'index 5 (avant le code) est sûr
    assert _is_safe_split(5, intervals) is True
    # L'index 15 (au milieu de 'code') est INTERDIT
    assert _is_safe_split(15, intervals) is False
    # L'index 25 (après le code) est sûr
    assert _is_safe_split(25, intervals) is True


def test_smart_chunk_avoids_latex_split():
    """Le test ULTIME : prouver que le découpage ne casse jamais le LaTeX."""
    intro = "Introduction classique avec une première phrase. "
    math_block = "$$\n\\int_{0}^{\\infty} x^2 dx = \\text{Magie}\n$$"
    outro = " Conclusion du chapitre."

    full_text = intro + math_block + outro

    # On force une limite maximale qui tombe EXACTEMENT au milieu du bloc LaTeX !
    # Sans protection, le texte serait coupé en plein milieu de l'intégrale.
    dangerous_limit = len(intro) + 10

    chunks = smart_chunk_text(full_text, strategy="Classique", max_chars=dangerous_limit)

    # Le chunker doit avoir refusé de couper dans le LaTeX et s'être rabattu sur le point '. '
    # de la première phrase.
    assert len(chunks) > 1
    assert chunks[0] == "Introduction classique avec une première phrase."

    # Le bloc mathématique entier doit se retrouver intact dans le morceau suivant
    assert math_block in chunks[1]


def test_semantic_chunking_with_giant_chapter():
    """Vérifie que si un chapitre Markdown est trop grand, il est sous-découpé (Récursivité)."""
    text = (
        "# Chapitre 1\n" + "A" * 8000 + "\n"  # Un chapitre géant de 8000 caractères
        "# Chapitre 2\n"
        "Texte normal."
    )

    # On limite à 5000 caractères. Le Chapitre 1 devrait être coupé en 2.
    chunks = smart_chunk_text(text, strategy="Sémantique (Titres)", max_chars=5000, overlap=0)

    # On s'attend à au moins 3 morceaux : (Chap1 part1), (Chap1 part2), (Chapitre 2)
    assert len(chunks) >= 3
    # Aucun morceau ne doit dépasser la limite
    for chunk in chunks:
        assert len(chunk) <= 5000


def test_chunking_no_strategy():
    """Vérifie le passe-droit 'Aucun'."""
    text = "A" * 10000
    chunks = smart_chunk_text(text, strategy="Aucun (Document entier)", max_chars=100)
    assert len(chunks) == 1
    assert len(chunks[0]) == 10000
