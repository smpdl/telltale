"""
This module defines the floors that can be played in the game.

Floors are the different levels of the game.
Each floor has a name, a buy-in, a starting stack, a number of opponents, and a number of rewards.
The floors are ordered from level 1 to level 5 (inclusive).
Level 5 is the final level and is the boss fight.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BlindStructure:
    """
    Defines the blind structure (the amount of chips that each player must 
    post as the small blind and big blind) for a given floor.
    """
    small_blind: int
    big_blind: int
    # escalation interval is the number of hands that must pass before the blinds are increased.
    # this is used to create a dynamic blind structure that increases over time. 
    escalation_interval_hands: int = 0 


@dataclass(frozen=True)
class FloorConfig:
    floor_number: int
    name: str
    buy_in: int
    player_starting_stack: int # the number of chips the player starts with at the beginning of the floor
    opponent_count_min: int
    opponent_count_max: int
    blinds: BlindStructure
    win_target: int # the number of chips the player must have at the end of the floor to win the floor
    reward_choices_count: int 
    is_boss: bool = False

    @property
    def total_players_min(self) -> int:
        return self.opponent_count_min + 1

    @property
    def total_players_max(self) -> int:
        return self.opponent_count_max + 1


FLOOR_CONFIGS: tuple[FloorConfig, ...] = (
    FloorConfig(
        floor_number=1,
        name="Level 1 (Tutorial)",
        buy_in=40,
        player_starting_stack=100,
        opponent_count_min=2,
        opponent_count_max=2,
        blinds=BlindStructure(small_blind=2, big_blind=4),
        win_target=160,
        reward_choices_count=3,
    ),
    FloorConfig(
        floor_number=2,
        name="Level 2",
        buy_in=70,
        player_starting_stack=140,
        opponent_count_min=2,
        opponent_count_max=3,
        blinds=BlindStructure(small_blind=3, big_blind=6),
        win_target=225,
        reward_choices_count=3,
    ),
    FloorConfig(
        floor_number=3,
        name="Level 3",
        buy_in=110,
        player_starting_stack=180,
        opponent_count_min=3,
        opponent_count_max=3,
        blinds=BlindStructure(small_blind=5, big_blind=10, escalation_interval_hands=8),
        win_target=300,
        reward_choices_count=3,
    ),
    FloorConfig(
        floor_number=4,
        name="Level 4",
        buy_in=160,
        player_starting_stack=230,
        opponent_count_min=3,
        opponent_count_max=4,
        blinds=BlindStructure(small_blind=8, big_blind=16, escalation_interval_hands=6),
        win_target=390,
        reward_choices_count=3,
    ),
    FloorConfig(
        floor_number=5,
        name="Level 5 (Final)",
        buy_in=240,
        player_starting_stack=320,
        opponent_count_min=4,
        opponent_count_max=4,
        blinds=BlindStructure(small_blind=12, big_blind=24, escalation_interval_hands=5),
        win_target=560,
        reward_choices_count=0,
        is_boss=True,
    ),
)

def get_floor_config(floor_index: int) -> FloorConfig:
    if floor_index < 0 or floor_index >= len(FLOOR_CONFIGS):
        raise ValueError(f"invalid floor index: {floor_index}")
    return FLOOR_CONFIGS[floor_index]
