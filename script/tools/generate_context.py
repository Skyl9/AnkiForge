import os
from pathlib import Path


def generate_context():
    # 1. Définition des chemins
    root_dir = Path(__file__).resolve().parent.parent
    output_file = root_dir / "llm_context.txt"
    gemini_file = root_dir / "GEMINI.md"

    # On scanne directement la racine pour inclure le maximum de fichiers (racine, docs, scripts, etc.)
    dirs_to_scan = [root_dir]

    # Dossiers et extensions à ignorer strictement (ajouts des dossiers de build et d'IDE)
    ignore_dirs = {".venv", "__pycache__", ".git", ".pytest_cache", ".ankiforge", "assets", "build", "dist", "dist_prod", ".idea", ".vscode", ".mypy_cache", ".ruff_cache"}
    ignore_exts = {".pyc", ".so", ".dll", ".pdf", ".png", ".jpg", ".jpeg", ".pyo", ".pyd", ".icns", ".ico", ".dmg", ".zip", ".tar", ".gz", ".gaphor"}
    # Fichiers spécifiques à ignorer (le fichier de sortie lui-même et les lockfiles lourds)
    ignore_files = {"llm_context.txt", "uv.lock", "GEMINI.md"}

    print("⏳ Génération du contexte pour l'IA en cours...")

    with open(output_file, "w", encoding="utf-8") as out:
        # --- ETAPE 1 : INJECTION DES RÈGLES ---
        if gemini_file.exists():
            out.write("=========================================\n")
            out.write("=== CONTEXTE ET RÈGLES (GEMINI.md) ===\n")
            out.write("=========================================\n\n")
            out.write(gemini_file.read_text(encoding="utf-8"))
            out.write("\n\n")

        # --- ETAPE 2 : ARBORESCENCE ---
        out.write("=========================================\n")
        out.write("=== ARBORESCENCE DU PROJET ===\n")
        out.write("=========================================\n\n")

        for scan_dir in dirs_to_scan:
            if not scan_dir.exists():
                continue

            out.write(f"📁 {scan_dir.name}/\n")
            for root, dirs, files in os.walk(scan_dir):
                # Modification de la liste 'dirs' en place pour ignorer les dossiers parasites
                dirs[:] = [d for d in dirs if d not in ignore_dirs]

                level = root.replace(str(scan_dir), "").count(os.sep)
                indent = " " * 4 * (level + 1)

                if root != str(scan_dir):
                    out.write(f"{indent}📁 {os.path.basename(root)}/\n")

                subindent = " " * 4 * (level + 2)
                for f in files:
                    if f in ignore_files:
                        continue
                    if Path(f).suffix not in ignore_exts:
                        out.write(f"{subindent}📄 {f}\n")
        out.write("\n\n")

        # --- ETAPE 3 : CODE SOURCE ---
        out.write("=========================================\n")
        out.write("=== CODE SOURCE ===\n")
        out.write("=========================================\n\n")

        for scan_dir in dirs_to_scan:
            if not scan_dir.exists():
                continue

            for root, dirs, files in os.walk(scan_dir):
                dirs[:] = [d for d in dirs if d not in ignore_dirs]
                for file in files:
                    if file in ignore_files:
                        continue

                    file_path = Path(root) / file
                    if file_path.suffix not in ignore_exts:
                        rel_path = file_path.relative_to(root_dir)
                        out.write(f"--- Fichier : {rel_path} ---\n")

                        lang = file_path.suffix[1:] if file_path.suffix else "text"
                        # Correction pour certains langages
                        if lang == "sh":
                            lang = "bash"
                        if lang == "md":
                            lang = "markdown"

                        out.write(f"```{lang}\n")

                        try:
                            out.write(file_path.read_text(encoding="utf-8"))
                        except Exception as e:
                            out.write(f"// Impossible de lire le fichier: {e}")

                        out.write("\n```\n\n")

    print(f"✅ Contexte généré avec succès dans : {output_file.relative_to(root_dir)}")
    print("👉 Tu peux maintenant fournir le fichier 'llm_context.txt' à l'IA.")


if __name__ == "__main__":
    generate_context()
