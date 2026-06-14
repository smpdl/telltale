from __future__ import annotations

from dataclasses import asdict, dataclass
import json


@dataclass(frozen=True)
class PlayerUtterance:
    raw_text: str = ""
    target_agent_id: str | None = None

    @property
    def is_empty(self) -> bool:
        return self.raw_text.strip() == ""

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
