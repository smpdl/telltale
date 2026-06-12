from __future__ import annotations

from telltale.game.economy import RunState
from telltale.game.holdem import ActionType, HandState, PlayerState


class HoldemEngine:
    def start_hand(
        self,
        players: list[PlayerState],
        seed: int | str | bytes | None = None,
        dealer_button_index: int = 0,
        small_blind: int = 5,
        big_blind: int = 10,
    ) -> HandState:
        return HandState.start(
            players=players,
            seed=seed,
            dealer_button_index=dealer_button_index,
            small_blind=small_blind,
            big_blind=big_blind,
        )

    def legal_actions(self, hand: HandState, player_id: str | None = None) -> set[ActionType]:
        return hand.legal_actions(player_id)

    def apply_action(
        self,
        hand: HandState,
        action: ActionType | str,
        amount: int = 0,
        player_id: str | None = None,
    ) -> HandState:
        hand.apply_action(action, amount=amount, player_id=player_id)
        return hand

    def start_run(self, seed: int | str | bytes | None = None, bankroll: int = 250) -> RunState:
        return RunState.start(seed=seed, bankroll=bankroll)

    def enter_floor(self, run: RunState, use_continue: bool = True) -> RunState:
        run.enter_current_floor(use_continue=use_continue)
        return run

    def win_floor(self, run: RunState, ending_stack: int | None = None) -> RunState:
        run.win_current_floor(ending_stack=ending_stack)
        return run

    def lose_floor(self, run: RunState, all_in_loss: bool = False) -> RunState:
        run.lose_current_floor(all_in_loss=all_in_loss)
        return run

    def choose_reward(self, run: RunState, perk_id: str) -> RunState:
        run.choose_reward(perk_id)
        return run
