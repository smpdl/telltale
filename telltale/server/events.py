from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4
import json
from typing import Any


@dataclass(frozen=True)
class GameEvent:
    event_id: str
    event_type: str
    run_id: str
    sequence: int
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "payload": self.payload,
        }


@dataclass(frozen=True)
class EventBatch:
    run_id: str
    events: list[GameEvent]
    public_state: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "events": [event.to_dict() for event in self.events],
            "public_state": self.public_state,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


class EventBuilder:
    def __init__(self, run_id: str, start_sequence: int = 0):
        self.run_id = run_id
        self._sequence = start_sequence
        self.events: list[GameEvent] = []

    @property
    def sequence(self) -> int:
        return self._sequence

    def emit(self, event_type: str, **payload: Any) -> GameEvent:
        self._sequence += 1
        event = GameEvent(
            event_id=str(uuid4()),
            event_type=event_type,
            run_id=self.run_id,
            sequence=self._sequence,
            payload=payload,
        )
        self.events.append(event)
        return event
