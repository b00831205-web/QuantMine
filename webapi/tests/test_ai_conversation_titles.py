from app.api.v1.ai.db import DEFAULT_TITLE, is_default_conversation_title


def test_default_conversation_title_is_language_neutral() -> None:
    assert DEFAULT_TITLE == "New chat"


def test_legacy_chinese_default_title_is_still_recognized() -> None:
    assert is_default_conversation_title("New chat")
    assert is_default_conversation_title("新对话")
    assert not is_default_conversation_title("Factor IC analysis")
