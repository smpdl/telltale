from __future__ import annotations

import ctypes
from dataclasses import dataclass
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from telltale.game.cards import Card


CardLike = Card | str
_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_DIR = _ROOT / "telltale" / "native" / "poker_solver"
_BUILD_DIR = _ROOT / "build" / "native_poker_solver"
_LIB_NAME = "libtelltale_poker_solver.dylib" if sys.platform == "darwin" else "libtelltale_poker_solver.so"
_LIB_PATH = _BUILD_DIR / _LIB_NAME


@dataclass(frozen=True)
class HandRank:
    category: int
    tiebreakers: tuple[int, ...]
    label: str

    def as_tuple(self) -> tuple[int, ...]:
        return (self.category, *self.tiebreakers)


@dataclass(frozen=True)
class EquityResult:
    wins: int
    ties: int
    losses: int
    iterations: int
    win_probability: float
    tie_probability: float
    loss_probability: float

    @property
    def equity(self) -> float:
        return self.win_probability + (self.tie_probability * 0.5)


@dataclass(frozen=True)
class RangeCombo:
    first: CardLike
    second: CardLike
    weight: float = 1.0


@dataclass(frozen=True)
class DecisionFeatures:
    street: str
    hero_equity: float
    pot_size: int
    amount_to_call: int
    pot_odds: float
    stack_to_pot_ratio: float
    players_remaining: int
    can_check: bool
    legal_actions: tuple[str, ...]
    hero_stack: int = 0
    minimum_raise_amount: int = 1
    board_texture: str = "dry"
    street_action_count: int = 0
    previous_aggression_count: int = 0


@dataclass(frozen=True)
class PolicyRecommendation:
    probabilities: dict[str, float]
    suggested_action: str
    suggested_amount: int
    equity: float
    pot_odds: float
    confidence: float
    explanation: str
    risk_label: str = "low"
    board_texture: str = "dry"
    decision_margin: float = 0.0
    amount_options: dict[str, int] | None = None
    hand_strength_bucket: str = "medium"
    spr_bucket: str = "medium"
    abstract_actions: tuple[str, ...] = ()


class NativePokerSolver:
    def estimate_equity(
        self,
        hero_cards: Sequence[CardLike],
        board_cards: Sequence[CardLike] = (),
        num_opponents: int = 1,
        dead_cards: Sequence[CardLike] | None = None,
        iterations: int = 1000,
        seed: int | str | bytes | None = None,
        opponent_count: int | None = None,
        simulations: int | None = None,
    ) -> EquityResult:
        if opponent_count is not None:
            num_opponents = opponent_count
        if simulations is not None:
            iterations = simulations
        return estimate_equity(
            hero_cards=hero_cards,
            board_cards=board_cards,
            num_opponents=num_opponents,
            dead_cards=dead_cards,
            iterations=iterations,
            seed=seed,
        )

    def estimate_equity_vs_range(
        self,
        hero_cards: Sequence[CardLike],
        board_cards: Sequence[CardLike],
        opponent_range: Sequence[RangeCombo],
        dead_cards: Sequence[CardLike] | None = None,
        iterations: int = 1000,
        seed: int | str | bytes | None = None,
    ) -> EquityResult:
        return estimate_equity_vs_range(
            hero_cards=hero_cards,
            board_cards=board_cards,
            opponent_range=opponent_range,
            dead_cards=dead_cards,
            iterations=iterations,
            seed=seed,
        )


def native_available() -> bool:
    try:
        _load_library()
    except RuntimeError:
        return False
    return True


def evaluate_7(cards: Sequence[CardLike]) -> HandRank:
    data = _call_json("telltale_evaluate7", _cards_csv(cards))
    return HandRank(data["category"], tuple(data["tiebreakers"]), data["label"])


def compare_hands(cards_a: Sequence[CardLike], cards_b: Sequence[CardLike]) -> int:
    data = _call_json("telltale_compare7", _cards_csv(cards_a), _cards_csv(cards_b))
    return int(data["comparison"])


def estimate_equity(
    hero_cards: Sequence[CardLike],
    board_cards: Sequence[CardLike],
    num_opponents: int,
    dead_cards: Sequence[CardLike] | None = None,
    iterations: int = 1000,
    seed: int | str | bytes | None = None,
) -> EquityResult:
    data = _call_json(
        "telltale_estimate_equity",
        _cards_csv(hero_cards),
        _cards_csv(board_cards),
        int(num_opponents),
        _cards_csv(dead_cards or ()),
        int(iterations),
        _seed_to_uint64(seed),
    )
    return EquityResult(
        wins=data["wins"],
        ties=data["ties"],
        losses=data["losses"],
        iterations=data["iterations"],
        win_probability=data["win_probability"],
        tie_probability=data["tie_probability"],
        loss_probability=data["loss_probability"],
    )


def estimate_equity_vs_range(
    hero_cards: Sequence[CardLike],
    board_cards: Sequence[CardLike],
    opponent_range: Sequence[RangeCombo],
    dead_cards: Sequence[CardLike] | None = None,
    iterations: int = 1000,
    seed: int | str | bytes | None = None,
) -> EquityResult:
    data = _call_json(
        "telltale_estimate_equity_vs_range",
        _cards_csv(hero_cards),
        _cards_csv(board_cards),
        _range_csv(opponent_range),
        _cards_csv(dead_cards or ()),
        int(iterations),
        _seed_to_uint64(seed),
    )
    return EquityResult(
        wins=data["wins"],
        ties=data["ties"],
        losses=data["losses"],
        iterations=data["iterations"],
        win_probability=data["win_probability"],
        tie_probability=data["tie_probability"],
        loss_probability=data["loss_probability"],
    )


