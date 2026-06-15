"""Parse, validate, and repair agent decisions from model output."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
import re
from typing import Any, Iterable

from telltale.agents.dialogue import PlayerUtterance
from telltale.agents.memory import MemoryDelta
from telltale.agents.prompts import build_agent_prompt
from telltale.game.holdem import ActionType


@dataclass
class AgentDecision:
    """
    Describes a decision made by the agent. This is the output from the 
    model.  
    """
    action: ActionType | str # The action the agent is taking. 
    amount: int
    speech: str # the thing that the agent says when making this decision. 
    honest_rationale: str # the reason the agent gives for making this decision. 
    emotional_state: str
    memory_delta: MemoryDelta
    source: str = "model"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action"] = self.action.value if isinstance(self.action, ActionType) else self.action
        return data


def parse_agent_decision(raw_model_output: str) -> AgentDecision:
    """
    Parses the model output into an AgentDecision object. 
    """
    data = _loads_model_json(raw_model_output)
    missing = [field for field in ("action", "speech", "honest_rationale") if not data.get(field)]
    if missing:
        raise ValueError(f"model decision missing required field(s): {', '.join(missing)}")
    raw_action = str(data["action"])
    try:
        action: ActionType | str = ActionType(raw_action)
    except ValueError:
        action = raw_action
    return AgentDecision(
        action=action,
        amount=max(0, int(data.get("amount") or 0)),
        speech=str(data["speech"]),
        honest_rationale=str(data["honest_rationale"]),
        emotional_state=str(data.get("emotional_state") or "composed"),
        memory_delta=MemoryDelta.from_mapping(_normalize_memory_delta(data.get("memory_delta") or data.get("memory_updates"))),
        source="model",
    )


def _normalize_memory_delta(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    aliases = {
        "respect_delta": "respect_for_player",
        "fear_delta": "fear_of_player",
        "charm_delta": "charmed_by_player",
        "grudge_delta": "grudge_against_player",
        "note": "summary",
    }
    for source, target in aliases.items():
        if source in normalized and target not in normalized:
            normalized[target] = normalized[source]
    return normalized


def validate_and_repair(
    decision: AgentDecision,
    legal_actions: Iterable[ActionType | str],
    solver_recommendation: Any,
) -> AgentDecision:
    """
    Validates whether the decision made by the model is valid. 
    If it is not, it will be repaired (check or the first legal action from the solver). 
    """

    if not decision.speech.strip() or not decision.honest_rationale.strip():
        raise ValueError("model decision requires non-empty speech and honest_rationale")

    legal = _normalize_legal_actions(legal_actions)
    if not legal:
        repaired_action = ActionType.CHECK
    elif decision.action not in legal:
        repaired_action = _solver_action_or_first_legal(solver_recommendation, legal)
    else:
        repaired_action = decision.action

    amount = _repair_amount(decision.amount, repaired_action, solver_recommendation)

    decision.action = repaired_action
    decision.amount = amount
    decision.source = "model"
    return decision


def _loads_model_json(raw_model_output: str) -> dict[str, Any]:
    """
    Loads the model output as a JSON object. 
    """
    try:
        data = json.loads(raw_model_output)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_model_output, flags=re.DOTALL)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("model output must be a JSON object")
    return data


def _normalize_legal_actions(legal_actions: Iterable[ActionType | str]) -> set[ActionType]:
    """
    Normalizes the legal actions to a set of ActionType objects. 
    """
    legal: set[ActionType] = set()
    for action in legal_actions:
        if isinstance(action, ActionType):
            legal.add(action)
        else:
            legal.add(ActionType(str(action)))
    return legal


def _solver_action_or_first_legal(solver_recommendation: Any, legal: set[ActionType]) -> ActionType:
    """
    Returns the action from the solver if it is legal, otherwise returns the first legal action. 
    """
    solver_action = _action_from_solver(solver_recommendation)
    if solver_action in legal:
        return solver_action
    preferred_order = (
        ActionType.CHECK,
        ActionType.CALL,
        ActionType.FOLD,
        ActionType.BET,
        ActionType.RAISE,
        ActionType.ALL_IN,
    )
    for action in preferred_order:
        if action in legal:
            return action
    return sorted(legal, key=lambda item: item.value)[0]


def _action_from_solver(solver_recommendation: Any) -> ActionType | None:
    """
    Returns the action from the solver. 
    """
    value = None
    if isinstance(solver_recommendation, dict):
        value = solver_recommendation.get("action") or solver_recommendation.get("suggested_action")
    else:
        value = getattr(solver_recommendation, "action", None) or getattr(
            solver_recommendation,
            "suggested_action",
            None,
        )
    if isinstance(value, ActionType):
        return value
    if isinstance(value, Enum):
        value = value.value
    if value is None:
        return None
    try:
        return ActionType(str(value))
    except ValueError:
        return None


def _repair_amount(action_amount: int, action: ActionType, solver_recommendation: Any) -> int:
    if action in {ActionType.FOLD, ActionType.CHECK, ActionType.CALL}:
        return 0
    if action == ActionType.ALL_IN:
        solver_amount = _amount_from_solver(solver_recommendation)
        return max(0, solver_amount if solver_amount is not None else action_amount)
    solver_amount = _amount_from_solver(solver_recommendation)
    if action_amount <= 0 and solver_amount is not None:
        return max(0, solver_amount)
    return max(0, action_amount)


def _amount_from_solver(solver_recommendation: Any) -> int | None:
    """
    Returns the amount from the solver. 
    """
    if isinstance(solver_recommendation, dict):
        value = solver_recommendation.get("amount") or solver_recommendation.get("suggested_amount")
    else:
        value = getattr(solver_recommendation, "amount", None)
        if value is None:
            value = getattr(solver_recommendation, "suggested_amount", None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "AgentDecision",
    "PlayerUtterance",
    "build_agent_prompt",
    "parse_agent_decision",
    "validate_and_repair",
]
