import pytest

from telltale.game.cards import Card, CardError, Deck


def test_deck_has_52_unique_cards():
    deck = Deck()

    assert len(deck) == 52
    assert len(set(deck.cards)) == 52


def test_same_seed_creates_same_order():
    assert Deck.shuffled(seed=7).to_strings() == Deck.shuffled(seed=7).to_strings()


def test_different_seeds_usually_create_different_order():
    assert Deck.shuffled(seed=7).to_strings() != Deck.shuffled(seed=8).to_strings()


def test_drawing_reduces_deck_size():
    deck = Deck()
    drawn = deck.draw()

    assert isinstance(drawn, Card)
    assert len(deck) == 51


@pytest.mark.parametrize("value", ["1h", "Acx", "TT", ""])
def test_invalid_card_strings_fail_validation(value):
    with pytest.raises(CardError):
        Card.parse(value)


def test_drawing_beyond_deck_length_raises_clear_error():
    deck = Deck()

    with pytest.raises(CardError, match="cannot draw"):
        deck.draw(53)
