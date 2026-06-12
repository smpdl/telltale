from telltale.game.economy import RunState, RunStatus
from telltale.game.floors import FLOOR_CONFIGS
from telltale.game.perks import ActivePerk, get_perk


def test_starting_run_creates_floor_one_with_bankroll_and_zero_continues():
    run = RunState.start(seed="start")

    assert run.floor_index == 0
    assert run.current_floor.floor_number == 1
    assert run.bankroll == 250
    assert run.continues == 0
    assert run.status == RunStatus.ACTIVE


def test_entering_floor_deducts_buy_in():
    run = RunState.start(seed="enter")
    buy_in = run.current_floor.buy_in

    assert run.enter_current_floor()

    assert run.bankroll == 250 - buy_in
    assert run.current_table is not None
    assert run.current_table.floor_number == 1


def test_winning_floor_advances_to_reward_selection():
    run = RunState.start(seed="win-floor")
    run.enter_current_floor()

    run.win_current_floor(ending_stack=run.current_floor.win_target)

    assert run.awaiting_reward
    assert run.completed_floors == [1]
    assert len(run.available_rewards) == run.current_floor.reward_choices_count
    assert run.current_table is None


def test_choosing_reward_adds_exactly_one_perk():
    run = RunState.start(seed="reward")
    run.enter_current_floor()
    run.win_current_floor(ending_stack=run.current_floor.win_target)

    run.choose_reward(run.available_rewards[0])

    assert len(run.active_perks) == 1
    assert not run.awaiting_reward
    assert run.floor_index == 1


def test_completing_floors_one_through_four_advances_to_next_floor():
    run = RunState.start(seed="advance")

    for expected_floor in range(1, 5):
        assert run.current_floor.floor_number == expected_floor
        run.enter_current_floor()
        run.win_current_floor(ending_stack=run.current_floor.win_target)
        run.choose_reward(run.available_rewards[0])

    assert run.current_floor.floor_number == 5
    assert run.status == RunStatus.ACTIVE


def test_winning_floor_five_marks_run_won():
    run = RunState.start(seed="boss-win", bankroll=2_000)
    for floor in FLOOR_CONFIGS[:-1]:
        run.completed_floors.append(floor.floor_number)
    run.floor_index = 4

    run.enter_current_floor()
    run.win_current_floor(ending_stack=run.current_floor.win_target)

    assert run.status == RunStatus.WON
    assert run.completed_floors[-1] == 5


def test_bankroll_never_becomes_negative_when_continue_is_used():
    run = RunState.start(seed="continue", bankroll=0)

    assert run.enter_current_floor(use_continue=True)

    assert run.continues == 1
    assert run.bankroll == 0


def test_final_floor_loss_marks_run_lost_without_continue_bailout():
    run = RunState.start(seed="boss-loss", bankroll=2_000)
    run.floor_index = 4
    run.enter_current_floor()

    run.lose_current_floor()

    assert run.status == RunStatus.LOST


def test_buy_in_discount_modifies_floor_buy_in_and_is_consumed_on_entry():
    run = RunState.start(seed="discount", bankroll=1_000)
    run.floor_index = 1
    run.active_perks.append(ActivePerk.from_definition(get_perk("buy_in_discount")))

    assert run.buy_in_for_floor() == round(FLOOR_CONFIGS[1].buy_in * 0.85)

    run.enter_current_floor()

    assert [perk.perk_id for perk in run.active_perks] == []

