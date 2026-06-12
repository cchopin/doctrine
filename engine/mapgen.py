"""Procedural map generation.

Terrain blobs are grown with random walks, then base positions are picked
in opposite areas and checked for connectivity with a BFS. Deposits are
scattered on walkable tiles, with a few guaranteed near each base.
"""
from __future__ import annotations

import random
from collections import deque

from .world import Deposit, GameMap, ResourceType, Terrain

MIN_WIDTH = 120
MIN_HEIGHT = 80

# Guaranteed deposits close to each base so the early game always works.
STARTER_RESOURCES = (ResourceType.FOOD, ResourceType.ORE, ResourceType.WOOD)


def generate_map(
    width: int = MIN_WIDTH,
    height: int = MIN_HEIGHT,
    seed: int | None = None,
    num_teams: int = 2,
) -> tuple[GameMap, list[tuple[int, int]]]:
    """Build a map and return it with one base position per team."""
    rng = random.Random(seed)
    for _ in range(30):
        gmap = _build_terrain(rng, width, height)
        bases = _place_bases(gmap, rng, num_teams)
        if bases is not None and _all_connected(gmap, bases):
            _place_deposits(gmap, rng, bases)
            return gmap, bases
    # Extremely unlikely fallback: carve plain corridors between bases.
    gmap = _build_terrain(rng, width, height)
    bases = _force_bases(gmap, num_teams)
    _carve_corridors(gmap, bases)
    _place_deposits(gmap, rng, bases)
    return gmap, bases


def _build_terrain(rng: random.Random, width: int, height: int) -> GameMap:
    gmap = GameMap(width, height)
    area = width * height
    _grow_blobs(gmap, rng, Terrain.WATER, area // 800, 30, 90)
    _grow_blobs(gmap, rng, Terrain.FOREST, area // 450, 20, 70)
    _grow_blobs(gmap, rng, Terrain.MOUNTAIN, area // 900, 15, 45)
    return gmap


def _grow_blobs(
    gmap: GameMap,
    rng: random.Random,
    terrain: Terrain,
    count: int,
    min_size: int,
    max_size: int,
) -> None:
    for _ in range(count):
        x = rng.randrange(gmap.width)
        y = rng.randrange(gmap.height)
        for _ in range(rng.randint(min_size, max_size)):
            if gmap.in_bounds(x, y):
                gmap.set(x, y, terrain)
            dx, dy = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
            x = min(max(x + dx, 0), gmap.width - 1)
            y = min(max(y + dy, 0), gmap.height - 1)


def _base_anchors(width: int, height: int, num_teams: int) -> list[tuple[int, int]]:
    if num_teams <= 2:
        return [(width // 8, height // 2), (7 * width // 8, height // 2)]
    corners = [
        (width // 8, height // 8),
        (7 * width // 8, 7 * height // 8),
        (7 * width // 8, height // 8),
        (width // 8, 7 * height // 8),
    ]
    return corners[:num_teams]


def _place_bases(
    gmap: GameMap, rng: random.Random, num_teams: int
) -> list[tuple[int, int]] | None:
    bases: list[tuple[int, int]] = []
    for ax, ay in _base_anchors(gmap.width, gmap.height, num_teams):
        jx = ax + rng.randint(-gmap.width // 12, gmap.width // 12)
        jy = ay + rng.randint(-gmap.height // 6, gmap.height // 6)
        pos = _nearest_open(gmap, jx, jy)
        if pos is None:
            return None
        _clear_area(gmap, pos[0], pos[1], 2)
        bases.append(pos)
    return bases


def _force_bases(gmap: GameMap, num_teams: int) -> list[tuple[int, int]]:
    bases = []
    for ax, ay in _base_anchors(gmap.width, gmap.height, num_teams):
        _clear_area(gmap, ax, ay, 2)
        bases.append((ax, ay))
    return bases


def _nearest_open(gmap: GameMap, x: int, y: int) -> tuple[int, int] | None:
    """Closest plain tile to (x, y), spiral search."""
    x = min(max(x, 0), gmap.width - 1)
    y = min(max(y, 0), gmap.height - 1)
    for radius in range(0, max(gmap.width, gmap.height)):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                nx, ny = x + dx, y + dy
                if gmap.in_bounds(nx, ny) and gmap.get(nx, ny) is Terrain.PLAIN:
                    return (nx, ny)
    return None


def _clear_area(gmap: GameMap, x: int, y: int, radius: int) -> None:
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            nx, ny = x + dx, y + dy
            if gmap.in_bounds(nx, ny):
                gmap.set(nx, ny, Terrain.PLAIN)


def _all_connected(gmap: GameMap, bases: list[tuple[int, int]]) -> bool:
    start = bases[0]
    seen = {start}
    queue = deque([start])
    targets = set(bases[1:])
    while queue and targets:
        x, y = queue.popleft()
        for npos in gmap.neighbors4(x, y):
            if npos not in seen:
                seen.add(npos)
                targets.discard(npos)
                queue.append(npos)
    return not targets


def _carve_corridors(gmap: GameMap, bases: list[tuple[int, int]]) -> None:
    x0, y0 = bases[0]
    for x1, y1 in bases[1:]:
        x, y = x0, y0
        while x != x1:
            x += 1 if x1 > x else -1
            gmap.set(x, y, Terrain.PLAIN)
        while y != y1:
            y += 1 if y1 > y else -1
            gmap.set(x, y, Terrain.PLAIN)


def _place_deposits(
    gmap: GameMap, rng: random.Random, bases: list[tuple[int, int]]
) -> None:
    # Guaranteed starter deposits near each base.
    for bx, by in bases:
        for rtype in STARTER_RESOURCES:
            pos = _random_open_near(gmap, rng, bx, by, 4, 10)
            if pos is not None:
                gmap.deposits[pos] = Deposit(
                    pos[0], pos[1], rtype, rng.randint(260, 380)
                )
    # Random scatter over the whole map.
    for rtype in ResourceType:
        for _ in range(12 + rng.randint(0, 5)):
            for _ in range(40):  # placement attempts
                x = rng.randrange(gmap.width)
                y = rng.randrange(gmap.height)
                if not gmap.is_walkable(x, y) or (x, y) in gmap.deposits:
                    continue
                if any(abs(x - bx) + abs(y - by) < 4 for bx, by in bases):
                    continue
                gmap.deposits[(x, y)] = Deposit(
                    x, y, rtype, rng.randint(220, 450)
                )
                break


def _random_open_near(
    gmap: GameMap,
    rng: random.Random,
    cx: int,
    cy: int,
    min_dist: int,
    max_dist: int,
) -> tuple[int, int] | None:
    for _ in range(120):
        x = cx + rng.randint(-max_dist, max_dist)
        y = cy + rng.randint(-max_dist, max_dist)
        dist = abs(x - cx) + abs(y - cy)
        if (
            min_dist <= dist <= max_dist
            and gmap.is_walkable(x, y)
            and (x, y) not in gmap.deposits
        ):
            return (x, y)
    return None
