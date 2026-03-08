import json
import logging

import pytest
import typer
from typer.testing import CliRunner
import yaml

from hedge_fund.chat.command import ChatCommandRunner
from hedge_fund.chat.models import ChatResponse
from hedge_fund.cli.app import app
from hedge_fund.config.settings import Settings


runner = CliRunner()


class FakeContext:
    def __init__(self) -> None:
        self.settings = Settings.load()
        self.env = type(
            "Env",
            (),
            {
                "openai_api_key": "key",
                "gemini_api_key": None,
                "tavily_api_key": None,
            },
        )()
        self.logger = logging.getLogger("test")
        self.market_data = None
        self.ai = None
        self.repository = None
        self.broker = None
        self.web_search = None


def test_chat_command_passes_parsed_arguments(monkeypatch) -> None:
    calls = {}

    class FakeRunner:
        def __init__(self, context) -> None:
            pass

        def run(self, **kwargs) -> None:
            calls.update(kwargs)

    monkeypatch.setattr("hedge_fund.cli.app.ApplicationContext", FakeContext)
    monkeypatch.setattr("hedge_fund.cli.app.ChatCommandRunner", FakeRunner)

    result = runner.invoke(
        app,
        ["chat", "Scan GBPUSD for me", "--print", "--output-format", "json", "--permission-mode", "plan"],
    )

    assert result.exit_code == 0
    assert calls["prompt"] == "Scan GBPUSD for me"
    assert calls["print_mode"] is True
    assert calls["output_format"] == "json"
    assert calls["permission_mode"] == "plan"


def test_chat_command_rejects_conflicting_resume_flags(monkeypatch) -> None:
    monkeypatch.setattr("hedge_fund.cli.app.ApplicationContext", FakeContext)

    result = runner.invoke(app, ["chat", "--continue", "--resume", "abc123"])

    assert result.exit_code == 2
    assert "either --continue or --resume" in result.stdout


def test_chat_command_requires_prompt_in_print_mode(monkeypatch) -> None:
    monkeypatch.setattr("hedge_fund.cli.app.ApplicationContext", FakeContext)

    result = runner.invoke(app, ["chat", "--print"])

    assert result.exit_code == 2
    assert "Print mode requires a prompt" in result.stdout


def test_chat_command_runner_renders_json_output(tmp_path, capsys) -> None:
    command = ChatCommandRunner(FakeContext(), cwd=tmp_path)
    response = ChatResponse(session_id="abc123", message="hello", metadata={"ok": True})

    command._render_response(response, "json", True)
    output = capsys.readouterr().out

    assert json.loads(output)["session_id"] == "abc123"


def test_chat_command_runner_rejects_invalid_output_format(tmp_path) -> None:
    command = ChatCommandRunner(FakeContext(), cwd=tmp_path)

    with pytest.raises(Exception):
        command.run(
            prompt="Bias on Gold",
            print_mode=True,
            continue_last=False,
            resume_session=None,
            output_format="xml",
            model_override=None,
            permission_mode="default",
            append_system_prompt=None,
        )


def test_chat_command_runner_uses_cli_settings_fallbacks(tmp_path) -> None:
    settings_dir = tmp_path / ".hedge_fund"
    settings_dir.mkdir()
    (settings_dir / "settings.yaml").write_text(
        yaml.safe_dump({"output_format": "json", "permission_mode": "plan"}, sort_keys=False),
        encoding="utf-8",
    )
    command = ChatCommandRunner(FakeContext(), cwd=tmp_path)
    captured = {}

    def fake_load_state(continue_last, resume_session, permission_mode, model_override, append_system_prompt):
        captured["permission_mode"] = permission_mode
        raise typer.Exit()

    command._load_state = fake_load_state  # type: ignore[method-assign]

    with pytest.raises(typer.Exit):
        command.run(
            prompt="Bias on Gold",
            print_mode=True,
            continue_last=False,
            resume_session=None,
            output_format=None,
            model_override=None,
            permission_mode=None,
            append_system_prompt=None,
        )

    assert captured["permission_mode"] == "plan"


def test_chat_command_runner_uses_spinner_for_text_prompts(tmp_path, monkeypatch) -> None:
    command = ChatCommandRunner(FakeContext(), cwd=tmp_path)
    events = []

    class FakeStatus:
        def update(self, message: str) -> None:
            events.append(("update", message))

    class FakeSpinner:
        def __enter__(self):
            events.append(("enter", None))
            return FakeStatus()

        def __exit__(self, exc_type, exc, tb):
            events.append(("exit", None))

    class FakeService:
        def process_message(self, state, message, authorize, event_sink=None):
            event_sink.update_status("Searching the web...")
            return ChatResponse(session_id="abc123", message="done")

    monkeypatch.setattr("hedge_fund.chat.command.agent_status", lambda message: FakeSpinner())

    response = command._process_with_optional_status(FakeService(), object(), "Any news on Gold today?", "text", False)

    assert response.message == "done"
    assert events[0] == ("enter", None)
    assert events[-1] == ("exit", None)
    assert any(item[0] == "update" and "Searching the web" in item[1] for item in events)


def test_chat_command_runner_renders_prophet_intro(tmp_path, monkeypatch, capsys) -> None:
    command = ChatCommandRunner(FakeContext(), cwd=tmp_path)
    monkeypatch.setattr(
        "hedge_fund.chat.command.current_session_status",
        lambda sessions: {"current_session": "New York", "status": "New York is open now."},
    )

    command._render_session_intro()
    output = capsys.readouterr().out

    assert "Prophet" in output
    assert "Session: New York Open" in output
