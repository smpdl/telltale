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
    """Defines the different stages of the poker game."""
    PREFLOP = "preflop" 
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"
    COMPLETE = "complete"


class ActionType(str, Enum):
    """Defines the different actions a player can take in the poker game."""
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all_in"


@dataclass
class PlayerState:
    """Represents the state of a player in the poker game."""
    player_id: str 
    name: str
    seat_index: int
    stack: int # number of chips the player has available to bet
    hole_cards: list[Card] = field(default_factory=list) # the cards the player has in their hand
    current_bet: int = 0 # the amount of chips the player has bet in the current round
    has_folded: bool = False
    is_all_in: bool = False
    is_human: bool = False


@dataclass(frozen=True)
class ActionRecord:
    """Represents a record of an action taken by a player in the poker game."""
    player_id: str
    action: ActionType
    amount: int
    street: Street


@dataclass(frozen=True)
class Pot:
    amount: int
    eligible_player_ids: tuple[str, ...] # the ids of the players who are eligible to win the pot


@dataclass
class HandState:
    hand_id: str 
    deck: Deck
    players: list[PlayerState]
    dealer_button_index: int # note this is the index of the player who is the dealer, not the player id. 
    small_blind_index: int 
    big_blind_index: int
    current_actor_index: int | None # the index of the player who is currently allowed to act
    street: Street = Street.PREFLOP # the current street of the game
    board_cards: list[Card] = field(default_factory=list) # the cards on the table
    pot_contributions: dict[str, int] = field(default_factory=dict) # the amount of chips each player has contributed to the pot
    minimum_call_amount: int = 0
    minimum_raise_amount: int = 0
    action_history: list[ActionRecord] = field(default_factory=list) # the history of actions taken by the players
    street_acted_player_ids: set[str] = field(default_factory=set) # the ids of the players who have acted on the current street

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
        """Starts a new hand of poker."""
        if len(players) < 2:
            raise PokerError("at least two players are required") 
        if small_blind < 0 or big_blind <= 0:
            raise PokerError("blind amounts must be positive")

        ordered = sorted(players, key=lambda player: player.seat_index)
        deck = Deck.shuffled(seed)
        dealer_pos = dealer_button_index % len(ordered)
        small_blind_pos = _next_seat(ordered, dealer_pos)
        # the index of the player in the players list who is the big blind
        big_blind_pos = _next_seat(ordered, small_blind_pos) 
        pot_contributions: dict[str, int] = {}
        for player in ordered:
            pot_contributions[player.player_id] = 0
        hand = cls(
            hand_id=hand_id or str(uuid4()),
            deck=deck,
            players=ordered,
            dealer_button_index=dealer_pos,
            small_blind_index=small_blind_pos,
            big_blind_index=big_blind_pos,
            current_actor_index=_next_seat(ordered, big_blind_pos),
            pot_contributions=pot_contributions,
            minimum_raise_amount=big_blind,
        )
        for _ in range(2):
            for player in ordered:
                player.hole_cards.append(deck.draw())
        hand._post_blind(small_blind_pos, small_blind) # the small blind player posts the small blind amount
        hand._post_blind(big_blind_pos, big_blind) # the big blind player posts the big blind amount
        hand.minimum_call_amount = hand.current_max_bet()
        hand._skip_unavailable_actor()
        return hand

    def legal_actions(self, player_id: str | None = None) -> set[ActionType]:
        player = self._actor_or_player(player_id)
        if self.street == Street.COMPLETE:
            return set[ActionType]()
        if player.has_folded or player.is_all_in or player.stack <= 0:
            return set[ActionType]()

        # the amount of chips the player needs to call to match the current maximum bet
        outstanding = self.current_max_bet() - player.current_bet 
        actions = {ActionType.ALL_IN}
        # if the player has no outstanding amount to call, they can check or bet
        if outstanding == 0:
            actions.add(ActionType.CHECK)
            # if the current maximum bet is 0, the player can bet
            if self.current_max_bet() == 0:
                actions.add(ActionType.BET)
        else:
            # if the player has an outstanding amount to call, they can fold or call
            actions.update({ActionType.FOLD, ActionType.CALL})
            # if the player has more chips than the outstanding amount, they can raise
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

        # if the action is a bet or a raise,
        # OR (all-in AND player's current bet is greater than the min. call amount):
        #   update the minimum call amount and minimum raise amount
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
        """Returns the private state of the hand. This is internal to the game and not visible to the viewer."""
        board_cards = _card_strings(self.board_cards)
        players = []
        for player in self.players:
            players.append(self._serialize_player(player, reveal_hole_cards=True))
        action_history = []
        for record in self.action_history:
            action_history.append(_serialize_action_record(record))
        return {
            "hand_id": self.hand_id,
            "street": self.street.value,
            "deck": self.deck.to_strings(),
            "board_cards": board_cards,
            "players": players,
            "pot_contributions": dict(self.pot_contributions),
            "current_actor_index": self.current_actor_index,
            "action_history": action_history,
        }

    def to_public_state(self, viewer_player_id: str) -> dict:
        """Returns the public state of the hand. This is what is visble to the viewer."""
        # if the street is showdown or complete, the hole cards are visible to the viewer
        showdown_visible = self.street in {Street.SHOWDOWN, Street.COMPLETE}
        board_cards = _card_strings(self.board_cards)
        players = []
        for player in self.players:
            reveal_hole_cards = showdown_visible or player.player_id == viewer_player_id
            players.append(self._serialize_player(player, reveal_hole_cards=reveal_hole_cards))
        legal_actions = []
        for action in sorted(self.legal_actions(viewer_player_id), key=lambda item: item.value):
            legal_actions.append(action.value)
        action_history = []
        for record in self.action_history:
            action_history.append(_serialize_action_record(record))
        return {
            "hand_id": self.hand_id,
            "street": self.street.value,
            "board_cards": board_cards,
            "players": players,
            "pot_contributions": dict(self.pot_contributions),
            "current_actor_index": self.current_actor_index,
            "legal_actions": legal_actions,
            "action_history": action_history,
        }

    def _validate_action(self, player: PlayerState, action: ActionType, amount: int) -> None:
        """Validates the action taken by the player."""
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
        """
        Applies the payment for the action taken by the player.
        Returns the amount of chips paid by the player.
        """
        paid = 0
        if action == ActionType.FOLD:
            player.has_folded = True
        elif action == ActionType.CHECK:
            paid = 0
        elif action == ActionType.CALL:
            # current max bet - player's current bet = the amount of chips the player needs to call to match the current maximum bet
            paid = self._pay(player, min(player.stack, self.current_max_bet() - player.current_bet))
        elif action in {ActionType.BET, ActionType.RAISE}:
            paid = self._pay(player, amount)
        elif action == ActionType.ALL_IN:
            paid = self._pay(player, player.stack)
        return paid

    def _pay(self, player: PlayerState, amount: int) -> int:
        """Pays the player the specified amount of chips."""
        paid = min(amount, player.stack)
        player.stack -= paid
        player.current_bet += paid
        self.pot_contributions[player.player_id] += paid
        if player.stack == 0:
            player.is_all_in = True
        return paid

    def _post_blind(self, player_index: int, amount: int) -> None:
        """Posts the blind for the player at the specified index."""
        player = self.players[player_index]
        self._pay(player, amount)

    def _settle_or_advance(self) -> None:
        """Setstles the pot or advances the street."""
        active = _players_not_folded(self.players)
        # if there is only one active player, award the pot to them
        if len(active) == 1:
            self._award_uncontested(active[0])
            return

        # if all remaining players are all-in, showdown
        if self._all_remaining_all_in():
            self._deal_remaining_board() # deal the remaining board cards
            self._showdown() # showdown
            return

        if self._street_is_complete():
            self._advance_street() # advance the street
        else:
            self.current_actor_index = self._next_actionable_index(self.current_actor_index) # set the current actor index to the next actionable index

    def _advance_street(self) -> None:
        """Advances the street."""
        for player in self.players:
            player.current_bet = 0
        self.street_acted_player_ids.clear()
        self.minimum_call_amount = 0 # reset the minimum call amount

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

        self.current_actor_index = self._next_actionable_index(self.dealer_button_index) # set the current actor index to the next actionable index
        if self.current_actor_index is None:
            self._deal_remaining_board()
            self._showdown()

    def _showdown(self) -> None:
        """
        Shows down the hand.

        We will build the side pots. Each side pot will be a Pot(amount, eligible_player_ids).
        For all pots, we will find the winners and award the pot to them.
        """
        self.street = Street.SHOWDOWN # set the street to the showdown
        for pot in build_side_pots(self.pot_contributions, self.players):
            winners = self._best_players(pot.eligible_player_ids)
            share, remainder = divmod(pot.amount, len(winners))
            for player in winners:
                player.stack += share
            for player in self._clockwise_players_from_dealer(winners)[:remainder]:
                player.stack += 1
        self.street = Street.COMPLETE
        self.current_actor_index = None

    def _award_uncontested(self, winner: PlayerState) -> None:
        """Awards the pot to the winner."""
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
        actionable = _actionable_players(self.players)
        if len(actionable) <= 1:
            return True
        max_bet = self.current_max_bet()
        for player in actionable:
            if player.current_bet != max_bet:
                return False
            if player.player_id not in self.street_acted_player_ids:
                return False
        return True

    def _all_remaining_all_in(self) -> bool:
        active = _players_not_folded(self.players)
        if len(active) <= 1:
            return False
        for player in active:
            if not player.is_all_in:
                return False
        return True

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
        """
        Gets the player state for the given player id.
        If the player id is None, it returns the player state for the current actor.
        If the player id is not None, it returns the player state for the given player id.
        """
        if player_id is None:
            if self.current_actor_index is None:
                raise PokerError("there is no current actor")
            else:
                return self.players[self.current_actor_index]
        return self._player_by_id(player_id)

    def _player_by_id(self, player_id: str) -> PlayerState:
        """Returns the player state for the given player id."""
        for player in self.players:
            if player.player_id == player_id:
                return player
        raise PokerError(f"unknown player id: {player_id}")

    def _serialize_player(self, player: PlayerState, reveal_hole_cards: bool) -> dict:
        hole_cards: list[str] = []
        if reveal_hole_cards:
            hole_cards = _card_strings(player.hole_cards)
        return {
            "player_id": player.player_id,
            "name": player.name,
            "seat_index": player.seat_index,
            "stack": player.stack,
            "hole_cards": hole_cards,
            "current_bet": player.current_bet,
            "has_folded": player.has_folded,
            "is_all_in": player.is_all_in,
            "is_human": player.is_human,
        }

    def _burn(self) -> None:
        self.deck.draw()

    def current_max_bet(self) -> int:
        max_bet = 0
        for player in self.players:
            if player.current_bet > max_bet:
                max_bet = player.current_bet
        return max_bet

    def _clockwise_players_from_dealer(self, players: list[PlayerState]) -> list[PlayerState]:
        """Returns the players in the clockwise order from the dealer."""
        ids: set[str] = set()
        for player in players:
            ids.add(player.player_id)
        ordered = []
        for offset in range(1, len(self.players) + 1):
            player = self.players[(self.dealer_button_index + offset) % len(self.players)]
            if player.player_id in ids:
                ordered.append(player)
        return ordered

    def _best_players(self, eligible_player_ids: tuple[str, ...]) -> list[PlayerState]:
        """Returns all eligible players tied for the best hand on the current board."""
        best_rank: tuple[int, ...] | None = None
        winners: list[PlayerState] = []
        for player in self.players:
            if player.player_id not in eligible_player_ids:
                continue
            rank = evaluate_7(player.hole_cards + self.board_cards)
            if best_rank is None or rank > best_rank:
                best_rank = rank
                winners = [player]
            elif rank == best_rank:
                winners.append(player)
        return winners


