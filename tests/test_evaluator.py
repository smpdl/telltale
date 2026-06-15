from telltale.poker import native


def rank(cards: list[str]):
    return native.evaluate_7(cards).as_tuple()


def test_straight_flush_beats_four_of_a_kind():
    assert rank(["As", "Ks", "Qs", "Js", "Ts", "2c", "3d"]) > rank(["Ah", "Ad", "Ac", "As", "Kh", "2c", "3d"])


def test_four_of_a_kind_beats_full_house():
    assert rank(["Ah", "Ad", "Ac", "As", "Kh", "2c", "3d"]) > rank(["Kh", "Kd", "Kc", "2s", "2h", "3c", "4d"])


def test_full_house_beats_flush():
    assert rank(["Kh", "Kd", "Kc", "2s", "2h", "3c", "4d"]) > rank(["Ah", "Th", "8h", "6h", "4h", "2c", "3d"])


def test_flush_beats_straight():
    assert rank(["Ah", "Th", "8h", "6h", "4h", "2c", "3d"]) > rank(["9c", "8d", "7h", "6s", "5c", "2h", "3d"])


def test_straight_beats_trips():
    assert rank(["9c", "8d", "7h", "6s", "5c", "2h", "3d"]) > rank(["Qc", "Qd", "Qh", "9s", "5c", "2h", "3d"])


def test_trips_beats_two_pair():
    assert rank(["Qc", "Qd", "Qh", "9s", "5c", "2h", "3d"]) > rank(["Ac", "Ad", "Kh", "Ks", "5c", "2h", "3d"])


def test_two_pair_beats_one_pair():
    assert rank(["Ac", "Ad", "Kh", "Ks", "5c", "2h", "3d"]) > rank(["Ac", "Ad", "Qh", "9s", "5c", "2h", "3d"])


def test_one_pair_beats_high_card():
    assert rank(["Ac", "Ad", "Qh", "9s", "5c", "2h", "3d"]) > rank(["Ac", "Kd", "Qh", "9s", "5c", "2h", "3d"])


def test_wheel_straight_works():
    assert native.evaluate_7(["Ac", "2d", "3h", "4s", "5c", "Kh", "Qd"]).label == "straight"
    assert native.evaluate_7(["Ac", "2d", "3h", "4s", "5c", "Kh", "Qd"]).tiebreakers == (5,)


def test_best_five_of_seven_cards_are_selected():
    best = native.evaluate_7(["Ah", "Ad", "Ac", "Ks", "Kh", "2c", "3d"])

    assert best.label == "full house"
    assert best.tiebreakers == (14, 13)
