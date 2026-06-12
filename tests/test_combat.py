"""Combat resolution and victory by HQ destruction."""
import unittest

from engine import ai, combat
from engine.entities import UnitType
from tests.helpers import clear_units, make_game


class TestCombat(unittest.TestCase):
    def test_attack_applies_damage(self):
        game = make_game()
        clear_units(game)
        soldier = game.spawn_unit(game.teams[0], UnitType.SOLDIER, (5, 10))
        victim = game.spawn_unit(game.teams[1], UnitType.WORKER, (6, 10))
        hp_before = victim.hp
        dmg = combat.attack(soldier, victim, damage_mult=1.0)
        self.assertEqual(dmg, soldier.spec.damage)
        self.assertEqual(victim.hp, hp_before - dmg)
        self.assertEqual(soldier.attack_cooldown, combat.ATTACK_PERIOD)

    def test_combat_skill_scales_damage_and_hp(self):
        game = make_game(skills_a={"combat": 5})
        clear_units(game)
        strong = game.spawn_unit(game.teams[0], UnitType.SOLDIER, (5, 10))
        weak = game.spawn_unit(game.teams[1], UnitType.SOLDIER, (6, 10))
        self.assertGreater(strong.max_hp, weak.max_hp)
        dmg = combat.attack(strong, weak, game.teams[0].damage_mult)
        self.assertGreater(dmg, strong.spec.damage)

    def test_dead_unit_removed_with_event(self):
        game = make_game()
        clear_units(game)
        victim = game.spawn_unit(game.teams[1], UnitType.WORKER, (6, 10))
        victim.hp = 0
        game._cleanup_dead()
        self.assertNotIn(victim.uid, game.units)
        self.assertTrue(
            any("Unité perdue" in msg for _, msg in game.events)
        )

    def test_civilian_flees_when_hit(self):
        game = make_game()
        clear_units(game)
        worker = game.spawn_unit(game.teams[1], UnitType.WORKER, (6, 10))
        ai.on_damaged(game, worker)
        self.assertGreater(worker.flee_until, game.tick_count)

    def test_hq_destruction_ends_game(self):
        game = make_game()
        enemy_hq = game.hq(game.teams[1])
        enemy_hq.hp = 0
        game._cleanup_dead()
        game._check_end()
        self.assertTrue(game.finished)
        self.assertEqual(game.winner, 0)
        self.assertEqual(game.end_reason, "destruction")
        self.assertFalse(game.teams[1].alive)

    def test_timeout_picks_higher_score(self):
        game = make_game()
        game.teams[0].stocks = {
            r: v + 500 for r, v in game.teams[0].stocks.items()
        }
        game.tick_count = game.time_limit_ticks
        game._check_end()
        self.assertTrue(game.finished)
        self.assertEqual(game.end_reason, "temps")
        self.assertEqual(game.winner, 0)

    def test_soldier_engages_adjacent_enemy(self):
        game = make_game()
        clear_units(game)
        soldier = game.spawn_unit(game.teams[0], UnitType.SOLDIER, (6, 10))
        victim = game.spawn_unit(game.teams[1], UnitType.WORKER, (7, 10))
        game._update_visibility(game.teams[0])
        hp_before = victim.hp
        ai.update_unit(game, soldier)
        self.assertLess(victim.hp, hp_before)


class TestFullMatch(unittest.TestCase):
    def test_seeded_match_completes(self):
        from engine.game import Game
        from engine.mapgen import generate_map
        from engine.team import TeamConfig

        gmap, bases = generate_map(seed=42)
        configs = [
            TeamConfig("A", "blue", {"combat": 3, "recolte": 2}),
            TeamConfig("B", "red", {"recolte": 3, "transport": 2}),
        ]
        game = Game(gmap, bases, configs, seed=42)
        guard = game.time_limit_ticks + 10
        while not game.finished and guard > 0:
            game.tick()
            guard -= 1
        self.assertTrue(game.finished)
        self.assertLessEqual(game.tick_count, game.time_limit_ticks)
        self.assertIn(game.end_reason, ("destruction", "temps"))


if __name__ == "__main__":
    unittest.main()
