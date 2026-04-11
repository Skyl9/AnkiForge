from __future__ import annotations

from typing import Any


def is_template_cloze(templates: list[dict[str, Any]]) -> bool:
    return any("{{cloze:" in t.get("qfmt", "") or "{{cloze:" in t.get("afmt", "") for t in templates)


def get_cloze_card_count(fields: dict[str, str], minimum: int = 1) -> int:
    """
    Calcule le nombre de cartes cloze à afficher à partir des champs remplis.
    """
    from ankiforge.utils.anki_renderer import get_max_cloze_index

    return max(minimum, get_max_cloze_index(fields))


def sync_preview_card_selector(
    selector: Any,
    templates: list[dict[str, Any]],
    current_fields: dict[str, str],
) -> tuple[bool, int]:
    """
    Met à jour le sélecteur de cartes selon le type de note.
    Retourne (is_cloze, selected_index).
    """
    is_cloze = is_template_cloze(templates)

    current_selector_count = selector.count()
    if is_cloze:
        num_cards = get_cloze_card_count(current_fields)
        if current_selector_count != num_cards:
            selector.blockSignals(True)
            selector.clear()
            for i in range(num_cards):
                selector.addItem(f"Trou {i + 1} (c{i + 1})")
            selector.blockSignals(False)
    else:
        if current_selector_count != len(templates):
            selector.blockSignals(True)
            selector.clear()
            for tmpl in templates:
                selector.addItem(tmpl.get("name", "Carte"))
            selector.blockSignals(False)

    selected_idx = selector.currentIndex()
    if selected_idx < 0:
        selected_idx = 0

    if not is_cloze and templates and selected_idx >= len(templates):
        selected_idx = 0

    return is_cloze, selected_idx


def get_preview_template(
    templates: list[dict[str, Any]],
    is_cloze: bool,
    selected_index: int,
) -> tuple[dict[str, Any], int]:
    """
    Renvoie le template à utiliser pour l'aperçu et l'index de carte réel.
    """
    if is_cloze:
        return templates[0] if templates else {}, selected_index

    if not templates:
        return {}, 0

    safe_index = selected_index if selected_index < len(templates) else 0
    return templates[safe_index], safe_index
