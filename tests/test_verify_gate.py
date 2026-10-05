"""Tests unitaires et d'intégration pour la porte de vérification canonique et le hook pre-push versionné."""

from __future__ import annotations

import logging
import os
import stat
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

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
    """Le script canonique doit définir les 5 étapes dans l'ordre strict requis avec timeouts."""
    from script.verify import CANONICAL_STEPS

    expected_steps = [
        ("ruff-check", ["ruff", "check", "."]),
        ("ruff-format", ["ruff", "format", "--check", "."]),
        ("mypy", ["mypy", "src/ankiforge"]),
        ("bandit", ["bandit", "-c", "pyproject.toml", "-r", "src/"]),
        ("pytest-fast", ["pytest", "-m", "not slow", "--max-worker-restart=0"]),
    ]

    assert len(CANONICAL_STEPS) == len(expected_steps), f"Attendu 5 étapes canoniques, reçu {len(CANONICAL_STEPS)}"

    for i, (expected_name, expected_cmd) in enumerate(expected_steps):
        step = CANONICAL_STEPS[i]
        assert step.name == expected_name
        assert step.command == expected_cmd


def test_verify_steps_have_timeouts() -> None:
    """Toutes les étapes canoniques doivent définir un timeout positif."""
    from script.verify import CANONICAL_STEPS

    for step in CANONICAL_STEPS:
        assert step.timeout is not None, f"L'étape '{step.name}' doit définir un timeout"
        assert step.timeout > 0, f"L'étape '{step.name}' doit avoir un timeout positif (actuel : {step.timeout})"


def test_pytest_step_has_max_worker_restart() -> None:
    """L'étape pytest doit inclure --max-worker-restart=0 pour empêcher les relances en boucle de workers crashés."""
    from script.verify import CANONICAL_STEPS

    pytest_steps = [s for s in CANONICAL_STEPS if s.name.startswith("pytest")]
    assert pytest_steps, "Au moins une étape pytest doit exister"

    for step in pytest_steps:
        assert "--max-worker-restart=0" in step.command, f"L'étape '{step.name}' doit inclure --max-worker-restart=0"


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
    from script.verify import StepResult, VerificationStep, run_verification

    executed_steps: list[str] = []

    def mock_run_step(step: VerificationStep, *args: object, **kwargs: object) -> StepResult:
        executed_steps.append(step.name)
        if step.name == "step-fail":
            return StepResult(name=step.name, status="ÉCHEC", duration=0.1, return_code=2)
        return StepResult(name=step.name, status="OK", duration=0.1, return_code=0)

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
    from script.verify import StepResult, VerificationStep, run_verification

    executed_steps: list[str] = []

    def mock_run_step(step: VerificationStep, *args: object, **kwargs: object) -> StepResult:
        executed_steps.append(step.name)
        if step.name == "step-fail":
            return StepResult(name=step.name, status="ÉCHEC", duration=0.1, return_code=5)
        return StepResult(name=step.name, status="OK", duration=0.1, return_code=0)

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
    from script.verify import StepResult, VerificationStep, run_verification

    def mock_run_step(step: VerificationStep, *args: object, **kwargs: object) -> StepResult:
        return StepResult(name=step.name, status="OK", duration=0.05, return_code=0)

    custom_steps = [
        VerificationStep(name="step-1", command=["true"]),
        VerificationStep(name="step-2", command=["true"]),
    ]

    monkeypatch.setattr("script.verify.run_single_step", mock_run_step)

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


# --- Nouveaux tests : Résilience aux crashs et blocages ---


def test_decode_return_code_normal() -> None:
    """decode_return_code doit formater lisiblement un code de retour normal."""
    from script.verify import decode_return_code

    assert decode_return_code(0) == "code 0"
    assert decode_return_code(1) == "code 1"
    assert decode_return_code(42) == "code 42"


def test_decode_return_code_signals() -> None:
    """decode_return_code doit identifier les signaux POSIX connus."""
    from script.verify import decode_return_code

    assert "SIGSEGV" in decode_return_code(-11)
    assert "SIGABRT" in decode_return_code(-6)
    assert "SIGKILL" in decode_return_code(-9)
    assert "SIGTERM" in decode_return_code(-15)


def test_decode_return_code_unknown_signal() -> None:
    """decode_return_code doit formater un signal inconnu avec son numéro."""
    from script.verify import decode_return_code

    result = decode_return_code(-99)
    assert "99" in result


