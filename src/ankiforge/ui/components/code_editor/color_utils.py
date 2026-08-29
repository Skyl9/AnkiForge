import re
from typing import List, Tuple
from PySide6.QtGui import QColor

COLOR_PATTERN = re.compile(
    r"(#[0-9a-fA-F]{3,8}\b|"
    r"rgba?\s*\(\s*\d+\s*,\s*\d+\s*,\s*\d+(?:\s*,\s*[\d\.]+)?\s*\)|"
    r"hsla?\s*\(\s*\d+\s*,\s*\d+%\s*,\s*\d+%(?:\s*,\s*[\d\.]+)?\s*\))"
)


def extract_colors_from_text(line_text: str) -> List[Tuple[str, QColor]]:
    """Extrait tous les codes couleurs hexadécimaux, rgb/rgba ou hsl/hsla d'une ligne de code."""
    colors: List[Tuple[str, QColor]] = []
    for match in COLOR_PATTERN.finditer(line_text):
        col_str = match.group(0)
        c = QColor(col_str)
        if not c.isValid():
            m = re.match(r"rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d\.]+))?\s*\)", col_str)
            if m:
                r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
                a = float(m.group(4)) if m.group(4) is not None else 1.0
                c = QColor(r, g, b, int(a * 255))
        if c.isValid():
            colors.append((col_str, c))
    return colors
