from __future__ import annotations

from contextlib import contextmanager

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from hedge_fund.chat.models import ReverseRiskCalculation
from hedge_fund.domain.models import AiAnalysisResult, BiasResult, RiskCalculation, SetupScanResult


console = Console()
PROPHET_BANNER = """
  ██████╗ ██████╗  ██████╗ ██████╗ ██╗  ██╗███████╗████████╗
  ██╔══██╗██╔══██╗██╔═══██╗██╔══██╗██║  ██║██╔════╝╚══██╔══╝
  ██████╔╝██████╔╝██║   ██║██████╔╝███████║█████╗     ██║
  ██╔═══╝ ██╔══██╗██║   ██║██╔═══╝ ██╔══██║██╔══╝     ██║
  ██║     ██║  ██║╚██████╔╝██║     ██║  ██║███████╗   ██║
  ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚═╝  ╚═╝╚══════╝   ╚═╝

  Personal AI Trading Assistant  |  v3.0  |  Forex Edition
""".strip("\n")


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
                title=f"Prophet Analysis: {item.provider}/{item.model} [{item.recommendation}]",
                subtitle=", ".join(item.caution_flags) if item.caution_flags else None,
                border_style="blue",
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


def render_chat_status(message: str) -> None:
    console.print(f"[bold cyan]Prophet>[/bold cyan] {message}")


def render_chat_message(message: str) -> None:
    markdown_like = "\n" in message or any(token in message for token in ("# ", "- ", "* ", "`", "**"))
    if not markdown_like:
        render_chat_status(message)
        return

    console.print(
        Panel(
            Markdown(message),
            title="Prophet",
            border_style="cyan",
            expand=True,
        )
    )


def render_help_menu(commands: list[tuple[str, str]]) -> None:
    table = Table(title="Command Palette")
    table.add_column("Command", style="bold cyan")
    table.add_column("What it does")
    for command, description in commands:
        table.add_row(command, description)
    console.print(table)


def render_model_picker(current: str, options: list[tuple[str, str, str]]) -> None:
    table = Table(title="Model Picker")
    table.add_column("Option", style="bold cyan")
    table.add_column("Target")
    table.add_column("Use when")
    for option, target, note in options:
        label = f"{option} [green](current)[/green]" if option == current else option
        table.add_row(label, target, note)
    console.print(table)
    console.print("[bold cyan]Tip:[/bold cyan] use /model auto, /model gemini, /model openai, or /model reset")


def render_reverse_risk(calculation: ReverseRiskCalculation) -> None:
    table = Table(title="Risk Exposure")
    for column in (
        "Pair",
        "Balance",
        "Lot Size",
        "SL (pips)",
        "Risk Amount",
        "Risk %",
        "Price",
        "Pip Value / Lot",
    ):
        table.add_column(column)
    table.add_row(
        calculation.pair,
        f"{calculation.account_balance:.2f}",
        f"{calculation.lot_size:.4f}",
        str(calculation.sl_pips),
        f"{calculation.risk_amount:.2f}",
        f"{calculation.risk_pct:.2f}",
        f"{calculation.current_price:.5f}",
        f"{calculation.pip_value_per_standard_lot:.5f}",
    )
    console.print(table)


def render_prophet_banner() -> None:
    console.print(Panel.fit(PROPHET_BANNER, title="Prophet", border_style="blue"))


def render_session_header(message: str) -> None:
    console.print(f"[bold white]{message}[/bold white]")


@contextmanager
def agent_status(message: str = "Thinking..."):
    with console.status(f"[bold cyan]{message}[/bold cyan]", spinner="dots12") as status:
        yield status
