import re


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
