from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


class TraceLogger:
    def __init__(self, run_id: str, root_dir: str | Path = "runs"):
        self.run_id = run_id
        self.run_dir = Path(root_dir) / run_id
        self.path = self.run_dir / "trace.jsonl"
        self.records: list[dict[str, Any]] = []

    def record(self, **fields: Any) -> dict[str, Any]:
        record = {
            "trace_version": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            **fields,
        }
        self.records.append(record)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, default=_json_default, ensure_ascii=True) + "\n")
        return record

    def export_text(self) -> str:
        if self.path.exists():
            return self.path.read_text(encoding="utf-8")
        return "\n".join(json.dumps(record, default=_json_default) for record in self.records)


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "value"):
        return value.value
    return str(value)
