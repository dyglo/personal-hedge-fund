from hedge_fund.chat.utils import normalize_pair_alias


def test_pair_alias_normalization() -> None:
    cases = {
        "Gold": "XAUUSD",
        "XAU": "XAUUSD",
        "XAU/USD": "XAUUSD",
        "Euro": "EURUSD",
        "EUR/USD": "EURUSD",
        "Cable": "GBPUSD",
        "Pound": "GBPUSD",
        "GBP/USD": "GBPUSD",
        "Yen": "USDJPY",
        "USD/JPY": "USDJPY",
    }

    for raw, expected in cases.items():
        assert normalize_pair_alias(raw) == expected
