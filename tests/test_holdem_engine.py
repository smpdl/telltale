import pytest

from telltale.game.engine import HoldemEngine
from telltale.game.holdem import ActionType, PlayerState, PokerError, Street


def make_players(stacks: tuple[int, ...] = (100, 100, 100)) -> list[PlayerState]:
    players: list[PlayerState] = []
    for index, stack in enumerate(stacks):
        players.append(PlayerState(f"p{index}", f"Player {index}", index, stack, is_human=index == 0))
    return players


def start_hand(stacks: tuple[int, ...] = (100, 100, 100)):
    return HoldemEngine().start_hand(make_players(stacks), seed=42, dealer_button_index=0)


def test_starting_three_player_hand_deals_two_cards_each():
    hand = start_hand()

    hole_card_counts = []
    for player in hand.players:
        hole_card_counts.append(len(player.hole_cards))
    assert hole_card_counts == [2, 2, 2]


def test_preflop_blinds_are_posted_correctly():
    hand = start_hand()

    assert hand.players[1].current_bet == 5
    assert hand.players[2].current_bet == 10
    assert hand.pot_contributions == {"p0": 0, "p1": 5, "p2": 10}


def test_big_blind_can_check_when_no_raise_occurred():
    engine = HoldemEngine()
    hand = start_hand()

    engine.apply_action(hand, ActionType.CALL)
    engine.apply_action(hand, ActionType.CALL)

    assert hand.current_actor_index == 2
    assert ActionType.CHECK in engine.legal_actions(hand)


def test_illegal_check_facing_bet_is_rejected():
    hand = start_hand()

    with pytest.raises(PokerError, match="check is not legal"):
        hand.apply_action(ActionType.CHECK)


def test_folded_players_are_skipped():
    hand = start_hand()

    hand.apply_action(ActionType.FOLD)

    assert hand.players[0].has_folded
    assert hand.current_actor_index == 1


def test_all_in_players_are_skipped():
    hand = start_hand(stacks=(10, 100, 100))

    hand.apply_action(ActionType.CALL)

    assert hand.players[0].is_all_in
    assert hand.current_actor_index == 1


def test_street_advances_after_all_active_players_have_acted():
    hand = start_hand()

    hand.apply_action(ActionType.CALL)
    hand.apply_action(ActionType.CALL)
    hand.apply_action(ActionType.CHECK)

    assert hand.street == Street.FLOP
    assert len(hand.board_cards) == 3


def test_board_reaches_flop_turn_and_river():
    hand = start_hand()
    hand.apply_action(ActionType.CALL)
    hand.apply_action(ActionType.CALL)
    hand.apply_action(ActionType.CHECK)
    assert len(hand.board_cards) == 3

    for _ in range(3):
        hand.apply_action(ActionType.CHECK)
    assert hand.street == Street.TURN
    assert len(hand.board_cards) == 4

    for _ in range(3):
        hand.apply_action(ActionType.CHECK)
    assert hand.street == Street.RIVER
    assert len(hand.board_cards) == 5


def test_hand_completes_when_only_one_player_remains():
    hand = start_hand()

    hand.apply_action(ActionType.FOLD)
    hand.apply_action(ActionType.FOLD)

    assert hand.street == Street.COMPLETE
    assert hand.players[2].stack == 105


def test_public_state_hides_opponent_hole_cards_before_showdown():
    hand = start_hand()

    public = hand.to_public_state("p0")

    expected_hole_cards = []
    for card in hand.players[0].hole_cards:
        expected_hole_cards.append(str(card))
    assert public["players"][0]["hole_cards"] == expected_hole_cards
    assert public["players"][1]["hole_cards"] == []
    assert public["players"][2]["hole_cards"] == []
    assert "deck" not in public


def test_seeded_first_legal_action_simulation_conserves_chips_and_cards():
    hand = start_hand()
    total_chips = 0
    for player in hand.players:
        total_chips += player.stack
    total_chips += sum(hand.pot_contributions.values())
    priority = [
        ActionType.CHECK,
        ActionType.CALL,
        ActionType.FOLD,
        ActionType.BET,
        ActionType.RAISE,
        ActionType.ALL_IN,
    ]

    while hand.street != Street.COMPLETE:
        legal = hand.legal_actions()
        action = None
        for candidate in priority:
            if candidate in legal:
                action = candidate
                break
        hand.apply_action(action, amount=10 if action in {ActionType.BET, ActionType.RAISE} else 0)

    visible_and_deck_cards = []
    for player in hand.players:
        for card in player.hole_cards:
            visible_and_deck_cards.append(card)
    visible_and_deck_cards.extend(hand.board_cards)
    visible_and_deck_cards.extend(hand.deck.cards)

    for player in hand.players:
        assert player.stack >= 0
    assert len(visible_and_deck_cards) == len(set(visible_and_deck_cards))
    final_chips = 0
    for player in hand.players:
        final_chips += player.stack
    assert final_chips == total_chips