def test_get_step_environment_sets_faulthandler() -> None:
    """get_step_environment doit injecter PYTHONFAULTHANDLER=1."""
    from script.verify import get_step_environment

    env = get_step_environment()
    assert env.get("PYTHONFAULTHANDLER") == "1"
    assert env.get("PYTHONUNBUFFERED") == "1"
    assert env.get("QT_QPA_PLATFORM") == "offscreen"


def test_get_step_environment_preserves_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_step_environment ne doit pas écraser les valeurs déjà définies dans l'environnement."""
    monkeypatch.setenv("PYTHONFAULTHANDLER", "0")

    from script.verify import get_step_environment

    env = get_step_environment()
    assert env["PYTHONFAULTHANDLER"] == "0", "La valeur existante ne doit pas être écrasée"


def test_filter_steps_only() -> None:
    """filter_steps avec only ne retient que les étapes listées."""
    from script.verify import VerificationStep, filter_steps

    steps = [
        VerificationStep(name="a", command=["x"]),
        VerificationStep(name="b", command=["y"]),
        VerificationStep(name="c", command=["z"]),
    ]

    filtered = filter_steps(steps, only=["b"])
    assert [s.name for s in filtered] == ["b"]


def test_filter_steps_skip() -> None:
    """filter_steps avec skip exclut les étapes listées."""
    from script.verify import VerificationStep, filter_steps

    steps = [
        VerificationStep(name="a", command=["x"]),
        VerificationStep(name="b", command=["y"]),
        VerificationStep(name="c", command=["z"]),
    ]

    filtered = filter_steps(steps, skip=["b"])
    assert [s.name for s in filtered] == ["a", "c"]


def test_filter_steps_only_and_skip() -> None:
    """filter_steps applique only puis skip dans cet ordre."""
    from script.verify import VerificationStep, filter_steps

    steps = [
        VerificationStep(name="a", command=["x"]),
        VerificationStep(name="b", command=["y"]),
        VerificationStep(name="c", command=["z"]),
    ]

    filtered = filter_steps(steps, only=["a", "b"], skip=["b"])
    assert [s.name for s in filtered] == ["a"]


def test_filter_steps_unknown_name_ignored(capsys: pytest.CaptureFixture[str]) -> None:
    """filter_steps avertit sur les noms d'étapes inconnus sans planter."""
    from script.verify import VerificationStep, filter_steps

    steps = [VerificationStep(name="a", command=["x"])]

    filtered = filter_steps(steps, only=["a", "unknown-step"])
    assert [s.name for s in filtered] == ["a"]
    captured = capsys.readouterr()
    assert "unknown-step" in captured.err


def test_run_single_step_timeout(tmp_path: Path) -> None:
    """run_single_step doit tuer l'arbre de processus et retourner TIMEOUT en cas de dépassement."""
    from script.verify import VerificationStep, run_single_step

    # Script Python qui boucle indéfiniment
    hang_script = tmp_path / "hang.py"
    hang_script.write_text("import time\nwhile True:\n    time.sleep(0.1)\n", encoding="utf-8")

    step = VerificationStep(
        name="hang-test",
        command=["python", str(hang_script)],
        timeout=1.0,
    )

    # On appelle directement sans build_full_command pour contrôler le chemin
    with patch("script.verify.build_full_command", return_value=[sys.executable, str(hang_script)]):
        result = run_single_step(step, quiet=True, timeout_override=1.0)

    assert result.status == "TIMEOUT"
    assert result.duration >= 0.9  # doit avoir attendu au moins ~1s
    assert result.return_code is None


@pytest.mark.skipif(sys.platform == "win32", reason="Signaux POSIX uniquement")
def test_run_single_step_crash_signal() -> None:
    """run_single_step doit détecter un crash par signal et retourner CRASH."""
    from script.verify import VerificationStep, run_single_step

    # Script Python qui s'auto-kill avec SIGABRT
    crash_cmd = [sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGABRT)"]

    step = VerificationStep(
        name="crash-test",
        command=crash_cmd,
        timeout=5.0,
    )

    with patch("script.verify.build_full_command", return_value=crash_cmd):
        result = run_single_step(step, quiet=True)

    assert result.status == "CRASH"
    assert result.signal_name == "SIGABRT"
    assert result.return_code is not None and result.return_code < 0


