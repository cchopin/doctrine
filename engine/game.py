"""Match simulation: tick orchestration, visibility, economy and victory.

The Game class is pure logic and never imports the renderer.
"""
from __future__ import annotations

import random
from collections import deque
from functools import lru_cache

from . import ai
from .entities import (
    BUILDING_ATTACKS,
    BUILDING_SPECS,
    Building,
    BuildingType,
    UNIT_SPECS,
    Unit,
    UnitType,
)
from .pathfinding import PathCache, find_nearest
from .team import Team, TeamConfig
from .world import GameMap, ResourceType, RESOURCE_LABEL_FR

TICKS_PER_SECOND = 8
DEFAULT_TIME_LIMIT_TICKS = 20 * 60 * TICKS_PER_SECOND

STARTING_UNITS = (
    UnitType.WORKER,
    UnitType.WORKER,
    UnitType.SCOUT,
    UnitType.TRANSPORTER,
    UnitType.SOLDIER,
)

MACRO_PERIOD = 12
MARKET_PERIOD = 40
MARKET_KEEP = 80          # stock floor kept when selling surplus
MARKET_BATCH = 20
REPAIR_PERIOD = 10
REPAIR_RANGE = 6
ESPIONAGE_PERIOD = 480
ESPIONAGE_RADIUS = 5


@lru_cache(maxsize=32)
def _disk_offsets(radius: int) -> tuple[tuple[int, int], ...]:
    r2 = radius * radius
    return tuple(
        (dx, dy)
        for dx in range(-radius, radius + 1)
        for dy in range(-radius, radius + 1)
        if dx * dx + dy * dy <= r2
    )


