"""
This file contains the Card and Deck classes for the game of poker.

Cards are represented as a string of two characters, the rank and the suit. 
For example, "Ah" is the ace of hearts.

Deck is a collection of 52 unique cards.
It can be shuffled and drawn from.

CardError is raised when card or deck operations are invalid.
"""


from __future__ import annotations

from dataclasses import dataclass
import random


RANKS = "23456789TJQKA"
SUITS = "cdhs"


class CardError(ValueError):
    """Raised when card or deck operations are invalid."""

'''   
Note for self regarding dataclasses:

The order=true argument will add things like __lt__, __gt__, __le__, __ge__
, __eq__, and __ne__ methods to the class. These will be useful for sorting 
and comparing cards.

The frozen=True argument adds __setattr__ and __delattr__ methods to the class. 
These methods will prevent the card from being modified after it is created.
'''
@dataclass(frozen=True, order=True)
class Card:
    rank: str
    suit: str

    @classmethod
    def parse(cls, value: str) -> "Card":
        """ 
        Parse a string representation of a card into a Card object.
        """
        if len(value) != 2:
            raise CardError(f"card must be two characters like 'Ah': {value!r}")
        rank = value[0]
        suit = value[1]
        if rank not in RANKS:
            raise CardError(f"invalid rank {rank!r} in {value!r}")
        if suit not in SUITS:
            raise CardError(f"invalid suit {suit!r} in {value!r}")
        return cls(rank=rank, suit=suit)

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"


class Deck:
    def __init__(self, seed: int | str | bytes | None = None, cards: list[Card] | None = None):
        # note to self: [:] is a shallow copy of the list
        if cards is not None:
            self.cards = cards[:]
        else:
            self.cards = _standard_deck()
        if cards is None and seed is not None:
            random.Random(seed).shuffle(self.cards)

    @classmethod
    def shuffled(cls, seed: int | str | bytes | None = None) -> "Deck":
        return cls(seed=seed)

    def draw(self, count: int = 1) -> Card | list[Card]:
        if count < 1:
            raise CardError("draw count must be at least 1")
        if count > len(self.cards):
            raise CardError(f"cannot draw {count} cards from deck with {len(self.cards)} cards")
        drawn: list[Card] = []
        for _ in range(count):
            drawn.append(self.cards.pop())
        return drawn[0] if count == 1 else drawn

    def to_strings(self) -> list[str]:
        strings: list[str] = []
        for card in self.cards:
            strings.append(str(card))
        return strings

    def __len__(self) -> int:
        return len(self.cards)


def _standard_deck() -> list[Card]:
    cards: list[Card] = []
    for suit in SUITS:
        for rank in RANKS:
            cards.append(Card(rank, suit))
    return cards
