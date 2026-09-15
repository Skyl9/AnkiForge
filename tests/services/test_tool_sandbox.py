"""Tests du sandbox pour l'exécution des outils Python personnalisés."""

from __future__ import annotations

import pytest

from ankiforge.services.tools.tool_sandbox import run_python_tool


def test_simple_execution_succeeds() -> None:
    result = run_python_tool("def run(state):\n    return 1 + 2", {})
    assert result == 3


def test_stdlib_import_blocked() -> None:
    with pytest.raises(ImportError):
        run_python_tool("import math\ndef run(state):\n    return math.sqrt(16)", {})


def test_import_open_blocked() -> None:
    with pytest.raises(NameError):
        run_python_tool("__import__('os')", {})


def test_open_blocked() -> None:
    with pytest.raises(NameError):
        run_python_tool("open('/etc/passwd')", {})


def test_eval_and_globals_blocked() -> None:
    with pytest.raises(NameError):
        run_python_tool("eval('1+1')", {})
    with pytest.raises(NameError):
        run_python_tool("globals()", {})


def test_infinite_loop_times_out() -> None:
    with pytest.raises(TimeoutError):
        run_python_tool("while True: pass", {}, timeout=0.2)


def test_missing_run_raises_value_error() -> None:
    with pytest.raises(ValueError):
        run_python_tool("x = 1", {})


def test_run_receives_state_and_args() -> None:
    result = run_python_tool(
        "def run(state):\n    return state['a'] + args['b']",
        {"a": 40},
        {"b": 2},
    )
    assert result == 42


def test_script_exception_propagates() -> None:
    with pytest.raises(ValueError):
        run_python_tool("def run(state):\n    return int('not-a-number')", {})
