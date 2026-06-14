import json

from telltale.agents.memory import AgentMemory, MemoryDelta


def test_new_memory_starts_neutral():
    memory = AgentMemory.neutral("mike_mcdermott")

    assert memory.respect_for_player == 0
    assert memory.fear_of_player == 0
    assert memory.charmed_by_player == 0
    assert memory.grudge_against_player == 0
    assert memory.recent_player_patterns == []
    assert memory.recent_dialogue_impressions == []
    assert memory.summary == ""


def test_recent_lists_stay_within_max_length():
    memory = AgentMemory.neutral("worm")
    for index in range(8):
        memory.apply_delta(
            MemoryDelta(
                recent_player_patterns=[f"pattern-{index}"],
                recent_dialogue_impressions=[f"impression-{index}"],
            )
        )

    assert memory.recent_player_patterns == ["pattern-3", "pattern-4", "pattern-5", "pattern-6", "pattern-7"]
    assert memory.recent_dialogue_impressions == [
        "impression-3",
        "impression-4",
        "impression-5",
        "impression-6",
        "impression-7",
    ]


def test_memory_serializes_to_json():
    memory = AgentMemory.neutral("molly_bloom")

    data = json.loads(memory.to_json())

    assert data["agent_id"] == "molly_bloom"
    assert data["respect_for_player"] == 0


def test_memory_reset_creates_neutral_state_for_new_run():
    memory = AgentMemory.neutral("teddy_kgb")
    memory.apply_delta({"respect_for_player": 1, "grudge_against_player": 1, "summary": "bad history"})

    reset = AgentMemory.reset_for_run("teddy_kgb")

    assert reset.agent_id == memory.agent_id
    assert reset.respect_for_player == 0
    assert reset.grudge_against_player == 0
    assert reset.summary == ""


def test_applying_bounded_memory_updates_from_model_decision():
    memory = AgentMemory.neutral("ginger_mckenna")

    memory.apply_delta(
        {
            "respect_for_player": 2,
            "fear_of_player": -1,
            "charmed_by_player": 1.5,
            "grudge_against_player": 0.25,
            "recent_player_patterns": ["overbets turns"],
            "recent_dialogue_impressions": ["compliment felt sincere"],
            "summary": "Warming up to the player.",
        }
    )

    assert memory.respect_for_player == 1
    assert memory.fear_of_player == 0
    assert memory.charmed_by_player == 1
    assert memory.grudge_against_player == 0.25
    assert memory.recent_player_patterns == ["overbets turns"]
    assert memory.recent_dialogue_impressions == ["compliment felt sincere"]
    assert memory.summary == "Warming up to the player."
