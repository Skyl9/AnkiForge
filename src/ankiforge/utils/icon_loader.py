import logging

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.paths import get_resource_path

logger = logging.getLogger(__name__)

_icon_cache: dict[tuple[str, str, str], QIcon] = {}
_logo_cache: dict[str, QIcon] = {}
_ICON_SIZES = (16, 20, 24, 32, 48, 64, 128, 256)


def clear_icon_cache() -> None:
    """Vide le cache mémoire des icônes."""
    _icon_cache.clear()
    _logo_cache.clear()


def _render_svg_to_icon(svg_content: str) -> QIcon:
    """Rendu d'un contenu SVG vers une QIcon multi-résolutions haute fidélité."""
    if QGuiApplication.instance() is None:
        return QIcon()

    data = QByteArray(svg_content.encode("utf-8"))
    renderer = QSvgRenderer(data)
    if not renderer.isValid():
        return QIcon()

    icon = QIcon()
    for size_val in _ICON_SIZES:
        pixmap = QPixmap(size_val, size_val)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        icon.addPixmap(pixmap)

    return icon


def load_phosphor_icon(name: str, color: str = DesignTokens.TEXT_SECONDARY, weight: str = "regular") -> QIcon:
    """
    Charge une icône Phosphor SVG, applique la couleur demandée et retourne une QIcon multi-résolution.
    Supporte les préfixes 'ph.', 'ph:' et les suffixes '.svg'.
    """
    if not name:
        return QIcon()

    # Nettoyage du nom d'icône
    clean_name = name
    for prefix in ("ph.", "ph:", "phosphor.", "phosphor:"):
        if clean_name.startswith(prefix):
            clean_name = clean_name[len(prefix) :]
            break

    if clean_name.endswith(".svg"):
        clean_name = clean_name[:-4]

    weight = weight.lower().strip() or "regular"
    cache_key = (clean_name, color, weight)
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    suffix = f"-{weight}" if weight != "regular" else ""
    filename = f"{clean_name}{suffix}.svg"

    candidates = [
        get_resource_path("src", "ressources", "phosphor-icons", "SVGs", weight, filename),
        get_resource_path("ressources", "phosphor-icons", "SVGs", weight, filename),
        get_resource_path("src", "ressources", "phosphor-icons", "SVGs Flat", weight, filename),
        get_resource_path("ressources", "phosphor-icons", "SVGs Flat", weight, filename),
        # Repli sur le mode regular si le poids spécifique n'existe pas
        get_resource_path("src", "ressources", "phosphor-icons", "SVGs", "regular", f"{clean_name}.svg"),
        get_resource_path("ressources", "phosphor-icons", "SVGs", "regular", f"{clean_name}.svg"),
        get_resource_path("src", "ressources", "phosphor-icons", "SVGs Flat", "regular", f"{clean_name}.svg"),
        get_resource_path("ressources", "phosphor-icons", "SVGs Flat", "regular", f"{clean_name}.svg"),
    ]

    svg_path = next((p for p in candidates if p.exists()), None)
    if not svg_path:
        logger.debug("Icône Phosphor introuvable : '%s' (poids=%s)", clean_name, weight)
        return QIcon()

    try:
        with open(svg_path, encoding="utf-8") as f:
            svg_content = f.read()

        # Remplacement de couleur (fill & stroke)
        svg_content = svg_content.replace("currentColor", color) if "currentColor" in svg_content else svg_content.replace("<svg ", f'<svg fill="{color}" ')

        icon = _render_svg_to_icon(svg_content)
        _icon_cache[cache_key] = icon
        return icon
    except Exception as e:
        logger.debug("Erreur de chargement de l'icône '%s': %s", clean_name, e)
        return QIcon()


def load_logo_icon(color: str = DesignTokens.ACCENT_PRIMARY) -> QIcon:
    """Charge le logo AnkiForge SVG et lui applique la couleur spécifiée."""
    if color in _logo_cache:
        return _logo_cache[color]

    candidates = [
        get_resource_path("src", "ressources", "icons", "logo.svg"),
        get_resource_path("ressources", "icons", "logo.svg"),
    ]

    logo_path = next((p for p in candidates if p.exists()), None)
    if not logo_path:
        logger.debug("Logo AnkiForge introuvable dans les ressources")
        return QIcon()

    try:
        with open(logo_path, encoding="utf-8") as f:
            svg_content = f.read()

        svg_content = svg_content.replace("currentColor", color) if "currentColor" in svg_content else svg_content.replace("<svg ", f'<svg fill="{color}" ')

        icon = _render_svg_to_icon(svg_content)
        _logo_cache[color] = icon
        return icon
    except Exception as e:
        logger.debug("Erreur de chargement du logo AnkiForge: %s", e)
        return QIcon()