def evaluate_7(cards: list[Card]) -> tuple[int, ...]:
    """Returns the best five-card Hold'em rank from seven cards."""
    best_rank: tuple[int, ...] | None = None
    for hand in combinations(cards, 5):
        rank = evaluate_5(list(hand))
        if best_rank is None or rank > best_rank:
            best_rank = rank
    if best_rank is None:
        raise PokerError("evaluate_7 requires at least seven cards")
    return best_rank

def evaluate_5(cards: list[Card]) -> tuple[int, ...]:
    """Returns the best five-card Hold'em rank from five cards."""
    values: list[int] = []
    for card in cards:
        values.append(_rank_value(card.rank))
    values.sort(reverse=True)

    suits: set[str] = set()
    for card in cards:
        suits.add(card.suit)
    is_flush = len(suits) == 1

    unique_values = sorted(set(values), reverse=True)
    is_straight = False
    straight_high = 0
    if len(unique_values) == 5:
        if unique_values[0] - unique_values[4] == 4:
            is_straight = True
            straight_high = unique_values[0]
        elif unique_values == [14, 5, 4, 3, 2]:
            is_straight = True
            straight_high = 5

    counts = Counter()
    for card in cards:
        counts[_rank_value(card.rank)] += 1
    by_count = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)

    if is_straight and is_flush:
        return (8, straight_high)
    if by_count[0][1] == 4:
        return (7, by_count[0][0], by_count[1][0])
    if by_count[0][1] == 3 and by_count[1][1] == 2:
        return (6, by_count[0][0], by_count[1][0])
    if is_flush:
        return (5, *values)
    if is_straight:
        return (4, straight_high)
    if by_count[0][1] == 3:
        kickers = _ranks_with_count_other_than(counts, 3)
        return (3, by_count[0][0], *kickers)
    if by_count[0][1] == 2 and by_count[1][1] == 2:
        high_pair, low_pair = sorted((by_count[0][0], by_count[1][0]), reverse=True)
        return (2, high_pair, low_pair, by_count[2][0])
    if by_count[0][1] == 2:
        kickers = _ranks_with_count_other_than(counts, 2)
        return (1, by_count[0][0], *kickers)
    return (0, *values)