def test_run_single_step_success() -> None:
    """run_single_step retourne OK pour un processus qui réussit."""
    from script.verify import VerificationStep, run_single_step

    success_cmd = [sys.executable, "-c", "pass"]

    step = VerificationStep(
        name="success-test",
        command=success_cmd,
        timeout=5.0,
    )

    with patch("script.verify.build_full_command", return_value=success_cmd):
        result = run_single_step(step, quiet=True)

    assert result.status == "OK"
    assert result.return_code == 0


def test_run_single_step_failure() -> None:
    """run_single_step retourne ÉCHEC pour un processus qui échoue avec un code non-zéro."""
    from script.verify import VerificationStep, run_single_step

    fail_cmd = [sys.executable, "-c", "raise SystemExit(3)"]

    step = VerificationStep(
        name="fail-test",
        command=fail_cmd,
        timeout=5.0,
    )

    with patch("script.verify.build_full_command", return_value=fail_cmd):
        result = run_single_step(step, quiet=True)

    assert result.status == "ÉCHEC"
    assert result.return_code == 3


def test_kill_process_tree_posix(tmp_path: Path) -> None:
    """kill_process_tree doit tuer un processus et son groupe."""
    if sys.platform == "win32":
        pytest.skip("Test POSIX uniquement")

    from script.verify import kill_process_tree

    # Lancer un processus qui boucle
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )

    # Vérifier qu'il tourne
    assert proc.poll() is None

    kill_process_tree(proc)

    # Vérifier qu'il est terminé (attendre un peu)
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("kill_process_tree n'a pas réussi à terminer le processus")


def test_kill_process_tree_already_dead() -> None:
    """kill_process_tree ne doit pas planter si le processus est déjà terminé."""
    from script.verify import kill_process_tree

    proc = subprocess.Popen(
        [sys.executable, "-c", "pass"],
        start_new_session=sys.platform != "win32",
    )
    proc.wait(timeout=5.0)

    # Ne doit pas lever d'exception
    kill_process_tree(proc)


def test_step_result_dataclass() -> None:
    """StepResult doit être instanciable avec les champs attendus."""
    from script.verify import StepResult

    result = StepResult(
        name="test",
        status="TIMEOUT",
        duration=1.5,
        timeout_limit=2.0,
        return_code=None,
        signal_name=None,
    )
    assert result.name == "test"
    assert result.status == "TIMEOUT"
    assert result.duration == 1.5


