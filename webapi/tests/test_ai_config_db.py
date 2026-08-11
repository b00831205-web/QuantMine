from app.api.v1.ai.db import resolve_default_model


def test_resolve_default_model_uses_only_available_model() -> None:
    config = {
        "providers": [{"models": ["deepseek-v4-pro"]}],
        "defaultModel": "",
    }

    assert resolve_default_model(config) == "deepseek-v4-pro"


def test_resolve_default_model_preserves_valid_selection() -> None:
    config = {
        "providers": [{"models": ["deepseek-v4-flash", "deepseek-v4-pro"]}],
        "defaultModel": "deepseek-v4-pro",
    }

    assert resolve_default_model(config) == "deepseek-v4-pro"


def test_resolve_default_model_replaces_stale_selection() -> None:
    config = {
        "providers": [{"models": ["deepseek-v4-flash"]}],
        "defaultModel": "removed-model",
    }

    assert resolve_default_model(config) == "deepseek-v4-flash"
