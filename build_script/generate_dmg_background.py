import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def _get_font(font_names: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Tente de charger l'une des polices spécifiées ou bascule sur la police par défaut."""
    for name in font_names:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, RuntimeError):
            continue
    return ImageFont.load_default()


def generate_dmg_backgrounds(output_dir: Path) -> tuple[Path, Path]:
    """Génère l'asset 2x (1280x840) et 1x (640x420) pour le DMG macOS."""
    output_dir.mkdir(parents=True, exist_ok=True)

    w_2x, h_2x = 1280, 840
    # Création du fond avec un dégradé vertical subtil sombre (ardoise/zinc)
    base = Image.new("RGBA", (w_2x, h_2x), (20, 20, 23, 255))
    draw = ImageDraw.Draw(base)

    for y in range(h_2x):
        # Dégradé discret de #16161a à #1a1a20
        ratio = y / h_2x
        r = int(22 + 6 * ratio)
        g = int(22 + 6 * ratio)
        b = int(26 + 10 * ratio)
        draw.line([(0, y), (w_2x, y)], fill=(r, g, b, 255))

    # Cadre discret intérieur
    draw.rounded_rectangle(
        [(16, 16), (w_2x - 16, h_2x - 16)],
        radius=24,
        outline=(45, 45, 55, 255),
        width=2,
    )

    # Polices système macOS
    system_fonts = [
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    bold_fonts = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/SFNS.ttf",
    ]

    title_font = _get_font(bold_fonts, 34)
    subtitle_font = _get_font(system_fonts, 22)
    label_font = _get_font(bold_fonts, 24)

    # Titre principal en haut
    title_text = "Installer AnkiForge"
    subtitle_text = "Glissez l'application dans le dossier Applications"

    # Calcul du centrage du texte
    title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    draw.text(((w_2x - title_w) // 2, 70), title_text, fill=(240, 240, 245, 255), font=title_font)

    subtitle_bbox = draw.textbbox((0, 0), subtitle_text, font=subtitle_font)
    subtitle_w = subtitle_bbox[2] - subtitle_bbox[0]
    draw.text(((w_2x - subtitle_w) // 2, 120), subtitle_text, fill=(160, 160, 175, 255), font=subtitle_font)

    # Repères des icônes :
    # Positions standard 1x : (160, 205) et (480, 205)
    # Positions 2x : (320, 410) et (960, 410)
    left_center = (320, 410)
    right_center = (960, 410)
    pedestal_radius = 110

    # Socle discret sous AnkiForge (gauche)
    draw.ellipse(
        [
            (left_center[0] - pedestal_radius, left_center[1] - pedestal_radius),
            (left_center[0] + pedestal_radius, left_center[1] + pedestal_radius),
        ],
        fill=(30, 30, 36, 200),
        outline=(55, 55, 68, 255),
        width=3,
    )

    # Socle discret sous Applications (droite) avec lueur d'accentuation bleutée
    draw.ellipse(
        [
            (right_center[0] - pedestal_radius, right_center[1] - pedestal_radius),
            (right_center[0] + pedestal_radius, right_center[1] + pedestal_radius),
        ],
        fill=(26, 32, 48, 220),
        outline=(59, 130, 246, 255),
        width=3,
    )

    # Flèche centrale stylisée glisser-déposer de gauche à droite
    arrow_y = 410
    start_x = 480
    end_x = 800
    arrow_color = (96, 165, 250, 255)  # Bleu clair vibrant (Tailwind blue-400)

    # Ligne principale pointillée ou dégradée
    arrow_width = 8
    draw.line([(start_x, arrow_y), (end_x, arrow_y)], fill=arrow_color, width=arrow_width)

    # Tête de flèche
    head_size = 28
    head_points = [
        (end_x, arrow_y),
        (end_x - head_size, arrow_y - head_size),
        (end_x - head_size + 6, arrow_y),
        (end_x - head_size, arrow_y + head_size),
    ]
    draw.polygon(head_points, fill=arrow_color)

    # Légende d'action au-dessus de la flèche
    action_text = "Glisser & Déposer"
    action_bbox = draw.textbbox((0, 0), action_text, font=label_font)
    action_w = action_bbox[2] - action_bbox[0]
    draw.text(
        ((start_x + end_x - action_w) // 2, arrow_y - 50),
        action_text,
        fill=(147, 197, 253, 255),
        font=label_font,
    )

    # Libellé discret en bas
    footer_text = "AnkiForge • Environnement de création de cartes optimisé par l'IA"
    footer_font = _get_font(system_fonts, 18)
    footer_bbox = draw.textbbox((0, 0), footer_text, font=footer_font)
    footer_w = footer_bbox[2] - footer_bbox[0]
    draw.text(((w_2x - footer_w) // 2, h_2x - 55), footer_text, fill=(110, 110, 125, 255), font=footer_font)

    # Sauvegarde version Retina 2x
    path_2x = output_dir / "dmg_background@2x.png"
    base.save(path_2x, "PNG", optimize=True)

    # Sauvegarde version 1x avec échantillonnage haute qualité Lanczos
    path_1x = output_dir / "dmg_background.png"
    base_1x = base.resize((640, 420), Image.Resampling.LANCZOS)
    base_1x.save(path_1x, "PNG", optimize=True)

    return path_1x, path_2x


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    assets_dir = Path(__file__).resolve().parent / "assets"
    p1, p2 = generate_dmg_backgrounds(assets_dir)
    logger.info("Assets DMG générés avec succès : 1x=%s, 2x=%s", p1, p2)
