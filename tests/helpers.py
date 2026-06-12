"""Shared fixtures: a small flat map and a two team game."""
from __future__ import annotations

from engine.game import Game
from engine.team import TeamConfig
from engine.world import GameMap


def make_game(
    skills_a: dict[str, int] | None = None,
    skills_b: dict[str, int] | None = None,
    width: int = 30,
    height: int = 20,
) -> Game:
    gmap = GameMap(width, height)
    configs = [
        TeamConfig("A", "blue", skills_a or {}, is_player=True),
        TeamConfig("B", "red", skills_b or {}),
    ]
    bases = [(2, height // 2), (width - 3, height // 2)]
    return Game(gmap, bases, configs, seed=1)


def clear_units(game: Game) -> None:
    game.units.clear()
