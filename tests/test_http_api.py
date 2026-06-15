from fastapi.testclient import TestClient

from app import app
from telltale.server import api


client = TestClient(app)


def setup_function():
    api.reset_sessions()


def test_react_index_is_player_facing_shell():
    response = client.get("/")

    assert response.status_code == 200
    assert "id=\"root\"" in response.text
    assert "gradio-container" not in response.text


def test_root_public_assets_are_served_before_spa_fallback():
    soundtrack = client.get("/dream.mp3")

    assert soundtrack.status_code == 200
    assert soundtrack.headers["content-type"].startswith("audio/")


def test_floors_endpoint_returns_backend_floor_definitions():
    response = client.get("/api/floors")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_floors"] == 5
    assert len(payload["floors"]) == 5
    assert payload["floors"][0]["name"] == "Level 1 (Tutorial)"
    assert payload["floors"][0]["buy_in"] == 40
    assert payload["floors"][4]["is_boss"] is True


def test_start_endpoint_returns_public_state():
    response = client.post("/api/start", json={"seed": 321, "model_mode": "mock"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"]
    assert payload["floor"]["floor_number"] == 1
    assert payload["legal_actions"]


def test_start_endpoint_uses_configured_model_mode_when_omitted():
    response = client.post("/api/start", json={"seed": 3210})

    assert response.status_code == 200
    assert response.json()["model"]["runtime_backend"] == "mock"


def test_start_endpoint_accepts_voice_flags():
    response = client.post(
        "/api/start",
        json={"seed": 3211, "model_mode": "mock", "tts_enabled": True, "stt_enabled": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["voice"] == {"tts_enabled": True, "stt_enabled": True}


def test_invalid_run_id_uses_error_envelope():
    response = client.get("/api/state/missing-run")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_illegal_action_uses_error_envelope():
    started = client.post("/api/start", json={"seed": 322, "model_mode": "mock"}).json()
    illegal = "check" if "check" not in started["legal_actions"] else "fold"

    response = client.post(
        "/api/action",
        json={"run_id": started["run_id"], "action": illegal, "amount": 0, "utterance": ""},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "illegal_action"


def test_legal_action_returns_event_batch():
    started = client.post("/api/start", json={"seed": 323, "model_mode": "mock"}).json()

    response = client.post(
        "/api/action",
        json={
            "run_id": started["run_id"],
            "action": started["legal_actions"][0],
            "amount": 0,
            "utterance": "The room feels priced in.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == started["run_id"]
    assert payload["events"]
    assert payload["public_state"]["run_id"] == started["run_id"]


def test_continue_endpoint_returns_event_batch():
    started = client.post("/api/start", json={"seed": 324, "model_mode": "mock"}).json()

    response = client.post("/api/continue", json={"run_id": started["run_id"]})

    assert response.status_code == 200
    assert response.json()["public_state"]["run_id"] == started["run_id"]


def test_reward_endpoint_rejects_when_no_reward_pending():
    started = client.post("/api/start", json={"seed": 325, "model_mode": "mock"}).json()

    response = client.post("/api/reward", json={"run_id": started["run_id"], "perk_id": "not-a-perk"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_trace_export_endpoint_returns_trace_payload():
    started = client.post("/api/start", json={"seed": 326, "model_mode": "mock"}).json()
    client.post(
        "/api/action",
        json={"run_id": started["run_id"], "action": started["legal_actions"][0], "amount": 0, "utterance": ""},
    )

    response = client.get(f"/api/trace/{started['run_id']}")

    assert response.status_code == 200
    assert response.json()["run_id"] == started["run_id"]


def test_transcribe_endpoint_returns_structured_disabled_result():
    started = client.post("/api/start", json={"seed": 327, "model_mode": "mock"}).json()

    response = client.post(
        f"/api/transcribe/{started['run_id']}",
        content=b"audio",
        headers={"Content-Type": "audio/webm"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == ""
    assert payload["disabled"] is True
    assert payload["error"] == "speech input is disabled"


def test_audio_endpoint_rejects_path_traversal():
    response = client.get("/api/audio/%5Csecret.wav")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"
