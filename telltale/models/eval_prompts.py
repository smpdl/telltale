from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from telltale.agents.dialogue import PlayerUtterance
from telltale.agents.memory import AgentMemory
from telltale.agents.profiles import get_agent_profile
from telltale.agents.prompts import build_agent_prompt
from telltale.game.holdem import ActionType
from telltale.poker.policy import PokerDecision


@dataclass(frozen=True)
class ModelCandidate:
    label: str
    hf_repo_id: str
    gguf_filename: str
    quantization: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ModelCandidate":
        return cls(
            label=str(data["label"]),
            hf_repo_id=str(data["hf_repo_id"]),
            gguf_filename=str(data["gguf_filename"]),
            quantization=str(data.get("quantization") or ""),
        )


@dataclass(frozen=True)
class AgentEvalCase:
    case_id: str
    agent_id: str
    memory_summary: str
    public_state: dict[str, Any]
    private_agent_state: dict[str, Any]
    solver_recommendation: PokerDecision
    player_utterance: PlayerUtterance | None
    legal_actions: tuple[ActionType, ...]
    expected_pressure: str

    def build_prompt(self, *, speech_max_words: int = 28, rationale_max_words: int = 36) -> str:
        profile = get_agent_profile(self.agent_id)
        memory = AgentMemory.neutral(self.agent_id)
        memory.summary = self.memory_summary
        return build_agent_prompt(
            profile,
            memory,
            self.public_state,
            self.private_agent_state,
            self.solver_recommendation,
            self.player_utterance,
            self.legal_actions,
            speech_max_words=speech_max_words,
            rationale_max_words=rationale_max_words,
        )


NEMOTRON_3_NANO_4B_Q4_K_M = ModelCandidate(
    label="nemotron_3_nano_4b_q4_k_m",
    hf_repo_id="nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF",
    gguf_filename="NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf",
    quantization="Q4_K_M",
)

QWEN3_4B_Q4_K_M = ModelCandidate(
    label="qwen3_4b_q4_k_m",
    hf_repo_id="Qwen/Qwen3-4B-GGUF",
    gguf_filename="Qwen3-4B-Q4_K_M.gguf",
    quantization="Q4_K_M",
)

MINICPM41_8B_Q4_K_M = ModelCandidate(
    label="minicpm41_8b_q4_k_m",
    hf_repo_id="openbmb/MiniCPM4.1-8B-GGUF",
    gguf_filename="MiniCPM4.1-8B-Q4_K_M.gguf",
    quantization="Q4_K_M",
)

QWEN3_8B_Q4_K_M = ModelCandidate(
    label="qwen3_8b_q4_k_m",
    hf_repo_id="Qwen/Qwen3-8B-GGUF",
    gguf_filename="Qwen3-8B-Q4_K_M.gguf",
    quantization="Q4_K_M",
)


DEFAULT_MODEL_CANDIDATES: tuple[ModelCandidate, ...] = (NEMOTRON_3_NANO_4B_Q4_K_M,)
COMPARISON_MODEL_CANDIDATES: tuple[ModelCandidate, ...] = (
    NEMOTRON_3_NANO_4B_Q4_K_M,
    QWEN3_4B_Q4_K_M,
    MINICPM41_8B_Q4_K_M,
    QWEN3_8B_Q4_K_M,
)
MODEL_CANDIDATES_BY_LABEL: dict[str, ModelCandidate] = {
    candidate.label: candidate for candidate in COMPARISON_MODEL_CANDIDATES
}


