from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from hedge_fund.domain.models import AiAnalysisResult, BiasResult, RiskCalculation, SetupScanResult


console = Console()


def render_biases(biases: list[BiasResult]) -> None:
    table = Table(title="Market Bias")
    for column in ("Pair", "Bias", "Structure", "Key Level", "Level Type"):
        table.add_column(column)
    for bias in biases:
        table.add_row(
            bias.pair,
            bias.bias,
            bias.structure,
            f"{bias.key_level:.5f}",
            bias.key_level_type,
        )
    console.print(table)


def render_setups(setups: list[SetupScanResult]) -> None:
    table = Table(title="Setup Scanner")
    for column in ("Pair", "Score", "Signals", "FVG", "Fib", "Sweep"):
        table.add_column(column)
    for setup in setups:
        color = "green" if setup.score >= 8 else "yellow" if setup.score >= 6 else "red"
        fvg = f"{setup.fvg_range.low:.5f}-{setup.fvg_range.high:.5f}" if setup.fvg_range else "-"
        fib = str(setup.fib_level) if setup.fib_level is not None else "-"
        sweep = f"{setup.sweep_level:.5f}" if setup.sweep_level is not None else "-"
        table.add_row(
            setup.pair,
            f"[{color}]{setup.score}[/{color}]",
            setup.signals_summary,
            fvg,
            fib,
            sweep,
        )
    console.print(table)


def render_ai_output(ai_analysis: list[AiAnalysisResult]) -> None:
    for item in ai_analysis:
        console.print(
            Panel(
                item.narrative,
                title=f"AI Analysis: {item.provider}/{item.model} [{item.recommendation}]",
                subtitle=", ".join(item.caution_flags) if item.caution_flags else None,
            )
        )


def render_risk(calculation: RiskCalculation) -> None:
    table = Table(title="Risk Calculation")
    for column in ("Pair", "Balance", "Risk %", "Risk Amount", "SL (pips)", "Lot Size", "TP 1:2", "TP 1:3"):
        table.add_column(column)
    table.add_row(
        calculation.pair,
        f"{calculation.account_balance:.2f}",
        f"{calculation.risk_pct:.2f}",
        f"{calculation.risk_amount:.2f}",
        str(calculation.sl_pips),
        f"{calculation.lot_size:.4f}",
        f"{calculation.tp_1r2:.5f}",
        f"{calculation.tp_1r3:.5f}",
    )
    console.print(table)


def render_error(message: str) -> None:
    console.print(Panel(message, title="Error", border_style="red"))
