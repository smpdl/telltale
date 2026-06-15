from telltale.agents.dialogue import PlayerUtterance
from telltale.agents.memory import AgentMemory
from telltale.agents.profiles import get_agent_profile
from telltale.agents.prompts import build_agent_prompt
from telltale.game.holdem import ActionType


def test_empty_utterance_serializes_cleanly_and_prompt_omits_it():
    utterance = PlayerUtterance()

    prompt = build_agent_prompt(
        get_agent_profile("mike_mcdermott"),
        AgentMemory.neutral("mike_mcdermott"),
        {},
        {},
        {"action": "check", "reason": "free card"},
        utterance,
        [ActionType.CHECK],
    )

    assert utterance.to_dict() == {"raw_text": "", "target_agent_id": None}
    assert '"player_utterance"' not in prompt


def test_non_empty_utterance_preserves_raw_text_and_target():
    utterance = PlayerUtterance("You look scared of this river.", target_agent_id="worm")

    assert utterance.to_dict() == {
        "raw_text": "You look scared of this river.",
        "target_agent_id": "worm",
    }


def test_prompt_builder_includes_player_utterance_when_present():
    prompt = build_agent_prompt(
        get_agent_profile("worm"),
        AgentMemory.neutral("worm"),
        {},
        {},
        {"action": "call", "reason": "pot odds"},
        PlayerUtterance("I know you missed.", target_agent_id="worm"),
        [ActionType.CALL, ActionType.FOLD],
    )

    assert "I know you missed." in prompt
    assert "worm" in prompt
