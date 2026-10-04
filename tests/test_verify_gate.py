"""Tests unitaires et d'intégration pour la porte de vérification canonique et le hook pre-push versionné."""

from __future__ import annotations

import logging
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
GITHOOKS_PRE_PUSH = REPO_ROOT / ".githooks" / "pre-push"
SCRIPT_VERIFY = REPO_ROOT / "script" / "verify.py"
PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"


def test_githooks_pre_push_exists_and_executable() -> None:
    """Le hook pre-push doit être présent dans .githooks et être exécutable."""
    assert GITHOOKS_PRE_PUSH.is_file(), f"Fichier attendu introuvable : {GITHOOKS_PRE_PUSH}"

    # Vérification des permissions d'exécution (POSIX)
    if sys.platform != "win32":
        mode = os.stat(GITHOOKS_PRE_PUSH).st_mode
        assert mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH), f"Le fichier {GITHOOKS_PRE_PUSH} doit être exécutable (+x)"


def test_githooks_pre_push_script_content() -> None:
    """Le hook pre-push doit référencer script/verify.py et le mécanisme de bypass explicite."""
    assert GITHOOKS_PRE_PUSH.is_file()
    content = GITHOOKS_PRE_PUSH.read_text(encoding="utf-8")

    assert "script/verify.py" in content, "Le hook doit exécuter le script canonique script/verify.py"
    assert "ANKIFORGE_BYPASS_PRE_PUSH" in content, "Le hook doit supporter ANKIFORGE_BYPASS_PRE_PUSH"
    assert "ANKIFORGE_SKIP_VERIFY" in content, "Le hook doit supporter ANKIFORGE_SKIP_VERIFY"
    assert "WARNING" in content, "Le contournement doit journaliser un niveau WARNING"


