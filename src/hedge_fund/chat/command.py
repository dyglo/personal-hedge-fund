from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.prompt import Confirm

from hedge_fund.chat.ai import ChatLanguageService
from hedge_fund.chat.cli_settings import CliSettings
from hedge_fund.chat.config_manager import ConfigManager
from hedge_fund.chat.models import ChatResponse
from hedge_fund.chat.service import ChatService, ReverseRiskService
from hedge_fund.chat.session_store import SessionStore
from hedge_fund.cli.rendering import (
    console,
    render_biases,
    render_chat_status,
    render_error,
    render_reverse_risk,
    render_risk,
    render_setups,
)
from hedge_fund.services.scan_service import RiskService, ScanService


class ChatCommandRunner:
    def __init__(self, context, cwd: str | Path | None = None) -> None:
        self.context = context
        self.cwd = Path(cwd or Path.cwd())
        self.cli_settings = CliSettings.load(self.cwd)
        self.session_store = SessionStore(self.cwd)

    def run(
        self,
        prompt: str | None,
        print_mode: bool,
        continue_last: bool,
        resume_session: str | None,
        output_format: str | None,
        model_override: str | None,
        permission_mode: str | None,
        append_system_prompt: str | None,
    ) -> None:
        if continue_last and resume_session:
            raise typer.BadParameter("Use either --continue or --resume, not both.")
        if print_mode and not prompt:
            raise typer.BadParameter("Print mode requires a prompt.")

        effective_output = output_format if output_format != "text" else (self.cli_settings.output_format or output_format)
        effective_model = model_override or self.cli_settings.model
        effective_permission = permission_mode if permission_mode != "default" else (self.cli_settings.permission_mode or permission_mode)
        effective_prompt = append_system_prompt or self.cli_settings.append_system_prompt
        if effective_output not in {"text", "json"}:
            raise typer.BadParameter("Output format must be text or json.")
        if effective_permission not in {"default", "plan", "accept_edits"}:
            raise typer.BadParameter("Permission mode must be default, plan, or accept_edits.")

        state = self._load_state(continue_last, resume_session, effective_permission, effective_model, effective_prompt)
        service = self._build_service(effective_model, effective_prompt)

        if prompt:
            response = service.process_message(state, prompt, self._confirm if not print_mode else None)
            self._render_response(response, effective_output, print_mode)
            if print_mode:
                return

        self._interactive_loop(state, service)

    def _load_state(
        self,
        continue_last: bool,
        resume_session: str | None,
        permission_mode: str,
        model_override: str | None,
        append_system_prompt: str | None,
    ):
        if continue_last:
            return self.session_store.load_latest()
        if resume_session:
            return self.session_store.load(resume_session)
        return self.session_store.create(
            max_context_turns=self.context.settings.chat.max_context_turns,
            permission_mode=permission_mode,
            model_override=model_override,
            append_system_prompt=append_system_prompt,
        )

    def _build_service(self, model_override: str | None, append_system_prompt: str | None) -> ChatService:
        language = ChatLanguageService(
            self.context.settings,
            self.context.env,
            self.context.logger,
            model_override=model_override,
            append_system_prompt=append_system_prompt,
        )
        scan_service = ScanService(
            self.context.settings,
            self.context.market_data,
            self.context.ai,
            self.context.repository,
            self.context.logger,
        )
        risk_service = RiskService(self.context.market_data, self.context.broker)
        reverse_risk_service = ReverseRiskService(self.context.market_data, self.context.broker)
        config_manager = ConfigManager(self.cwd / "config.yaml")
        return ChatService(
            self.context.settings,
            scan_service,
            risk_service,
            reverse_risk_service,
            language,
            config_manager,
            self.session_store,
        )

    def _interactive_loop(self, state, service: ChatService) -> None:
        render_chat_status(
            f"Chat session {state.session.session_id}. Type /help for commands. Type exit or quit to leave."
        )
        while True:
            try:
                message = console.input("[bold cyan]> [/bold cyan]").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                break
            if message.lower() in {"exit", "quit"}:
                break
            response = service.process_message(state, message, self._confirm)
            self._render_response(response, "text", False)
            if response.should_exit:
                break

    def _render_response(self, response: ChatResponse, output_format: str, print_mode: bool) -> None:
        if output_format == "json":
            typer.echo(json.dumps(response.model_dump(mode="json", exclude_none=True), indent=2))
            return

        if response.message:
            render_chat_status(response.message)
        if response.biases:
            render_biases(response.biases)
        if response.setups:
            render_setups(response.setups)
        if response.risk:
            render_risk(response.risk)
        if response.reverse_risk:
            render_reverse_risk(response.reverse_risk)
        if response.ai_analysis and not print_mode:
            from hedge_fund.cli.rendering import render_ai_output

            render_ai_output(response.ai_analysis)

    def _confirm(self, question: str) -> bool:
        try:
            return Confirm.ask(question, default=False)
        except Exception:  # noqa: BLE001
            render_error("Could not confirm config change.")
            return False
