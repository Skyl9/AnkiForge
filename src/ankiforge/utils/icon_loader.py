from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import QByteArray
from ankiforge.utils.paths import get_project_root
from ankiforge.ui.theme import DesignTokens


def load_phosphor_icon(name: str, color: str = DesignTokens.TEXT_SECONDARY) -> QIcon:
    """Load a Phosphor SVG icon and replace currentColor with the specified color."""
    # Handle the prefix 'ph.' if it was passed
    if name.startswith("ph."):
        name = name[3:]

    svg_path = get_project_root() / "src" / "ankiforge" / "ressources" / "phosphor-icons" / "SVGs" / "Regular" / f"{name}.svg"

    if not svg_path.exists():
        print(f"[Warning] Icon not found: {svg_path}")
        return QIcon()

    with open(svg_path, "r", encoding="utf-8") as f:
        svg_content = f.read()

    # Replace currentColor with our target color
    svg_content = svg_content.replace("currentColor", color)

    # Load into QPixmap
    pixmap = QPixmap()
    pixmap.loadFromData(QByteArray(svg_content.encode("utf-8")), "SVG")

    return QIcon(pixmap)
