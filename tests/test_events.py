from telltale.server.events import EventBuilder, EventBatch


def test_events_have_unique_ids_and_monotonic_sequences():
    builder = EventBuilder("run-a")

    first = builder.emit("run_started")
    second = builder.emit("player_turn")

    assert first.event_id != second.event_id
    assert [event.sequence for event in builder.events] == [1, 2]


def test_event_batch_serializes_to_json():
    builder = EventBuilder("run-a")
    builder.emit("agent_spoke", text="Price is price.")

    payload = EventBatch("run-a", builder.events, {"status": "active"}).to_json()

    assert "agent_spoke" in payload
    assert "active" in payload
