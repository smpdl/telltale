from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any


MAX_RECENT_ITEMS = 5


@dataclass
class MemoryDelta:
    """
    Describes a change in the agent's memory. 
    """
    respect_for_player: float | None = None
    fear_of_player: float | None = None
    charmed_by_player: float | None = None
    grudge_against_player: float | None = None
    recent_player_patterns: list[str] = field(default_factory=list)
    recent_dialogue_impressions: list[str] = field(default_factory=list)
    summary: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "MemoryDelta":
        if not data:
            return cls()
        return cls(
            respect_for_player=_optional_float(data.get("respect_for_player")),
            fear_of_player=_optional_float(data.get("fear_of_player")),
            charmed_by_player=_optional_float(data.get("charmed_by_player")),
            grudge_against_player=_optional_float(data.get("grudge_against_player")),
            recent_player_patterns=_string_list(data.get("recent_player_patterns")),
            recent_dialogue_impressions=_string_list(data.get("recent_dialogue_impressions")),
            summary=_optional_string(data.get("summary")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentMemory:
    """
    Describes the memory of an agent. 
    """
    agent_id: str  
    respect_for_player: float = 0.0 # how much the agent respects the player. 
    fear_of_player: float = 0.0 # how much the agent fears the player. 
    charmed_by_player: float = 0.0 # how much the agent is charmed by the player. 
    grudge_against_player: float = 0.0 # how much the agent is grudge against the player. 
    recent_player_patterns: list[str] = field(default_factory=list) # a list of recent patterns the player has exhibited. 
    recent_dialogue_impressions: list[str] = field(default_factory=list) # a list of recent dialogue impressions the player has given. 
    summary: str = "" # a summary of the agent's memory. 
    max_recent_items: int = MAX_RECENT_ITEMS # the maximum number of recent items to store. 

    def __post_init__(self) -> None:
        self.respect_for_player = _clamp(self.respect_for_player, -1.0, 1.0)
        self.fear_of_player = _clamp(self.fear_of_player, 0.0, 1.0)
        self.charmed_by_player = _clamp(self.charmed_by_player, 0.0, 1.0)
        self.grudge_against_player = _clamp(self.grudge_against_player, 0.0, 1.0)
        self.recent_player_patterns = _bounded(_string_list(self.recent_player_patterns), self.max_recent_items)
        self.recent_dialogue_impressions = _bounded(
            _string_list(self.recent_dialogue_impressions),
            self.max_recent_items,
        )
        self.summary = str(self.summary or "")

    @classmethod
    def neutral(cls, agent_id: str) -> "AgentMemory":
        return cls(agent_id=agent_id)

    @classmethod
    def reset_for_run(cls, agent_id: str) -> "AgentMemory":
        return cls.neutral(agent_id)

    def apply_delta(self, delta: MemoryDelta | dict[str, Any] | None) -> None:
        update = delta if isinstance(delta, MemoryDelta) else MemoryDelta.from_mapping(delta)
        if update.respect_for_player is not None:
            self.respect_for_player = _clamp(update.respect_for_player, -1.0, 1.0)
        if update.fear_of_player is not None:
            self.fear_of_player = _clamp(update.fear_of_player, 0.0, 1.0)
        if update.charmed_by_player is not None:
            self.charmed_by_player = _clamp(update.charmed_by_player, 0.0, 1.0)
        if update.grudge_against_player is not None:
            self.grudge_against_player = _clamp(update.grudge_against_player, 0.0, 1.0)
        if update.recent_player_patterns:
            self.recent_player_patterns = _bounded(
                [*self.recent_player_patterns, *update.recent_player_patterns],
                self.max_recent_items,
            )
        if update.recent_dialogue_impressions:
            self.recent_dialogue_impressions = _bounded(
                [*self.recent_dialogue_impressions, *update.recent_dialogue_impressions],
                self.max_recent_items,
            )
        if update.summary is not None:
            self.summary = update.summary

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


def _bounded(items: list[str], limit: int) -> list[str]:
    return items[-limit:]


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        return [str(value)]
    return [str(item) for item in value if item is not None]
