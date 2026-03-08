from hedge_fund.services.risk_calculator import RiskCalculator


def test_risk_calculator_handles_fx_pair() -> None:
    result = RiskCalculator().calculate(
        pair="EURUSD",
        account_balance=10000,
        risk_pct=1,
        sl_pips=20,
        current_price=1.1,
        metadata={"pipLocation": -4},
    )

    assert result.risk_amount == 100
    assert result.lot_size > 0
    assert result.tp_1r3 > result.tp_1r2


def test_risk_calculator_handles_xauusd_precision() -> None:
    result = RiskCalculator().calculate(
        pair="XAUUSD",
        account_balance=10000,
        risk_pct=1,
        sl_pips=15,
        current_price=2900.0,
        metadata={},
    )

    assert result.lot_size == 6.6667
    assert result.tp_1r2 == 2900.3
