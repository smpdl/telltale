from telltale.game.engine import HoldemEngine
from telltale.game.cards import Card
from telltale.game.holdem import ActionType, PlayerState
from telltale.poker.policy import board_texture
from telltale.poker import PokerPolicyConfig, PokerPolicyWriter, native


class FixedSolver:
    def __init__(self, result: native.EquityResult):
        self.result = result

    def estimate_equity(self, *args, **kwargs):
        return self.result


def make_players() -> list[PlayerState]:
    players: list[PlayerState] = []
    for index in range(3):
        players.append(PlayerState(f"p{index}", f"Player {index}", index, 100))
    return players


def equity(value: float) -> native.EquityResult:
    wins = int(value * 100)
    losses = 100 - wins
    return native.EquityResult(wins, 0, losses, 100, value, 0.0, 1.0 - value)


def test_recommendation_contains_only_legal_actions():
    hand = HoldemEngine().start_hand(make_players(), seed=42, dealer_button_index=0)
    writer = PokerPolicyWriter(FixedSolver(equity(0.5)))

    decision = writer.choose_action(hand)

    assert decision.action in hand.legal_actions()


def test_native_policy_probabilities_sum_to_one():
    features = native.DecisionFeatures(
        street="flop",
        hero_equity=0.5,
        pot_size=100,
        amount_to_call=30,
        pot_odds=30 / 130,
        stack_to_pot_ratio=2.0,
        players_remaining=3,
        can_check=False,
        legal_actions=("fold", "call", "raise", "all_in"),
    )

    recommendation = native.recommend_action(features)

    assert abs(sum(recommendation.probabilities.values()) - 1.0) < 1e-12
    assert set(recommendation.probabilities) <= set(features.legal_actions)
    assert recommendation.amount_options is not None
    assert recommendation.board_texture == "dry"


def test_native_policy_returns_richer_advice_fields():
    features = native.DecisionFeatures(
        street="turn",
        hero_equity=0.76,
        pot_size=120,
        amount_to_call=0,
        pot_odds=0.0,
        stack_to_pot_ratio=2.0,
        players_remaining=2,
        can_check=True,
        legal_actions=("check", "bet", "all_in"),
        hero_stack=200,
        minimum_raise_amount=20,
        board_texture="two_tone",
        street_action_count=1,
        previous_aggression_count=0,
    )

    recommendation = native.recommend_action(features)

    assert recommendation.risk_label in {"low", "medium", "high"}
    assert recommendation.board_texture == "two_tone"
    assert recommendation.decision_margin >= 0
    assert recommendation.amount_options == {
        "all_in": 200,
        "large": 120,
        "medium": 60,
        "small": 40,
    }
    assert recommendation.hand_strength_bucket == "strong"
    assert recommendation.spr_bucket == "medium"
    assert recommendation.abstract_actions == ("check", "bet_33", "bet_66", "bet_100", "all_in")


def test_weak_equity_facing_bad_pot_odds_favors_fold():
    hand = HoldemEngine().start_hand(make_players(), seed=42, dealer_button_index=0)
    writer = PokerPolicyWriter(FixedSolver(equity(0.05)))

    decision = writer.choose_action(hand)

    assert decision.action == ActionType.FOLD


def test_weak_equity_with_check_available_favors_check():
    hand = HoldemEngine().start_hand(make_players(), seed=42, dealer_button_index=0)
    hand.apply_action(ActionType.CALL)
    hand.apply_action(ActionType.CALL)
    hand.apply_action(ActionType.CHECK)
    writer = PokerPolicyWriter(FixedSolver(equity(0.12)))

    decision = writer.choose_action(hand)

    assert decision.action == ActionType.CHECK


def test_strong_equity_favors_bet_or_raise():
    hand = HoldemEngine().start_hand(make_players(), seed=42, dealer_button_index=0)
    writer = PokerPolicyWriter(FixedSolver(equity(0.85)), PokerPolicyConfig(simulations=100))

    decision = writer.choose_action(hand)

    assert decision.action == ActionType.RAISE


def test_suggested_bet_or_raise_amount_is_legal_when_present():
    hand = HoldemEngine().start_hand(make_players(), seed=42, dealer_button_index=0)
    writer = PokerPolicyWriter(FixedSolver(equity(0.85)), PokerPolicyConfig(simulations=100))

    decision = writer.apply_action(hand)

    assert decision.action == ActionType.RAISE
    assert hand.action_history[-1].amount >= 20


def test_explanation_includes_equity_and_pot_odds():
    hand = HoldemEngine().start_hand(make_players(), seed=42, dealer_button_index=0)
    writer = PokerPolicyWriter(FixedSolver(equity(0.45)))

    decision = writer.choose_action(hand)

    assert "equity" in decision.reason
    assert "pot odds" in decision.reason


