#!/usr/bin/env python3
"""Porte de vérification canonique unique d'AnkiForge (Verification Gate).

Enchaîne de manière déterministe et ordonnée l'ensemble des contrôles de qualité,
typage, sécurité et tests pré-push du projet :
1. ruff check .                (Linting et règles PEP8 / T20 no print)
2. ruff format --check .       (Formatage uniforme)
3. mypy src/ankiforge          (Typage statique strict 100%)
4. bandit -c pyproject.toml -r src/ (Audit sécurité statique)
5. pytest -m "not slow"        (Tests unitaires et headless rapides < 15s)

Utilisation :
    uv run python script/verify.py             # Exécution standard fail-fast
    uv run python script/verify.py --fix       # Auto-format & fix ruff avant vérification
    uv run python script/verify.py --all-tests # Exécute tous les tests (sans filtre slow)
    uv run python script/verify.py --install-hook # Installe et active le hook git pre-push
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("ankiforge.verify")

REPO_ROOT = Path(__file__).resolve().parent.parent
GITHOOKS_DIR = REPO_ROOT / ".githooks"
GITHOOKS_PRE_PUSH = GITHOOKS_DIR / "pre-push"
GIT_DIR = REPO_ROOT / ".git"
GIT_HOOKS_DIR = GIT_DIR / "hooks"


@dataclass(frozen=True)
class VerificationStep:
    """Représentation immuable d'une étape de vérification."""

    name: str
    command: list[str]
    description: str = ""


CANONICAL_STEPS: list[VerificationStep] = [
    VerificationStep(
        name="ruff-check",
        command=["ruff", "check", "."],
        description="Linting et conformité des règles de code (Ruff)",
    ),
    VerificationStep(
        name="ruff-format",
        command=["ruff", "format", "--check", "."],
        description="Vérification du formatage uniforme du code (Ruff)",
    ),
    VerificationStep(
        name="mypy",
        command=["mypy", "src/ankiforge"],
        description="Typage statique strict 100% (Mypy)",
    ),
    VerificationStep(
        name="bandit",
        command=["bandit", "-c", "pyproject.toml", "-r", "src/"],
        description="Audit de sécurité et scan de vulnérabilités (Bandit)",
    ),
    VerificationStep(
        name="pytest-fast",
        command=["pytest", "-m", "not slow"],
        description="Suite de tests rapides non-slow (< 15s) (Pytest)",
    ),
]


def is_bypass_requested(args_bypass: bool = False) -> bool:
    """Détermine si un contournement explicite est demandé via argument ou variable d'environnement."""
    if args_bypass:
        return True
    bypass_env_keys = (
        "ANKIFORGE_BYPASS_VERIFY",
        "ANKIFORGE_SKIP_VERIFY",
        "ANKIFORGE_BYPASS_PRE_PUSH",
    )
    for key in bypass_env_keys:
        val = os.environ.get(key, "").strip().lower()
        if val in ("1", "true", "yes"):
            return True
    return False


def build_full_command(cmd: list[str]) -> list[str]:
    """Construit la commande finale avec le préfixe de runtime adapté (uv run ou sys.executable)."""
    if shutil.which("uv"):
        return ["uv", "run", *cmd]
    return [sys.executable, "-m", *cmd]


def run_single_step(step: VerificationStep, cwd: Path = REPO_ROOT, quiet: bool = False) -> int:
    """Exécute une étape de vérification unitaire et retourne son code de sortie."""
    full_cmd = build_full_command(step.command)
    if not quiet:
        print(f"▶ [{step.name}] Exécution : {' '.join(full_cmd)}")

    start_time = time.perf_counter()
    result = subprocess.run(
        full_cmd,
        cwd=cwd,
        text=True,
        check=False,
    )
    duration = time.perf_counter() - start_time

    if result.returncode == 0:
        if not quiet:
            print(f"✅ [{step.name}] OK ({duration:.2f}s)\n")
    else:
        print(f"❌ [{step.name}] Échec (code {result.returncode}, {duration:.2f}s)\n", file=sys.stderr)
        logger.error(
            "Étape %s échouée avec le code %d (durée : %.2fs)",
            step.name,
            result.returncode,
            duration,
        )

    return result.returncode


def apply_auto_fix(cwd: Path = REPO_ROOT, quiet: bool = False) -> int:
    """Applique les corrections automatiques Ruff lint et format."""
    if not quiet:
        print("🛠️  Application automatique des corrections Ruff (lint --fix + format)...")

    cmd_lint_fix = build_full_command(["ruff", "check", "--fix", "."])
    res_lint = subprocess.run(cmd_lint_fix, cwd=cwd, check=False)
    if res_lint.returncode != 0:
        return res_lint.returncode

    cmd_format = build_full_command(["ruff", "format", "."])
    res_fmt = subprocess.run(cmd_format, cwd=cwd, check=False)
    return res_fmt.returncode