SMOKE_EVAL_CASES: tuple[AgentEvalCase, ...] = (
    AgentEvalCase(
        case_id="worm_needle_facing_call",
        agent_id="worm",
        memory_summary="Player needled Worm after winning a small pot and Worm has been talking faster since.",
        public_state={
            "street": "turn",
            "board_cards": ["Ah", "7d", "7s", "2c"],
            "pot": 140,
            "amount_to_call": 45,
            "stacks": {"player": 310, "worm": 220},
            "recent_actions": ["player bet 45 into 140"],
        },
        private_agent_state={
            "hole_cards": ["Ks", "Qs"],
            "stack": 220,
            "position": "button",
        },
        solver_recommendation=PokerDecision(
            ActionType.FOLD,
            amount=0,
            equity=0.18,
            pot_odds=0.24,
            reason="equity trails pot odds and paired ace board favors the bettor",
        ),
        player_utterance=PlayerUtterance("You always pay me off when you're tilted.", target_agent_id="worm"),
        legal_actions=(ActionType.FOLD, ActionType.CALL, ActionType.RAISE, ActionType.ALL_IN),
        expected_pressure="Tests whether table talk can tempt a volatile agent without breaking legality.",
    ),
    AgentEvalCase(
        case_id="molly_bluff_catcher",
        agent_id="molly_bloom",
        memory_summary="Player has shown one river bluff and one disciplined fold this floor.",
        public_state={
            "street": "river",
            "board_cards": ["Kh", "Jd", "8d", "3s", "2c"],
            "pot": 260,
            "amount_to_call": 80,
            "stacks": {"player": 520, "molly": 430},
            "recent_actions": ["player bet 80 into 260"],
        },
        private_agent_state={
            "hole_cards": ["Kc", "Tc"],
            "stack": 430,
            "position": "field",
        },
        solver_recommendation=PokerDecision(
            ActionType.CALL,
            amount=0,
            equity=0.46,
            pot_odds=0.235,
            reason="top pair has enough showdown value for this price",
        ),
        player_utterance=PlayerUtterance("You know I would not fire river without it.", target_agent_id="molly_bloom"),
        legal_actions=(ActionType.FOLD, ActionType.CALL, ActionType.RAISE, ActionType.ALL_IN),
        expected_pressure="Tests charm/intimidation resistance and honest rationale.",
    ),
    AgentEvalCase(
        case_id="teddy_boss_value_raise",
        agent_id="teddy_kgb",
        memory_summary="Player has repeated the same confident speech pattern before two bluffs.",
        public_state={
            "street": "flop",
            "board_cards": ["Qh", "9h", "4s"],
            "pot": 180,
            "amount_to_call": 0,
            "stacks": {"player": 650, "teddy": 700},
            "recent_actions": ["player checked"],
        },
        private_agent_state={
            "hole_cards": ["Qd", "Qs"],
            "stack": 700,
            "position": "button",
        },
        solver_recommendation=PokerDecision(
            ActionType.BET,
            amount=90,
            equity=0.82,
            pot_odds=0.0,
            reason="monster equity on a wet board should build the pot",
        ),
        player_utterance=PlayerUtterance("Careful. I set traps too.", target_agent_id="teddy_kgb"),
        legal_actions=(ActionType.CHECK, ActionType.BET, ActionType.ALL_IN),
        expected_pressure="Tests boss voice, aggression, and legal bet amount JSON.",
    ),
)

EVAL_CASES_BY_ID: dict[str, AgentEvalCase] = {case.case_id: case for case in SMOKE_EVAL_CASES}


def get_model_candidate(label: str) -> ModelCandidate:
    try:
        return MODEL_CANDIDATES_BY_LABEL[label]
    except KeyError as error:
        known = ", ".join(sorted(MODEL_CANDIDATES_BY_LABEL))
        raise KeyError(f"unknown model candidate {label!r}; known candidates: {known}") from error


def get_eval_case(case_id: str) -> AgentEvalCase:
    try:
        return EVAL_CASES_BY_ID[case_id]
    except KeyError as error:
        known = ", ".join(sorted(EVAL_CASES_BY_ID))
        raise KeyError(f"unknown eval case {case_id!r}; known cases: {known}") from error


def load_candidates_from_json(path: str) -> tuple[ModelCandidate, ...]:
    import json
    from pathlib import Path

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("candidates", [])
    if not isinstance(data, list):
        raise ValueError("candidate JSON must be a list or an object with a candidates list")
    candidates = tuple(ModelCandidate.from_mapping(item) for item in data)
    labels = [candidate.label for candidate in candidates]
    if len(labels) != len(set(labels)):
        raise ValueError("candidate labels must be unique")
    return candidates


__all__ = [
    "AgentEvalCase",
    "COMPARISON_MODEL_CANDIDATES",
    "DEFAULT_MODEL_CANDIDATES",
    "EVAL_CASES_BY_ID",
    "MODEL_CANDIDATES_BY_LABEL",
    "ModelCandidate",
    "MINICPM41_8B_Q4_K_M",
    "NEMOTRON_3_NANO_4B_Q4_K_M",
    "QWEN3_4B_Q4_K_M",
    "QWEN3_8B_Q4_K_M",
    "SMOKE_EVAL_CASES",
    "get_eval_case",
    "get_model_candidate",
    "load_candidates_from_json",
]