def recommend_action(features: DecisionFeatures) -> PolicyRecommendation:
    data = _call_json(
        "telltale_recommend_action",
        features.street,
        float(features.hero_equity),
        int(features.pot_size),
        int(features.amount_to_call),
        float(features.pot_odds),
        float(features.stack_to_pot_ratio),
        int(features.players_remaining),
        bool(features.can_check),
        ",".join(features.legal_actions),
        int(features.hero_stack),
        int(features.minimum_raise_amount),
        features.board_texture,
        int(features.street_action_count),
        int(features.previous_aggression_count),
    )
    return PolicyRecommendation(
        probabilities={str(action): float(probability) for action, probability in data["probabilities"].items()},
        suggested_action=str(data["suggested_action"]),
        suggested_amount=int(data["suggested_amount"]),
        equity=float(data["equity"]),
        pot_odds=float(data["pot_odds"]),
        confidence=float(data["confidence"]),
        explanation=str(data["explanation"]),
        risk_label=str(data.get("risk_label", "low")),
        board_texture=str(data.get("board_texture", features.board_texture)),
        decision_margin=float(data.get("decision_margin", 0.0)),
        amount_options={str(label): int(amount) for label, amount in data.get("amount_options", {}).items()},
        hand_strength_bucket=str(data.get("hand_strength_bucket", "medium")),
        spr_bucket=str(data.get("spr_bucket", "medium")),
        abstract_actions=tuple(str(action) for action in data.get("abstract_actions", ())),
    )


def _load_library() -> ctypes.CDLL:
    if not _LIB_PATH.exists() or _native_sources_are_newer():
        _build_library()
    library = ctypes.CDLL(str(_LIB_PATH))
    library.telltale_evaluate7.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    library.telltale_evaluate7.restype = ctypes.c_int
    library.telltale_compare7.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    library.telltale_compare7.restype = ctypes.c_int
    library.telltale_estimate_equity.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_ulonglong,
        ctypes.c_char_p,
        ctypes.c_int,
    ]
    library.telltale_estimate_equity.restype = ctypes.c_int
    library.telltale_estimate_equity_vs_range.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_ulonglong,
        ctypes.c_char_p,
        ctypes.c_int,
    ]
    library.telltale_estimate_equity_vs_range.restype = ctypes.c_int
    library.telltale_recommend_action.argtypes = [
        ctypes.c_char_p,
        ctypes.c_double,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_int,
        ctypes.c_bool,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
    ]
    library.telltale_recommend_action.restype = ctypes.c_int
    return library


def _build_library() -> None:
    _BUILD_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        "c++",
        "-std=c++17",
        "-O3",
        "-shared",
        "-fPIC",
        str(_SOURCE_DIR / "bindings.cpp"),
        str(_SOURCE_DIR / "evaluator.cpp"),
        str(_SOURCE_DIR / "equity.cpp"),
        str(_SOURCE_DIR / "action_policy.cpp"),
        "-o",
        str(_LIB_PATH),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as error:
        stderr = getattr(error, "stderr", "")
        raise RuntimeError(f"native poker solver build failed: {stderr}") from error


def _native_sources_are_newer() -> bool:
    if not _LIB_PATH.exists():
        return True
    library_mtime = _LIB_PATH.stat().st_mtime
    for source in _SOURCE_DIR.glob("*.*"):
        if source.suffix in {".cpp", ".hpp"} and source.stat().st_mtime > library_mtime:
            return True
    return False


def _call_json(function_name: str, *args) -> dict:
    library = _load_library()
    function = getattr(library, function_name)
    encoded_args = [_encode_arg(arg) for arg in args]
    output = ctypes.create_string_buffer(4096)
    status = function(*encoded_args, output, ctypes.sizeof(output))
    if status > ctypes.sizeof(output):
        output = ctypes.create_string_buffer(status)
        status = function(*encoded_args, output, ctypes.sizeof(output))
    if status != 0:
        raise RuntimeError(f"native call {function_name} failed with status {status}")
    data = json.loads(output.value.decode("utf-8"))
    if "error" in data:
        raise ValueError(data["error"])
    return data


def _encode_arg(value):
    if isinstance(value, str):
        return value.encode("utf-8")
    return value


def _cards_csv(cards: Sequence[CardLike]) -> str:
    return ",".join(str(card) for card in cards)


def _range_csv(opponent_range: Sequence[RangeCombo]) -> str:
    return ",".join(
        f"{combo.first}{combo.second}:{float(combo.weight)}"
        for combo in opponent_range
    )


def _seed_to_uint64(seed: int | str | bytes | None) -> int:
    if seed is None:
        return 0
    if isinstance(seed, int):
        return seed % (2**64)
    if isinstance(seed, str):
        seed = seed.encode("utf-8")
    digest = hashlib.sha256(seed).digest()
    return int.from_bytes(digest[:8], "little")
