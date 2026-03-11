from __future__ import annotations

from hedge_fund.domain.models import RuleCheck, TradePlanOutput
from hedge_fund.services.risk_calculator import RiskCalculator
from hedge_fund.services.utils import normalize_pair, pip_size_from_metadata


_DIRECTION_ALIASES = {
    "BUY": "LONG",
    "SELL": "SHORT",
    "LONG": "LONG",
    "SHORT": "SHORT",
}


class TradePlanService:
    def __init__(self, broker, calculator: RiskCalculator | None = None) -> None:
        self.broker = broker
        self.calculator = calculator or RiskCalculator()

    def generate(
        self,
        pair: str,
        direction: str,
        entry: float,
        stop_loss: float,
        setup_type: str,
        session: str,
        confluence_score: int,
        risk_pct: float,
    ) -> TradePlanOutput:
        normalized_pair = normalize_pair(pair)
        raw_direction = direction.strip().upper()
        normalized_direction = _DIRECTION_ALIASES.get(raw_direction, raw_direction)
        if normalized_direction not in {"LONG", "SHORT"}:
            raise ValueError(f"Unrecognised direction '{direction}'. Use LONG, SHORT, BUY, or SELL.")
        sl_distance = abs(entry - stop_loss)
        if sl_distance <= 0:
            raise ValueError("Entry and stop loss must be different prices.")

        account_balance = self.broker.get_account_balance()
        metadata = {} if self.calculator._is_xau_pair(normalized_pair) else self.broker.get_instrument_metadata(normalized_pair)  # noqa: SLF001
        pip_size = self.calculator.XAU_PIP_SIZE if self.calculator._is_xau_pair(normalized_pair) else pip_size_from_metadata(metadata)  # noqa: SLF001
        sl_pips = max(int(round(sl_distance / pip_size)), 1)

        calculation = self.calculator.calculate(
            normalized_pair,
            account_balance,
            risk_pct,
            sl_pips,
            entry,
            metadata,
        )

        tp1 = entry + (sl_distance * 2) if normalized_direction == "LONG" else entry - (sl_distance * 2)
        tp2 = entry + (sl_distance * 3) if normalized_direction == "LONG" else entry - (sl_distance * 3)
        lot_size = max(round(calculation.lot_size, 2), 0.01)
        rule_checks = self._rule_checks(risk_pct, confluence_score, session, sl_distance, tp1, entry)
        narrative = self._narrative(
            normalized_pair,
            normalized_direction,
            session,
            entry,
            stop_loss,
            sl_distance,
            risk_pct,
            calculation.account_balance,
            lot_size,
            calculation.risk_amount,
            tp1,
            tp2,
            confluence_score,
        )
        formatted_block = self._formatted_block(
            normalized_pair,
            normalized_direction,
            setup_type,
            session,
            entry,
            stop_loss,
            sl_distance,
            tp1,
            tp2,
            lot_size,
            calculation.risk_amount,
            risk_pct,
            calculation.risk_amount * 3,
            rule_checks,
        )

        return TradePlanOutput(
            pair=normalized_pair,
            direction=normalized_direction,
            entry=entry,
            stop_loss=stop_loss,
            sl_distance=sl_distance,
            tp1=tp1,
            tp2=tp2,
            lot_size=round(lot_size, 2),
            risk_amount=round(calculation.risk_amount, 2),
            risk_pct=risk_pct,
            tp2_reward=round(calculation.risk_amount * 3, 2),
            setup_type=setup_type,
            session=session,
            confluence_score=confluence_score,
            rule_checks=rule_checks,
            narrative=narrative,
            formatted_block=formatted_block,
        )

    def _rule_checks(
        self,
        risk_pct: float,
        confluence_score: int,
        session: str,
        sl_distance: float,
        tp1: float,
        entry: float,
    ) -> list[RuleCheck]:
        session_clean = session.strip()
        tp1_meets_min_rr = round(abs(tp1 - entry), 8) == round(sl_distance * 2, 8)
        return [
            RuleCheck(
                rule="Risk within limit",
                passed=risk_pct <= 1.0,
                detail=(
                    f"Risk {risk_pct}% is within the 0.5-1% limit"
                    if risk_pct <= 1.0
                    else f"Risk {risk_pct}% exceeds the 1% maximum"
                ),
            ),
            RuleCheck(
                rule="Confluence score",
                passed=confluence_score >= 7,
                detail=(
                    f"Confluence {confluence_score}/10 meets the minimum threshold of 7"
                    if confluence_score >= 7
                    else f"Confluence {confluence_score}/10 is below the minimum threshold of 7"
                ),
            ),
            RuleCheck(
                rule="Approved session",
                passed=session_clean in {"London", "New York"},
                detail=(
                    f"{session_clean} session is approved for trading"
                    if session_clean in {"London", "New York"}
                    else f"{session_clean} is not an approved trading session"
                ),
            ),
            RuleCheck(
                rule="Minimum RR at TP1",
                passed=tp1_meets_min_rr,
                detail=(
                    "TP1 achieves 1:2 RR - minimum requirement satisfied"
                    if tp1_meets_min_rr
                    else "TP1 does not achieve the required 1:2 RR"
                ),
            ),
        ]

    def _narrative(
        self,
        pair: str,
        direction: str,
        session: str,
        entry: float,
        stop_loss: float,
        sl_distance: float,
        risk_pct: float,
        account_balance: float,
        lot_size: float,
        risk_amount: float,
        tp1: float,
        tp2: float,
        confluence_score: int,
    ) -> str:
        return (
            f"Based on your {pair} {direction} setup in the {session} session, here is your trade plan. "
            f"Your entry is {entry:.2f} with a stop at {stop_loss:.2f}, which puts {sl_distance:.2f} points of risk on the setup. "
            f"At {risk_pct}% risk on a {account_balance:.2f} account, your position size comes out to {lot_size:.2f} lots with {risk_amount:.2f} at risk. "
            f"TP1 is {tp1:.2f} for a 1:2 and TP2 is {tp2:.2f} for the 1:3 target. "
            f"Confluence is currently {confluence_score}/10."
        )

    def _formatted_block(
        self,
        pair: str,
        direction: str,
        setup_type: str,
        session: str,
        entry: float,
        stop_loss: float,
        sl_distance: float,
        tp1: float,
        tp2: float,
        lot_size: float,
        risk_amount: float,
        risk_pct: float,
        tp2_reward: float,
        rule_checks: list[RuleCheck],
    ) -> str:
        lines = [
            "◆ PROPHET - TRADE PLAN",
            "──────────────────────────────────────────",
            f"{pair} {direction}  ·  {setup_type}  ·  {session}",
            "──────────────────────────────────────────",
            f"ENTRY        {entry:.2f}",
            f"STOP LOSS    {stop_loss:.2f}    (-{sl_distance:.2f} pts)",
            f"TP1          {tp1:.2f}    (1:2 RR)",
            f"TP2          {tp2:.2f}    (1:3 RR)",
            "──────────────────────────────────────────",
            f"LOT SIZE     {lot_size:.2f} lots",
            f"RISK         ${risk_amount:.2f}    ({risk_pct:.2f}% of account)",
            f"MAX REWARD   ${tp2_reward:.2f}    at TP2",
            "──────────────────────────────────────────",
            "RULE CHECK",
        ]
        for item in rule_checks:
            marker = "✓" if item.passed else "✗"
            lines.append(f"{marker} {item.detail}")
        lines.append("──────────────────────────────────────────")
        return "\n".join(lines)
