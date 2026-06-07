from __future__ import annotations

from pydantic import BaseModel, Field

from telltale.game.holdem import ActionType, Street


class ActionRequest(BaseModel):
    player_id: str
    action: ActionType
    amount: int = Field(default=0, ge=0)


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
