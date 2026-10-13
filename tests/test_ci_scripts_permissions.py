"""Tests de validation des permissions des scripts de build et de la configuration git."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_gitattributes_enforces_lf_for_shell_scripts() -> None:
    """Vérifie que .gitattributes existe et force LF pour tous les scripts .sh."""
    gitattributes = REPO_ROOT / ".gitattributes"
    assert gitattributes.is_file(), ".gitattributes est absent à la racine du dépôt"
    content = gitattributes.read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in content, "La règle '*.sh text eol=lf' est absente de .gitattributes"


def test_build_scripts_git_index_executable() -> None:
    """Vérifie que tous les scripts shell de build_script ont le mode 100755 dans l'index Git."""
    cmd = ["git", "ls-files", "-s", "build_script/"]
    res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    lines = res.stdout.strip().splitlines()

    sh_files_found = 0
    for line in lines:
        parts = line.split()
        if len(parts) >= 4:
            mode = parts[0]
            rel_path = parts[3]
            if rel_path.endswith(".sh"):
                sh_files_found += 1
                assert mode == "100755", f"Le script {rel_path} n'a pas le mode 100755 dans l'index Git (mode={mode})"
            elif rel_path.endswith((".json", ".png", ".py", ".md", ".iss")):
                assert mode == "100644", f"Le fichier non exécutable {rel_path} ne devrait pas avoir le mode {mode}"

    assert sh_files_found >= 4, f"Au moins 4 scripts .sh attendus dans build_script/, trouvés: {sh_files_found}"


def test_no_redundant_chmod_in_ci_workflows() -> None:
    """Vérifie que les workflows CI ne contiennent plus de 'chmod +x' manuel redondant sur build_script."""
    workflows_dir = REPO_ROOT / ".github" / "workflows"
    for wf in ("nightly.yml", "release.yml"):
        wf_path = workflows_dir / wf
        if wf_path.exists():
            content = wf_path.read_text(encoding="utf-8")
            assert "chmod +x build_script" not in content, f"L'étape manuelle 'chmod +x build_script' est toujours présente dans {wf}"