def install_git_pre_push_hook(quiet: bool = False) -> int:
    """Installe et active le hook pre-push versionné dans le dépôt git."""
    if not GIT_DIR.exists():
        print("⚠️  Aucun répertoire .git trouvé à la racine. Hook non installé.", file=sys.stderr)
        return 1

    GITHOOKS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Rendre .githooks/pre-push exécutable
    if GITHOOKS_PRE_PUSH.is_file():
        mode = os.stat(GITHOOKS_PRE_PUSH).st_mode
        os.chmod(GITHOOKS_PRE_PUSH, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # 2. Configurer core.hooksPath = .githooks
    proc = subprocess.run(
        ["git", "config", "core.hooksPath", ".githooks"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(f"❌ Impossible de définir core.hooksPath : {proc.stderr}", file=sys.stderr)
        return proc.returncode

    # 3. Synchroniser également .git/hooks/pre-push par précaution
    if GIT_HOOKS_DIR.is_dir():
        local_pre_push = GIT_HOOKS_DIR / "pre-push"
        wrapper_content = '#!/usr/bin/env bash\nHOOK_DIR="$(cd "$(dirname "$0")/../../.githooks" && pwd)"\nif [ -x "$HOOK_DIR/pre-push" ]; then\n    exec "$HOOK_DIR/pre-push" "$@"\nfi\nexit 0\n'
        local_pre_push.write_text(wrapper_content, encoding="utf-8")
        mode = os.stat(local_pre_push).st_mode
        os.chmod(local_pre_push, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    if not quiet:
        print("✅ Hook pre-push versionné configuré avec succès :")
        print("   - .githooks/pre-push actif via git config core.hooksPath .githooks")
        print("   - .git/hooks/pre-push synchronisé en délégation")

    return 0


def run_verification(
    steps: list[VerificationStep] | None = None,
    fail_fast: bool = True,
    bypass: bool = False,
    quiet: bool = False,
    all_tests: bool = False,
    fix: bool = False,
) -> int:
    """Exécute l'ensemble de la chaîne de vérification canonique."""
    if is_bypass_requested(args_bypass=bypass):
        msg = "⚠️  [WARNING] Porte de vérification canonique contournée explicitement. Aucun contrôle n'a été exécuté !"
        print(msg, file=sys.stderr)
        logger.warning("Porte de vérification AnkiForge contournée explicitement (bypass).")
        return 0

    if fix:
        fix_code = apply_auto_fix(quiet=quiet)
        if fix_code != 0 and fail_fast:
            return fix_code

    active_steps = list(steps if steps is not None else CANONICAL_STEPS)

    if all_tests:
        active_steps = [
            (
                VerificationStep(
                    name="pytest-all",
                    command=["pytest"],
                    description="Suite complète de tests (Pytest)",
                )
                if step.name == "pytest-fast"
                else step
            )
            for step in active_steps
        ]

    total_start = time.perf_counter()
    if not quiet:
        print("=" * 65)
        print("🛡️  Porte de Vérification Canonique AnkiForge (Pre-Push Gate)")
        print(f"📋 {len(active_steps)} contrôles programmés | Mode fail-fast : {fail_fast}")
        print("=" * 65)

    failed_steps: list[tuple[str, int]] = []

    for idx, step in enumerate(active_steps, start=1):
        if not quiet:
            print(f"[{idx}/{len(active_steps)}] {step.description} ({step.name})")

        code = run_single_step(step, quiet=quiet)
        if code != 0:
            failed_steps.append((step.name, code))
            if fail_fast:
                if not quiet:
                    print("=" * 65)
                    print(f"❌ Arrêt immédiat (fail-fast) sur l'étape '{step.name}' (code {code}).")
                    print("💡 Pour auto-corriger le formatage : uv run python script/verify.py --fix")
                    print("=" * 65)
                return code

    total_duration = time.perf_counter() - total_start

    if failed_steps:
        if not quiet:
            print("=" * 65)
            print(f"❌ {len(failed_steps)} étape(s) en échec sur {len(active_steps)} :")
            for name, code in failed_steps:
                print(f"   - {name} (code de sortie : {code})")
            print("=" * 65)
        return failed_steps[0][1]

    if not quiet:
        print("=" * 65)
        print(f"✨ Tous les contrôles de vérification ont réussi avec succès en {total_duration:.2f}s !")
        print("=" * 65)

    return 0


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée CLI pour la commande canonique de vérification."""
    parser = argparse.ArgumentParser(
        description="Porte de vérification canonique unique et pre-push gate pour AnkiForge.",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Applique automatiquement le linting fix et formatage Ruff avant de vérifier.",
    )
    parser.add_argument(
        "--all-tests",
        "--full",
        dest="all_tests",
        action="store_true",
        help="Exécute l'intégralité des tests pytest (sans exclure le marqueur slow).",
    )
    parser.add_argument(
        "--no-fail-fast",
        "--keep-going",
        dest="no_fail_fast",
        action="store_true",
        help="Continue d'exécuter les étapes restantes même en cas d'échec intermédiaire.",
    )
    parser.add_argument(
        "--bypass",
        "--skip",
        dest="bypass",
        action="store_true",
        help="Contourne explicitement la vérification (journalise un warning).",
    )
    parser.add_argument(
        "--install-hook",
        action="store_true",
        help="Installe et active le hook pre-push versionné dans git.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Supprime les affichages d'étape non essentiels.",
    )

    args = parser.parse_args(argv)

    if args.install_hook:
        return install_git_pre_push_hook(quiet=args.quiet)

    return run_verification(
        fail_fast=not args.no_fail_fast,
        bypass=args.bypass,
        quiet=args.quiet,
        all_tests=args.all_tests,
        fix=args.fix,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
