"""A* pathfinding with a small cache, plus a BFS nearest-tile search.

Terrain is static for a whole match, so cached paths never go stale.
"""
from __future__ import annotations

import heapq
from collections import OrderedDict, deque
from collections.abc import Callable

from .world import GameMap

Pos = tuple[int, int]


def astar(
    gmap: GameMap, start: Pos, goal: Pos, max_expand: int = 30000
) -> list[Pos] | None:
    """Return the path from start to goal, excluding start, or None.

    Moving onto a tile costs its terrain cost, so paths prefer plains.
    """
    if start == goal:
        return []
    if not gmap.is_walkable(*goal) or not gmap.is_walkable(*start):
        return None
    gx, gy = goal
    counter = 0
    open_heap: list[tuple[float, int, Pos]] = [(0.0, counter, start)]
    g_score: dict[Pos, float] = {start: 0.0}
    parent: dict[Pos, Pos] = {}
    expanded = 0
    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current == goal:
            return _rebuild(parent, start, goal)
        expanded += 1
        if expanded > max_expand:
            return None
        cx, cy = current
        base_g = g_score[current]
        for nx, ny in gmap.neighbors4(cx, cy):
            tentative = base_g + gmap.cost(nx, ny)
            npos = (nx, ny)
            if tentative < g_score.get(npos, float("inf")):
                g_score[npos] = tentative
                parent[npos] = current
                counter += 1
                h = abs(nx - gx) + abs(ny - gy)
                heapq.heappush(open_heap, (tentative + h, counter, npos))
    return None


def _rebuild(parent: dict[Pos, Pos], start: Pos, goal: Pos) -> list[Pos]:
    path = [goal]
    node = goal
    while parent[node] != start:
        node = parent[node]
        path.append(node)
    path.reverse()
    return path


class PathCache:
    """LRU cache over astar results, keyed by (start, goal)."""

    def __init__(self, capacity: int = 1024):
        self.capacity = capacity
        self._store: OrderedDict[tuple[Pos, Pos], list[Pos] | None] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def path(self, gmap: GameMap, start: Pos, goal: Pos) -> list[Pos] | None:
        key = (start, goal)
        if key in self._store:
            self.hits += 1
            self._store.move_to_end(key)
            cached = self._store[key]
            return list(cached) if cached is not None else None
        self.misses += 1
        result = astar(gmap, start, goal)
        self._store[key] = list(result) if result is not None else None
        if len(self._store) > self.capacity:
            self._store.popitem(last=False)
        return result


def find_nearest(
    gmap: GameMap,
    start: Pos,
    predicate: Callable[[Pos], bool],
    max_radius: int | None = None,
) -> Pos | None:
    """BFS over walkable tiles for the closest tile matching predicate."""
    if predicate(start):
        return start
    seen = {start}
    queue = deque([(start, 0)])
    while queue:
        (x, y), dist = queue.popleft()
        if max_radius is not None and dist >= max_radius:
            continue
        for npos in gmap.neighbors4(x, y):
            if npos in seen:
                continue
            seen.add(npos)
            if predicate(npos):
                return npos
            queue.append((npos, dist + 1))
    return None
