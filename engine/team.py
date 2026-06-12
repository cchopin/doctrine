"""Team state: skills, stocks, fog of war and skill driven multipliers.

Every skill effect goes through a small helper here, so adding a skill
means adding an entry in meta/skills.py and reading it from one of these
helpers (or a new one), without touching unit or building logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .entities import BuildingType
from .world import ResourceType


@dataclass
class TeamStats:
    """Per match counters, shown in the end screen and the stats page."""

    collected: dict[ResourceType, int] = field(
        default_factory=lambda: {r: 0 for r in ResourceType}
    )
    units_trained: int = 0
    units_lost: int = 0
    units_killed: int = 0
    buildings_built: int = 0
    buildings_destroyed: int = 0
    damage_dealt: int = 0

    @property
    def total_collected(self) -> int:
        return sum(self.collected.values())


@dataclass
class TeamConfig:
    name: str
    color: str                     # renderer color key: "blue", "red", ...
    skills: dict[str, int]
    is_player: bool = False
    level: int = 1                 # gates advanced buildings


STARTING_STOCKS = {
    ResourceType.FOOD: 80,
    ResourceType.WOOD: 0,
    ResourceType.ORE: 0,
    ResourceType.CRYSTAL: 0,
}


@dataclass
class Team:
    tid: int
    name: str
    color: str
    skills: dict[str, int]
    is_player: bool = False
    level: int = 1
    alive: bool = True
    stocks: dict[ResourceType, int] = field(
        default_factory=lambda: dict(STARTING_STOCKS)
    )
    explored: set[tuple[int, int]] = field(default_factory=set)
    visible: set[tuple[int, int]] = field(default_factory=set)
    # Last known enemy buildings: bid -> (BuildingType, x, y)
    known_enemy_buildings: dict[int, tuple[BuildingType, int, int]] = field(
        default_factory=dict
    )
    stats: TeamStats = field(default_factory=TeamStats)
    # Runtime combat stance: once the squad is ready the offensive
    # continues until most of it is lost (hysteresis, avoids yo-yo).
    attacking: bool = False

    def sk(self, key: str) -> int:
        return self.skills.get(key, 0)

    # Skill driven multipliers and rates

    @property
    def speed_mult(self) -> float:
        return 1.0 + 0.10 * self.sk("exploration")

    @property
    def transporter_speed_mult(self) -> float:
        return self.speed_mult * (1.0 + 0.15 * self.sk("logistique"))

    @property
    def damage_mult(self) -> float:
        return 1.0 + 0.18 * self.sk("combat")

    @property
    def hp_mult(self) -> float:
        return 1.0 + 0.15 * self.sk("combat")

    @property
    def harvest_rate(self) -> float:
        """Resource units extracted per worker per tick."""
        return 0.7 * (1.0 + 0.20 * self.sk("recolte"))

    @property
    def pickup_rate(self) -> float:
        """Resource units loaded from a pile per tick."""
        return 2.5 * (1.0 + 0.20 * self.sk("transport"))

    @property
    def capacity_mult(self) -> float:
        return 1.0 + 0.12 * self.sk("transport")

    @property
    def build_rate(self) -> float:
        """Build work produced per worker per tick."""
        return 1.0 * (1.0 + 0.25 * self.sk("construction"))

    @property
    def trade_rate(self) -> float:
        """Food received per resource unit sold at the market."""
        return 0.4 + 0.15 * self.sk("tradeur")

    @property
    def repair_rate(self) -> int:
        """Hit points restored near buildings every repair pulse."""
        return self.sk("mecanique")

    @property
    def building_hp_mult(self) -> float:
        return 1.0 + 0.20 * self.sk("fortification")

    @property
    def sight_bonus(self) -> int:
        return self.sk("cartographie")

    @property
    def soldier_train_mult(self) -> float:
        """Multiplier applied to soldier training work (lower is faster)."""
        return 1.0 / (1.0 + 0.15 * self.sk("conscription"))

    @property
    def attack_period(self) -> int:
        """Ticks between two attacks of a unit of this team."""
        from .combat import ATTACK_PERIOD

        return max(2, round(ATTACK_PERIOD / (1.0 + 0.12 * self.sk("frenesie"))))

    @property
    def loot_food_per_kill(self) -> int:
        return 8 * self.sk("pillage")

    @property
    def loot_per_building(self) -> int:
        return 25 * self.sk("pillage")

    def can_afford(self, cost: dict[ResourceType, int]) -> bool:
        return all(self.stocks.get(r, 0) >= n for r, n in cost.items())

    def pay(self, cost: dict[ResourceType, int]) -> None:
        for r, n in cost.items():
            self.stocks[r] -= n

    def add_stock(self, rtype: ResourceType, amount: int) -> None:
        self.stocks[rtype] = self.stocks.get(rtype, 0) + amount
