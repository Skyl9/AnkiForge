#!/usr/bin/env python3
"""Script de génération des icônes et logos officiels d'AnkiDraft pour macOS, Windows, Linux et Web."""

from __future__ import annotations

import logging
import math
import pathlib
import subprocess
import tempfile

from PIL import Image
from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QFont,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QTransform,
)
from PySide6.QtSvg import QSvgRenderer

logger = logging.getLogger(__name__)


def _qpath_to_svg_d(path: QPainterPath) -> str:
    """Convertit un QPainterPath en chaîne SVG `d`."""
    cmds: list[str] = []
    i = 0
    count = path.elementCount()
    while i < count:
        el = path.elementAt(i)
        etype = el.type
        if etype == QPainterPath.ElementType.MoveToElement:
            if cmds and cmds[-1] != "Z":
                cmds.append("Z")
            cmds.append(f"M {el.x:.2f} {el.y:.2f}")
            i += 1
        elif etype == QPainterPath.ElementType.LineToElement:
            cmds.append(f"L {el.x:.2f} {el.y:.2f}")
            i += 1
        elif etype == QPainterPath.ElementType.CurveToElement:
            c1 = el
            c2 = path.elementAt(i + 1)
            end = path.elementAt(i + 2)
            cmds.append(f"C {c1.x:.2f} {c1.y:.2f}, {c2.x:.2f} {c2.y:.2f}, {end.x:.2f} {end.y:.2f}")
            i += 3
        else:
            i += 1
    if cmds and cmds[-1] != "Z":
        cmds.append("Z")
    return " ".join(cmds)


def _extract_question_glyph_paths(
    family: str,
    weight: QFont.Weight,
    target_cx: float,
    target_top_y: float,
    target_total_height: float,
) -> tuple[QPainterPath, QPainterPath]:
    """Extrait les contours vectoriels de la crosse et du point du glyphe '?'."""
    font = QFont(family)
    font.setPixelSize(240)
    font.setWeight(weight)

    raw_path = QPainterPath()
    raw_path.addText(QPointF(0, 0), font, "?")
    rect = raw_path.boundingRect()

    scale = target_total_height / rect.height()
    raw_cx = rect.center().x()
    raw_top = rect.top()

    t = QTransform()
    t.translate(target_cx, target_top_y)
    t.scale(scale, scale)
    t.translate(-raw_cx, -raw_top)

    transformed = t.map(raw_path)

    subpaths: list[tuple[QPainterPath, float]] = []
    cur = QPainterPath()
    min_y = 1e9
    i = 0
    count = transformed.elementCount()
    while i < count:
        el = transformed.elementAt(i)
        if el.type == QPainterPath.ElementType.MoveToElement:
            if not cur.isEmpty():
                cur.closeSubpath()
                subpaths.append((cur, min_y))
            cur = QPainterPath()
            cur.moveTo(el.x, el.y)
            min_y = el.y
            i += 1
        elif el.type == QPainterPath.ElementType.LineToElement:
            cur.lineTo(el.x, el.y)
            min_y = min(min_y, el.y)
            i += 1
        elif el.type == QPainterPath.ElementType.CurveToElement:
            c1 = el
            c2 = transformed.elementAt(i + 1)
            end = transformed.elementAt(i + 2)
            cur.cubicTo(c1.x, c1.y, c2.x, c2.y, end.x, end.y)
            min_y = min(min_y, c1.y, c2.y, end.y)
            i += 3
        else:
            i += 1
    if not cur.isEmpty():
        cur.closeSubpath()
        subpaths.append((cur, min_y))

    subpaths.sort(key=lambda item: item[1])
    return subpaths[0][0], subpaths[-1][0]


def _apple_superellipse_path(
    cx: float,
    cy: float,
    half_size: float,
    exponent: float = 4.6,
    steps: int = 256,
) -> str:
    """Génère le tracé SVG d'une superellipse Apple à courbure continue."""
    pts: list[str] = []
    for i in range(steps):
        theta = 2.0 * math.pi * i / steps
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        x = cx + half_size * math.copysign(abs(cos_t) ** (2.0 / exponent), cos_t)
        y = cy + half_size * math.copysign(abs(sin_t) ** (2.0 / exponent), sin_t)
        cmd = "M" if i == 0 else "L"
        pts.append(f"{cmd} {x:.2f} {y:.2f}")
    pts.append("Z")
    return " ".join(pts)