def test_wet_board_reduces_strong_bet_probability():
    dry = native.DecisionFeatures(
        street="flop",
        hero_equity=0.68,
        pot_size=100,
        amount_to_call=0,
        pot_odds=0.0,
        stack_to_pot_ratio=2.0,
        players_remaining=2,
        can_check=True,
        legal_actions=("check", "bet", "all_in"),
        hero_stack=200,
        minimum_raise_amount=10,
        board_texture="dry",
    )
    wet = native.DecisionFeatures(
        street="flop",
        hero_equity=0.68,
        pot_size=100,
        amount_to_call=0,
        pot_odds=0.0,
        stack_to_pot_ratio=2.0,
        players_remaining=2,
        can_check=True,
        legal_actions=("check", "bet", "all_in"),
        hero_stack=200,
        minimum_raise_amount=10,
        board_texture="wet",
    )

    assert native.recommend_action(wet).probabilities["bet"] < native.recommend_action(dry).probabilities["bet"]


def test_multiway_pot_reduces_marginal_raise_probability():
    heads_up = native.DecisionFeatures(
        street="turn",
        hero_equity=0.74,
        pot_size=100,
        amount_to_call=20,
        pot_odds=20 / 120,
        stack_to_pot_ratio=2.0,
        players_remaining=2,
        can_check=False,
        legal_actions=("fold", "call", "raise", "all_in"),
        hero_stack=200,
        minimum_raise_amount=20,
        board_texture="dry",
    )
    multiway = native.DecisionFeatures(
        street="turn",
        hero_equity=0.74,
        pot_size=100,
        amount_to_call=20,
        pot_odds=20 / 120,
        stack_to_pot_ratio=2.0,
        players_remaining=4,
        can_check=False,
        legal_actions=("fold", "call", "raise", "all_in"),
        hero_stack=200,
        minimum_raise_amount=20,
        board_texture="dry",
    )

    assert native.recommend_action(multiway).probabilities["raise"] < native.recommend_action(heads_up).probabilities["raise"]


def test_low_spr_strong_equity_can_suggest_all_in():
    features = native.DecisionFeatures(
        street="river",
        hero_equity=0.9,
        pot_size=200,
        amount_to_call=0,
        pot_odds=0.0,
        stack_to_pot_ratio=0.8,
        players_remaining=2,
        can_check=True,
        legal_actions=("check", "bet", "all_in"),
        hero_stack=160,
        minimum_raise_amount=20,
        board_texture="dry",
    )

    recommendation = native.recommend_action(features)

    assert recommendation.probabilities["all_in"] > 0
    assert recommendation.risk_label == "high"


def test_suggested_amounts_are_clamped_to_stack_and_minimum_raise():
    features = native.DecisionFeatures(
        street="flop",
        hero_equity=0.8,
        pot_size=300,
        amount_to_call=40,
        pot_odds=40 / 340,
        stack_to_pot_ratio=0.25,
        players_remaining=2,
        can_check=False,
        legal_actions=("fold", "call", "raise", "all_in"),
        hero_stack=75,
        minimum_raise_amount=30,
        board_texture="dry",
    )

    recommendation = native.recommend_action(features)

    assert recommendation.suggested_amount <= 75
    assert recommendation.amount_options is not None
    assert recommendation.amount_options["small"] == 75
    assert recommendation.amount_options["all_in"] == 75


def test_board_texture_extraction():
    hand = HoldemEngine().start_hand(make_players(), seed=42, dealer_button_index=0)

    hand.board_cards = [Card.parse("Ah"), Card.parse("7h"), Card.parse("2h")]
    assert board_texture(hand) == "monotone"

    hand.board_cards = [Card.parse("Ah"), Card.parse("Ad"), Card.parse("7c")]
    assert board_texture(hand) == "paired"

    hand.board_cards = [Card.parse("9h"), Card.parse("8d"), Card.parse("7h")]
    assert board_texture(hand) == "wet"

    hand.board_cards = [Card.parse("Kh"), Card.parse("8h"), Card.parse("2c")]
    assert board_texture(hand) == "two_tone"

    hand.board_cards = [Card.parse("Kh"), Card.parse("8d"), Card.parse("2c")]
    assert board_texture(hand) == "dry"


def test_runtime_and_build_references_use_action_policy_name():
    checked_paths = [
        "telltale/native/poker_solver/bindings.cpp",
        "telltale/native/poker_solver/CMakeLists.txt",
        "telltale/poker/native.py",
    ]

    for path in checked_paths:
        with open(path) as file:
            assert "cfr_lite" not in file.read()
