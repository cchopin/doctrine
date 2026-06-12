"""Economy: harvest, pile pickup, delivery and market trading."""
import unittest

from engine import ai
from engine.entities import BuildingType, UnitType
from engine.world import Deposit, ResourceType
from tests.helpers import clear_units, make_game


class TestHarvestFlow(unittest.TestCase):
    def test_worker_alone_harvests_and_delivers(self):
        game = make_game()
        clear_units(game)
        team = game.teams[0]
        deposit = Deposit(5, 10, ResourceType.WOOD, 50)
        game.map.deposits[(5, 10)] = deposit
        worker = game.spawn_unit(team, UnitType.WORKER, (5, 10))
        game._update_visibility(team)
        for _ in range(400):
            ai.update_unit(game, worker)
        self.assertGreater(team.stocks[ResourceType.WOOD], 0)

    def test_transporter_hauls_pile(self):
        game = make_game()
        clear_units(game)
        team = game.teams[0]
        deposit = Deposit(5, 10, ResourceType.ORE, 60)
        game.map.deposits[(5, 10)] = deposit
        worker = game.spawn_unit(team, UnitType.WORKER, (5, 10))
        hauler = game.spawn_unit(team, UnitType.TRANSPORTER, (3, 10))
        game._update_visibility(team)
        for _ in range(600):
            ai.update_unit(game, worker)
            ai.update_unit(game, hauler)
        self.assertGreater(team.stocks[ResourceType.ORE], 0)
        # With a transporter on duty the worker never carries cargo.
        self.assertEqual(worker.cargo_total, 0)

    def test_harvest_skill_speeds_collection(self):
        slow = make_game()
        fast = make_game(skills_a={"recolte": 5})
        self.assertGreater(
            fast.teams[0].harvest_rate, slow.teams[0].harvest_rate
        )

    def test_deposit_depletes_and_disappears(self):
        game = make_game()
        clear_units(game)
        team = game.teams[0]
        game.map.deposits[(5, 10)] = Deposit(5, 10, ResourceType.FOOD, 5)
        worker = game.spawn_unit(team, UnitType.WORKER, (5, 10))
        game._update_visibility(team)
        for _ in range(300):
            ai.update_unit(game, worker)
            game._remove_depleted_deposits()
        self.assertNotIn((5, 10), game.map.deposits)


class TestMarket(unittest.TestCase):
    def _game_with_market(self, skills=None):
        game = make_game(skills_a=skills)
        team = game.teams[0]
        hq = game.hq(team)
        market = game.start_construction(
            team, BuildingType.MARKET, (hq.x + 2, hq.y)
        )
        market.complete = True
        market.hp = market.max_hp
        return game, team

    def test_market_sells_surplus(self):
        game, team = self._game_with_market()
        team.stocks[ResourceType.WOOD] = 200
        food_before = team.stocks[ResourceType.FOOD]
        game._run_markets()
        self.assertEqual(team.stocks[ResourceType.WOOD], 180)
        self.assertEqual(team.stocks[ResourceType.FOOD], food_before + 8)

    def test_trader_skill_improves_rate(self):
        game, team = self._game_with_market(skills={"tradeur": 4})
        team.stocks[ResourceType.WOOD] = 200
        food_before = team.stocks[ResourceType.FOOD]
        game._run_markets()
        self.assertEqual(team.stocks[ResourceType.FOOD], food_before + 20)

    def test_no_sale_without_surplus(self):
        game, team = self._game_with_market()
        team.stocks[ResourceType.WOOD] = 50
        food_before = team.stocks[ResourceType.FOOD]
        game._run_markets()
        self.assertEqual(team.stocks[ResourceType.WOOD], 50)
        self.assertEqual(team.stocks[ResourceType.FOOD], food_before)


if __name__ == "__main__":
    unittest.main()
