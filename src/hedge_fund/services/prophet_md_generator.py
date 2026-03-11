from __future__ import annotations

from datetime import UTC, datetime


def _format_money(value: float) -> str:
    return f"{value:,.2f}"


def generate_prophet_md(profile) -> str:
    watchlist = list(profile.watchlist)
    sessions = list(profile.sessions)
    primary_market = watchlist[0] if watchlist else "None"
    risk_amount = round(profile.account_balance * (profile.risk_pct / 100), 2)
    generated = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    rules = [
        "- Only trade during approved sessions",
        "- Minimum confluence score of 7/10 required before entry",
        "- Always confirm H1 bias before M15 entry",
        f"- Risk maximum {profile.risk_pct}% per trade - no exceptions",
        f"- Minimum {profile.min_rr} risk-reward - do not take trades below this",
        "- No trading during high-impact news events",
        "- Always use the trade plan generator before executing",
    ]
    if profile.experience_level == "beginner":
        rules.append("- Review H1 structure before every session")
    if profile.experience_level == "professional":
        rules.append("- Treat every session independently, no revenge trading")

    sections = [
        "# PROPHET - My Trading Rules",
        f"Generated: {generated}",
        "",
        "## Identity",
        f"Name: {profile.display_name}",
        f"Experience: {profile.experience_level}",
        "",
        "## Markets",
        f"Watchlist: {', '.join(watchlist)}",
        f"Primary market: {primary_market}",
        "",
        "## Risk Management",
        f"Account balance: ${_format_money(profile.account_balance)}",
        f"Risk per trade: {profile.risk_pct}%",
        f"Risk amount per trade: ${_format_money(risk_amount)}",
        f"Minimum risk-reward: {profile.min_rr}",
        "Preferred risk-reward: 1:3",
        "",
        "## Sessions",
        f"Active sessions: {', '.join(sessions)}",
        "Avoid: High-impact news events",
        "",
        "## Strategy",
        "Timeframes: H1 for bias and structure, M15 for entry confirmation",
        "Core signals: Fair Value Gaps (FVG), Fibonacci retracement 0.5-0.786, liquidity sweeps, market structure (HH/HL, LH/LL)",
        "",
        "## Rules",
        *rules,
        "",
        "## Notes",
        "This file was auto-generated during onboarding.",
        "Use /remember to add personal rules.",
        "Use /forget to remove rules that no longer apply.",
    ]
    return "\n".join(sections)
