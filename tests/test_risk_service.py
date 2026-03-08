from hedge_fund.services.scan_service import RiskService


class _MarketData:
    def __init__(self) -> None:
        self.seen_pair = None

    def get_price(self, pair: str):
        self.seen_pair = pair
        return 2900.0


class _Broker:
    def __init__(self) -> None:
        self.seen_pair = None
        self.metadata_calls = 0

    def get_instrument_metadata(self, pair: str):
        self.seen_pair = pair
        self.metadata_calls += 1
        return {"pipLocation": -1}

    def get_account_balance(self):
        return 10000.0


def test_risk_service_normalizes_pair_before_provider_calls() -> None:
    market = _MarketData()
    broker = _Broker()

    result = RiskService(market, broker).calculate("eur/usd", 1, 15)

    assert broker.seen_pair == "EURUSD"
    assert market.seen_pair == "EURUSD"
    assert result.pair == "EURUSD"


def test_risk_service_skips_metadata_fetch_for_xauusd() -> None:
    market = _MarketData()
    broker = _Broker()

    RiskService(market, broker).calculate("XAUUSD", 1, 15)

    assert broker.metadata_calls == 0
