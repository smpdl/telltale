from telltale.poker import native


def test_same_seed_gives_same_equity_result():
    first = native.estimate_equity(["Ah", "Ad"], [], 1, iterations=200, seed=7)
    second = native.estimate_equity(["Ah", "Ad"], [], 1, iterations=200, seed=7)

    assert first == second


def test_different_seed_remains_in_probability_range():
    result = native.estimate_equity(["Ah", "Kd"], ["Qs", "Jh", "2c"], 2, iterations=150, seed=8)

    assert 0.0 <= result.win_probability <= 1.0
    assert 0.0 <= result.tie_probability <= 1.0
    assert 0.0 <= result.loss_probability <= 1.0


def test_probabilities_sum_to_one():
    result = native.estimate_equity(["Ah", "Ad"], [], 2, iterations=200, seed=9)

    assert result.win_probability + result.tie_probability + result.loss_probability == 1.0


def test_pocket_aces_preflop_outperform_pocket_twos():
    aces = native.estimate_equity(["Ah", "Ad"], [], 1, iterations=500, seed=10)
    twos = native.estimate_equity(["2h", "2d"], [], 1, iterations=500, seed=10)

    assert aces.equity > twos.equity


def test_known_made_hand_on_river_is_deterministic():
    result = native.estimate_equity(
        ["As", "Ks"],
        ["Qs", "Js", "Ts", "2c", "3d"],
        1,
        iterations=50,
        seed=11,
    )

    assert result.wins == 50
    assert result.ties == 0
    assert result.losses == 0


def test_dead_cards_are_excluded_from_known_cards():
    result = native.estimate_equity(
        ["Ah", "Ad"],
        ["2c", "3d", "4h"],
        1,
        dead_cards=["Ks", "Qd"],
        iterations=100,
        seed=12,
    )

    assert result.iterations == 100


def test_duplicate_dead_cards_are_rejected():
    try:
        native.estimate_equity(["Ah", "Ad"], ["2c"], 1, dead_cards=["Ah"], iterations=10)
    except ValueError as error:
        assert "unique" in str(error)
    else:
        raise AssertionError("duplicate known cards should be rejected")


def test_range_equity_is_deterministic_under_seed():
    opponent_range = (
        native.RangeCombo("Kh", "Kd", 1.0),
        native.RangeCombo("Qs", "Qd", 0.5),
    )

    first = native.estimate_equity_vs_range(["Ah", "Ad"], [], opponent_range, iterations=200, seed=21)
    second = native.estimate_equity_vs_range(["Ah", "Ad"], [], opponent_range, iterations=200, seed=21)

    assert first == second


def test_range_equity_filters_known_conflicting_combos():
    opponent_range = (
        native.RangeCombo("Ah", "Kd", 10.0),
        native.RangeCombo("Qs", "Qd", 1.0),
    )

    result = native.estimate_equity_vs_range(["Ah", "Ad"], [], opponent_range, iterations=50, seed=22)

    assert result.iterations == 50
    assert 0.0 <= result.equity <= 1.0


def test_empty_live_range_is_rejected():
    try:
        native.estimate_equity_vs_range(
            ["Ah", "Ad"],
            [],
            (native.RangeCombo("Ah", "Kd", 1.0),),
            iterations=10,
        )
    except ValueError as error:
        assert "live combos" in str(error)
    else:
        raise AssertionError("range with no live combos should be rejected")
