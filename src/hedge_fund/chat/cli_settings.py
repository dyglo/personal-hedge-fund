from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from hedge_fund.chat.models import CliPermissionMode
from hedge_fund.chat.utils import chat_root


class CliSettings(BaseModel):
    output_format: str = "text"
    permission_mode: CliPermissionMode = "default"
    model: str | None = None
    append_system_prompt: str | None = None

    @classmethod
    def load(cls, cwd: str | Path) -> "CliSettings":
        project_root = chat_root(cwd)
        paths = [
            Path.home() / ".hedge_fund" / "settings.yaml",
            project_root / "settings.yaml",
            project_root / "settings.local.yaml",
        ]
        merged: dict = {}
        for path in paths:
            if not path.exists():
                continue
            content = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(content, dict):
                merged.update(content)
        return cls.model_validate(merged)
