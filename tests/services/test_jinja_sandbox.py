"""Tests de l'environnement Jinja2 sandboxé (blocage des accès réflexifs)."""

from __future__ import annotations

import pytest
from jinja2.exceptions import SecurityError

from ankiforge.utils.jinja_sandbox import create_prompt_environment

pytestmark = pytest.mark.unit


def test_renders_plain_variable() -> None:
    env = create_prompt_environment()
    tpl = env.from_string("Hello {{ name }}")
    assert tpl.render(name="world") == "Hello world"


def test_reflective_attribute_access_blocked() -> None:
    env = create_prompt_environment()
    tpl = env.from_string("{{ ''.__class__.__mro__ }}")
    with pytest.raises(SecurityError):
        tpl.render()


def test_subclasses_escape_blocked() -> None:
    env = create_prompt_environment()
    tpl = env.from_string("{{ ().__class__.__bases__[0].__subclasses__() }}")
    with pytest.raises(SecurityError):
        tpl.render()


def test_system_shell_escape_blocked() -> None:
    env = create_prompt_environment()
    tpl = env.from_string("{{ self.__init__.__globals__.__builtins__.__import__('os').popen('id').read() }}")
    with pytest.raises(SecurityError):
        tpl.render()
