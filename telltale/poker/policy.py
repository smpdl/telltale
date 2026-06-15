from __future__ import annotations

from dataclasses import dataclass

from telltale.game.holdem import ActionType, HandState, PlayerState
from telltale.poker import native


RANK_ORDER = "23456789TJQKA"


@dataclass(frozen=True)
class PokerPolicyConfig:
    simulations: int = 1_500


@dataclass(frozen=True)
class PokerDecision:
    action: ActionType
    amount: int = 0
    equity: float = 0.0
    pot_odds: float = 0.0
    reason: str = ""


class PokerPolicyWriter:
    """Writes solver equity into legal Hold'em actions."""

    def __init__(
        self,
        solver: native.NativePokerSolver | None = None,
        config: PokerPolicyConfig | None = None,
    ):
        self.solver = solver or native.NativePokerSolver()
        self.config = config or PokerPolicyConfig()

    def choose_action(
        self,
        hand: HandState,
        player_id: str | None = None,
        seed: int | str | bytes | None = None,
    ) -> PokerDecision:
        player = _actor_or_player(hand, player_id)
        legal = hand.legal_actions(player.player_id)
        if not legal:
            return PokerDecision(ActionType.CHECK, reason="no legal betting action")

        opponent_count = _active_opponent_count(hand, player)
        result = self.solver.estimate_equity(
            player.hole_cards,
            hand.board_cards,
            num_opponents=opponent_count,
            iterations=self.config.simulations,
            seed=seed,
        )
        pot_odds = _pot_odds(hand, player)
        outstanding = hand.current_max_bet() - player.current_bet
        features = native.DecisionFeatures(
            street=hand.street.value,
            hero_equity=result.equity,
            pot_size=sum(hand.pot_contributions.values()),
            amount_to_call=outstanding,
            pot_odds=pot_odds,
            stack_to_pot_ratio=_stack_to_pot_ratio(hand, player),
            players_remaining=opponent_count + 1,
            can_check=ActionType.CHECK in legal,
            legal_actions=tuple(sorted(action.value for action in legal)),
            hero_stack=player.stack,
            minimum_raise_amount=hand.minimum_raise_amount,
            board_texture=board_texture(hand),
            street_action_count=_street_action_count(hand),
            previous_aggression_count=_previous_aggression_count(hand),
        )
        recommendation = native.recommend_action(features)
        chosen = ActionType(recommendation.suggested_action)

        if chosen in {ActionType.BET, ActionType.RAISE}:
            amount = _legal_bet_or_raise_amount(hand, player, chosen, recommendation.suggested_amount)
        elif chosen == ActionType.ALL_IN:
            amount = player.stack
        else:
            amount = 0
        return PokerDecision(
            chosen,
            amount=amount,
            equity=result.equity,
            pot_odds=pot_odds,
            reason=recommendation.explanation,
        )

    def apply_action(
        self,
        hand: HandState,
        player_id: str | None = None,
        seed: int | str | bytes | None = None,
    ) -> PokerDecision:
        decision = self.choose_action(hand, player_id=player_id, seed=seed)
        hand.apply_action(decision.action, amount=decision.amount, player_id=player_id)
        return decision


def _actor_or_player(hand: HandState, player_id: str | None) -> PlayerState:
    if player_id is None:
        if hand.current_actor_index is None:
            raise ValueError("there is no current actor")
        return hand.players[hand.current_actor_index]
    for player in hand.players:
        if player.player_id == player_id:
            return player
    raise ValueError(f"unknown player id: {player_id}")


def _active_opponent_count(hand: HandState, player: PlayerState) -> int:
    opponents = 0
    for other in hand.players:
        if other.player_id != player.player_id and not other.has_folded:
            opponents += 1
    return max(1, opponents)


def _pot_odds(hand: HandState, player: PlayerState) -> float:
    outstanding = hand.current_max_bet() - player.current_bet
    if outstanding <= 0:
        return 0.0
    pot = sum(hand.pot_contributions.values())
    return outstanding / (pot + outstanding)


def _legal_bet_or_raise_amount(
    hand: HandState,
    player: PlayerState,
    action: ActionType,
    suggested_amount: int,
) -> int:
    if action == ActionType.BET:
        return min(player.stack, max(hand.minimum_raise_amount, suggested_amount))
    if action == ActionType.RAISE:
        outstanding = hand.current_max_bet() - player.current_bet
        minimum_amount = outstanding + hand.minimum_raise_amount
        return min(player.stack, max(minimum_amount, suggested_amount))
    return 0


def _stack_to_pot_ratio(hand: HandState, player: PlayerState) -> float:
    pot = sum(hand.pot_contributions.values())
    if pot <= 0:
        return float(player.stack)
    return player.stack / pot


def board_texture(hand: HandState) -> str:
    board = hand.board_cards
    if len(board) < 3:
        return "dry"

    ranks = [_rank_value(card.rank) for card in board]
    suits = [card.suit for card in board]
    unique_suits = set(suits)
    paired = len(set(ranks)) < len(ranks)
    monotone = len(unique_suits) == 1
    two_tone = len(unique_suits) == 2
    connected = _is_connected(ranks)

    if monotone:
        return "monotone"
    if connected and (two_tone or paired):
        return "wet"
    if connected:
        return "connected"
    if paired:
        return "paired"
    if two_tone:
        return "two_tone"
    return "dry"


def _rank_value(rank: str) -> int:
    return RANK_ORDER.index(rank) + 2


def _is_connected(ranks: list[int]) -> bool:
    unique = sorted(set(ranks))
    if len(unique) < 3:
        return False
    for window_start in range(len(unique) - 2):
        window = unique[window_start : window_start + 3]
        if window[-1] - window[0] <= 4:
            return True
    if 14 in unique:
        wheel = sorted({1 if rank == 14 else rank for rank in unique})
        for window_start in range(len(wheel) - 2):
            window = wheel[window_start : window_start + 3]
            if window[-1] - window[0] <= 4:
                return True
    return False


def _street_action_count(hand: HandState) -> int:
    return sum(1 for record in hand.action_history if record.street == hand.street)


def _previous_aggression_count(hand: HandState) -> int:
    return sum(
        1
        for record in hand.action_history
        if record.action in {ActionType.BET, ActionType.RAISE, ActionType.ALL_IN}
    )
