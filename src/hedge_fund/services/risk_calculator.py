from __future__ import annotations

from hedge_fund.domain.models import RiskCalculation
from hedge_fund.services.utils import pip_size_from_metadata


class RiskCalculator:
    XAU_PIP_SIZE = 0.01
    XAU_STANDARD_LOT_OUNCES = 100
    XAU_PIP_VALUE_PER_STANDARD_LOT_USD = 1.0

    def calculate(
        self,
        pair: str,
        account_balance: float,
        risk_pct: float,
        sl_pips: int,
        current_price: float,
        metadata: dict,
    ) -> RiskCalculation:
        risk_amount = account_balance * (risk_pct / 100)
        if self._is_xau_pair(pair):
            pip_size = self.XAU_PIP_SIZE
            lot_size = round(risk_amount / (sl_pips * self.XAU_PIP_VALUE_PER_STANDARD_LOT_USD), 4)
            stop_distance = sl_pips * pip_size
        else:
            pip_size = pip_size_from_metadata(metadata)
            quote_to_usd = 1.0 if pair.endswith("USD") else current_price
            units = risk_amount / (sl_pips * pip_size * quote_to_usd)
            lot_size = round(units / 100000, 4)
            stop_distance = sl_pips * pip_size

        tp_1r2 = current_price + (stop_distance * 2)
        tp_1r3 = current_price + (stop_distance * 3)
        return RiskCalculation(
            pair=pair,
            account_balance=round(account_balance, 2),
            risk_pct=risk_pct,
            risk_amount=round(risk_amount, 2),
            sl_pips=sl_pips,
            lot_size=lot_size,
            tp_1r2=round(tp_1r2, 5),
            tp_1r3=round(tp_1r3, 5),
            rr_used=3.0,
        )

    def _is_xau_pair(self, pair: str) -> bool:
        normalized = pair.replace("_", "").upper()
        return normalized == "XAUUSD"
