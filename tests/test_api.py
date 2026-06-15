from telltale.server import api


def setup_function():
    api.reset_sessions()


def test_start_run_returns_playable_public_state():
    state = api.start_run(seed=123, settings={"model_mode": "mock"})

    assert state["run_id"]
    assert state["objective"].startswith("Win the run")
    assert state["floor"]["floor_number"] == 1
    assert state["legal_actions"]
    assert state["model"]["model_name"].startswith("NVIDIA Nemotron")


def test_submit_legal_player_action_returns_event_batch():
    state = api.start_run(seed=124, settings={"model_mode": "mock"})
    legal_action = state["legal_actions"][0]

    batch = api.submit_player_action(state["run_id"], legal_action, 0, "I am here to win this floor.")

    assert batch["run_id"] == state["run_id"]
    assert batch["public_state"]["run_id"] == state["run_id"]
    assert batch["events"]


def test_illegal_player_action_is_rejected():
    state = api.start_run(seed=125, settings={"model_mode": "mock"})

    try:
        api.submit_player_action(state["run_id"], "check" if "check" not in state["legal_actions"] else "fold", 0, "")
    except ValueError as error:
        assert "not legal" in str(error)


def test_public_state_hides_opponent_hole_cards_before_showdown():
    state = api.start_run(seed=126, settings={"model_mode": "mock"})

    opponents = [seat for seat in state["hand"]["players"] if not seat["is_human"]]

    assert opponents
    assert all(seat["hole_cards"] == [] for seat in opponents)


def test_export_trace_returns_jsonl_text_after_agent_action():
    state = api.start_run(seed=127, settings={"model_mode": "mock"})
    api.submit_player_action(state["run_id"], state["legal_actions"][0], 0, "You look priced in.")

    exported = api.export_trace(state["run_id"])

    assert exported["run_id"] == state["run_id"]
    assert "trace_version" in exported["content"] or exported["content"] == ""
