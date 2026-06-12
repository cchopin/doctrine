"""Unit behaviors (state machine) and team level macro decisions.

All randomness goes through game.rng so a seeded match is deterministic.
"""
from __future__ import annotations

import random

from meta.skills import SKILLS, unlocked_skills

from . import combat
from .entities import (
    BUILDING_SPECS,
    Building,
    BuildingType,
    Unit,
    UnitState,
    UnitType,
)
from .pathfinding import find_nearest
from .team import Team
from .world import Deposit, ResourceType, RESOURCE_LABEL_FR

FLEE_DURATION = 60        # ticks a damaged civilian keeps running
MAX_BUILDERS_PER_SITE = 2
HQ_SOLDIER_WORK_PENALTY = 1.5


# Movement helpers

def _set_destination(game, unit: Unit, dest: tuple[int, int]) -> bool:
    """Compute a path to dest unless one is already in progress."""
    if unit.dest == dest and (unit.path or unit.pos == dest):
        return True
    path = game.path_cache.path(game.map, unit.pos, dest)
    if path is None:
        unit.clear_task()
        return False
    unit.dest = dest
    unit.path = path
    return True


def _follow_path(game, unit: Unit, speed: float) -> bool:
    """Advance along the path, return True when the destination is reached."""
    if not unit.path:
        return unit.dest is None or unit.pos == unit.dest
    unit.move_progress += speed
    while unit.path:
        nx, ny = unit.path[0]
        step_cost = game.map.cost(nx, ny)
        if unit.move_progress < step_cost:
            break
        unit.move_progress -= step_cost
        unit.x, unit.y = unit.path.pop(0)
    if not unit.path:
        unit.move_progress = 0.0
        return True
    return False


def _near(unit: Unit, pos: tuple[int, int], dist: int = 1) -> bool:
    return max(abs(unit.x - pos[0]), abs(unit.y - pos[1])) <= dist


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


# Entry point

def update_unit(game, unit: Unit) -> None:
    team = game.teams[unit.team_id]
    if unit.attack_cooldown > 0:
        unit.attack_cooldown -= 1
    if unit.utype is not UnitType.SOLDIER and unit.flee_until > game.tick_count:
        _update_flee(game, unit, team)
        return
    if unit.utype is UnitType.SCOUT:
        _update_scout(game, unit, team)
    elif unit.utype is UnitType.WORKER:
        _update_worker(game, unit, team)
    elif unit.utype is UnitType.TRANSPORTER:
        _update_transporter(game, unit, team)
    else:
        _update_soldier(game, unit, team)


def on_damaged(game, victim: Unit) -> None:
    """Civilians drop their task and run home when hit."""
    if victim.utype is UnitType.SOLDIER:
        return
    if victim.flee_until <= game.tick_count:
        victim.clear_task()
    victim.flee_until = game.tick_count + FLEE_DURATION
    victim.state = UnitState.FLEE


def _update_flee(game, unit: Unit, team: Team) -> None:
    unit.state = UnitState.FLEE
    hq = game.hq(team)
    if hq is None or _near(unit, hq.pos, 2):
        return
    _set_destination(game, unit, hq.pos)
    _follow_path(game, unit, unit.spec.speed * team.speed_mult * 1.2)


# Exploration (shared by scouts, idle soldiers and jobless workers)

def _explore_step(game, unit: Unit, team: Team, speed: float) -> None:
    unit.state = UnitState.EXPLORE
    if unit.path:
        _follow_path(game, unit, speed)
        return
    gmap = game.map
    for _ in range(40):
        x = game.rng.randrange(gmap.width)
        y = game.rng.randrange(gmap.height)
        if not gmap.is_walkable(x, y):
            continue
        if (x, y) in team.explored:
            continue
        if _set_destination(game, unit, (x, y)):
            return
    # Everything sampled is known: wander somewhere explored.
    spots = [p for p in team.explored if gmap.is_walkable(*p)]
    if spots:
        _set_destination(game, unit, game.rng.choice(spots))


