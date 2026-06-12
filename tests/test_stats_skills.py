"""Match statistics tracking and endgame skill effects."""
import unittest

from engine import ai, combat
from engine.entities import BUILDING_SPECS, BuildingType, UnitType
from engine.world import Deposit, ResourceType
from tests.helpers import clear_units, make_game


class TestStatsTracking(unittest.TestCase):
    def test_kill_and_loss_counted(self):
        game = make_game()
        clear_units(game)
        soldier = game.spawn_unit(game.teams[0], UnitType.SOLDIER, (5, 10))
        victim = game.spawn_unit(game.teams[1], UnitType.WORKER, (6, 10))
        victim.hp = 1
        combat.attack(soldier, victim, 1.0)
        game._cleanup_dead()
        self.assertEqual(game.teams[0].stats.units_killed, 1)
        self.assertEqual(game.teams[1].stats.units_lost, 1)

    def test_collected_counted_on_delivery(self):
        game = make_game()
        clear_units(game)
        team = game.teams[0]
        game.map.deposits[(5, 10)] = Deposit(5, 10, ResourceType.WOOD, 40)
        worker = game.spawn_unit(team, UnitType.WORKER, (5, 10))
        game._update_visibility(team)
        for _ in range(400):
            ai.update_unit(game, worker)
        self.assertGreater(team.stats.collected[ResourceType.WOOD], 0)
        self.assertEqual(
            team.stats.collected[ResourceType.WOOD],
            team.stocks[ResourceType.WOOD],
        )

    def test_damage_dealt_counted(self):
        game = make_game()
        clear_units(game)
        soldier = game.spawn_unit(game.teams[0], UnitType.SOLDIER, (6, 10))
        game.spawn_unit(game.teams[1], UnitType.WORKER, (7, 10))
        game._update_visibility(game.teams[0])
        ai.update_unit(game, soldier)
        self.assertGreater(game.teams[0].stats.damage_dealt, 0)


class TestEndgameSkills(unittest.TestCase):
    def test_fortification_scales_building_hp(self):
        plain = make_game()
        fortified = make_game(skills_a={"fortification": 5})
        hq_plain = plain.hq(plain.teams[0])
        hq_fort = fortified.hq(fortified.teams[0])
        self.assertEqual(
            hq_fort.max_hp, round(hq_plain.max_hp * 2.0)
        )

    def test_cartographie_extends_sight(self):
        game = make_game(skills_a={"cartographie": 3})
        clear_units(game)
        team = game.teams[0]
        scout = game.spawn_unit(team, UnitType.SCOUT, (15, 10))
        game._update_visibility(team)
        reach = scout.spec.sight + 3
        self.assertIn((15 + reach, 10), team.visible)

    def test_frenesie_reduces_attack_period(self):
        game = make_game(skills_a={"frenesie": 5})
        self.assertLess(game.teams[0].attack_period, combat.ATTACK_PERIOD)

    def test_conscription_speeds_soldier_training(self):
        game = make_game(skills_a={"conscription": 5})
        self.assertLess(game.teams[0].soldier_train_mult, 1.0)

    def test_pillage_loots_kills(self):
        game = make_game(skills_a={"pillage": 3})
        clear_units(game)
        soldier = game.spawn_unit(game.teams[0], UnitType.SOLDIER, (5, 10))
        victim = game.spawn_unit(game.teams[1], UnitType.WORKER, (6, 10))
        victim.hp = 1
        food_before = game.teams[0].stocks[ResourceType.FOOD]
        combat.attack(soldier, victim, 1.0)
        game._cleanup_dead()
        self.assertEqual(
            game.teams[0].stocks[ResourceType.FOOD], food_before + 24
        )

    def test_pillage_loots_buildings(self):
        game = make_game(skills_a={"pillage": 2})
        team = game.teams[0]
        enemy_b = game.start_construction(
            game.teams[1], BuildingType.WAREHOUSE, (20, 10)
        )
        enemy_b.hp = 0
        enemy_b.last_hit_team = 0
        wood_before = team.stocks[ResourceType.WOOD]
        ore_before = team.stocks[ResourceType.ORE]
        game._cleanup_dead()
        self.assertEqual(
            team.stocks[ResourceType.WOOD] + team.stocks[ResourceType.ORE],
            wood_before + ore_before + 50,
        )

    def test_tower_requires_science(self):
        spec = BUILDING_SPECS[BuildingType.TOWER]
        self.assertEqual(spec.requires_skill, "science")


class TestCounterMechanics(unittest.TestCase):
    def test_famine_hurts_unfed_soldiers(self):
        game = make_game()
        clear_units(game)
        team = game.teams[0]
        team.stocks[ResourceType.FOOD] = 0
        soldiers = [
            game.spawn_unit(team, UnitType.SOLDIER, (5 + i, 10))
            for i in range(4)
        ]
        hp_before = [s.hp for s in soldiers]
        game._run_upkeep()
        self.assertTrue(all(s.hp < h for s, h in zip(soldiers, hp_before)))

    def test_fed_army_pays_upkeep(self):
        game = make_game()
        clear_units(game)
        team = game.teams[0]
        team.stocks[ResourceType.FOOD] = 100
        for i in range(4):
            game.spawn_unit(team, UnitType.SOLDIER, (5 + i, 10))
        game._run_upkeep()
        self.assertEqual(team.stocks[ResourceType.FOOD], 98)

    def test_workers_repair_damaged_buildings(self):
        game = make_game()
        clear_units(game)
        team = game.teams[0]
        hq = game.hq(team)
        hq.hp = hq.max_hp // 2
        worker = game.spawn_unit(team, UnitType.WORKER, hq.pos)
        for _ in range(30):
            ai.update_unit(game, worker)
        self.assertGreater(hq.hp, hq.max_hp // 2)


class TestBuildingLevelGates(unittest.TestCase):
    def _rich_team(self, game):
        team = game.teams[0]
        for rtype in ResourceType:
            team.stocks[rtype] = 500
        # The AI only builds a warehouse near a far known rich deposit.
        game.map.deposits[(25, 4)] = Deposit(25, 4, ResourceType.WOOD, 400)
        game._update_visibility(team)
        team.explored.add((25, 4))
        return team

    def _planned(self, game, team):
        ai._plan_construction(game, team)
        return {b.btype for b in game.construction_sites(team)}

    def test_level_one_builds_nothing(self):
        game = make_game(skills_a={"combat": 2, "tradeur": 2})
        team = self._rich_team(game)
        self.assertEqual(self._planned(game, team), set())

    def test_level_two_unlocks_warehouse(self):
        game = make_game(skills_a={"combat": 2}, level=2)
        team = self._rich_team(game)
        self.assertEqual(self._planned(game, team), {BuildingType.WAREHOUSE})

    def test_level_three_unlocks_barracks(self):
        game = make_game(skills_a={"combat": 2}, level=3)
        team = self._rich_team(game)
        game.start_construction(team, BuildingType.WAREHOUSE, (3, 3)).complete = True
        self.assertEqual(self._planned(game, team), {BuildingType.BARRACKS})


if __name__ == "__main__":
    unittest.main()
