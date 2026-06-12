"""
"""


from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from random import Random
from uuid import uuid5, NAMESPACE_URL

from telltale.game.floors import FloorConfig, get_floor_config
from telltale.game.holdem import HandState
from telltale.game.perks import ActivePerk, PERK_DEFINITIONS, PerkEffectContext, TriggerTiming, get_perk


STARTING_BANKROLL = 250
MAX_CONTINUES = 2


class RunStatus(str, Enum):
    ACTIVE = "active"
    WON = "won"
    LOST = "lost"


@dataclass
class TableState:
    """
    Represents the state of the table for a given floor. 
    A table is created when a player enters a floor and is destroyed when the floor is won or lost.
    """
    floor_number: int
    seed: str
    player_stack: int # number of chips the player has available to bet
    opponent_stacks: list[int]
    small_blind: int
    big_blind: int
    hand_index: int = 0 # index of the current hand being played
    pending_metadata: dict = field(default_factory=dict)

    def serialize(self) -> dict:
        return {
            "floor_number": self.floor_number,
            "seed": self.seed,
            "player_stack": self.player_stack,
            "opponent_stacks": list(self.opponent_stacks),
            "small_blind": self.small_blind,
            "big_blind": self.big_blind,
            "hand_index": self.hand_index,
            "pending_metadata": dict(self.pending_metadata),
        }