def _update_scout(game, unit: Unit, team: Team) -> None:
    _explore_step(game, unit, team, unit.spec.speed * team.speed_mult)


# Worker: build first, then harvest, otherwise explore

def _update_worker(game, unit: Unit, team: Team) -> None:
    speed = unit.spec.speed * team.speed_mult
    site = _pick_construction_site(game, unit, team)
    if site is not None:
        _work_on_site(game, unit, team, site, speed)
        return
    unit.target_building_id = None
    if unit.cargo_total > 0:
        _deliver(game, unit, team, speed)
        return
    deposit = _pick_deposit(game, unit, team, need_amount=True)
    if deposit is not None:
        if unit.pos == deposit.pos:
            _harvest(game, unit, team, deposit)
        else:
            unit.state = UnitState.MOVE
            if not _set_destination(game, unit, deposit.pos):
                return
            _follow_path(game, unit, speed)
        return
    _explore_step(game, unit, team, speed)


def _pick_construction_site(game, unit: Unit, team: Team) -> Building | None:
    sites = game.construction_sites(team)
    if not sites:
        return None
    if unit.target_building_id is not None:
        for site in sites:
            if site.bid == unit.target_building_id:
                return site
    sites.sort(key=lambda b: _manhattan(unit.pos, b.pos))
    for site in sites:
        if game.builders_on(site.bid) < MAX_BUILDERS_PER_SITE:
            return site
    return None


def _work_on_site(game, unit: Unit, team: Team, site: Building, speed: float) -> None:
    unit.state = UnitState.BUILD
    unit.target_building_id = site.bid
    if _near(unit, site.pos, 1):
        unit.path = []
        unit.dest = None
        site.progress += team.build_rate
        if site.progress >= site.spec.build_work:
            site.complete = True
            site.hp = site.max_hp
            unit.target_building_id = None
            team.stats.buildings_built += 1
            game.add_event(
                f"Bâtiment terminé: {site.spec.label_fr} ({team.name})"
            )
        return
    if _set_destination(game, unit, site.pos):
        _follow_path(game, unit, speed)


def _pick_deposit(
    game, unit: Unit, team: Team, need_amount: bool
) -> Deposit | None:
    # Stick to the current target while it stays valid.
    if unit.dest is not None:
        current = game.map.deposits.get(unit.dest)
        if current is not None and (
            (need_amount and current.amount > 0)
            or (not need_amount and current.pile > 0)
        ):
            return current
    best = None
    best_score = None
    for dep in game.known_deposits(team):
        if need_amount:
            if dep.amount <= 0:
                continue
            score = -_manhattan(unit.pos, dep.pos)
        else:
            if dep.pile <= 0:
                continue
            score = dep.pile - 1.5 * _manhattan(unit.pos, dep.pos)
        if best_score is None or score > best_score:
            best, best_score = dep, score
    return best


def _harvest(game, unit: Unit, team: Team, deposit: Deposit) -> None:
    unit.state = UnitState.HARVEST
    unit.work_acc += team.harvest_rate
    take = int(unit.work_acc)
    if take <= 0:
        return
    unit.work_acc -= take
    take = min(take, deposit.amount)
    deposit.amount -= take
    deposit.pile += take
    if deposit.amount <= 0:
        game.add_event(
            f"Gisement de {RESOURCE_LABEL_FR[deposit.rtype]} épuisé"
        )
    # Without transporters the worker carries the harvest itself.
    capacity = round(unit.spec.capacity * team.capacity_mult)
    if game.unit_counts(team).get(UnitType.TRANSPORTER, 0) == 0:
        if deposit.pile >= capacity or (deposit.amount <= 0 < deposit.pile):
            load = min(capacity - unit.cargo_total, deposit.pile)
            if load > 0:
                deposit.pile -= load
                unit.cargo[deposit.rtype] = (
                    unit.cargo.get(deposit.rtype, 0) + load
                )


