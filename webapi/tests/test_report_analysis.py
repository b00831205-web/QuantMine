import pytest

from app.ai import report_analysis


def test_report_ai_requires_a_default_model() -> None:
    with pytest.raises(RuntimeError, match="select a default model"):
        report_analysis._call_llm(
            {"providers": [], "defaultModel": ""},
            system="system",
            prompt="prompt",
        )


def test_report_ai_does_not_swallow_provider_errors(monkeypatch) -> None:
    config = {
        "defaultModel": "deepseek-v4-flash",
        "providers": [
            {
                "models": ["deepseek-v4-flash"],
                "apiKeyEnv": "TEST_DEEPSEEK_KEY",
                "baseUrl": "https://api.deepseek.com",
            }
        ],
    }
    monkeypatch.setenv("TEST_DEEPSEEK_KEY", "test-key")
    monkeypatch.setattr(
        report_analysis,
        "complete_chat",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("provider rejected model")),
    )

    with pytest.raises(RuntimeError, match="provider rejected model"):
        report_analysis._call_llm(config, system="system", prompt="prompt")