def _rank_value(rank: str) -> int:
    """Returns the value of a rank in the game of poker.
    For example, the value of "2" is 2, the value of "T" is 10, the value of "J" is 11, etc.
    """
    return "23456789TJQKA".index(rank) + 2


def _card_strings(cards: list[Card]) -> list[str]:
    strings: list[str] = []
    for card in cards:
        strings.append(str(card))
    return strings


def _serialize_action_record(record: ActionRecord) -> dict:
    return record.__dict__ | {"action": record.action.value, "street": record.street.value}


def _players_not_folded(players: list[PlayerState]) -> list[PlayerState]:
    active: list[PlayerState] = []
    for player in players:
        if not player.has_folded:
            active.append(player)
    return active


def _actionable_players(players: list[PlayerState]) -> list[PlayerState]:
    actionable: list[PlayerState] = []
    for player in players:
        if not player.has_folded and not player.is_all_in:
            actionable.append(player)
    return actionable


def _ranks_with_count_other_than(counts: Counter, excluded_count: int) -> list[int]:
    ranks: list[int] = []
    for rank, count in counts.items():
        if count != excluded_count:
            ranks.append(rank)
    ranks.sort(reverse=True)
    return ranks


def build_side_pots(contributions: dict[str, int], players: list[PlayerState]) -> list[Pot]:
    """
    Builds the side pots for the hands.
    Side pots are built when a player goes all-in and there are other players who have not folded.
    """
    levels: set[int] = set()
    for amount in contributions.values():
        if amount > 0:
            levels.add(amount)
    levels = sorted(levels)
    pots: list[Pot] = []
    previous = 0
    for level in levels:
        contributors: list[PlayerState] = []
        for player in players:
            if contributions[player.player_id] >= level:
                contributors.append(player)
        amount = (level - previous) * len(contributors)
        eligible_ids: list[str] = []
        for player in contributors:
            if not player.has_folded:
                eligible_ids.append(player.player_id)
        eligible = tuple(eligible_ids)
        if amount > 0 and eligible:
            pots.append(Pot(amount=amount, eligible_player_ids=eligible))
        previous = level
    return pots


def _next_seat(players: list[PlayerState], start_index: int) -> int:
    """
    Returns the index of the next player in the list of players. 
    This is a circular list, so if the start_index is the last player, 
    the next player is the first player.
    """
    return (start_index + 1) % len(players)