def _deliver(game, unit: Unit, team: Team, speed: float) -> None:
    unit.state = UnitState.DELIVER
    depot = game.nearest_depot(team, unit.pos)
    if depot is None:
        return
    if _near(unit, depot.pos, 1):
        for rtype, amount in unit.cargo.items():
            team.add_stock(rtype, amount)
            team.stats.collected[rtype] += amount
        unit.cargo.clear()
        unit.clear_task()
        return
    if _set_destination(game, unit, depot.pos):
        _follow_path(game, unit, speed)


# Transporter: shuttle piles from deposits to the nearest depot

def _update_transporter(game, unit: Unit, team: Team) -> None:
    speed = unit.spec.speed * team.transporter_speed_mult
    capacity = round(unit.spec.capacity * team.capacity_mult)
    if unit.cargo_total >= capacity:
        _deliver(game, unit, team, speed)
        return
    deposit = _pick_deposit(game, unit, team, need_amount=False)
    if deposit is not None:
        if unit.pos == deposit.pos:
            _load_pile(game, unit, team, deposit, capacity)
        else:
            unit.state = UnitState.MOVE
            if _set_destination(game, unit, deposit.pos):
                _follow_path(game, unit, speed)
        return
    if unit.cargo_total > 0:
        _deliver(game, unit, team, speed)
        return
    # Nothing to haul: wait near the base.
    unit.state = UnitState.IDLE
    hq = game.hq(team)
    if hq is not None and not _near(unit, hq.pos, 5):
        if _set_destination(game, unit, hq.pos):
            _follow_path(game, unit, speed)


def _load_pile(game, unit: Unit, team: Team, deposit: Deposit, capacity: int) -> None:
    unit.state = UnitState.LOAD
    unit.work_acc += team.pickup_rate
    take = int(unit.work_acc)
    if take <= 0:
        return
    unit.work_acc -= take
    take = min(take, deposit.pile, capacity - unit.cargo_total)
    if take > 0:
        deposit.pile -= take
        unit.cargo[deposit.rtype] = unit.cargo.get(deposit.rtype, 0) + take


# Soldier: defend the base until a squad is ready, then hunt the enemy

ATTACK_SQUAD_SIZE = 4
DEFENSE_RADIUS = 8


def _squad_size(team: Team) -> int:
    """Soldiers required before attacking, larger at high skill budgets."""
    return ATTACK_SQUAD_SIZE + sum(team.skills.values()) // 15


