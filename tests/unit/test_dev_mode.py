"""Tests unitaires du module développeur (mode dev + données factices)."""

from __future__ import annotations

import os

import pytest

from ankiforge.dev import (
    FakeDeckRepository,
    FakeDocumentRepository,
    FakeLLMProvider,
    FakeNoteRepository,
    is_dev_mode,
    make_fake_collection,
)
from ankiforge.dev.fake_data import make_fake_decks
from ankiforge.utils.environment import AppEnvironment, set_environment

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_env():
    original = os.environ.get("ANKIFORGE_ENV")
    yield
    import ankiforge.utils.environment as env_mod

    env_mod._current_env = None
    if original is not None:
        os.environ["ANKIFORGE_ENV"] = original
    else:
        os.environ.pop("ANKIFORGE_ENV", None)


def test_is_dev_mode_true_in_development():
    set_environment(AppEnvironment.DEVELOPMENT)
    assert is_dev_mode() is True


def test_is_dev_mode_false_in_testing():
    set_environment(AppEnvironment.TESTING)
    assert is_dev_mode() is False


def test_fake_collection_deterministic():
    a = make_fake_collection()
    b = make_fake_collection()
    assert a == b


def test_fake_decks_non_empty():
    decks = make_fake_decks()
    assert len(decks) > 0
    assert all(d.name for d in decks)


def test_fake_llm_provider_returns_json():
    import json

    provider = FakeLLMProvider()
    result = provider.generate(system_prompt="s", user_prompt="u")
    data = json.loads(result)
    assert "cards" in data
    assert len(data["cards"]) > 0


def test_fake_repositories_non_empty():
    assert len(FakeDeckRepository().list_all()) > 0
    assert len(FakeDocumentRepository().list_all()) > 0
    assert len(FakeNoteRepository().list_all()) > 0


def test_is_dev_mode_via_env_var_without_set_environment():
    os.environ["ANKIFORGE_ENV"] = "development"
    import ankiforge.utils.environment as env_mod

    env_mod._current_env = None
    assert is_dev_mode() is True