def build_ankidraft_icon_svg(card_rx: float = 5.2, line_rx: float = 1.6) -> str:
    """Construit le SVG officiel d'AnkiDraft (F4 : Brouillon structuré au 1er plan, Flashcard '?' au 2nd plan)."""
    card_w, card_h = 52.0, 74.0
    bx_center, by_center = 80.5, 56.0
    fx_center, fy_center = 44.0, 68.0
    q_offset_x = 8.2
    q_height = 41.5
    trench_w = 8.5

    bx = bx_center - card_w / 2.0
    by = by_center - card_h / 2.0
    back_local = QPainterPath()
    back_local.addRoundedRect(QRectF(bx, by, card_w, card_h), card_rx, card_rx)
    t_back = QTransform()
    t_back.translate(bx_center, by_center)
    t_back.rotate(9)
    t_back.translate(-bx_center, -by_center)
    back_world = t_back.map(back_local)

    q_top_y = by + (card_h - q_height) / 2.0
    hook_local, dot_local = _extract_question_glyph_paths(
        "Helvetica Neue",
        QFont.Weight.Bold,
        target_cx=bx_center + q_offset_x,
        target_top_y=q_top_y,
        target_total_height=q_height,
    )
    hook_world = t_back.map(hook_local)
    dot_world = t_back.map(dot_local)

    fx = fx_center - card_w / 2.0
    fy = fy_center - card_h / 2.0
    front_local = QPainterPath()
    front_local.addRoundedRect(QRectF(fx, fy, card_w, card_h), card_rx, card_rx)
    t_front = QTransform()
    t_front.translate(fx_center, fy_center)
    t_front.rotate(-5)
    t_front.translate(-fx_center, -fy_center)
    front_world = t_front.map(front_local)

    # Loi de Proximité (Gestalt) : 1 Titre indigo (68%) + saut de paragraphe (10.2) + 2 lignes de corps (100%, 56%)
    prim_front_local = QPainterPath()
    sec_front_local = QPainterPath()
    margin_x = 8.5
    lx = fx + margin_x
    max_lw = card_w - 2.0 * margin_x
    total_bars_h = 35.8
    top_y = fy + (card_h - total_bars_h) / 2.0 - 1.2

    prim_front_local.addRoundedRect(QRectF(lx, top_y, max_lw * 0.68, 7.4), line_rx, line_rx)
    sec_front_local.addRoundedRect(QRectF(lx, top_y + 17.6, max_lw * 1.00, 6.4), line_rx, line_rx)
    sec_front_local.addRoundedRect(QRectF(lx, top_y + 29.4, max_lw * 0.56, 6.4), line_rx, line_rx)

    prim_front_world = t_front.map(prim_front_local)
    sec_front_world = t_front.map(sec_front_local)

    stroker = QPainterPathStroker()
    stroker.setWidth(trench_w)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    cutter = front_world.united(stroker.createStroke(front_world))

    back_cut = back_world.subtracted(cutter)
    hook_cut = hook_world.subtracted(cutter)
    dot_cut = dot_world.subtracted(cutter)

    squircle_outer_d = _apple_superellipse_path(64.0, 64.0, 59.5, exponent=4.6)
    squircle_inset_d = _apple_superellipse_path(64.0, 64.0, 58.6, exponent=4.6)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="512" height="512">
  <defs>
    <linearGradient id="bg-grad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#191736" />
      <stop offset="100%" stop-color="#0d0e14" />
    </linearGradient>
    <linearGradient id="card-indigo" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#6366f1" />
      <stop offset="100%" stop-color="#4338ca" />
    </linearGradient>
    <linearGradient id="paper-warm" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#ffffff" />
      <stop offset="100%" stop-color="#f4f1ea" />
    </linearGradient>
    <linearGradient id="rim-light" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#818cf8" stop-opacity="0.55" />
      <stop offset="100%" stop-color="#4f46e5" stop-opacity="0.15" />
    </linearGradient>
  </defs>

  <path d="{squircle_outer_d}" fill="url(#bg-grad)" />
  <path d="{squircle_inset_d}" fill="none" stroke="url(#rim-light)" stroke-width="1.6" />
  <path d="{_qpath_to_svg_d(back_cut)}" fill="url(#card-indigo)" />
  <path d="{_qpath_to_svg_d(hook_cut)}" fill="#ffffff" />
  <path d="{_qpath_to_svg_d(dot_cut)}" fill="#c7d2fe" />
  <path d="{_qpath_to_svg_d(front_world)}" fill="url(#paper-warm)" />
  <path d="{_qpath_to_svg_d(prim_front_world)}" fill="#4f46e5" />
  <path d="{_qpath_to_svg_d(sec_front_world)}" fill="#0f1117" fill-opacity="0.88" />
</svg>
"""


def _render_svg_to_png(renderer: QSvgRenderer, size: int, out_path: pathlib.Path) -> None:
    """Rend un QSvgRenderer dans un fichier PNG carré avec anticrénelage."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter, QRectF(0, 0, float(size), float(size)))
    painter.end()
    img.save(str(out_path))


def generate_icons() -> None:
    """Génère l'ensemble des fichiers d'icônes vectoriels et matriciels du projet."""
    _app = QGuiApplication.instance() or QGuiApplication([])

    repo_root = pathlib.Path(__file__).resolve().parent.parent
    icons_dir = repo_root / "src" / "ressources" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    svg_content = build_ankidraft_icon_svg()

    svg_targets = [
        icons_dir / "ankidraft.svg",
        icons_dir / "logo.svg",
        repo_root / "website" / "public" / "assets" / "icons" / "ankidraft.svg",
        repo_root / "docs" / "assets" / "icons" / "ankidraft.svg",
    ]
    for target in svg_targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(svg_content, encoding="utf-8")
        print(f"[SUCCESS] SVG écrit dans {target}")

    renderer = QSvgRenderer(QByteArray(svg_content.encode("utf-8")))

    # 1. Génération des PNG 512x512 et 1024x1024
    png_512 = icons_dir / "ankidraft.png"
    png_1024 = icons_dir / "ankidraft_1024.png"
    _render_svg_to_png(renderer, 512, png_512)
    _render_svg_to_png(renderer, 1024, png_1024)
    print(f"[SUCCESS] PNG 512x512 et 1024x1024 générés dans {icons_dir}")

    # 2. Génération du fichier Windows .ico
    img = Image.open(png_1024)
    ico_path = icons_dir / "ankidraft.ico"
    img.save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"[SUCCESS] ICO multi-résolutions généré dans {ico_path}")

    # 3. Génération du fichier macOS .icns via iconutil
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            iconset_dir = pathlib.Path(tmp_dir) / "ankidraft.iconset"
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
                _render_svg_to_png(renderer, sz, iconset_dir / filename)

            icns_path = icons_dir / "ankidraft.icns"
            subprocess.run(["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)], check=True)
            print(f"[SUCCESS] ICNS Apple Retina généré dans {icns_path}")
    except Exception as e:
        print(f"[WARNING] Erreur lors de la génération de l'icns: {e}")


if __name__ == "__main__":
    generate_icons()