class Game:
    def __init__(
        self,
        gmap: GameMap,
        base_positions: list[tuple[int, int]],
        team_configs: list[TeamConfig],
        seed: int | None = None,
        time_limit_ticks: int = DEFAULT_TIME_LIMIT_TICKS,
    ):
        assert len(base_positions) >= len(team_configs)
        self.map = gmap
        self.rng = random.Random(seed)
        self.time_limit_ticks = time_limit_ticks
        self.tick_count = 0
        self.finished = False
        self.winner: int | None = None
        self.end_reason = ""
        self.events: deque[tuple[int, str]] = deque(maxlen=200)
        self.path_cache = PathCache()
        self._next_id = 1

        self.teams: dict[int, Team] = {}
        self.units: dict[int, Unit] = {}
        self.buildings: dict[int, Building] = {}

        for tid, config in enumerate(team_configs):
            team = Team(
                tid=tid,
                name=config.name,
                color=config.color,
                skills=dict(config.skills),
                is_player=config.is_player,
                level=config.level,
            )
            self.teams[tid] = team
            bx, by = base_positions[tid]
            hq_spec = BUILDING_SPECS[BuildingType.HQ]
            hq_hp = round(hq_spec.hp * team.building_hp_mult)
            hq_id = self._new_id()
            self.buildings[hq_id] = Building(
                bid=hq_id,
                team_id=tid,
                btype=BuildingType.HQ,
                x=bx,
                y=by,
                hp=hq_hp,
                max_hp=hq_hp,
                complete=True,
            )
            for utype in STARTING_UNITS:
                self.spawn_unit(team, utype, (bx, by))
        for team in self.teams.values():
            self._update_visibility(team)

    # Identifiers and events

    def _new_id(self) -> int:
        nid = self._next_id
        self._next_id += 1
        return nid

    def add_event(self, message: str) -> None:
        self.events.append((self.tick_count, message))

    # Entity helpers used by the behavior module

    def units_of(self, tid: int) -> list[Unit]:
        return [u for u in self.units.values() if u.team_id == tid]

    def buildings_of(self, tid: int, only_complete: bool = False) -> list[Building]:
        return [
            b
            for b in self.buildings.values()
            if b.team_id == tid and (b.complete or not only_complete)
        ]

    def hq(self, team: Team) -> Building | None:
        for building in self.buildings.values():
            if building.team_id == team.tid and building.btype is BuildingType.HQ:
                return building
        return None

    def nearest_depot(self, team: Team, pos: tuple[int, int]) -> Building | None:
        depots = [
            b
            for b in self.buildings_of(team.tid, only_complete=True)
            if b.btype in (BuildingType.HQ, BuildingType.WAREHOUSE)
        ]
        if not depots:
            return None
        return min(
            depots, key=lambda b: abs(b.x - pos[0]) + abs(b.y - pos[1])
        )

    def known_deposits(self, team: Team):
        return [
            dep
            for pos, dep in self.map.deposits.items()
            if pos in team.explored and not dep.depleted
        ]

    def unit_counts(self, team: Team) -> dict[UnitType, int]:
        counts: dict[UnitType, int] = {}
        for unit in self.units.values():
            if unit.team_id == team.tid:
                counts[unit.utype] = counts.get(unit.utype, 0) + 1
        return counts

    def construction_sites(self, team: Team) -> list[Building]:
        return [
            b
            for b in self.buildings.values()
            if b.team_id == team.tid and not b.complete
        ]

    def builders_on(self, bid: int) -> int:
        return sum(
            1 for u in self.units.values() if u.target_building_id == bid
        )

    def free_building_spot(self, anchor: tuple[int, int]) -> tuple[int, int] | None:
        occupied = {b.pos for b in self.buildings.values()}

        def is_free(pos: tuple[int, int]) -> bool:
            return pos not in occupied and pos not in self.map.deposits

        return find_nearest(self.map, anchor, is_free, max_radius=12)

    def start_construction(
        self, team: Team, btype: BuildingType, pos: tuple[int, int]
    ) -> Building:
        spec = BUILDING_SPECS[btype]
        max_hp = round(spec.hp * team.building_hp_mult)
        building = Building(
            bid=self._new_id(),
            team_id=team.tid,
            btype=btype,
            x=pos[0],
            y=pos[1],
            hp=max(1, max_hp // 5),
            max_hp=max_hp,
            complete=False,
        )
        self.buildings[building.bid] = building
        return building

    def spawn_unit(
        self, team: Team, utype: UnitType, near: tuple[int, int]
    ) -> Unit | None:
        occupied = {u.pos for u in self.units.values()}

        def is_free(pos: tuple[int, int]) -> bool:
            return pos not in occupied

        pos = find_nearest(self.map, near, is_free, max_radius=8)
        if pos is None:
            return None
        spec = UNIT_SPECS[utype]
        hp = round(spec.hp * team.hp_mult)
        unit = Unit(
            uid=self._new_id(),
            team_id=team.tid,
            utype=utype,
            x=pos[0],
            y=pos[1],
            hp=hp,
            max_hp=hp,
        )
        self.units[unit.uid] = unit
        return unit

    # Main loop

    def tick(self) -> None:
        if self.finished:
            return
        self.tick_count += 1
        if self.tick_count % 2 == 0:
            for team in self.teams.values():
                if team.alive:
                    self._update_visibility(team)
        for unit in list(self.units.values()):
            if unit.uid in self.units and self.teams[unit.team_id].alive:
                ai.update_unit(self, unit)
        for building in list(self.buildings.values()):
            if building.bid in self.buildings:
                self._update_building(building)
        if self.tick_count % MACRO_PERIOD == 0:
            for team in self.teams.values():
                ai.update_team_macro(self, team)
        if self.tick_count % MARKET_PERIOD == 0:
            self._run_markets()
        if self.tick_count % REPAIR_PERIOD == 0:
            self._run_repairs()
        if self.tick_count % ESPIONAGE_PERIOD == 0:
            self._run_espionage()
        self._remove_depleted_deposits()
        self._cleanup_dead()
        self._check_end()

    # Building updates: training queues and tower fire

    def _update_building(self, building: Building) -> None:
        if not building.complete:
            return
        if building.training is not None:
            building.training_left -= 1
            if building.training_left <= 0:
                team = self.teams[building.team_id]
                utype = building.training
                building.training = None
                unit = self.spawn_unit(team, utype, building.pos)
                if unit is not None:
                    team.stats.units_trained += 1
                    self.add_event(
                        f"Unité prête: {unit.spec.label_fr} ({team.name})"
                    )
        if building.btype in BUILDING_ATTACKS:
            self._building_fire(building)

    def _building_fire(self, building: Building) -> None:
        attack_range, damage, period = BUILDING_ATTACKS[building.btype]
        if building.attack_cooldown > 0:
            building.attack_cooldown -= 1
            return
        target = None
        best = None
        for unit in self.units.values():
            if unit.team_id == building.team_id:
                continue
            dist = max(abs(unit.x - building.x), abs(unit.y - building.y))
            if dist <= attack_range and (best is None or dist < best):
                target, best = unit, dist
        if target is not None:
            target.hp -= damage
            target.last_hit_team = building.team_id
            self.teams[building.team_id].stats.damage_dealt += damage
            building.attack_cooldown = period
            ai.on_damaged(self, target)

    # Periodic systems

    def _run_markets(self) -> None:
        for team in self.teams.values():
            if not team.alive:
                continue
            has_market = any(
                b.btype is BuildingType.MARKET
                for b in self.buildings_of(team.tid, only_complete=True)
            )
            if not has_market:
                continue
            rtype = max(
                (r for r in ResourceType if r is not ResourceType.FOOD),
                key=lambda r: team.stocks.get(r, 0),
            )
            surplus = team.stocks.get(rtype, 0) - MARKET_KEEP
            if surplus <= 0:
                continue
            sold = min(MARKET_BATCH, surplus)
            gained = int(sold * team.trade_rate)
            if gained <= 0:
                continue
            team.stocks[rtype] -= sold
            team.add_stock(ResourceType.FOOD, gained)
            self.add_event(
                f"Marché: {sold} {RESOURCE_LABEL_FR[rtype]} vendus ({team.name})"
            )

    def _run_repairs(self) -> None:
        for team in self.teams.values():
            rate = team.repair_rate
            if rate <= 0 or not team.alive:
                continue
            anchors = [
                b.pos for b in self.buildings_of(team.tid, only_complete=True)
            ]
            if not anchors:
                continue
            for unit in self.units.values():
                if unit.team_id != team.tid or unit.hp >= unit.max_hp:
                    continue
                near_base = any(
                    max(abs(unit.x - x), abs(unit.y - y)) <= REPAIR_RANGE
                    for x, y in anchors
                )
                if near_base:
                    unit.hp = min(unit.max_hp, unit.hp + rate)

    def _run_espionage(self) -> None:
        for team in self.teams.values():
            if team.sk("espionnage") <= 0 or not team.alive:
                continue
            enemy_buildings = [
                b for b in self.buildings.values() if b.team_id != team.tid
            ]
            if not enemy_buildings:
                continue
            target = self.rng.choice(enemy_buildings)
            for dx, dy in _disk_offsets(ESPIONAGE_RADIUS):
                pos = (target.x + dx, target.y + dy)
                if self.map.in_bounds(*pos):
                    team.explored.add(pos)
            team.known_enemy_buildings[target.bid] = (
                target.btype, target.x, target.y
            )
            self.add_event(f"Espionnage: zone adverse révélée ({team.name})")

    # Cleanup and end conditions

    def _remove_depleted_deposits(self) -> None:
        depleted = [
            pos for pos, dep in self.map.deposits.items() if dep.depleted
        ]
        for pos in depleted:
            del self.map.deposits[pos]

    def _cleanup_dead(self) -> None:
        for uid in [u.uid for u in self.units.values() if u.hp <= 0]:
            unit = self.units.pop(uid)
            team = self.teams[unit.team_id]
            team.stats.units_lost += 1
            self.add_event(
                f"Unité perdue: {unit.spec.label_fr} ({team.name})"
            )
            if unit.last_hit_team is not None:
                killer = self.teams[unit.last_hit_team]
                killer.stats.units_killed += 1
                loot = killer.loot_food_per_kill
                if loot > 0:
                    killer.add_stock(ResourceType.FOOD, loot)
        for bid in [b.bid for b in self.buildings.values() if b.hp <= 0]:
            building = self.buildings.pop(bid)
            team = self.teams[building.team_id]
            self.add_event(
                f"Bâtiment détruit: {building.spec.label_fr} ({team.name})"
            )
            if building.last_hit_team is not None:
                killer = self.teams[building.last_hit_team]
                killer.stats.buildings_destroyed += 1
                loot = killer.loot_per_building
                if loot > 0:
                    killer.add_stock(ResourceType.WOOD, loot // 2)
                    killer.add_stock(ResourceType.ORE, loot - loot // 2)
            if building.btype is BuildingType.HQ:
                team.alive = False
                self.add_event(f"Le QG de l'équipe {team.name} est détruit !")

    def _check_end(self) -> None:
        if self.finished:
            return
        alive = [t for t in self.teams.values() if t.alive]
        if len(alive) <= 1:
            self.finished = True
            self.winner = alive[0].tid if alive else None
            self.end_reason = "destruction"
            if self.winner is not None:
                self.add_event(f"Victoire de l'équipe {alive[0].name} !")
            return
        if self.tick_count >= self.time_limit_ticks:
            self.finished = True
            self.end_reason = "temps"
            scores = {t.tid: self.score(t) for t in alive}
            best = max(scores.values())
            leaders = [tid for tid, s in scores.items() if s == best]
            self.winner = leaders[0] if len(leaders) == 1 else None
            if self.winner is not None:
                name = self.teams[self.winner].name
                self.add_event(
                    f"Temps écoulé, victoire aux points: équipe {name}"
                )
            else:
                self.add_event("Temps écoulé, égalité")

    def score(self, team: Team) -> int:
        units = len(self.units_of(team.tid))
        buildings = len(self.buildings_of(team.tid, only_complete=True))
        return (
            sum(team.stocks.values())
            + 5 * units
            + 20 * buildings
            + len(team.explored) // 50
        )

    # Fog of war

    def _update_visibility(self, team: Team) -> None:
        visible: set[tuple[int, int]] = set()
        bonus = team.sight_bonus
        sources: list[tuple[int, int, int]] = [
            (u.x, u.y, u.spec.sight + bonus)
            for u in self.units.values()
            if u.team_id == team.tid
        ]
        sources.extend(
            (b.x, b.y, b.spec.sight + bonus)
            for b in self.buildings.values()
            if b.team_id == team.tid and b.complete
        )
        in_bounds = self.map.in_bounds
        for x, y, sight in sources:
            for dx, dy in _disk_offsets(sight):
                pos = (x + dx, y + dy)
                if in_bounds(*pos):
                    visible.add(pos)
        team.visible = visible
        team.explored |= visible
        for building in self.buildings.values():
            if building.team_id != team.tid and building.pos in visible:
                team.known_enemy_buildings[building.bid] = (
                    building.btype, building.x, building.y
                )
        for bid, (_, x, y) in list(team.known_enemy_buildings.items()):
            if (x, y) in visible and bid not in self.buildings:
                del team.known_enemy_buildings[bid]

    # Convenience for the UI

    @property
    def elapsed_seconds(self) -> float:
        return self.tick_count / TICKS_PER_SECOND
