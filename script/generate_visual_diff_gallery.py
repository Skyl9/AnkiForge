"""
Script de génération des galeries de comparaison visuelle :
1. Dark Mode : Baseline (39bcf3d4) vs Current Dark (JetBrains Dark)
2. Light Mode : Baseline (39bcf3d4) vs Current Light (JetBrains Light)
"""

import shutil
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont


def make_composite(left_path: Path, right_path: Path, out_path: Path, left_title: str, right_title: str) -> float:
    img_l = Image.open(left_path).convert("RGB")
    img_r = Image.open(right_path).convert("RGB")

    w = max(img_l.width, img_r.width)
    h = max(img_l.height, img_r.height)
    if img_l.size != (w, h):
        img_l = img_l.resize((w, h), Image.Resampling.LANCZOS)
    if img_r.size != (w, h):
        img_r = img_r.resize((w, h), Image.Resampling.LANCZOS)

    diff = ImageChops.difference(img_l, img_r)
    diff_gray = diff.convert("L")
    diff_pixels = sum(1 for p in diff_gray.getdata() if p > 5)
    total_pixels = w * h
    diff_pct = (diff_pixels / total_pixels) * 100.0

    header_h = 60
    border_w = 4
    canvas_w = (w * 2) + border_w
    canvas_h = h + header_h

    composite = Image.new("RGB", (canvas_w, canvas_h), (22, 24, 29))
    draw = ImageDraw.Draw(composite)

    draw.rectangle([0, 0, w, header_h], fill=(30, 33, 40))
    draw.rectangle([w + border_w, 0, canvas_w, header_h], fill=(30, 33, 40))
    draw.rectangle([w, 0, w + border_w, canvas_h], fill=(99, 102, 241))

    try:
        font = ImageFont.truetype("Menlo", 16)
    except Exception:
        font = ImageFont.load_default()

    draw.text((20, 20), left_title, fill=(248, 113, 113), font=font)
    draw.text((w + border_w + 20, 20), f"{right_title} [Diff: {diff_pct:.2f}%]", fill=(52, 211, 153), font=font)

    composite.paste(img_l, (0, header_h))
    composite.paste(img_r, (w + border_w, header_h))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    preview = composite.resize((canvas_w // 2, canvas_h // 2), Image.Resampling.LANCZOS)
    preview.save(str(out_path), quality=90)
    return diff_pct


def main():
    root = Path(__file__).resolve().parent.parent
    base_dir = root / "temp" / "visual_diffs" / "baseline"
    curr_dark_dir = root / "temp" / "visual_diffs" / "current_dark"
    curr_light_dir = root / "temp" / "visual_diffs" / "current_light"
    comp_dir = root / "temp" / "visual_diffs" / "comparisons"
    artifact_dir = Path("/Users/tristanrigaud-humbert/.gemini/antigravity-cli/brain/e505ac87-3c27-444a-a095-8ccc8845a763")

    views = [
        ("dashboard", "Tableau de Bord"),
        ("creation", "Studio de Création"),
        ("edition", "Édition & Navigateur"),
        ("analysis", "Analyse & Audit IA"),
        ("consultant", "AI Consultant"),
        ("batch", "Batch Factory"),
        ("documents", "My Documents"),
        ("card_models", "Modèles de Cartes"),
        ("agents", "Éditeur d'Agents"),
        ("pipelines", "Pipelines DAG"),
        ("ab_tests", "Laboratoire A/B"),
    ]

    print("\n--- 1. COMPARAISONS DARK MODE (Baseline vs JetBrains Dark Harmonisé) ---")
    for vid, name in views:
        b_file = base_dir / f"{vid}.png"
        c_file = curr_dark_dir / f"{vid}.png"
        out_file = comp_dir / f"diff_dark_{vid}.png"
        art_file = artifact_dir / f"diff_dark_{vid}.png"

        if b_file.exists() and c_file.exists():
            pct = make_composite(b_file, c_file, out_file, f"🔴 AVANT (HEAD 39bcf3d4) : {name}", f"🟢 APRÈS (Sombre Harmonisé) : {name}")
            shutil.copy(str(out_file), str(art_file))
            print(f"• {name} (Sombre vs Sombre): {pct:.2f}% de variation de pixels")

    print("\n--- 2. COMPARAISONS LIGHT MODE (Baseline vs JetBrains Light) ---")
    for vid, name in views:
        b_file = base_dir / f"{vid}.png"
        c_file = curr_light_dir / f"{vid}.png"
        out_file = comp_dir / f"diff_light_{vid}.png"
        art_file = artifact_dir / f"diff_light_{vid}.png"

        if b_file.exists() and c_file.exists():
            pct = make_composite(b_file, c_file, out_file, f"🔴 AVANT (Sombre Référence) : {name}", f"☀️ APRÈS (Nouveau Mode Clair) : {name}")
            shutil.copy(str(out_file), str(art_file))
            print(f"• {name} (Sombre vs Clair): {pct:.2f}% de variation")


if __name__ == "__main__":
    main()