@dataclass
class RunState:
    """
    A run is a sequence of floors that a player plays.
    Losing a floor ends the run unless the player uses a continue.
    Winning a floor advances to the next floor and rewards the player with perks.
    RunState manages the state of the run and provides methods to interact with the game.
    """
    run_id: str
    seed: str
    floor_index: int # index of the current floor being played
    # bankroll is the number of chips the player has available to bet. 
    bankroll: int 
    # continues track how many times the player has bailed out to keep the run alive.
    # each continue increases the cost of the next floor's buy-in.
    # the player starts with 0 continues and can use up to MAX_CONTINUES per run.
    continues: int = 0
    # perks are special abilities that can be used to gain an advantage over the house. 
    # the player starts with no active perks and can earn them by winning floors. 
    active_perks: list[ActivePerk] = field(default_factory=list)
    completed_floors: list[int] = field(default_factory=list)
    status: RunStatus = RunStatus.ACTIVE
    current_hand: HandState | None = None
    current_table: TableState | None = None
    event_log: list[dict] = field(default_factory=list)
    available_rewards: list[str] = field(default_factory=list)
    awaiting_reward: bool = False

    @classmethod
    def start(cls, seed: int | str | bytes | None = None, bankroll: int = STARTING_BANKROLL) -> "RunState":
        normalized_seed = _normalize_seed(seed)
        run = cls(
            run_id=str(uuid5(NAMESPACE_URL, f"telltale-run:{normalized_seed}")),
            seed=normalized_seed,
            floor_index=0,
            bankroll=bankroll,
        )
        run._log("run_started", bankroll=bankroll)
        return run

    @property
    def current_floor(self) -> FloorConfig:
        return get_floor_config(self.floor_index)

    def floor_seed(self, floor_index: int | None = None) -> str:
        index = self.floor_index if floor_index is None else floor_index
        return derive_seed(self.seed, "floor", index)

    def hand_seed(self, floor_index: int | None = None, hand_index: int = 0) -> str:
        index = self.floor_index if floor_index is None else floor_index
        return derive_seed(self.seed, "hand", index, hand_index)

    def buy_in_for_floor(self, floor: FloorConfig | None = None) -> int:
        """
        Calculates the buy-in for the current floor. The buy-in is the amount of chips the player must pay to enter the floor.
        The buy-in is affected by the player's continues and active perks.
        - If the player has 1 continue, the buy-in is increased by 15%.
        - If the player has 2 or more continues, the buy-in is increased by 30%.
        - If the player has the Buy-In Discount perk, the buy-in is reduced by 15%.
        - If the player has the Continue Waiver perk, one of the used continues is waived for buy-in penalty calculations, which will 
        reduce the buy-in by the amount of the waived continue.
        """
        floor = self.current_floor if floor is None else floor
        amount = floor.buy_in
        effective_continues = self.effective_continues()
        if effective_continues == 1:
            amount = round(amount * 1.15)
        elif effective_continues >= 2:
            amount = round(amount * 1.30)

        for perk in list(self.active_perks):
            definition = get_perk(perk.perk_id)
            if definition.trigger_timing != TriggerTiming.NEXT_FLOOR_BUY_IN:
                continue
            result = definition.effect(PerkEffectContext(amount=amount))
            if result.amount is not None:
                amount = result.amount
        return max(0, amount)

    def effective_continues(self) -> int:
        count = self.continues
        for perk in self.active_perks:
            definition = get_perk(perk.perk_id)
            if definition.trigger_timing == TriggerTiming.CONTINUE_PENALTY:
                result = definition.effect(PerkEffectContext(continues=count))
                if result.continues is not None:
                    count = result.continues
        return max(0, count)

    def enter_current_floor(self, use_continue: bool = True) -> bool:
        if self.status != RunStatus.ACTIVE:
            return False
        if self.awaiting_reward:
            raise ValueError("choose a reward before entering the next floor")
        if self.current_table is not None:
            return True

        floor = self.current_floor
        buy_in = self.buy_in_for_floor(floor)
        if self.bankroll < buy_in:
            if not self._use_continue_if_allowed(buy_in, use_continue):
                self.status = RunStatus.LOST
                self._log("run_lost", reason="insufficient_bankroll", floor_number=floor.floor_number)
                return False

        self.bankroll -= buy_in
        if self.bankroll < 0:
            raise ValueError("bankroll cannot be negative")
        self._consume_perks(TriggerTiming.NEXT_FLOOR_BUY_IN)
        self.current_table = self._create_table(floor)
        self._log("floor_entered", floor_number=floor.floor_number, buy_in=buy_in, bankroll=self.bankroll)
        return True

    def win_current_floor(self, ending_stack: int | None = None) -> None:
        if self.current_table is None:
            self.enter_current_floor()
        if self.current_table is None or self.status != RunStatus.ACTIVE:
            return
        floor = self.current_floor
        stack = self.current_table.player_stack if ending_stack is None else ending_stack
        stack = max(0, stack)
        self.bankroll += stack
        self.completed_floors.append(floor.floor_number)
        self.current_table = None
        self.current_hand = None
        self._log("floor_won", floor_number=floor.floor_number, returned_stack=stack, bankroll=self.bankroll)

        if floor.is_boss:
            self.status = RunStatus.WON
            self.available_rewards = []
            self.awaiting_reward = False
            self._log("run_won")
            return

        self.available_rewards = self._reward_choices(floor)
        self.awaiting_reward = True

    def lose_current_floor(self, all_in_loss: bool = False) -> None:
        if self.current_table is None:
            return
        floor = self.current_floor
        recovered = 0
        if all_in_loss:
            recovered = self._trigger_insurance(self.current_table.player_stack)
            self.bankroll += recovered
        self.current_table = None
        self.current_hand = None
        self._log("floor_lost", floor_number=floor.floor_number, recovered_stack=recovered, bankroll=self.bankroll)
        if floor.is_boss:
            self.status = RunStatus.LOST
            self._log("run_lost", reason="boss_floor_loss")
            return
        if not self._use_continue_if_allowed(self.current_floor.buy_in, use_continue=True):
            self.status = RunStatus.LOST
            self._log("run_lost", reason="max_continues")

    def choose_reward(self, perk_id: str) -> None:
        if not self.awaiting_reward:
            raise ValueError("there is no reward to choose")
        if perk_id not in self.available_rewards:
            raise ValueError(f"{perk_id} is not an available reward")
        definition = get_perk(perk_id)
        self.active_perks.append(ActivePerk.from_definition(definition))
        self.available_rewards = []
        self.awaiting_reward = False
        self.floor_index += 1
        self._log("reward_chosen", perk_id=perk_id)

    def serialize_public(self) -> dict:
        return {
            "run_id": self.run_id,
            "seed": self.seed,
            "floor_index": self.floor_index,
            "floor_number": self.current_floor.floor_number if self.status == RunStatus.ACTIVE else None,
            "bankroll": self.bankroll,
            "continues": self.continues,
            "active_perks": [perk.serialize() for perk in self.active_perks],
            "completed_floors": list(self.completed_floors),
            "status": self.status.value,
            "current_table": self.current_table.serialize() if self.current_table else None,
            "available_rewards": list(self.available_rewards),
            "awaiting_reward": self.awaiting_reward,
            "event_log": list(self.event_log),
        }

    def _create_table(self, floor: FloorConfig) -> TableState:
        rng = Random(self.floor_seed())
        opponent_count = rng.randint(floor.opponent_count_min, floor.opponent_count_max)
        opponent_stacks = [floor.player_starting_stack for _ in range(opponent_count)]
        metadata = self._apply_floor_start_perks()
        return TableState(
            floor_number=floor.floor_number,
            seed=self.floor_seed(),
            player_stack=floor.player_starting_stack,
            opponent_stacks=opponent_stacks,
            small_blind=floor.blinds.small_blind,
            big_blind=floor.blinds.big_blind,
            pending_metadata=metadata,
        )

    def _reward_choices(self, floor: FloorConfig) -> list[str]:
        count = floor.reward_choices_count
        if self.effective_continues() >= 2:
            count = max(1, count - 1)
        rng = Random(derive_seed(self.seed, "reward", floor.floor_number))
        available = [perk.perk_id for perk in PERK_DEFINITIONS]
        rng.shuffle(available)
        return available[:count]

    def _use_continue_if_allowed(self, needed_bankroll: int, use_continue: bool) -> bool:
        floor = self.current_floor
        if not use_continue or floor.is_boss or self.continues >= MAX_CONTINUES:
            return False
        self.continues += 1
        if self.bankroll < needed_bankroll:
            self.bankroll = needed_bankroll
        self._log("continue_used", continues=self.continues, bankroll=self.bankroll)
        return True

    def _consume_perks(self, timing: TriggerTiming) -> None:
        kept: list[ActivePerk] = []
        for perk in self.active_perks:
            definition = get_perk(perk.perk_id)
            if definition.trigger_timing == timing and perk.remaining_uses is not None:
                perk.remaining_uses -= 1
            if perk.remaining_uses is None or perk.remaining_uses > 0:
                kept.append(perk)
        self.active_perks = kept

    def _apply_floor_start_perks(self) -> dict:
        metadata: dict = {}
        kept: list[ActivePerk] = []
        for perk in self.active_perks:
            definition = get_perk(perk.perk_id)
            if definition.trigger_timing == TriggerTiming.NEXT_FLOOR_START:
                result = definition.effect(PerkEffectContext(metadata=perk.metadata))
                metadata.update(result.metadata)
                if perk.remaining_uses is not None:
                    perk.remaining_uses -= 1
            if perk.remaining_uses is None or perk.remaining_uses > 0:
                kept.append(perk)
        self.active_perks = kept
        return metadata

    def _trigger_insurance(self, table_stack: int) -> int:
        kept: list[ActivePerk] = []
        recovered = 0
        for perk in self.active_perks:
            definition = get_perk(perk.perk_id)
            if definition.trigger_timing == TriggerTiming.ALL_IN_LOSS and recovered == 0:
                result = definition.effect(PerkEffectContext(table_stack=table_stack))
                recovered = result.recovered_stack
                if perk.remaining_uses is not None:
                    perk.remaining_uses -= 1
            if perk.remaining_uses is None or perk.remaining_uses > 0:
                kept.append(perk)
        self.active_perks = kept
        return recovered

    def _log(self, event: str, **payload: object) -> None:
        self.event_log.append({"event": event, **payload})


def derive_seed(run_seed: str, *parts: object) -> str:
    payload = ":".join([run_seed, *(str(part) for part in parts)])
    return sha256(payload.encode("utf-8")).hexdigest()[:16]


def _normalize_seed(seed: int | str | bytes | None) -> str:
    if seed is None:
        return "default"
    if isinstance(seed, bytes):
        return seed.hex()
    return str(seed)
