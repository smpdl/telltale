from dataclasses import fields

from telltale.agents.profiles import AGENT_PROFILES, DEFAULT_FINAL_BOSS_ID, get_agent_profile


def test_at_least_eight_profiles_exist():
    assert len(AGENT_PROFILES) >= 8


def test_agent_ids_are_unique():
    ids = [profile.agent_id for profile in AGENT_PROFILES]
    assert len(ids) == len(set(ids))


def test_every_profile_has_required_descriptive_fields():
    required = {
        "agent_id",
        "name",
        "floor_min",
        "floor_max",
        "can_be_boss",
        "character_summary",
        "poker_style",
        "dialogue_style",
        "honesty_style",
        "speech_style",
        "voice_id",
    }
    for profile in AGENT_PROFILES:
        for field_name in required:
            value = getattr(profile, field_name)
            if field_name == "can_be_boss":
                assert isinstance(value, bool)
            else:
                assert value


def test_teddy_kgb_exists_and_can_be_boss():
    teddy = get_agent_profile(DEFAULT_FINAL_BOSS_ID)

    assert teddy.name == "Teddy KGB"
    assert teddy.can_be_boss


def test_every_profile_has_speech_style_and_voice_id():
    for profile in AGENT_PROFILES:
        assert profile.speech_style
        assert profile.voice_id


def test_profiles_do_not_expose_numeric_personality_sliders():
    banned = {"base_skill", "risk_tolerance", "bluff_frequency", "aggression", "looseness"}
    field_names = {field.name for field in fields(type(AGENT_PROFILES[0]))}

    assert field_names.isdisjoint(banned)
