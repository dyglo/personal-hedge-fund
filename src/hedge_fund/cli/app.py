from __future__ import annotations

import typer

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
        service = ScanService(
            context.settings,
            context.market_data,
            context.ai,
            context.repository,
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
        service = ScanService(
            context.settings,
            context.market_data,
            context.ai,
            context.repository,
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
