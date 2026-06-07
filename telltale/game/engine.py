from __future__ import annotations

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
