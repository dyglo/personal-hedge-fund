from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hedge_fund.config.settings import AgentConfig


class ScratchpadLogger:
    def __init__(self, root: Path, session_id: str, enabled: bool) -> None:
        self.enabled = enabled
        self.path = root / f"{session_id}.jsonl"
        if self.enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self.path.exists():
                self.log("init", {"session_id": session_id})

    def log(self, entry_type: str, content: dict[str, Any]) -> None:
        if not self.enabled:
            return
        payload = {
            "type": entry_type,
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "content": content,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str) + "\n")


class ScratchpadManager:
    def __init__(self, cwd: str | Path, config: AgentConfig) -> None:
        self.root = Path(cwd) / config.scratchpad_path
        self.enabled = config.scratchpad_enabled

    def for_session(self, session_id: str) -> ScratchpadLogger:
        return ScratchpadLogger(self.root, session_id, self.enabled)
