"""Progression, match history and HTML report generation."""
import json
import tempfile
import unittest
from pathlib import Path

from meta.history import (
    append_match,
    build_record,
    dominant_composition,
    load_history,
)
from meta.progress import Profile, add_xp, skill_budget, xp_needed
from meta.report import generate_report
from meta.skills import SKILLS, unlocked_skills
from tests.helpers import make_game


class TestProgress(unittest.TestCase):
    def test_budget_grows_with_level(self):
        self.assertEqual(skill_budget(1), 10)
        self.assertEqual(skill_budget(5), 18)

    def test_level_up(self):
        profile = Profile()
        gained = add_xp(profile, xp_needed(1) + 10)
        self.assertEqual(gained, 1)
        self.assertEqual(profile.level, 2)
        self.assertEqual(profile.xp, 10)

    def test_unlocks_by_level(self):
        base = {s.key for s in unlocked_skills(1)}
        self.assertNotIn("science", base)
        self.assertIn("science", {s.key for s in unlocked_skills(2)})
        endgame = {s.key for s in unlocked_skills(10)}
        self.assertEqual(endgame, set(SKILLS))


class TestHistory(unittest.TestCase):
    def test_dominant_composition(self):
        self.assertEqual(dominant_composition({}), "aucune")
        self.assertEqual(dominant_composition({"combat": 5, "recolte": 2}), "combat")
        self.assertEqual(
            dominant_composition({"combat": 3, "recolte": 3}), "combat+recolte"
        )

    def test_build_and_append_record(self):
        game = make_game(skills_a={"combat": 4})
        game.teams[0].stats.units_killed = 3
        record = build_record(game, 0, "victoire", 7, 2, "guerrier")
        self.assertEqual(record["composition"], "combat")
        self.assertEqual(record["player"]["units_killed"], 3)
        self.assertIn("score", record["ai"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            append_match(record, path)
            append_match(record, path)
            history = load_history(path)
            self.assertEqual(len(history), 2)
            json.loads(path.read_text(encoding="utf-8"))


class TestReport(unittest.TestCase):
    def test_generate_report_html(self):
        game = make_game(skills_a={"recolte": 5})
        records = [
            build_record(game, 0, result, 1, 1, profile)
            for result, profile in (
                ("victoire", "guerrier"),
                ("defaite", "economiste"),
                ("egalite", "guerrier"),
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stats.html"
            out = generate_report(records, path)
            html = out.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("Taux de victoire", html)
        self.assertIn("guerrier", html)
        self.assertIn("Récolte", html)

    def test_generate_report_empty_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stats.html"
            html = generate_report([], path).read_text(encoding="utf-8")
        self.assertIn("Pas encore de données", html)


if __name__ == "__main__":
    unittest.main()
