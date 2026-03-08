from pathlib import Path

from hedge_fund.chat.config_manager import ConfigManager
from hedge_fund.config.settings import Settings


def test_settings_include_chat_section_and_updated_openai_model() -> None:
    settings = Settings.load()

    assert settings.ai.models.openai == "gpt-5-mini"
    assert settings.chat.max_context_turns == 10
    assert settings.chat.response_timeout_seconds == 8


def test_config_manager_adds_and_removes_pair(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(Path("config.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    manager = ConfigManager(config_path)

    updated = manager.add_pair("Yen")
    assert "USDJPY" in updated.trading.pairs

    updated = manager.remove_pair("USDJPY")
    assert "USDJPY" not in updated.trading.pairs
