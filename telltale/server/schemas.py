from __future__ import annotations

from pydantic import BaseModel, Field

from telltale.game.economy import RunStatus
from telltale.game.holdem import ActionType, Street


class ActionRequest(BaseModel):
    player_id: str
    action: ActionType
    amount: int = Field(default=0, ge=0)
    table_talk: "PlayerUtteranceRequest | None" = None


class PlayerUtteranceRequest(BaseModel):
    raw_text: str = ""
    target_agent_id: str | None = None


class AgentMemoryUpdateSchema(BaseModel):
    respect_for_player: float | None = None
    fear_of_player: float | None = None
    charmed_by_player: float | None = None
    grudge_against_player: float | None = None
    recent_player_patterns: list[str] = Field(default_factory=list)
    recent_dialogue_impressions: list[str] = Field(default_factory=list)
    summary: str | None = None


class AgentDecisionSchema(BaseModel):
    action: ActionType
    amount: int = Field(default=0, ge=0)
    speech: str
    honest_rationale: str
    emotional_state: str
    memory_delta: AgentMemoryUpdateSchema = Field(default_factory=AgentMemoryUpdateSchema)
    source: str = "model"


class PlayerPublicState(BaseModel):
    player_id: str
    name: str
    seat_index: int
    stack: int
    hole_cards: list[str]
    current_bet: int
    has_folded: bool
    is_all_in: bool
    is_human: bool


class HandPublicState(BaseModel):
    hand_id: str
    street: Street
    board_cards: list[str]
    players: list[PlayerPublicState]
    pot_contributions: dict[str, int]
    current_actor_index: int | None
    legal_actions: list[ActionType]
    action_history: list[dict]


class PerkPublicState(BaseModel):
    perk_id: str
    name: str
    description: str
    trigger_timing: str
    remaining_uses: int | None = None
    remaining_floors: int | None = None
    metadata: dict = Field(default_factory=dict)


class TablePublicState(BaseModel):
    floor_number: int
    seed: str
    player_stack: int
    opponent_stacks: list[int]
    small_blind: int
    big_blind: int
    hand_index: int
    pending_metadata: dict = Field(default_factory=dict)


class RunPublicState(BaseModel):
    run_id: str
    seed: str
    floor_index: int
    floor_number: int | None
    bankroll: int
    continues: int
    active_perks: list[PerkPublicState]
    completed_floors: list[int]
    status: RunStatus
    current_table: TablePublicState | None
    available_rewards: list[str]
    awaiting_reward: bool
    event_log: list[dict]
