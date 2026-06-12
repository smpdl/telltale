from telltale.game.floors import FLOOR_CONFIGS


def test_exactly_five_floor_configs_exist():
    assert len(FLOOR_CONFIGS) == 5


def test_floor_numbers_are_ordered_one_through_five():
    assert [floor.floor_number for floor in FLOOR_CONFIGS] == [1, 2, 3, 4, 5]


def test_final_floor_is_boss():
    assert FLOOR_CONFIGS[-1].is_boss
    assert not any(floor.is_boss for floor in FLOOR_CONFIGS[:-1])


def test_every_floor_has_positive_economy_values():
    for floor in FLOOR_CONFIGS:
        assert floor.buy_in > 0
        assert floor.player_starting_stack > 0
        assert floor.blinds.small_blind > 0
        assert floor.blinds.big_blind > 0
        assert floor.win_target > 0


def test_opponent_count_makes_three_to_five_total_players():
    for floor in FLOOR_CONFIGS:
        assert 3 <= floor.total_players_min <= 5
        assert 3 <= floor.total_players_max <= 5
        assert floor.total_players_min <= floor.total_players_max
