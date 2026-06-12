"""Match history persistence, one JSON list of match records.

Records feed the end screen recap and the HTML stats report.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

DEFAULT_HISTORY_PATH = Path(__file__).resolve().parent.parent / "history.json"


def load_history(path: Path = DEFAULT_HISTORY_PATH) -> list[dict]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def append_match(record: dict, path: Path = DEFAULT_HISTORY_PATH) -> None:
    history = load_history(path)
    history.append(record)
    Path(path).write_text(
        json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def team_summary(game, team) -> dict:
    """Serializable per team match summary."""
    stats = team.stats
    return {
        "score": game.score(team),
        "explored": len(team.explored),
        "collected": {r.value: n for r, n in stats.collected.items()},
        "collected_total": stats.total_collected,
        "units_trained": stats.units_trained,
        "units_lost": stats.units_lost,
        "units_killed": stats.units_killed,
        "buildings_built": stats.buildings_built,
        "buildings_destroyed": stats.buildings_destroyed,
        "damage_dealt": stats.damage_dealt,
    }


def dominant_composition(skills: dict[str, int]) -> str:
    """Label a skill allocation by its strongest investments."""
    spent = {k: v for k, v in skills.items() if v > 0}
    if not spent:
        return "aucune"
    best = max(spent.values())
    tops = sorted(k for k, v in spent.items() if v == best)
    return "+".join(tops[:2])


def build_record(
    game,
    player_tid: int,
    result: str,
    seed: int | None,
    level: int,
    ai_profile: str,
) -> dict:
    player = game.teams[player_tid]
    enemy = next(t for t in game.teams.values() if t.tid != player_tid)
    return {
        "date": datetime.now().isoformat(timespec="seconds"),
        "seed": seed,
        "level": level,
        "result": result,
        "reason": game.end_reason,
        "duration_min": round(game.elapsed_seconds / 60, 2),
        "player_skills": dict(player.skills),
        "composition": dominant_composition(player.skills),
        "ai_profile": ai_profile,
        "ai_skills": dict(enemy.skills),
        "player": team_summary(game, player),
        "ai": team_summary(game, enemy),
    }
