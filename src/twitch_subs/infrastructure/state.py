from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from ..domain.models import BroadcasterType


class StateRepository:
    def __init__(self, path: Path | None = None):
        self.path = path or Path(".subs_status.json")

    def load(self) -> Dict[str, BroadcasterType]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text())
            return {k: BroadcasterType(v) for k, v in data.items()}
        except Exception:
            return {}

    def save(self, state: Dict[str, BroadcasterType]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        data = {k: v.value for k, v in state.items()}
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        tmp.replace(self.path)
