from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from itertools import combinations
from uuid import uuid4

from telltale.game.cards import Card, Deck


class PokerError(ValueError):
    """Raised when a poker action or state transition is invalid."""


class Street(str, Enum):
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"
    COMPLETE = "complete"


class ActionType(str, Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all_in"


@dataclass
class PlayerState:
    player_id: str
    name: str
    seat_index: int
    stack: int
    hole_cards: list[Card] = field(default_factory=list)
    current_bet: int = 0
    has_folded: bool = False
    is_all_in: bool = False
    is_human: bool = False


@dataclass(frozen=True)
class ActionRecord:
    player_id: str
    action: ActionType
    amount: int
    street: Street


@dataclass(frozen=True)
class Pot:
    amount: int
    eligible_player_ids: tuple[str, ...]


@dataclass
class HandState:
    hand_id: str
    deck: Deck
    players: list[PlayerState]
    dealer_button_index: int
    small_blind_index: int
    big_blind_index: int
    current_actor_index: int | None
    street: Street = Street.PREFLOP
    board_cards: list[Card] = field(default_factory=list)
    pot_contributions: dict[str, int] = field(default_factory=dict)
    minimum_call_amount: int = 0
    minimum_raise_amount: int = 0
    action_history: list[ActionRecord] = field(default_factory=list)
    street_acted_player_ids: set[str] = field(default_factory=set)

    @classmethod
    def start(
        cls,
        players: list[PlayerState],
        seed: int | str | bytes | None = None,
        dealer_button_index: int = 0,
        small_blind: int = 5,
        big_blind: int = 10,
        hand_id: str | None = None,
    ) -> "HandState":
        if len(players) < 2:
            raise PokerError("at least two players are required")
        if small_blind < 0 or big_blind <= 0:
            raise PokerError("blind amounts must be positive")

        ordered = sorted(players, key=lambda player: player.seat_index)
        deck = Deck.shuffled(seed)
        dealer_pos = dealer_button_index % len(ordered)
        small_blind_pos = _next_seat(ordered, dealer_pos)
        big_blind_pos = _next_seat(ordered, small_blind_pos)
        hand = cls(
            hand_id=hand_id or str(uuid4()),
            deck=deck,
            players=ordered,
            dealer_button_index=dealer_pos,
            small_blind_index=small_blind_pos,
            big_blind_index=big_blind_pos,
            current_actor_index=_next_seat(ordered, big_blind_pos),
            pot_contributions={player.player_id: 0 for player in ordered},
            minimum_raise_amount=big_blind,
        )
        for _ in range(2):
            for player in ordered:
                player.hole_cards.append(deck.draw())
        hand._post_blind(small_blind_pos, small_blind)
        hand._post_blind(big_blind_pos, big_blind)
        hand.minimum_call_amount = hand.current_max_bet()
        hand._skip_unavailable_actor()
        return hand

    def legal_actions(self, player_id: str | None = None) -> set[ActionType]:
        player = self._actor_or_player(player_id)
        if self.street == Street.COMPLETE:
            return set()
        if player.has_folded or player.is_all_in or player.stack <= 0:
            return set()

        outstanding = self.current_max_bet() - player.current_bet
        actions = {ActionType.ALL_IN}
        if outstanding == 0:
            actions.add(ActionType.CHECK)
            if self.current_max_bet() == 0:
                actions.add(ActionType.BET)
        else:
            actions.update({ActionType.FOLD, ActionType.CALL})
            if player.stack > outstanding:
                actions.add(ActionType.RAISE)
        return actions

    def apply_action(self, action: ActionType | str, amount: int = 0, player_id: str | None = None) -> None:
        if self.street == Street.COMPLETE:
            raise PokerError("hand is already complete")
        player = self._actor_or_player(player_id)
        if player_id is not None and self.current_actor_index is not None:
            actor = self.players[self.current_actor_index]
            if actor.player_id != player_id:
                raise PokerError(f"it is {actor.player_id}'s turn, not {player_id}")

        action_type = ActionType(action)
        self._validate_action(player, action_type, amount)
        paid = self._apply_payment(player, action_type, amount)
        self.action_history.append(ActionRecord(player.player_id, action_type, paid, self.street))
        self.street_acted_player_ids.add(player.player_id)

        if action_type in {ActionType.BET, ActionType.RAISE} or (
            action_type == ActionType.ALL_IN and player.current_bet > self.minimum_call_amount
        ):
            previous_call = self.minimum_call_amount
            self.minimum_call_amount = self.current_max_bet()
            raise_size = self.minimum_call_amount - previous_call
            if raise_size >= self.minimum_raise_amount:
                self.minimum_raise_amount = raise_size
                self.street_acted_player_ids = {player.player_id}

        self._settle_or_advance()

    def to_private_state(self) -> dict:
        return {
            "hand_id": self.hand_id,
            "street": self.street.value,
            "deck": self.deck.to_strings(),
            "board_cards": [str(card) for card in self.board_cards],
            "players": [self._serialize_player(player, reveal_hole_cards=True) for player in self.players],
            "pot_contributions": dict(self.pot_contributions),
            "current_actor_index": self.current_actor_index,
            "action_history": [record.__dict__ | {"action": record.action.value, "street": record.street.value} for record in self.action_history],
        }

    def to_public_state(self, viewer_player_id: str) -> dict:
        showdown_visible = self.street in {Street.SHOWDOWN, Street.COMPLETE}
        return {
            "hand_id": self.hand_id,
            "street": self.street.value,
            "board_cards": [str(card) for card in self.board_cards],
            "players": [
                self._serialize_player(
                    player,
                    reveal_hole_cards=showdown_visible or player.player_id == viewer_player_id,
                )
                for player in self.players
            ],
            "pot_contributions": dict(self.pot_contributions),
            "current_actor_index": self.current_actor_index,
            "legal_actions": [action.value for action in sorted(self.legal_actions(viewer_player_id), key=lambda item: item.value)],
            "action_history": [record.__dict__ | {"action": record.action.value, "street": record.street.value} for record in self.action_history],
        }

    def _validate_action(self, player: PlayerState, action: ActionType, amount: int) -> None:
        if player.has_folded:
            raise PokerError("folded players cannot act")
        if player.is_all_in:
            raise PokerError("all-in players cannot act")
        if player.stack <= 0:
            raise PokerError("players with no chips cannot act")
        if action not in self.legal_actions(player.player_id):
            raise PokerError(f"{action.value} is not legal for player {player.player_id}")
        if amount < 0:
            raise PokerError("action amount cannot be negative")

        outstanding = self.current_max_bet() - player.current_bet
        if action == ActionType.BET:
            if amount <= 0:
                raise PokerError("bet amount must be positive")
            if amount > player.stack:
                raise PokerError("bet amount exceeds stack")
            if amount < self.minimum_raise_amount and amount < player.stack:
                raise PokerError("bet amount is below the minimum bet")
        elif action == ActionType.RAISE:
            target = player.current_bet + amount
            minimum_target = self.current_max_bet() + self.minimum_raise_amount
            if amount <= outstanding:
                raise PokerError("raise amount must exceed the call amount")
            if amount > player.stack:
                raise PokerError("raise amount exceeds stack")
            if target < minimum_target and amount < player.stack:
                raise PokerError("raise amount is below the minimum raise")

    def _apply_payment(self, player: PlayerState, action: ActionType, amount: int) -> int:
        paid = 0
        if action == ActionType.FOLD:
            player.has_folded = True
        elif action == ActionType.CHECK:
            paid = 0
        elif action == ActionType.CALL:
            paid = self._pay(player, min(player.stack, self.current_max_bet() - player.current_bet))
        elif action in {ActionType.BET, ActionType.RAISE}:
            paid = self._pay(player, amount)
        elif action == ActionType.ALL_IN:
            paid = self._pay(player, player.stack)
        return paid

    def _pay(self, player: PlayerState, amount: int) -> int:
        paid = min(amount, player.stack)
        player.stack -= paid
        player.current_bet += paid
        self.pot_contributions[player.player_id] += paid
        if player.stack == 0:
            player.is_all_in = True
        return paid

    def _post_blind(self, player_index: int, amount: int) -> None:
        player = self.players[player_index]
        self._pay(player, amount)

    def _settle_or_advance(self) -> None:
        active = [player for player in self.players if not player.has_folded]
        if len(active) == 1:
            self._award_uncontested(active[0])
            return

        if self._all_remaining_all_in():
            self._deal_remaining_board()
            self._showdown()
            return

        if self._street_is_complete():
            self._advance_street()
        else:
            self.current_actor_index = self._next_actionable_index(self.current_actor_index)

    def _advance_street(self) -> None:
        for player in self.players:
            player.current_bet = 0
        self.street_acted_player_ids.clear()
        self.minimum_call_amount = 0

        if self.street == Street.PREFLOP:
            self.street = Street.FLOP
            self._burn()
            self.board_cards.extend(self.deck.draw(3))
        elif self.street == Street.FLOP:
            self.street = Street.TURN
            self._burn()
            self.board_cards.append(self.deck.draw())
        elif self.street == Street.TURN:
            self.street = Street.RIVER
            self._burn()
            self.board_cards.append(self.deck.draw())
        elif self.street == Street.RIVER:
            self._showdown()
            return

        self.current_actor_index = self._next_actionable_index(self.dealer_button_index)
        if self.current_actor_index is None:
            self._deal_remaining_board()
            self._showdown()

    def _showdown(self) -> None:
        self.street = Street.SHOWDOWN
        for pot in build_side_pots(self.pot_contributions, self.players):
            winners = self._best_players(pot.eligible_player_ids)
            share, remainder = divmod(pot.amount, len(winners))
            for player in winners:
                player.stack += share
            for player in self._clockwise_players_from_dealer(winners)[:remainder]:
                player.stack += 1
        self.street = Street.COMPLETE
        self.current_actor_index = None

    def _best_players(self, eligible_player_ids: tuple[str, ...]) -> list[PlayerState]:
        eligible = [self._player_by_id(player_id) for player_id in eligible_player_ids]
        rankings = {player.player_id: evaluate_holdem(player.hole_cards + self.board_cards) for player in eligible}
        best = max(rankings.values())
        return [player for player in eligible if rankings[player.player_id] == best]

    def _award_uncontested(self, winner: PlayerState) -> None:
        winner.stack += sum(self.pot_contributions.values())
        self.street = Street.COMPLETE
        self.current_actor_index = None

    def _deal_remaining_board(self) -> None:
        while len(self.board_cards) < 5:
            self._burn()
            draw_count = 3 if len(self.board_cards) == 0 else 1
            drawn = self.deck.draw(draw_count)
            self.board_cards.extend(drawn if isinstance(drawn, list) else [drawn])

    def _street_is_complete(self) -> bool:
        actionable = [player for player in self.players if not player.has_folded and not player.is_all_in]
        if len(actionable) <= 1:
            return True
        max_bet = self.current_max_bet()
        return all(player.current_bet == max_bet and player.player_id in self.street_acted_player_ids for player in actionable)

    def _all_remaining_all_in(self) -> bool:
        active = [player for player in self.players if not player.has_folded]
        return len(active) > 1 and all(player.is_all_in for player in active)

    def _next_actionable_index(self, start_index: int | None) -> int | None:
        if start_index is None:
            return None
        for offset in range(1, len(self.players) + 1):
            index = (start_index + offset) % len(self.players)
            player = self.players[index]
            if not player.has_folded and not player.is_all_in and player.stack > 0:
                return index
        return None

    def _skip_unavailable_actor(self) -> None:
        if self.current_actor_index is None:
            return
        actor = self.players[self.current_actor_index]
        if actor.has_folded or actor.is_all_in or actor.stack <= 0:
            self.current_actor_index = self._next_actionable_index(self.current_actor_index)

    def _actor_or_player(self, player_id: str | None) -> PlayerState:
        if player_id is None:
            if self.current_actor_index is None:
                raise PokerError("there is no current actor")
            return self.players[self.current_actor_index]
        return self._player_by_id(player_id)

    def _player_by_id(self, player_id: str) -> PlayerState:
        for player in self.players:
            if player.player_id == player_id:
                return player
        raise PokerError(f"unknown player id: {player_id}")

    def _serialize_player(self, player: PlayerState, reveal_hole_cards: bool) -> dict:
        return {
            "player_id": player.player_id,
            "name": player.name,
            "seat_index": player.seat_index,
            "stack": player.stack,
            "hole_cards": [str(card) for card in player.hole_cards] if reveal_hole_cards else [],
            "current_bet": player.current_bet,
            "has_folded": player.has_folded,
            "is_all_in": player.is_all_in,
            "is_human": player.is_human,
        }

    def _burn(self) -> None:
        self.deck.draw()

    def current_max_bet(self) -> int:
        return max((player.current_bet for player in self.players), default=0)

    def _clockwise_players_from_dealer(self, players: list[PlayerState]) -> list[PlayerState]:
        ids = {player.player_id for player in players}
        ordered = []
        for offset in range(1, len(self.players) + 1):
            player = self.players[(self.dealer_button_index + offset) % len(self.players)]
            if player.player_id in ids:
                ordered.append(player)
        return ordered


def build_side_pots(contributions: dict[str, int], players: list[PlayerState]) -> list[Pot]:
    levels = sorted({amount for amount in contributions.values() if amount > 0})
    pots: list[Pot] = []
    previous = 0
    for level in levels:
        contributors = [player for player in players if contributions[player.player_id] >= level]
        amount = (level - previous) * len(contributors)
        eligible = tuple(player.player_id for player in contributors if not player.has_folded)
        if amount > 0 and eligible:
            pots.append(Pot(amount=amount, eligible_player_ids=eligible))
        previous = level
    return pots


def evaluate_holdem(cards: list[Card]) -> tuple[int, tuple[int, ...]]:
    """Python fallback/reference seven-card evaluator; Step 03 replaces the hot path."""
    if len(cards) < 5:
        raise PokerError("at least five cards are required to evaluate a hand")
    return max(_evaluate_five(list(combo)) for combo in combinations(cards, 5))


def _evaluate_five(cards: list[Card]) -> tuple[int, tuple[int, ...]]:
    ranks = [_rank_value(card.rank) for card in cards]
    rank_counts = Counter(ranks)
    ordered_counts = sorted(rank_counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    is_flush = len({card.suit for card in cards}) == 1
    straight_high = _straight_high(ranks)

    if is_flush and straight_high:
        return (8, (straight_high,))
    if ordered_counts[0][1] == 4:
        quad = ordered_counts[0][0]
        kicker = max(rank for rank in ranks if rank != quad)
        return (7, (quad, kicker))
    if ordered_counts[0][1] == 3 and ordered_counts[1][1] == 2:
        return (6, (ordered_counts[0][0], ordered_counts[1][0]))
    if is_flush:
        return (5, tuple(sorted(ranks, reverse=True)))
    if straight_high:
        return (4, (straight_high,))
    if ordered_counts[0][1] == 3:
        trips = ordered_counts[0][0]
        kickers = sorted((rank for rank in ranks if rank != trips), reverse=True)
        return (3, (trips, *kickers))
    pairs = [rank for rank, count in ordered_counts if count == 2]
    if len(pairs) >= 2:
        top_pairs = sorted(pairs, reverse=True)[:2]
        kicker = max(rank for rank in ranks if rank not in top_pairs)
        return (2, (*top_pairs, kicker))
    if len(pairs) == 1:
        pair = pairs[0]
        kickers = sorted((rank for rank in ranks if rank != pair), reverse=True)
        return (1, (pair, *kickers))
    return (0, tuple(sorted(ranks, reverse=True)))


def _straight_high(ranks: list[int]) -> int | None:
    unique = sorted(set(ranks), reverse=True)
    if 14 in unique:
        unique.append(1)
    for index in range(len(unique) - 4):
        window = unique[index : index + 5]
        if window[0] - window[4] == 4:
            return window[0]
    return None


def _rank_value(rank: str) -> int:
    return "23456789TJQKA".index(rank) + 2


def _next_seat(players: list[PlayerState], start_index: int) -> int:
    return (start_index + 1) % len(players)
