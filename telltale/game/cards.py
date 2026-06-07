from __future__ import annotations

from dataclasses import dataclass
import random


RANKS = "23456789TJQKA"
SUITS = "cdhs"


class CardError(ValueError):
    """Raised when card or deck operations are invalid."""


@dataclass(frozen=True, order=True)
class Card:
    rank: str
    suit: str

    def __post_init__(self) -> None:
        if self.rank not in RANKS:
            raise CardError(f"invalid card rank: {self.rank!r}")
        if self.suit not in SUITS:
            raise CardError(f"invalid card suit: {self.suit!r}")

    @classmethod
    def parse(cls, value: str) -> "Card":
        if len(value) != 2:
            raise CardError(f"card must be two characters like 'Ah': {value!r}")
        return cls(rank=value[0], suit=value[1])

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"


class Deck:
    def __init__(self, seed: int | str | bytes | None = None, cards: list[Card] | None = None):
        self.cards = cards[:] if cards is not None else [Card(rank, suit) for suit in SUITS for rank in RANKS]
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
        drawn = [self.cards.pop() for _ in range(count)]
        return drawn[0] if count == 1 else drawn

    def to_strings(self) -> list[str]:
        return [str(card) for card in self.cards]

    def __len__(self) -> int:
        return len(self.cards)
