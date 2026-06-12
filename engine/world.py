"""Map grid, terrain types and resource deposits.

The engine is renderer agnostic: this module knows nothing about curses.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class Terrain(Enum):
    PLAIN = "plain"
    FOREST = "forest"
    MOUNTAIN = "mountain"
    WATER = "water"


# Movement cost per tile, infinity means impassable.
TERRAIN_COST: dict[Terrain, float] = {
    Terrain.PLAIN: 1.0,
    Terrain.FOREST: 1.6,
    Terrain.MOUNTAIN: 2.6,
    Terrain.WATER: math.inf,
}


class ResourceType(Enum):
    ORE = "ore"
    WOOD = "wood"
    CRYSTAL = "crystal"
    FOOD = "food"


RESOURCE_LABEL_FR: dict[ResourceType, str] = {
    ResourceType.ORE: "minerai",
    ResourceType.WOOD: "bois",
    ResourceType.CRYSTAL: "cristal",
    ResourceType.FOOD: "nourriture",
}


@dataclass
class Deposit:
    x: int
    y: int
    rtype: ResourceType
    amount: int     # still in the ground
    pile: int = 0   # harvested, waiting for pickup on the tile

    @property
    def pos(self) -> tuple[int, int]:
        return (self.x, self.y)

    @property
    def depleted(self) -> bool:
        return self.amount <= 0 and self.pile <= 0


class GameMap:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.terrain: list[list[Terrain]] = [
            [Terrain.PLAIN] * width for _ in range(height)
        ]
        self.deposits: dict[tuple[int, int], Deposit] = {}

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def get(self, x: int, y: int) -> Terrain:
        return self.terrain[y][x]

    def set(self, x: int, y: int, terrain: Terrain) -> None:
        self.terrain[y][x] = terrain

    def is_walkable(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and self.terrain[y][x] is not Terrain.WATER

    def cost(self, x: int, y: int) -> float:
        return TERRAIN_COST[self.terrain[y][x]]

    def neighbors4(self, x: int, y: int):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if self.is_walkable(nx, ny):
                yield nx, ny

    def deposit_at(self, x: int, y: int) -> Deposit | None:
        return self.deposits.get((x, y))
