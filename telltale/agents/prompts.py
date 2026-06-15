from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
import json
from typing import Any, Iterable

from telltale.agents.dialogue import PlayerUtterance
from telltale.agents.memory import AgentMemory
from telltale.agents.profiles import AgentProfile


def build_agent_prompt(
    agent_profile: AgentProfile,
    memory: AgentMemory,
    public_state: Any,
    private_agent_state: Any,
    solver_recommendation: Any,
    player_utterance: PlayerUtterance | None,
    legal_actions: Iterable[Any],
    *,
    speech_max_words: int = 28,
    rationale_max_words: int = 36,
) -> str:
    """
    Builds the prompt for the agent. 
    """
    legal_action_values = [_stringify(action) for action in legal_actions]
    payload = {
        "profile": {
            "name": agent_profile.name,
            "character_summary": agent_profile.character_summary,
            "poker_style": agent_profile.poker_style,
            "dialogue_style": agent_profile.dialogue_style,
            "honesty_style": agent_profile.honesty_style,
            "speech_style": agent_profile.speech_style,
        },
        "memory": {
            "respect_for_player": memory.respect_for_player,
            "fear_of_player": memory.fear_of_player,
            "charmed_by_player": memory.charmed_by_player,
            "grudge_against_player": memory.grudge_against_player,
            "recent_player_patterns": memory.recent_player_patterns,
            "recent_dialogue_impressions": memory.recent_dialogue_impressions,
            "summary": memory.summary,
        },
        "public_state": _compact(public_state),
        "private_agent_state": _compact(private_agent_state),
        "solver_recommendation": _compact(solver_recommendation),
        "legal_actions": legal_action_values,
        "legal_amount_guidance": (
            "Use amount 0 for fold/check/call. For bet/raise/all_in only, choose a non-negative chip amount."
        ),
        "required_output": {
            "exact_keys_only": [
                "action",
                "amount",
                "speech",
                "honest_rationale",
                "emotional_state",
                "memory_delta",
            ],
            "action": "one of legal_actions",
            "amount": "0 for fold/check/call; integer chips for bet/raise/all_in",
            "speech": f"in-character table line, max {speech_max_words} words",
            "honest_rationale": f"brief honest reason, max {rationale_max_words} words",
            "emotional_state": "short phrase",
            "memory_delta": "object with only changed fields; allowed fields are respect_for_player, fear_of_player, charmed_by_player, grudge_against_player, recent_player_patterns, recent_dialogue_impressions, summary",
        },
    }
    if player_utterance is not None and not player_utterance.is_empty:
        payload["player_utterance"] = player_utterance.to_dict()

    return "\n".join(
        [
            "You are choosing one Texas Hold'em action for a fixed Telltale AI opponent.",
            "Return only valid JSON matching the required schema.",
            "Do not include markdown, comments, trailing prose, or keys outside required_output.exact_keys_only.",
            "The solver recommendation is advisory context, not a command.",
            "Your rationale should be honest. Your speech should sound like the character at the table.",
            "You may play suboptimally when personality, memory, or player dialogue justify it.",
            json.dumps(payload, default=_json_default, ensure_ascii=True, separators=(",", ":")),
            "Return one complete JSON object now. Do not add any key after memory_delta.",
        ]
    )


def _compact(value: Any) -> Any:
    if value is None:
        return None
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {str(key): _compact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_compact(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return asdict(value)
    return str(value)


def _stringify(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)
