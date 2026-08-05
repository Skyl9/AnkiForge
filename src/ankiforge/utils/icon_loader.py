from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import QByteArray
from ankiforge.utils.paths import get_project_root
from ankiforge.ui.theme import DesignTokens


def load_phosphor_icon(name: str, color: str = DesignTokens.TEXT_SECONDARY, weight: str = "regular") -> QIcon:
    """Load a Phosphor SVG icon and replace currentColor with the specified color."""
    # Handle the prefix 'ph.' if it was passed
    if name.startswith("ph."):
        name = name[3:]

    weight = weight.lower()
    suffix = f"-{weight}" if weight != "regular" else ""
    filename = f"{name}{suffix}.svg"

    svg_path = get_project_root() / "src" / "ressources" / "phosphor-icons" / "SVGs" / weight / filename

    if not svg_path.exists():
        print(f"[Warning] Icon not found: {svg_path}")
        return QIcon()

    with open(svg_path, "r", encoding="utf-8") as f:
        svg_content = f.read()

    # Replace currentColor with our target color
    if "currentColor" in svg_content:
        svg_content = svg_content.replace("currentColor", color)
    else:
        # In case the SVG doesn't use currentColor (e.g. many fill icons default to black paths),
        # inject the fill color into the root SVG tag to cascade downwards.
        svg_content = svg_content.replace("<svg ", f'<svg fill="{color}" ')

    # Load into QPixmap
    pixmap = QPixmap()
    pixmap.loadFromData(QByteArray(svg_content.encode("utf-8")), "SVG")

    return QIcon(pixmap)


def load_logo_icon(color: str = DesignTokens.ACCENT_PRIMARY) -> QIcon:
    """Load the AnkiForge logo SVG and color it with the specified color."""
    logo_path = get_project_root() / "src" / "ressources" / "icons" / "logo.svg"
    if not logo_path.exists():
        print(f"[Warning] Logo icon not found: {logo_path}")
        return QIcon()

    with open(logo_path, "r", encoding="utf-8") as f:
        svg_content = f.read()

    svg_content = svg_content.replace("currentColor", color)

    pixmap = QPixmap()
    pixmap.loadFromData(QByteArray(svg_content.encode("utf-8")), "SVG")
    return QIcon(pixmap)
