import time

from telltale.poker import native


def test_native_backend_is_available_when_build_tools_are_present():
    assert native.native_available()


def test_thousand_iteration_equity_estimate_is_interactive_speed():
    started = time.perf_counter()

    result = native.estimate_equity(["Ah", "Ad"], [], 2, iterations=1000, seed=101)

    elapsed = time.perf_counter() - started
    assert result.iterations == 1000
    assert elapsed < 3.0