def _update_soldier(game, unit: Unit, team: Team) -> None:
    speed = unit.spec.speed * team.speed_mult
    soldiers = game.unit_counts(team).get(UnitType.SOLDIER, 0)
    required = _squad_size(team)
    if team.attacking:
        if soldiers < max(2, required // 2):
            team.attacking = False
    elif soldiers >= required:
        team.attacking = True
    attack_mode = team.attacking
    target = _nearest_visible_enemy(game, unit, team)
    if target is not None:
        unit.state = UnitState.FIGHT
        if combat.in_melee_range(unit.x, unit.y, target.x, target.y):
            if unit.attack_cooldown == 0:
                dmg = combat.attack(
                    unit, target, team.damage_mult, team.attack_period
                )
                team.stats.damage_dealt += dmg
                on_damaged(game, target)
            return
        _chase(game, unit, target.pos, speed)
        return
    if not attack_mode:
        _guard_base(game, unit, team, speed)
        return
    building = _nearest_known_enemy_building(game, unit, team)
    if building is not None:
        unit.state = UnitState.FIGHT
        if combat.in_melee_range(unit.x, unit.y, building.x, building.y):
            if unit.attack_cooldown == 0:
                dmg = combat.attack(
                    unit, building, team.damage_mult, team.attack_period
                )
                team.stats.damage_dealt += dmg
            return
        _chase(game, unit, building.pos, speed)
        return
    _explore_step(game, unit, team, speed)


def _guard_base(game, unit: Unit, team: Team, speed: float) -> None:
    """Patrol around the HQ while the attack squad is not ready."""
    unit.state = UnitState.IDLE
    hq = game.hq(team)
    if hq is None:
        _explore_step(game, unit, team, speed)
        return
    if not _near(unit, hq.pos, DEFENSE_RADIUS):
        if _set_destination(game, unit, hq.pos):
            _follow_path(game, unit, speed)
        return
    if not unit.path and game.rng.random() < 0.05:
        gmap = game.map
        for _ in range(10):
            x = hq.x + game.rng.randint(-DEFENSE_RADIUS, DEFENSE_RADIUS)
            y = hq.y + game.rng.randint(-DEFENSE_RADIUS, DEFENSE_RADIUS)
            if gmap.is_walkable(x, y):
                _set_destination(game, unit, (x, y))
                break
    if unit.path:
        _follow_path(game, unit, speed)


def _nearest_visible_enemy(game, unit: Unit, team: Team) -> Unit | None:
    best = None
    best_dist = None
    for other in game.units.values():
        if other.team_id == unit.team_id or other.pos not in team.visible:
            continue
        dist = _manhattan(unit.pos, other.pos)
        if best_dist is None or dist < best_dist:
            best, best_dist = other, dist
    return best


def _nearest_known_enemy_building(game, unit: Unit, team: Team) -> Building | None:
    best = None
    best_dist = None
    for bid in team.known_enemy_buildings:
        building = game.buildings.get(bid)
        if building is None:
            continue
        dist = _manhattan(unit.pos, building.pos)
        if best_dist is None or dist < best_dist:
            best, best_dist = building, dist
    return best


def _chase(game, unit: Unit, pos: tuple[int, int], speed: float) -> None:
    # Recompute when the target moved away from the planned destination.
    if unit.dest is None or _manhattan(unit.dest, pos) > 2 or not unit.path:
        if not _set_destination(game, unit, pos):
            return
    _follow_path(game, unit, speed)


# Team macro AI: training and construction priorities

def update_team_macro(game, team: Team) -> None:
    if not team.alive:
        return
    _plan_training(game, team)
    _plan_construction(game, team)


def _desired_units(game, team: Team) -> dict[UnitType, int]:
    counts = game.unit_counts(team)
    workers = counts.get(UnitType.WORKER, 0)
    return {
        UnitType.WORKER: min(8, 4 + team.sk("recolte") // 2),
        UnitType.TRANSPORTER: min(5, 1 + workers // 3 + team.sk("transport") // 3),
        UnitType.SCOUT: min(3, 1 + team.sk("exploration") // 4),
        # Always enough to eventually form an attack squad.
        UnitType.SOLDIER: min(
            12, max(_squad_size(team) + 1, 2 + team.sk("combat"))
        ),
    }


def _plan_training(game, team: Team) -> None:
    from .entities import UNIT_SPECS

    counts = dict(game.unit_counts(team))
    trainers: list[Building] = []
    for building in game.buildings_of(team.tid, only_complete=True):
        if building.btype in (BuildingType.HQ, BuildingType.BARRACKS):
            if building.training is not None:
                counts[building.training] = counts.get(building.training, 0) + 1
            else:
                trainers.append(building)
    if not trainers:
        return
    desired = _desired_units(game, team)
    # Most lacking type first (smallest filled ratio).
    needs = sorted(
        (
            (counts.get(ut, 0) / target, ut)
            for ut, target in desired.items()
            if target > 0
        ),
        key=lambda pair: pair[0],
    )
    for ratio, utype in needs:
        if ratio >= 1.0:
            break
        spec = UNIT_SPECS[utype]
        if not team.can_afford(spec.cost):
            continue
        trainer = _pick_trainer(trainers, utype)
        if trainer is None:
            continue
        team.pay(spec.cost)
        trainer.training = utype
        work = spec.train_work
        if utype is UnitType.SOLDIER:
            work *= team.soldier_train_mult
            if trainer.btype is BuildingType.HQ:
                work *= HQ_SOLDIER_WORK_PENALTY
        trainer.training_left = work
        trainers.remove(trainer)
        if not trainers:
            return


def _pick_trainer(trainers: list[Building], utype: UnitType) -> Building | None:
    if utype is UnitType.SOLDIER:
        for building in trainers:
            if building.btype is BuildingType.BARRACKS:
                return building
    for building in trainers:
        if building.btype is BuildingType.HQ:
            return building
    return None


def _plan_construction(game, team: Team) -> None:
    if game.construction_sites(team):
        return
    hq = game.hq(team)
    if hq is None:
        return
    have = {b.btype for b in game.buildings_of(team.tid)}
    plan: tuple[BuildingType, tuple[int, int]] | None = None
    if BuildingType.WAREHOUSE not in have:
        far = _far_deposit(game, team, hq.pos)
        if far is not None:
            plan = (BuildingType.WAREHOUSE, far.pos)
    if plan is None and BuildingType.BARRACKS not in have:
        if team.sk("combat") >= 1 or game.tick_count > 2400:
            plan = (BuildingType.BARRACKS, hq.pos)
    if plan is None and BuildingType.MARKET not in have and team.sk("tradeur") >= 1:
        plan = (BuildingType.MARKET, hq.pos)
    if plan is None and team.sk("science") >= 1 and BuildingType.TOWER not in have:
        plan = (BuildingType.TOWER, hq.pos)
    if plan is None:
        return
    btype, anchor = plan
    spec = BUILDING_SPECS[btype]
    if spec.requires_skill and team.sk(spec.requires_skill) <= 0:
        return
    if not team.can_afford(spec.cost):
        return
    pos = game.free_building_spot(anchor)
    if pos is None:
        return
    team.pay(spec.cost)
    game.start_construction(team, btype, pos)


def _far_deposit(game, team: Team, hq_pos: tuple[int, int]) -> Deposit | None:
    """A known still rich deposit far from the HQ, worth a warehouse."""
    best = None
    best_dist = 18
    for dep in game.known_deposits(team):
        if dep.amount < 100:
            continue
        dist = _manhattan(hq_pos, dep.pos)
        if dist > best_dist:
            best, best_dist = dep, dist
    return best


# AI opponent skill allocation

AI_PROFILES: dict[str, dict[str, int]] = {
    "guerrier": {
        "combat": 5, "exploration": 2, "recolte": 2, "transport": 1,
        "construction": 1, "tradeur": 0, "science": 2, "mecanique": 1,
        "logistique": 0, "espionnage": 1, "fortification": 1,
        "cartographie": 0, "conscription": 2, "pillage": 2, "frenesie": 2,
    },
    "economiste": {
        "combat": 1, "exploration": 1, "recolte": 4, "transport": 3,
        "construction": 2, "tradeur": 2, "science": 1, "mecanique": 1,
        "logistique": 2, "espionnage": 0, "fortification": 2,
        "cartographie": 1, "conscription": 0, "pillage": 0, "frenesie": 0,
    },
    "explorateur": {
        "combat": 2, "exploration": 4, "recolte": 2, "transport": 2,
        "construction": 1, "tradeur": 0, "science": 1, "mecanique": 0,
        "logistique": 1, "espionnage": 2, "fortification": 0,
        "cartographie": 2, "conscription": 1, "pillage": 1, "frenesie": 1,
    },
    "equilibre": {key: 1 for key in SKILLS},
}


def allocate_ai_skills(
    level: int, budget: int, rng: random.Random
) -> tuple[dict[str, int], str]:
    """Spread the budget over unlocked skills following a random profile."""
    profile_name = rng.choice(sorted(AI_PROFILES))
    weights = AI_PROFILES[profile_name]
    available = unlocked_skills(level)
    alloc = {s.key: 0 for s in available}
    for _ in range(budget):
        pool = [
            (s.key, weights.get(s.key, 0))
            for s in available
            if weights.get(s.key, 0) > 0 and alloc[s.key] < s.max_points
        ]
        if not pool:
            pool = [
                (s.key, 1) for s in available if alloc[s.key] < s.max_points
            ]
        if not pool:
            break
        keys = [k for k, _ in pool]
        wts = [w for _, w in pool]
        alloc[rng.choices(keys, weights=wts)[0]] += 1
    return alloc, profile_name
