from telltale.game.cards import Card, Deck
from telltale.game.holdem import HandState, PlayerState, Street


def cards(*values: str) -> list[Card]:
    parsed: list[Card] = []
    for value in values:
        parsed.append(Card.parse(value))
    return parsed


def showdown_hand(players: list[PlayerState], board: list[Card], contributions: dict[str, int]) -> HandState:
    return HandState(
        hand_id="pot-test",
        deck=Deck(),
        players=players,
        dealer_button_index=0,
        small_blind_index=1,
        big_blind_index=2 if len(players) > 2 else 1,
        current_actor_index=None,
        street=Street.RIVER,
        board_cards=board,
        pot_contributions=contributions,
        minimum_raise_amount=10,
    )


def player(player_id: str, seat: int, hole_cards: list[Card], folded: bool = False) -> PlayerState:
    return PlayerState(
        player_id=player_id,
        name=player_id,
        seat_index=seat,
        stack=0,
        hole_cards=hole_cards,
        has_folded=folded,
    )


def test_single_winner_receives_full_pot():
    players = [
        player("p0", 0, cards("Ah", "Ad")),
        player("p1", 1, cards("Kh", "Kd")),
    ]
    hand = showdown_hand(players, cards("2c", "3d", "4h", "9s", "Td"), {"p0": 50, "p1": 50})

    hand._showdown()

    assert players[0].stack == 100
    assert players[1].stack == 0


def test_tie_splits_pot():
    players = [
        player("p0", 0, cards("2c", "7d")),
        player("p1", 1, cards("3c", "8d")),
    ]
    hand = showdown_hand(players, cards("Ah", "Kh", "Qh", "Jh", "Th"), {"p0": 40, "p1": 40})

    hand._showdown()

    assert players[0].stack == 40
    assert players[1].stack == 40


def test_odd_chip_remainder_is_deterministic_clockwise_from_dealer():
    players = [
        player("p0", 0, cards("Jc", "7d")),
        player("p1", 1, cards("Jd", "8d")),
        player("p2", 2, cards("Tc", "9d")),
    ]
    hand = showdown_hand(players, cards("Ah", "Ad", "Kc", "Qs", "2h"), {"p0": 1, "p1": 1, "p2": 1})

    hand._showdown()

    assert players[0].stack == 1
    assert players[1].stack == 2
    assert players[2].stack == 0


def test_three_player_all_in_side_pot_distributes_correctly():
    players = [
        player("p0", 0, cards("Ah", "Ad")),
        player("p1", 1, cards("Kh", "Kd")),
        player("p2", 2, cards("Qh", "Qd")),
    ]
    hand = showdown_hand(
        players,
        cards("2c", "3d", "4h", "9s", "Td"),
        {"p0": 50, "p1": 100, "p2": 200},
    )

    hand._showdown()

    assert players[0].stack == 150
    assert players[1].stack == 100
    assert players[2].stack == 100


def test_folded_player_cannot_win_even_if_cards_are_best():
    players = [
        player("p0", 0, cards("Ah", "Ad"), folded=True),
        player("p1", 1, cards("Kh", "Kd")),
    ]
    hand = showdown_hand(players, cards("2c", "3d", "4h", "9s", "Td"), {"p0": 50, "p1": 50})

    hand._showdown()

    assert players[0].stack == 0
    assert players[1].stack == 100
