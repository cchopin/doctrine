"""Persistent player progression: level and experience, saved as JSON.

Skill point allocation is reset before every match. Only the level and
the experience are persistent.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

DEFAULT_PROFILE_PATH = Path(__file__).resolve().parent.parent / "profile.json"

BASE_BUDGET = 10
POINTS_PER_LEVEL = 2

XP_WIN = 100
XP_DRAW = 40
XP_LOSS = 15


@dataclass
class Profile:
    level: int = 1
    xp: int = 0
    wins: int = 0
    losses: int = 0


def xp_needed(level: int) -> int:
    """Experience required to go from `level` to `level + 1`."""
    return 200 * level


def skill_budget(level: int) -> int:
    return BASE_BUDGET + POINTS_PER_LEVEL * (level - 1)


def add_xp(profile: Profile, amount: int) -> int:
    """Add experience, apply level ups, return the number of levels gained."""
    profile.xp += amount
    gained = 0
    while profile.xp >= xp_needed(profile.level):
        profile.xp -= xp_needed(profile.level)
        profile.level += 1
        gained += 1
    return gained


def load_profile(path: Path = DEFAULT_PROFILE_PATH) -> Profile:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return Profile(
            level=int(data.get("level", 1)),
            xp=int(data.get("xp", 0)),
            wins=int(data.get("wins", 0)),
            losses=int(data.get("losses", 0)),
        )
    except (OSError, ValueError):
        return Profile()


def save_profile(profile: Profile, path: Path = DEFAULT_PROFILE_PATH) -> None:
    Path(path).write_text(
        json.dumps(asdict(profile), indent=2), encoding="utf-8"
    )
