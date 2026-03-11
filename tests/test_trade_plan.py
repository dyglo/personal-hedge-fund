import pytest
from pydantic import ValidationError

from hedge_fund.domain.models import TradePlanOutput
from hedge_fund.services.trade_plan_service import TradePlanService


class _Broker:
    def get_account_balance(self):
        return 10000.0

    def get_instrument_metadata(self, pair: str):
        return {"pipLocation": -4}


def _service() -> TradePlanService:
    return TradePlanService(_Broker())


def test_trade_plan_xauusd_long_calculates_targets_and_size() -> None:
    plan = _service().generate(
        pair="XAUUSD",
        direction="LONG",
        entry=2900.0,
        stop_loss=2890.0,
        setup_type="FVG + Fib 0.618",
        session="London",
        confluence_score=8,
        risk_pct=1.0,
    )

    assert plan.tp1 == 2920.0
    assert plan.tp2 == 2930.0
    assert plan.lot_size == 0.1
    assert plan.risk_amount == 100.0


def test_trade_plan_xauusd_short_inverts_targets() -> None:
    plan = _service().generate(
        pair="XAUUSD",
        direction="SHORT",
        entry=2900.0,
        stop_loss=2910.0,
        setup_type="FVG + Fib 0.618",
        session="New York",
        confluence_score=8,
        risk_pct=1.0,
    )

    assert plan.tp1 == 2880.0
    assert plan.tp2 == 2870.0
    assert plan.tp1 < plan.entry
    assert plan.tp2 < plan.entry


def test_trade_plan_accepts_buy_and_sell_aliases() -> None:
    long_plan = _service().generate(
        pair="XAUUSD",
        direction="buy",
        entry=2900.0,
        stop_loss=2890.0,
        setup_type="FVG + Fib 0.618",
        session="London",
        confluence_score=8,
        risk_pct=1.0,
    )
    short_plan = _service().generate(
        pair="XAUUSD",
        direction="sell",
        entry=2900.0,
        stop_loss=2910.0,
        setup_type="FVG + Fib 0.618",
        session="New York",
        confluence_score=8,
        risk_pct=1.0,
    )

    assert long_plan.direction == "LONG"
    assert long_plan.tp1 == 2920.0
    assert short_plan.direction == "SHORT"
    assert short_plan.tp1 == 2880.0


def test_trade_plan_rejects_unknown_direction() -> None:
    with pytest.raises(ValueError, match="Unrecognised direction"):
        _service().generate(
            pair="XAUUSD",
            direction="bullish",
            entry=2900.0,
            stop_loss=2890.0,
            setup_type="FVG + Fib 0.618",
            session="London",
            confluence_score=8,
            risk_pct=1.0,
        )


def test_trade_plan_eurusd_long_uses_fx_position_sizing() -> None:
    plan = _service().generate(
        pair="EURUSD",
        direction="LONG",
        entry=1.10,
        stop_loss=1.098,
        setup_type="London continuation",
        session="London",
        confluence_score=7,
        risk_pct=1.0,
    )

    assert plan.sl_distance == pytest.approx(0.002)
    assert plan.tp1 == pytest.approx(1.104)
    assert plan.tp2 == pytest.approx(1.106)
    assert plan.lot_size == 0.5
    assert plan.risk_amount == 100.0


def test_trade_plan_rule_check_fails_when_risk_exceeds_limit() -> None:
    plan = _service().generate(
        pair="XAUUSD",
        direction="LONG",
        entry=2900.0,
        stop_loss=2890.0,
        setup_type="FVG + Fib 0.618",
        session="London",
        confluence_score=8,
        risk_pct=1.5,
    )

    risk_rule = next(item for item in plan.rule_checks if item.rule == "Risk within limit")

    assert risk_rule.passed is False
    assert risk_rule.detail == "Risk 1.5% exceeds the 1% maximum"


def test_trade_plan_rule_check_fails_when_confluence_is_low() -> None:
    plan = _service().generate(
        pair="XAUUSD",
        direction="LONG",
        entry=2900.0,
        stop_loss=2890.0,
        setup_type="FVG + Fib 0.618",
        session="London",
        confluence_score=6,
        risk_pct=1.0,
    )

    score_rule = next(item for item in plan.rule_checks if item.rule == "Confluence score")

    assert score_rule.passed is False
    assert score_rule.detail == "Confluence 6/10 is below the minimum threshold of 7"


def test_trade_plan_rule_check_fails_for_invalid_session() -> None:
    plan = _service().generate(
        pair="XAUUSD",
        direction="LONG",
        entry=2900.0,
        stop_loss=2890.0,
        setup_type="FVG + Fib 0.618",
        session="Asia",
        confluence_score=8,
        risk_pct=1.0,
    )

    session_rule = next(item for item in plan.rule_checks if item.rule == "Approved session")

    assert session_rule.passed is False
    assert session_rule.detail == "Asia is not an approved trading session"


def test_trade_plan_formatted_block_excludes_markdown_symbols() -> None:
    plan = _service().generate(
        pair="XAUUSD",
        direction="LONG",
        entry=2900.0,
        stop_loss=2890.0,
        setup_type="FVG + Fib 0.618",
        session="London",
        confluence_score=8,
        risk_pct=1.0,
    )

    assert "*" not in plan.formatted_block
    assert "#" not in plan.formatted_block
    assert "`" not in plan.formatted_block
    assert "_" not in plan.formatted_block


def test_trade_plan_output_requires_all_required_fields() -> None:
    with pytest.raises(ValidationError):
        TradePlanOutput(pair="XAUUSD")