def test_dry_run_does_not_execute(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Le mode --dry-run doit afficher le plan sans lancer de processus."""
    from script.verify import VerificationStep, run_verification

    # Si run_single_step est appelé, le test échoue
    def should_not_be_called(*args: object, **kwargs: object) -> None:
        pytest.fail("run_single_step ne devrait pas être appelé en mode dry-run")

    monkeypatch.setattr("script.verify.run_single_step", should_not_be_called)

    custom_steps = [
        VerificationStep(name="step-1", command=["echo", "test"], timeout=10.0),
    ]

    exit_code = run_verification(steps=custom_steps, dry_run=True)
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "dry-run" in captured.out.lower() or "simulation" in captured.out.lower()
    assert "step-1" in captured.out


def test_check_hook_returns_zero_when_installed() -> None:
    """check_git_hook_status retourne 0 si le hook est correctement installé."""
    from script.verify import check_git_hook_status

    # Ce test dépend de l'état réel du dépôt — skip si pas de .git
    if not (REPO_ROOT / ".git").exists():
        pytest.skip("Pas de répertoire .git")
    if not GITHOOKS_PRE_PUSH.is_file():
        pytest.skip("Hook pre-push non présent")

    # Vérifier core.hooksPath
    proc = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.stdout.strip() != ".githooks":
        pytest.skip("core.hooksPath n'est pas configuré sur .githooks")

    result = check_git_hook_status(quiet=True)
    assert result == 0


def test_step_filtering_via_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le CLI --step doit filtrer les étapes transmises à run_verification."""
    from script.verify import StepResult, main

    invoked_steps: list[str] = []

    def mock_run_step(step: object, *args: object, **kwargs: object) -> StepResult:
        invoked_steps.append(step.name)  # type: ignore[union-attr]
        return StepResult(name=step.name, status="OK", duration=0.01, return_code=0)  # type: ignore[union-attr]

    monkeypatch.setattr("script.verify.run_single_step", mock_run_step)

    exit_code = main(["--step", "mypy"])

    assert exit_code == 0
    assert invoked_steps == ["mypy"]


def test_skip_step_via_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le CLI --skip-step doit exclure les étapes spécifiées."""
    from script.verify import StepResult, main

    invoked_steps: list[str] = []

    def mock_run_step(step: object, *args: object, **kwargs: object) -> StepResult:
        invoked_steps.append(step.name)  # type: ignore[union-attr]
        return StepResult(name=step.name, status="OK", duration=0.01, return_code=0)  # type: ignore[union-attr]

    monkeypatch.setattr("script.verify.run_single_step", mock_run_step)

    exit_code = main(["--skip-step", "bandit", "--skip-step", "pytest-fast"])

    assert exit_code == 0
    assert "bandit" not in invoked_steps
    assert "pytest-fast" not in invoked_steps
    # Les 3 étapes restantes doivent avoir été exécutées
    assert len(invoked_steps) == 3


def test_timeout_override_propagated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le timeout global passé au CLI doit être transmis à run_single_step."""
    from script.verify import StepResult, main

    captured_timeouts: list[float | None] = []

    def mock_run_step(step: object, *args: object, **kwargs: object) -> StepResult:
        captured_timeouts.append(kwargs.get("timeout_override"))
        return StepResult(name=step.name, status="OK", duration=0.01, return_code=0)  # type: ignore[union-attr]

    monkeypatch.setattr("script.verify.run_single_step", mock_run_step)

    main(["--timeout", "99.0"])

    assert all(t == 99.0 for t in captured_timeouts), f"Tous les timeouts doivent être 99.0 : {captured_timeouts}"


def test_pytest_timeout_only_affects_pytest_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le --pytest-timeout ne doit surcharger que les étapes pytest."""
    from script.verify import StepResult, main

    step_timeouts: dict[str, float | None] = {}

    def mock_run_step(step: object, *args: object, **kwargs: object) -> StepResult:
        step_timeouts[step.name] = kwargs.get("timeout_override")  # type: ignore[union-attr]
        return StepResult(name=step.name, status="OK", duration=0.01, return_code=0)  # type: ignore[union-attr]

    monkeypatch.setattr("script.verify.run_single_step", mock_run_step)

    main(["--pytest-timeout", "42.0"])

    assert step_timeouts.get("pytest-fast") == 42.0
    # Les étapes non-pytest ne doivent pas avoir de timeout_override
    assert step_timeouts.get("ruff-check") is None
    assert step_timeouts.get("mypy") is None


def test_all_tests_replaces_pytest_fast_with_max_worker_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    """--all-tests doit remplacer pytest-fast par pytest-all avec --max-worker-restart=0."""
    from script.verify import StepResult, main

    invoked_steps: dict[str, list[str]] = {}

    def mock_run_step(step: object, *args: object, **kwargs: object) -> StepResult:
        invoked_steps[step.name] = step.command  # type: ignore[union-attr]
        return StepResult(name=step.name, status="OK", duration=0.01, return_code=0)  # type: ignore[union-attr]

    monkeypatch.setattr("script.verify.run_single_step", mock_run_step)

    main(["--all-tests"])

    assert "pytest-all" in invoked_steps, "pytest-fast doit être remplacé par pytest-all"
    assert "pytest-fast" not in invoked_steps
    assert "--max-worker-restart=0" in invoked_steps["pytest-all"]


def test_print_summary_table(capsys: pytest.CaptureFixture[str]) -> None:
    """print_summary_table doit afficher un tableau formaté sans exception."""
    from script.verify import StepResult, print_summary_table

    results = [
        StepResult(name="ruff-check", status="OK", duration=0.5, return_code=0, timeout_limit=30.0),
        StepResult(name="mypy", status="ÉCHEC", duration=5.2, return_code=1, timeout_limit=120.0),
        StepResult(name="pytest-fast", status="TIMEOUT", duration=120.0, return_code=None, timeout_limit=120.0),
        StepResult(name="crash-step", status="CRASH", duration=0.3, return_code=-11, timeout_limit=30.0, signal_name="SIGSEGV"),
    ]

    print_summary_table(results, total_duration=126.0)

    captured = capsys.readouterr()
    assert "ruff-check" in captured.out
    assert "mypy" in captured.out
    assert "SIGSEGV" in captured.out
    assert "1/4" in captured.out


def test_empty_filter_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si le filtrage élimine toutes les étapes, le script retourne 0 avec un avertissement."""
    from script.verify import VerificationStep, run_verification

    custom_steps = [
        VerificationStep(name="step-1", command=["true"]),
    ]

    exit_code = run_verification(steps=custom_steps, only=["nonexistent"])
    assert exit_code == 0
