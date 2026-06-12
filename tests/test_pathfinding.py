"""Pathfinding: A* correctness, water avoidance, cache behavior."""
import unittest

from engine.pathfinding import PathCache, astar, find_nearest
from engine.world import GameMap, Terrain


def small_map() -> GameMap:
    gmap = GameMap(10, 10)
    return gmap


class TestAstar(unittest.TestCase):
    def test_straight_path(self):
        gmap = small_map()
        path = astar(gmap, (0, 0), (3, 0))
        self.assertIsNotNone(path)
        self.assertEqual(path[-1], (3, 0))
        self.assertEqual(len(path), 3)

    def test_same_start_goal(self):
        gmap = small_map()
        self.assertEqual(astar(gmap, (2, 2), (2, 2)), [])

    def test_path_steps_are_adjacent(self):
        gmap = small_map()
        path = astar(gmap, (0, 0), (5, 7))
        prev = (0, 0)
        for x, y in path:
            self.assertEqual(abs(x - prev[0]) + abs(y - prev[1]), 1)
            prev = (x, y)

    def test_avoids_water(self):
        gmap = small_map()
        # Vertical water wall with one gap at y = 8.
        for y in range(10):
            if y != 8:
                gmap.set(5, y, Terrain.WATER)
        path = astar(gmap, (0, 0), (9, 0))
        self.assertIsNotNone(path)
        self.assertIn((5, 8), path)
        for x, y in path:
            self.assertTrue(gmap.is_walkable(x, y))

    def test_no_path_when_blocked(self):
        gmap = small_map()
        for y in range(10):
            gmap.set(5, y, Terrain.WATER)
        self.assertIsNone(astar(gmap, (0, 0), (9, 0)))

    def test_goal_in_water_fails(self):
        gmap = small_map()
        gmap.set(4, 4, Terrain.WATER)
        self.assertIsNone(astar(gmap, (0, 0), (4, 4)))

    def test_prefers_cheap_terrain(self):
        gmap = GameMap(5, 3)
        # Mountains on the straight line, plains around.
        gmap.set(1, 1, Terrain.MOUNTAIN)
        gmap.set(2, 1, Terrain.MOUNTAIN)
        gmap.set(3, 1, Terrain.MOUNTAIN)
        path = astar(gmap, (0, 1), (4, 1))
        self.assertIsNotNone(path)
        self.assertFalse(any(pos in ((1, 1), (2, 1), (3, 1)) for pos in path))


class TestPathCache(unittest.TestCase):
    def test_cache_hits(self):
        gmap = small_map()
        cache = PathCache()
        p1 = cache.path(gmap, (0, 0), (5, 5))
        p2 = cache.path(gmap, (0, 0), (5, 5))
        self.assertEqual(p1, p2)
        self.assertEqual(cache.hits, 1)
        self.assertEqual(cache.misses, 1)

    def test_cache_returns_copies(self):
        gmap = small_map()
        cache = PathCache()
        p1 = cache.path(gmap, (0, 0), (5, 5))
        p1.clear()
        p2 = cache.path(gmap, (0, 0), (5, 5))
        self.assertTrue(p2)


class TestFindNearest(unittest.TestCase):
    def test_finds_closest_match(self):
        gmap = small_map()
        targets = {(4, 0), (0, 6)}
        found = find_nearest(gmap, (0, 0), lambda p: p in targets)
        self.assertEqual(found, (4, 0))

    def test_respects_max_radius(self):
        gmap = small_map()
        found = find_nearest(
            gmap, (0, 0), lambda p: p == (9, 9), max_radius=3
        )
        self.assertIsNone(found)


if __name__ == "__main__":
    unittest.main()
