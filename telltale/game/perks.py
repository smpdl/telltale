"""
This module defines the perks that can be used by the player in the game.

Perks are effects that can be applied to the player's game state.
They are triggered by certain events in the game and can have a variety of effects.

The perks defined here are:
- Buy-In Discount: The next floor buy-in is reduced by 15%.
- Continue Waiver: One used continue is waived for buy-in penalty calculations.
- Spotlight Seat: Act last on the first hand of the next floor when permitted.
- Stack Recovery: Recover 20% of the table stack once after an all-in loss.

You can get these perks by winning floors. When you win a floor, you are rewarded with a random perk.

Perks are defined by a trigger timing, which determines when the perk is triggered,
and an effect, which is a function that is called when the perk is triggered.

The perk can be triggered at the following times:
- Next floor buy-in: The perk is triggered when the player buys in for the next floor.
- Continue penalty: The perk is triggered when the player uses a continue.
- Next floor start: The perk is triggered when the player starts the next floor.
- All-in loss: The perk is triggered when the player loses an all-in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class TriggerTiming(str, Enum):
    NEXT_FLOOR_BUY_IN = "next_floor_buy_in"
    CONTINUE_PENALTY = "continue_penalty"
    NEXT_FLOOR_START = "next_floor_start"
    ALL_IN_LOSS = "all_in_loss"


@dataclass(frozen=True)
class PerkEffectContext:
    amount: int = 0
    continues: int = 0
    table_stack: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PerkEffectResult:
    amount: int | None = None
    continues: int | None = None
    recovered_stack: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    consumed: bool = False

# define a type alias for the effect function
EffectFunction = Callable[[PerkEffectContext], PerkEffectResult] 

@dataclass(frozen=True)
class PerkDefinition:
    perk_id: str
    name: str
    description: str
    trigger_timing: TriggerTiming
    effect: EffectFunction
    max_uses: int | None = None
    active_duration_floors: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def serialize(self) -> dict[str, Any]:
        return {
            "perk_id": self.perk_id,
            "name": self.name,
            "description": self.description,
            "trigger_timing": self.trigger_timing.value,
            "max_uses": self.max_uses,
            "active_duration_floors": self.active_duration_floors,
            "metadata": dict(self.metadata),
        }


@dataclass
class ActivePerk:
    perk_id: str
    remaining_uses: int | None = None
    remaining_floors: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_definition(cls, definition: PerkDefinition) -> "ActivePerk":
        return cls(
            perk_id=definition.perk_id,
            remaining_uses=definition.max_uses,
            remaining_floors=definition.active_duration_floors,
            metadata=dict(definition.metadata),
        )

    def serialize(self) -> dict[str, Any]:
        definition = get_perk(self.perk_id)
        return definition.serialize() | {
            "remaining_uses": self.remaining_uses,
            "remaining_floors": self.remaining_floors,
            "metadata": dict(self.metadata),
        }


def _buy_in_discount_effect(context: PerkEffectContext) -> PerkEffectResult:
    return PerkEffectResult(amount=max(0, round(context.amount * 0.85)), consumed=True)


def _continue_waiver_effect(context: PerkEffectContext) -> PerkEffectResult:
    return PerkEffectResult(continues=max(0, context.continues - 1))


def _spotlight_seat_effect(context: PerkEffectContext) -> PerkEffectResult:
    return PerkEffectResult(metadata={"player_acts_last_first_hand": True}, consumed=True)


def _stack_recovery_effect(context: PerkEffectContext) -> PerkEffectResult:
    return PerkEffectResult(recovered_stack=max(0, context.table_stack // 5), consumed=True)


PERK_DEFINITIONS: tuple[PerkDefinition, ...] = (
    PerkDefinition(
        perk_id="buy_in_discount",
        name="Buy-In Discount",
        description="Next floor buy-in reduced by 15%.",
        trigger_timing=TriggerTiming.NEXT_FLOOR_BUY_IN,
        effect=_buy_in_discount_effect,
        max_uses=1,
    ),
    PerkDefinition(
        perk_id="continue_waiver",
        name="Continue Waiver",
        description="One used continue is waived for buy-in penalty calculations.",
        trigger_timing=TriggerTiming.CONTINUE_PENALTY,
        effect=_continue_waiver_effect, 
        # there is no max uses for this perk because it is only used once per continue
        # and it is only triggered when the player uses a continue
        # so it is not possible to use it more than once
    ),
    PerkDefinition(
        perk_id="spotlight_seat",
        name="Spotlight Seat",
        description="Act last on the first hand of the next floor when permitted.",
        trigger_timing=TriggerTiming.NEXT_FLOOR_START,
        effect=_spotlight_seat_effect,
        max_uses=1,
    ),
    PerkDefinition(
        perk_id="stack_recovery",
        name="Stack Recovery",
        description="Recover 20% of your table stack once after an all-in loss.",
        trigger_timing=TriggerTiming.ALL_IN_LOSS,
        effect=_stack_recovery_effect,
        max_uses=1,
    ),
)

def get_perk(perk_id: str) -> PerkDefinition:
    for perk in PERK_DEFINITIONS:
        if perk.perk_id == perk_id:
            return perk
    raise ValueError(f"unknown perk id: {perk_id}")


def apply_buy_in_discount(amount: int) -> int:
    return _buy_in_discount_effect(PerkEffectContext(amount=amount)).amount or 0


def apply_continue_waiver(continues: int) -> int:
    result = _continue_waiver_effect(PerkEffectContext(continues=continues))
    return result.continues if result.continues is not None else continues

def trigger_stack_recovery(table_stack: int, already_used: bool = False) -> tuple[int, bool]:
    if already_used:
        return 0, True
    result = _stack_recovery_effect(PerkEffectContext(table_stack=table_stack))
    return result.recovered_stack, result.consumed