def test_pre_push_hook_explicit_bypass() -> None:
    """Le pre-push hook avec ANKIFORGE_BYPASS_PRE_PUSH=1 doit réussir et émettre un WARNING."""
    if not GITHOOKS_PRE_PUSH.is_file() or sys.platform == "win32":
        pytest.skip("Test exécutable uniquement sur environnement POSIX avec hook présent")

    env = dict(os.environ)
    env["ANKIFORGE_BYPASS_PRE_PUSH"] = "1"

    proc = subprocess.run(
        [str(GITHOOKS_PRE_PUSH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, f"Le bypass explicite doit autoriser le push (code 0) : {proc.stderr}"
    assert "WARNING" in proc.stderr or "WARNING" in proc.stdout, "Le bypass explicite doit émettre un message d'avertissement de niveau WARNING"


def test_pre_push_hook_blocks_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le pre-push hook doit bloquer le push (code != 0) lorsque verify.py échoue."""
    if not GITHOOKS_PRE_PUSH.is_file() or sys.platform == "win32":
        pytest.skip("Test exécutable uniquement sur environnement POSIX avec hook présent")

    # Création d'un mock verify.py retournant un code d'erreur 42
    fake_verify = tmp_path / "mock_verify.sh"
    fake_verify.write_text("#!/bin/sh\necho 'Verification failed mock' >&2\nexit 42\n", encoding="utf-8")
    fake_verify.chmod(0o755)

    env = dict(os.environ)
    env["ANKIFORGE_BYPASS_PRE_PUSH"] = "0"
    env["ANKIFORGE_SKIP_VERIFY"] = "0"
    # Redirection vers le script qui échoue via variable de test
    env["ANKIFORGE_VERIFY_SCRIPT_OVERRIDE"] = str(fake_verify)

    proc = subprocess.run(
        [str(GITHOOKS_PRE_PUSH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode != 0, f"Le hook doit bloquer le push en cas d'échec de vérification : {proc.stdout}"


def test_pre_push_hook_passes_on_success(tmp_path: Path) -> None:
    """Le pre-push hook doit autoriser le push (code 0) lorsque verify.py réussit."""
    if not GITHOOKS_PRE_PUSH.is_file() or sys.platform == "win32":
        pytest.skip("Test exécutable uniquement sur environnement POSIX avec hook présent")

    fake_verify = tmp_path / "mock_verify.sh"
    fake_verify.write_text("#!/bin/sh\necho 'Verification passed mock'\nexit 0\n", encoding="utf-8")
    fake_verify.chmod(0o755)

    env = dict(os.environ)
    env["ANKIFORGE_BYPASS_PRE_PUSH"] = "0"
    env["ANKIFORGE_SKIP_VERIFY"] = "0"
    env["ANKIFORGE_VERIFY_SCRIPT_OVERRIDE"] = str(fake_verify)

    proc = subprocess.run(
        [str(GITHOOKS_PRE_PUSH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, f"Le hook doit autoriser le push (code 0) : {proc.stderr}"


def test_verify_script_step_definitions() -> None:
    """Le script canonique doit définir les 5 étapes dans l'ordre strict requis."""
    from script.verify import CANONICAL_STEPS

    expected_steps = [
        ("ruff-check", ["ruff", "check", "."]),
        ("ruff-format", ["ruff", "format", "--check", "."]),
        ("mypy", ["mypy", "src/ankiforge"]),
        ("bandit", ["bandit", "-c", "pyproject.toml", "-r", "src/"]),
        ("pytest-fast", ["pytest", "-m", "not slow"]),
    ]

    assert len(CANONICAL_STEPS) == len(expected_steps), f"Attendu 5 étapes canoniques, reçu {len(CANONICAL_STEPS)}"

    for i, (expected_name, expected_cmd) in enumerate(expected_steps):
        step = CANONICAL_STEPS[i]
        assert step.name == expected_name
        assert step.command == expected_cmd


def test_verify_script_bypass_env(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """Le script verify.py doit être contournable via variables d'environnement en journalisant un WARNING."""
    from script.verify import run_verification

    monkeypatch.setenv("ANKIFORGE_BYPASS_VERIFY", "1")

    with caplog.at_level(logging.WARNING):
        exit_code = run_verification()

    assert exit_code == 0
    assert any("bypass" in record.message.lower() for record in caplog.records)
    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_verify_script_bypass_flag(caplog: pytest.LogCaptureFixture) -> None:
    """Le drapeau --bypass doit contourner les vérifications et journaliser un WARNING."""
    from script.verify import main

    with caplog.at_level(logging.WARNING):
        exit_code = main(["--bypass"])

    assert exit_code == 0
    assert any("bypass" in record.message.lower() for record in caplog.records)
    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_verify_script_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """Par défaut, le script doit s'arrêter à la première étape en échec (fail-fast)."""
    from script.verify import VerificationStep, run_verification

    executed_steps: list[str] = []

    def mock_run_step(step: VerificationStep, *args: object, **kwargs: object) -> int:
        executed_steps.append(step.name)
        if step.name == "step-fail":
            return 2
        return 0

    custom_steps = [
        VerificationStep(name="step-1", command=["true"]),
        VerificationStep(name="step-fail", command=["false"]),
        VerificationStep(name="step-3", command=["echo", "should not run"]),
    ]

    monkeypatch.setattr("script.verify.run_single_step", mock_run_step)

    exit_code = run_verification(steps=custom_steps, fail_fast=True)

    assert exit_code == 2
    assert executed_steps == ["step-1", "step-fail"], "L'étape 3 ne devait pas s'exécuter en mode fail-fast"


def test_verify_script_keep_going(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avec --no-fail-fast, le script exécute toutes les étapes même en cas d'échec intermédiaire."""
    from script.verify import VerificationStep, run_verification

    executed_steps: list[str] = []

    def mock_run_step(step: VerificationStep, *args: object, **kwargs: object) -> int:
        executed_steps.append(step.name)
        if step.name == "step-fail":
            return 5
        return 0

    custom_steps = [
        VerificationStep(name="step-1", command=["true"]),
        VerificationStep(name="step-fail", command=["false"]),
        VerificationStep(name="step-3", command=["echo", "should run"]),
    ]

    monkeypatch.setattr("script.verify.run_single_step", mock_run_step)

    exit_code = run_verification(steps=custom_steps, fail_fast=False)

    assert exit_code == 5
    assert executed_steps == ["step-1", "step-fail", "step-3"], "Toutes les étapes doivent s'exécuter"


def test_verify_script_all_steps_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si toutes les étapes réussissent, le script retourne 0."""
    from script.verify import VerificationStep, run_verification

    monkeypatch.setattr("script.verify.run_single_step", lambda step, *args, **kwargs: 0)

    custom_steps = [
        VerificationStep(name="step-1", command=["true"]),
        VerificationStep(name="step-2", command=["true"]),
    ]

    exit_code = run_verification(steps=custom_steps)
    assert exit_code == 0


def test_pre_commit_config_synchronization() -> None:
    """Le fichier .pre-commit-config.yaml doit déclarer le stage pre-push et appeler verify.py."""
    assert PRE_COMMIT_CONFIG.is_file()

    with open(PRE_COMMIT_CONFIG, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Vérification default_install_hook_types
    install_hook_types = config.get("default_install_hook_types", [])
    assert "pre-push" in install_hook_types, ".pre-commit-config.yaml doit déclarer 'pre-push' dans default_install_hook_types"

    # Vérification de l'existence du hook appelant script/verify.py
    found_verify_hook = False
    for repo in config.get("repos", []):
        for hook in repo.get("hooks", []):
            entry = hook.get("entry", "")
            stages = hook.get("stages", [])
            if "script/verify.py" in entry and "pre-push" in stages:
                found_verify_hook = True
                break

    assert found_verify_hook, "Un hook local exécutant 'script/verify.py' lors du stage 'pre-push' doit être présent dans .pre-commit-config.yaml"
