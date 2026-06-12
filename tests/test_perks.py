from telltale.game.economy import RunState
from telltale.game.perks import (
    PERK_DEFINITIONS,
    ActivePerk,
    apply_buy_in_discount,
    apply_continue_waiver,
    get_perk,
    trigger_stack_recovery,
)


def test_every_perk_has_required_fields_and_effect():
    for perk in PERK_DEFINITIONS:
        assert perk.perk_id
        assert perk.name
        assert perk.description
        assert perk.trigger_timing
        assert callable(perk.effect)


def test_perk_ids_are_unique():
    ids = [perk.perk_id for perk in PERK_DEFINITIONS]
    assert len(ids) == len(set(ids))


def test_buy_in_discount_reduces_next_buy_in():
    assert apply_buy_in_discount(100) == 85


def test_continue_waiver_removes_one_continue_penalty():
    assert apply_continue_waiver(2) == 1
    assert apply_continue_waiver(1) == 0
    assert apply_continue_waiver(0) == 0


def test_stack_recovery_only_triggers_once():
    recovered, used = trigger_stack_recovery(100, already_used=False)
    assert recovered == 20
    assert used

    recovered, used = trigger_stack_recovery(100, already_used=True)
    assert recovered == 0
    assert used


def test_perks_serialize_into_public_run_state():
    run = RunState.start(seed=1)
    run.active_perks.append(ActivePerk.from_definition(get_perk("spotlight_seat")))

    public = run.serialize_public()

    assert public["active_perks"][0]["perk_id"] == "spotlight_seat"
    assert public["active_perks"][0]["trigger_timing"] == "next_floor_start"
