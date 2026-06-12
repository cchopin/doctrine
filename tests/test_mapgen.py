"""Map generation: reproducibility, connectivity, deposits."""
import unittest
from collections import deque

from engine.mapgen import generate_map
from engine.world import ResourceType, Terrain


class TestMapGen(unittest.TestCase):
    def test_dimensions_and_bases(self):
        gmap, bases = generate_map(seed=7)
        self.assertEqual(gmap.width, 120)
        self.assertEqual(gmap.height, 80)
        self.assertEqual(len(bases), 2)
        for x, y in bases:
            self.assertTrue(gmap.is_walkable(x, y))

    def test_seed_reproducible(self):
        gmap1, bases1 = generate_map(seed=123)
        gmap2, bases2 = generate_map(seed=123)
        self.assertEqual(bases1, bases2)
        self.assertEqual(gmap1.terrain, gmap2.terrain)
        self.assertEqual(
            {p: (d.rtype, d.amount) for p, d in gmap1.deposits.items()},
            {p: (d.rtype, d.amount) for p, d in gmap2.deposits.items()},
        )

    def test_different_seeds_differ(self):
        gmap1, _ = generate_map(seed=1)
        gmap2, _ = generate_map(seed=2)
        self.assertNotEqual(gmap1.terrain, gmap2.terrain)

    def test_bases_connected(self):
        for seed in range(5):
            gmap, bases = generate_map(seed=seed)
            start, goal = bases[0], bases[1]
            seen = {start}
            queue = deque([start])
            found = False
            while queue:
                x, y = queue.popleft()
                if (x, y) == goal:
                    found = True
                    break
                for npos in gmap.neighbors4(x, y):
                    if npos not in seen:
                        seen.add(npos)
                        queue.append(npos)
            self.assertTrue(found, f"bases not connected for seed {seed}")

    def test_all_resource_types_present(self):
        gmap, _ = generate_map(seed=99)
        types = {d.rtype for d in gmap.deposits.values()}
        self.assertEqual(types, set(ResourceType))

    def test_starter_deposits_near_bases(self):
        gmap, bases = generate_map(seed=5)
        for bx, by in bases:
            near = [
                d for d in gmap.deposits.values()
                if abs(d.x - bx) + abs(d.y - by) <= 10
            ]
            self.assertGreaterEqual(len(near), 2)

    def test_deposits_on_walkable_tiles(self):
        gmap, _ = generate_map(seed=11)
        for (x, y), dep in gmap.deposits.items():
            self.assertTrue(gmap.is_walkable(x, y))
            self.assertGreater(dep.amount, 0)
            self.assertIsNot(gmap.get(x, y), Terrain.WATER)


if __name__ == "__main__":
    unittest.main()
