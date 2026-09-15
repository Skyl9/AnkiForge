#!/usr/bin/env python3
"""Générateur de Résumé Visuel GitHub Actions ($GITHUB_STEP_SUMMARY).

Parse le rapport de couverture XML (coverage.xml) et produit un tableau
récapitulatif Markdown de haute qualité pour la CI AnkiForge.
"""

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def generate_summary(coverage_xml_path: Path) -> str:
    lines: list[str] = []
    lines.append("## 📊 AnkiForge CI/CD Quality Report")
    lines.append("")

    if not coverage_xml_path.exists():
        lines.append("> ⚠️ **Rapport de couverture non trouvé.**")
        return "\n".join(lines)

    try:
        tree = ET.parse(coverage_xml_path)
        root = tree.getroot()

        # Métriques globales
        line_rate = float(root.attrib.get("line-rate", 0.0)) * 100
        lines_valid = int(root.attrib.get("lines-valid", 0))
        lines_covered = int(root.attrib.get("lines-covered", 0))
        lines_missed = lines_valid - lines_covered

        badge_emoji = "🟢" if line_rate >= 80 else ("🟡" if line_rate >= 70 else "🔴")

        lines.append(f"### {badge_emoji} Couverture Globale : **{line_rate:.1f}%**")
        lines.append("")
        lines.append("| Métrique | Valeur |")
        lines.append("|---|---|")
        lines.append(f"| **Taux de Couverture** | `{line_rate:.2f}%` |")
        lines.append(f"| **Lignes Testées** | `{lines_covered:,}` |")
        lines.append(f"| **Lignes Manquantes** | `{lines_missed:,}` |")
        lines.append(f"| **Total Lignes Exécutables** | `{lines_valid:,}` |")
        lines.append("")

        # Détail par package (database, services, ui, utils)
        lines.append("### 📦 Couverture Détaillée par Module")
        lines.append("")
        lines.append("| Module | Lignes | Couvertes | Couverture |")
        lines.append("|---|---|---|---|")

        packages = root.findall(".//package")
        for pkg in packages:
            raw_pkg_name = pkg.attrib.get("name", "")
            if not raw_pkg_name:
                continue

            pkg_name = raw_pkg_name.replace("src.", "")
            lines_in_pkg = pkg.findall(".//line")
            pkg_valid = len(lines_in_pkg)
            pkg_covered = len([lines for lines in lines_in_pkg if int(lines.attrib.get("hits", 0)) > 0])

            if pkg_valid == 0:
                continue

            pkg_rate = (pkg_covered / pkg_valid * 100) if pkg_valid > 0 else 0.0
            pkg_emoji = "🟢" if pkg_rate >= 80 else ("🟡" if pkg_rate >= 60 else "🔴")
            lines.append(f"| `{pkg_name}` | {pkg_valid:,} | {pkg_covered:,} | {pkg_emoji} **{pkg_rate:.1f}%** |")

        lines.append("")
        lines.append("> 🚀 *Généré automatiquement par le pipeline CI AnkiForge.*")

    except Exception as e:
        lines.append(f"> ❌ Erreur lors du parsing du rapport XML : `{e}`")

    return "\n".join(lines)


def main() -> None:
    root_dir = Path(__file__).resolve().parent.parent
    coverage_path = root_dir / "coverage.xml"

    if len(sys.argv) > 1:
        coverage_path = Path(sys.argv[1])

    summary_md = generate_summary(coverage_path)

    # Écriture dans GITHUB_STEP_SUMMARY si présent
    step_summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary_file:
        with open(step_summary_file, "a", encoding="utf-8") as f:
            f.write(summary_md + "\n")
        print("✅ Rapport ajouté à $GITHUB_STEP_SUMMARY")
    else:
        print(summary_md)


if __name__ == "__main__":
    main()
