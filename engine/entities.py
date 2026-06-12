"""Units and buildings: specs (declarative) and runtime instances."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .world import ResourceType


class UnitType(Enum):
    SCOUT = "scout"
    WORKER = "worker"
    TRANSPORTER = "transporter"
    SOLDIER = "soldier"


@dataclass(frozen=True)
class UnitSpec:
    symbol: str
    label_fr: str
    hp: int
    damage: int
    speed: float            # tiles per tick before skill multipliers
    capacity: int
    sight: int
    cost: dict[ResourceType, int]
    train_work: int         # ticks of training at base rate


UNIT_SPECS: dict[UnitType, UnitSpec] = {
    UnitType.SCOUT: UnitSpec(
        symbol="s", label_fr="éclaireur", hp=30, damage=2, speed=0.45,
        capacity=0, sight=8, cost={ResourceType.FOOD: 20}, train_work=50,
    ),
    UnitType.WORKER: UnitSpec(
        symbol="w", label_fr="ouvrier", hp=40, damage=3, speed=0.28,
        capacity=10, sight=5, cost={ResourceType.FOOD: 30}, train_work=60,
    ),
    UnitType.TRANSPORTER: UnitSpec(
        symbol="t", label_fr="transporteur", hp=35, damage=1, speed=0.34,
        capacity=28, sight=5,
        cost={ResourceType.FOOD: 25, ResourceType.WOOD: 10}, train_work=70,
    ),
    UnitType.SOLDIER: UnitSpec(
        symbol="S", label_fr="soldat", hp=80, damage=8, speed=0.30,
        capacity=0, sight=6,
        cost={ResourceType.FOOD: 25, ResourceType.ORE: 15}, train_work=90,
    ),
}


class UnitState(Enum):
    IDLE = "idle"
    EXPLORE = "explore"
    MOVE = "move"
    HARVEST = "harvest"
    LOAD = "load"
    DELIVER = "deliver"
    BUILD = "build"
    FIGHT = "fight"
    FLEE = "flee"


@dataclass
class Unit:
    uid: int
    team_id: int
    utype: UnitType
    x: int
    y: int
    hp: int
    max_hp: int
    state: UnitState = UnitState.IDLE
    cargo: dict[ResourceType, int] = field(default_factory=dict)
    path: list[tuple[int, int]] = field(default_factory=list)
    dest: tuple[int, int] | None = None
    move_progress: float = 0.0
    work_acc: float = 0.0           # fractional harvest/build accumulator
    attack_cooldown: int = 0
    target_unit_id: int | None = None
    target_building_id: int | None = None
    flee_until: int = 0

    @property
    def pos(self) -> tuple[int, int]:
        return (self.x, self.y)

    @property
    def spec(self) -> UnitSpec:
        return UNIT_SPECS[self.utype]

    @property
    def cargo_total(self) -> int:
        return sum(self.cargo.values())

    def clear_task(self) -> None:
        self.path = []
        self.dest = None
        self.target_unit_id = None
        self.target_building_id = None


class BuildingType(Enum):
    HQ = "hq"
    WAREHOUSE = "warehouse"
    BARRACKS = "barracks"
    MARKET = "market"
    TOWER = "tower"


@dataclass(frozen=True)
class BuildingSpec:
    symbol: str
    label_fr: str
    hp: int
    sight: int
    cost: dict[ResourceType, int]
    build_work: int                  # worker ticks at base rate
    requires_skill: str | None = None


BUILDING_SPECS: dict[BuildingType, BuildingSpec] = {
    BuildingType.HQ: BuildingSpec(
        symbol="B", label_fr="QG", hp=500, sight=7, cost={}, build_work=0,
    ),
    BuildingType.WAREHOUSE: BuildingSpec(
        symbol="E", label_fr="entrepôt", hp=150, sight=4,
        cost={ResourceType.WOOD: 60}, build_work=50,
    ),
    BuildingType.BARRACKS: BuildingSpec(
        symbol="C", label_fr="caserne", hp=200, sight=4,
        cost={ResourceType.WOOD: 40, ResourceType.ORE: 40}, build_work=70,
    ),
    BuildingType.MARKET: BuildingSpec(
        symbol="M", label_fr="marché", hp=150, sight=4,
        cost={ResourceType.WOOD: 50, ResourceType.CRYSTAL: 20}, build_work=60,
    ),
    BuildingType.TOWER: BuildingSpec(
        symbol="Y", label_fr="tour de garde", hp=180, sight=10,
        cost={ResourceType.ORE: 50, ResourceType.CRYSTAL: 15}, build_work=60,
        requires_skill="science",
    ),
}

# Buildings able to shoot back: btype -> (range, damage, period in ticks)
BUILDING_ATTACKS: dict[BuildingType, tuple[int, int, int]] = {
    BuildingType.TOWER: (3, 5, 6),
    BuildingType.HQ: (2, 3, 6),
}


@dataclass
class Building:
    bid: int
    team_id: int
    btype: BuildingType
    x: int
    y: int
    hp: int
    max_hp: int
    complete: bool = False
    progress: float = 0.0
    training: UnitType | None = None
    training_left: float = 0.0
    attack_cooldown: int = 0

    @property
    def pos(self) -> tuple[int, int]:
        return (self.x, self.y)

    @property
    def spec(self) -> BuildingSpec:
        return BUILDING_SPECS[self.btype]
