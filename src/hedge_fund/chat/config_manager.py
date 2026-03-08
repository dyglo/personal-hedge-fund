from __future__ import annotations

from pathlib import Path

import yaml

from hedge_fund.chat.utils import normalize_pair_alias
from hedge_fund.config.settings import Settings


class ConfigManager:
    def __init__(self, path: str | Path = "config.yaml") -> None:
        self.path = Path(path)

    def current_settings(self) -> Settings:
        return Settings.load(self.path)

    def show_pairs(self) -> list[str]:
        return self.current_settings().trading.pairs

    def show_risk(self) -> dict[str, float]:
        risk = self.current_settings().trading.risk
        return {
            "default_risk_pct": risk.default_risk_pct,
            "minimum_rr": risk.minimum_rr,
            "preferred_rr": risk.preferred_rr,
        }

    def add_pair(self, pair: str) -> Settings:
        canonical = normalize_pair_alias(pair) or pair
        content = self._load_raw()
        pairs = content.setdefault("trading", {}).setdefault("pairs", [])
        if canonical not in pairs:
            pairs.append(canonical)
        return self._validate_and_write(content)

    def remove_pair(self, pair: str) -> Settings:
        canonical = normalize_pair_alias(pair) or pair
        content = self._load_raw()
        pairs = content.setdefault("trading", {}).setdefault("pairs", [])
        content["trading"]["pairs"] = [item for item in pairs if item != canonical]
        return self._validate_and_write(content)

    def _load_raw(self) -> dict:
        return yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}

    def _validate_and_write(self, content: dict) -> Settings:
        settings = Settings.model_validate(content)
        self.path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
        return settings
