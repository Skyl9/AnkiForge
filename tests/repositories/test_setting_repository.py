"""
Unit tests for SettingRepository.
"""

from __future__ import annotations

from ankiforge.repositories.setting_repository import SettingRepository


def test_setting_repository_crud() -> None:
    repo = SettingRepository()

    # Settings
    repo.set_setting("theme_id", "dark_modern", category="appearance")
    repo.set_setting("default_model", "gpt-4o", category="ai")

    assert repo.get_setting("theme_id") == "dark_modern"
    assert repo.get_setting("default_model") == "gpt-4o"
    assert repo.get_setting("non_existent", default="fallback") == "fallback"

    app_settings = repo.get_settings_by_category("appearance")
    assert app_settings.get("theme_id") == "dark_modern"

    all_settings = repo.get_all_settings()
    assert "theme_id" in all_settings
    assert "default_model" in all_settings

    # Token Telemetry
    repo.record_token_usage(
        provider="openai",
        model_id="gpt-4o",
        prompt_tokens=100,
        completion_tokens=50,
        estimated_cost_usd=0.005,
    )
    repo.record_token_usage(
        provider="anthropic",
        model_id="claude-3-5-sonnet",
        prompt_tokens=200,
        completion_tokens=100,
        estimated_cost_usd=0.010,
    )

    stats = repo.get_total_token_usage_stats()
    assert stats["total_tokens"] == 450
    assert stats["total_prompt_tokens"] == 300
    assert stats["total_completion_tokens"] == 150
    assert stats["total_calls"] == 2
    assert abs(stats["total_cost_usd"] - 0.015) < 1e-4

    # AI Cache
    repo.cache_ai_response(
        prompt_hash="hash123",
        system_prompt_hash="sys123",
        model_id="gpt-4o",
        temperature=0.7,
        response_content="Cached output",
    )
    cached = repo.get_cached_ai_response(
        prompt_hash="hash123",
        system_prompt_hash="sys123",
        model_id="gpt-4o",
        temperature=0.7,
    )
    assert cached == "Cached output"
    assert repo.get_cached_ai_response("missing_hash") is None

    repo.clear_ai_cache()
    assert repo.get_cached_ai_response("hash123", "sys123", "gpt-4o", 0.7) is None
