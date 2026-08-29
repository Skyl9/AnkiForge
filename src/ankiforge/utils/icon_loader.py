from PySide6.QtCore import QByteArray
from PySide6.QtGui import QIcon, QPixmap

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.paths import get_resource_path


def load_phosphor_icon(name: str, color: str = DesignTokens.TEXT_SECONDARY, weight: str = "regular") -> QIcon:
    """Load a Phosphor SVG icon and replace currentColor with the specified color."""
    if name.startswith("ph."):
        name = name[3:]

    weight = weight.lower()
    suffix = f"-{weight}" if weight != "regular" else ""
    filename = f"{name}{suffix}.svg"

    svg_path = get_resource_path("src", "ressources", "phosphor-icons", "SVGs", weight, filename)
    if not svg_path.exists():
        svg_path = get_resource_path("ressources", "phosphor-icons", "SVGs", weight, filename)

    if not svg_path.exists():
        return QIcon()

    try:
        with open(svg_path, encoding="utf-8") as f:
            svg_content = f.read()

        # Replace currentColor with our target color
        svg_content = svg_content.replace("currentColor", color) if "currentColor" in svg_content else svg_content.replace("<svg ", f'<svg fill="{color}" ')

        pixmap = QPixmap()
        pixmap.loadFromData(QByteArray(svg_content.encode("utf-8")), b"SVG")
        return QIcon(pixmap)
    except Exception:
        return QIcon()


def load_logo_icon(color: str = DesignTokens.ACCENT_PRIMARY) -> QIcon:
    """Load the AnkiForge logo SVG and color it with the specified color."""
    logo_path = get_resource_path("src", "ressources", "icons", "logo.svg")
    if not logo_path.exists():
        logo_path = get_resource_path("ressources", "icons", "logo.svg")

    if not logo_path.exists():
        return QIcon()

    try:
        with open(logo_path, encoding="utf-8") as f:
            svg_content = f.read()

        svg_content = svg_content.replace("currentColor", color)

        pixmap = QPixmap()
        pixmap.loadFromData(QByteArray(svg_content.encode("utf-8")), b"SVG")
        return QIcon(pixmap)

    except Exception:
        return QIcon()
