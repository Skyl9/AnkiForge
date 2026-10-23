import json
import re

from ankiforge.database.models import NoteTypeModel


def extract_css_classes(css_text: str) -> list[str]:
    """Extrait la liste unique des classes CSS définies dans la feuille de style."""
    if not css_text:
        return []
    matches = re.findall(r"\.([a-zA-Z_-][a-zA-Z0-9_\-]*)", css_text)
    excluded = {
        "hover",
        "active",
        "focus",
        "visited",
        "disabled",
        "first-child",
        "last-child",
        "nth-child",
        "before",
        "after",
    }
    classes: list[str] = []
    for cls in matches:
        if cls not in classes and cls not in excluded and not cls.isdigit():
            classes.append(cls)
    return classes


def sort_note_types(models: list[NoteTypeModel], sort_order: str) -> list[NoteTypeModel]:
    """Applique le tri sur les modèles selon les 5 critères canoniques."""
    if not models:
        return []

    if sort_order == "name_asc":
        return sorted(models, key=lambda m: (m.name or "").lower())
    if sort_order == "name_desc":
        return sorted(models, key=lambda m: (m.name or "").lower(), reverse=True)
    if sort_order == "created_desc":
        return sorted(models, key=lambda m: getattr(m, "id", 0) or 0, reverse=True)
    if sort_order == "created_asc":
        return sorted(models, key=lambda m: getattr(m, "id", 0) or 0)
    if sort_order == "template_count_desc":

        def template_count(m: NoteTypeModel) -> tuple[int, str]:
            count = 1
            if getattr(m, "templates", None):
                try:
                    t_list = json.loads(m.templates)
                    if isinstance(t_list, list):
                        count = len(t_list)
                except Exception:
                    count = 1
            return (-count, (m.name or "").lower())

        return sorted(models, key=template_count)
    # Fallback par défaut
    return sorted(models, key=lambda m: (m.name or "").lower())
