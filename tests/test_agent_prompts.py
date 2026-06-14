import pytest

from telltale.agents.decision import parse_agent_decision, validate_and_repair
from telltale.agents.dialogue import PlayerUtterance
from telltale.agents.memory import AgentMemory
from telltale.agents.profiles import get_agent_profile
from telltale.agents.prompts import build_agent_prompt
from telltale.game.holdem import ActionType
from telltale.poker.policy import PokerDecision


def test_prompt_includes_profile_memory_solver_and_legal_actions():
    profile = get_agent_profile("lancey_howard")
    memory = AgentMemory.neutral(profile.agent_id)
    memory.summary = "Player has shown one river bluff."

    prompt = build_agent_prompt(
        profile,
        memory,
        {"street": "river", "pot": 120},
        {"hole_cards": ["As", "Ks"]},
        PokerDecision(ActionType.CALL, amount=0, equity=0.42, pot_odds=0.3, reason="equity beats pot odds"),
        None,
        [ActionType.CALL, ActionType.FOLD],
    )

    assert profile.character_summary in prompt
    assert "Player has shown one river bluff." in prompt
    assert "equity beats pot odds" in prompt
    assert "call" in prompt
    assert "fold" in prompt


def test_prompt_includes_player_utterance_when_provided():
    prompt = build_agent_prompt(
        get_agent_profile("ace_rothstein"),
        AgentMemory.neutral("ace_rothstein"),
        {},
        {},
        {"suggested_action": "fold"},
        PlayerUtterance("That sizing is a tell.", target_agent_id="ace_rothstein"),
        [ActionType.FOLD, ActionType.CALL],
    )

    assert "That sizing is a tell." in prompt


def test_valid_mocked_json_model_output_parses_into_decision():
    raw = """
    {
      "action": "call",
      "amount": 0,
      "speech": "I can pay to see that.",
      "honest_rationale": "The price is good enough against the story.",
      "emotional_state": "curious",
      "memory_delta": {
        "respect_for_player": 0.2,
        "recent_player_patterns": ["pressures paired boards"]
      }
    }
    """

    decision = parse_agent_decision(raw)

    assert decision.action == ActionType.CALL
    assert decision.source == "model"
    assert decision.memory_delta.respect_for_player == 0.2


def test_illegal_model_action_is_repaired_to_legal_solver_action():
    decision = parse_agent_decision(
        '{"action":"raise","amount":30,"speech":"No.","honest_rationale":"Pressure looked weak.","emotional_state":"sharp"}'
    )

    repaired = validate_and_repair(
        decision,
        [ActionType.CALL, ActionType.FOLD],
        PokerDecision(ActionType.CALL, reason="pot odds"),
    )

    assert repaired.action == ActionType.CALL


def test_malformed_model_action_reaches_repair():
    decision = parse_agent_decision(
        '{"action":"dance","amount":0,"speech":"Watch close.","honest_rationale":"The output action malformed.","emotional_state":"strange"}'
    )

    repaired = validate_and_repair(decision, [ActionType.FOLD], PokerDecision(ActionType.FOLD))

    assert repaired.action == ActionType.FOLD


def test_illegal_amount_is_repaired_or_clamped():
    decision = parse_agent_decision(
        '{"action":"check","amount":50,"speech":"Free card.","honest_rationale":"No need to invest.","emotional_state":"calm"}'
    )

    repaired = validate_and_repair(decision, [ActionType.CHECK], PokerDecision(ActionType.CHECK))

    assert repaired.amount == 0


def test_missing_speech_or_rationale_fails_predictably():
    with pytest.raises(ValueError, match="missing required"):
        parse_agent_decision('{"action":"call","amount":0,"speech":"Fine."}')

    decision = parse_agent_decision(
        '{"action":"call","amount":0,"speech":"Fine.","honest_rationale":"Price.","emotional_state":"flat"}'
    )
    decision.speech = ""
    with pytest.raises(ValueError, match="requires non-empty"):
        validate_and_repair(decision, [ActionType.CALL], PokerDecision(ActionType.CALL))


def test_negative_bet_amount_is_repaired_from_solver():
    decision = parse_agent_decision(
        '{"action":"bet","amount":-10,"speech":"I will set it.","honest_rationale":"I want fold equity.","emotional_state":"bold"}'
    )

    repaired = validate_and_repair(decision, [ActionType.BET], PokerDecision(ActionType.BET, amount=20))

    assert repaired.amount == 20
