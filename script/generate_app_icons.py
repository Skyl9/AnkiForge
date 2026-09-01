#!/usr/bin/env python3
"""Script de génération des icônes et logos de l'application AnkiForge pour macOS, Windows et Linux."""

import pathlib
import subprocess
import tempfile

from PIL import Image

SVG_ICON_CONTENT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <!-- Dark Squircle Background Gradient -->
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1e1b4b"/>
      <stop offset="45%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#020617"/>
    </linearGradient>

    <!-- Subtle Radial Glow -->
    <radialGradient id="radialGlow" cx="50%" cy="35%" r="60%">
      <stop offset="0%" stop-color="#4338ca" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#0f172a" stop-opacity="0"/>
    </radialGradient>

    <!-- Front Card Gradient (Vibrant Indigo/Violet) -->
    <linearGradient id="cardFront" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#6366f1"/>
      <stop offset="50%" stop-color="#7c3aed"/>
      <stop offset="100%" stop-color="#4f46e5"/>
    </linearGradient>

    <!-- Back Card Gradient (Pink / Purple Accent) -->
    <linearGradient id="cardBack" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ec4899"/>
      <stop offset="50%" stop-color="#c084fc"/>
      <stop offset="100%" stop-color="#9333ea"/>
    </linearGradient>

    <!-- Spark / Forge Flame Gradient -->
    <linearGradient id="sparkGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#fef08a"/>
      <stop offset="40%" stop-color="#f59e0b"/>
      <stop offset="100%" stop-color="#ea580c"/>
    </linearGradient>

    <!-- Glow Filter -->
    <filter id="forgeGlow" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="8" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>

    <!-- Soft Drop Shadow -->
    <filter id="softShadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="10" stdDeviation="14" flood-color="#000000" flood-opacity="0.55"/>
    </filter>
  </defs>

  <!-- Squircle Base Canvas (macOS / Windows App Icon style) -->
  <rect x="28" y="28" width="456" height="456" rx="108" ry="108" fill="url(#bgGrad)" stroke="#334155" stroke-width="3" filter="url(#softShadow)"/>
  <rect x="28" y="28" width="456" height="456" rx="108" ry="108" fill="url(#radialGlow)"/>

  <!-- Back Rotated Flashcard (Knowledge Layer) -->
  <rect x="160" y="96" width="204" height="268" rx="22" fill="url(#cardBack)" opacity="0.88" transform="rotate(14 262 230)" filter="url(#softShadow)"/>

  <!-- Front Main Flashcard (Active Card) -->
  <rect x="108" y="128" width="216" height="274" rx="22" fill="url(#cardFront)" filter="url(#softShadow)" stroke="#a5b4fc" stroke-width="2.5"/>

  <!-- Flashcard Content Mock Lines (Clean Typographic Aesthetic) -->
  <rect x="142" y="174" width="148" height="14" rx="7" fill="#ffffff" opacity="0.95"/>
  <rect x="142" y="206" width="104" height="10" rx="5" fill="#e0e7ff" opacity="0.8"/>
  <rect x="142" y="228" width="128" height="10" rx="5" fill="#e0e7ff" opacity="0.8"/>
  <rect x="142" y="250" width="88" height="10" rx="5" fill="#e0e7ff" opacity="0.6"/>

  <!-- Forge Emblem / Star Spark (Bottom Right of Card) -->
  <g transform="translate(254, 286)" filter="url(#forgeGlow)">
    <!-- Outer Glow Circle -->
    <circle cx="28" cy="28" r="32" fill="#f59e0b" opacity="0.25"/>
    <!-- Central Forge Star -->
    <path d="M28,4 L35,21 L52,28 L35,35 L28,52 L21,35 L4,28 L21,21 Z" fill="url(#sparkGrad)" stroke="#ffffff" stroke-width="1.5"/>
    <circle cx="28" cy="28" r="5" fill="#ffffff"/>
  </g>
</svg>"""


def generate_icons() -> None:
    icons_dir = pathlib.Path(__file__).resolve().parent.parent / "src" / "ressources" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    svg_path = icons_dir / "ankiforge.svg"
    svg_path.write_text(SVG_ICON_CONTENT, encoding="utf-8")
    print(f"[SUCCESS] SVG écrit dans {svg_path}")

    # 1. Génération du PNG 512x512 et 1024x1024
    png_512 = icons_dir / "ankiforge.png"
    png_1024 = icons_dir / "ankiforge_1024.png"

    try:
        subprocess.run(["rsvg-convert", "-w", "512", "-h", "512", str(svg_path), "-o", str(png_512)], check=True)
        subprocess.run(["rsvg-convert", "-w", "1024", "-h", "1024", str(svg_path), "-o", str(png_1024)], check=True)
        print(f"[SUCCESS] PNG 512x512 et 1024x1024 générés dans {icons_dir}")
    except Exception as e:
        print(f"[WARNING] Erreur avec rsvg-convert: {e}")

    # 2. Génération du fichier Windows .ico
    if png_1024.exists() or png_512.exists():
        src_png = png_1024 if png_1024.exists() else png_512
        img = Image.open(src_png)
        ico_path = icons_dir / "ankiforge.ico"
        img.save(
            ico_path,
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
        print(f"[SUCCESS] ICO multi-résolutions généré dans {ico_path}")

    # 3. Génération du fichier macOS .icns via iconutil
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            iconset_dir = pathlib.Path(tmp_dir) / "ankiforge.iconset"
            iconset_dir.mkdir()

            sizes = [
                (16, "icon_16x16.png"),
                (32, "icon_16x16@2x.png"),
                (32, "icon_32x32.png"),
                (64, "icon_32x32@2x.png"),
                (128, "icon_128x128.png"),
                (256, "icon_128x128@2x.png"),
                (256, "icon_256x256.png"),
                (512, "icon_256x256@2x.png"),
                (512, "icon_512x512.png"),
                (1024, "icon_512x512@2x.png"),
            ]

            for sz, filename in sizes:
                subprocess.run(
                    ["rsvg-convert", "-w", str(sz), "-h", str(sz), str(svg_path), "-o", str(iconset_dir / filename)],
                    check=True,
                )

            icns_path = icons_dir / "ankiforge.icns"
            subprocess.run(["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)], check=True)
            print(f"[SUCCESS] ICNS Apple Retina généré dans {icns_path}")
    except Exception as e:
        print(f"[WARNING] Erreur lors de la génération de l'icns: {e}")


if __name__ == "__main__":
    generate_icons()
