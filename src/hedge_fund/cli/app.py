from __future__ import annotations

import typer

from hedge_fund.chat.command import ChatCommandRunner
from hedge_fund.chat.session_store import SessionNotFoundError
from hedge_fund.cli.bootstrap import ApplicationContext
from hedge_fund.cli.rendering import render_ai_output, render_biases, render_error, render_risk, render_setups
from hedge_fund.services.scan_service import RiskService, ScanService


app = typer.Typer(add_completion=False)


def _pairs(context: ApplicationContext, pair: str | None) -> list[str]:
    return [pair] if pair else context.settings.trading.pairs


@app.command()
def scan(pair: str | None = typer.Option(None, "--pair")) -> None:
    context = ApplicationContext()
    try:
        with context.session_scope() as session:
            service = ScanService(
                context.settings,
                context.market_data,
                context.ai,
                context.create_repository(session),
                context.logger,
            )
            result = service.scan(_pairs(context, pair))
            render_biases(result.biases)
            render_setups(result.setups)
            if result.ai_analysis:
                render_ai_output(result.ai_analysis)
    except Exception as exc:  # noqa: BLE001
        context.logger.exception("Scan command failed")
        render_error(str(exc))
        raise typer.Exit(code=1) from exc


@app.command()
def bias(pair: str | None = typer.Option(None, "--pair")) -> None:
    context = ApplicationContext()
    try:
        with context.session_scope() as session:
            service = ScanService(
                context.settings,
                context.market_data,
                context.ai,
                context.create_repository(session),
                context.logger,
            )
            results = service.bias_only(_pairs(context, pair))
            render_biases(results)
    except Exception as exc:  # noqa: BLE001
        context.logger.exception("Bias command failed")
        render_error(str(exc))
        raise typer.Exit(code=1) from exc


@app.command()
def risk(
    pair: str = typer.Option(..., "--pair"),
    sl: int = typer.Option(..., "--sl"),
    risk: float = typer.Option(..., "--risk"),
) -> None:
    context = ApplicationContext()
    try:
        service = RiskService(context.market_data, context.broker)
        calculation = service.calculate(pair, risk, sl)
        render_risk(calculation)
    except Exception as exc:  # noqa: BLE001
        context.logger.exception("Risk command failed")
        render_error(str(exc))
        raise typer.Exit(code=1) from exc


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": False})
def chat(
    prompt: str | None = typer.Argument(None),
    print_mode: bool = typer.Option(False, "--print", "-p"),
    continue_last: bool = typer.Option(False, "--continue", "-c"),
    resume: str | None = typer.Option(None, "--resume", "-r"),
    output_format: str | None = typer.Option(None, "--output-format"),
    model: str | None = typer.Option(None, "--model"),
    permission_mode: str | None = typer.Option(None, "--permission-mode"),
    append_system_prompt: str | None = typer.Option(None, "--append-system-prompt"),
) -> None:
    context = ApplicationContext()
    runner = None
    try:
        runner = ChatCommandRunner(context)
        runner.run(
            prompt=prompt,
            print_mode=print_mode,
            continue_last=continue_last,
            resume_session=resume,
            output_format=output_format,
            model_override=model,
            permission_mode=permission_mode,
            append_system_prompt=append_system_prompt,
        )
    except typer.BadParameter as exc:
        render_error(str(exc))
        raise typer.Exit(code=2) from exc
    except (FileNotFoundError, SessionNotFoundError) as exc:
        render_error(str(exc))
        raise typer.Exit(code=1) from exc
    except Exception as exc:  # noqa: BLE001
        context.logger.exception("Chat command failed")
        render_error("Chat session failed. Check logs/app.log for details.")
        raise typer.Exit(code=1) from exc
    finally:
        if runner is not None and hasattr(runner, "close"):
            runner.close()
