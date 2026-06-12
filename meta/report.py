"""Static HTML stats report built from the match history.

Self contained page (inline CSS, no JavaScript, no dependency), written
next to the project so it can be opened in any browser.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

from .skills import SKILLS

DEFAULT_REPORT_PATH = Path(__file__).resolve().parent.parent / "stats.html"

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2rem; background: #12151c; color: #e6e9f0;
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
h1 { margin: 0 0 .25rem; font-size: 1.7rem; }
h2 { margin: 2.2rem 0 .8rem; font-size: 1.15rem; color: #9db4ff; }
.sub { color: #8b93a7; margin-bottom: 1.5rem; }
.cards { display: flex; flex-wrap: wrap; gap: .8rem; }
.card {
  background: #1b2030; border: 1px solid #2a3147; border-radius: 10px;
  padding: .9rem 1.2rem; min-width: 130px;
}
.card .v { font-size: 1.5rem; font-weight: 700; }
.card .l { color: #8b93a7; font-size: .8rem; }
.win { color: #5fd38a; } .loss { color: #ff7a7a; } .draw { color: #ffc66d; }
.row { display: flex; align-items: center; gap: .6rem; margin: .3rem 0; }
.row .name { width: 160px; color: #b9c2d8; text-align: right; }
.row .track {
  flex: 1; background: #1b2030; border-radius: 5px; height: 18px;
  overflow: hidden;
}
.row .bar { height: 100%; border-radius: 5px; }
.row .val { width: 150px; color: #8b93a7; font-size: .85rem; }
.bar.g { background: linear-gradient(90deg, #2f9e5f, #5fd38a); }
.bar.r { background: linear-gradient(90deg, #b04040, #ff7a7a); }
.bar.b { background: linear-gradient(90deg, #3d62c9, #7da2ff); }
table { border-collapse: collapse; width: 100%; }
th, td { padding: .4rem .7rem; text-align: left; }
th { color: #8b93a7; font-weight: 600; border-bottom: 1px solid #2a3147; }
tr:nth-child(even) td { background: #181d2a; }
.empty { color: #8b93a7; font-style: italic; }
"""


def _bar_row(name: str, ratio: float, css: str, value_text: str) -> str:
    width = max(0.0, min(1.0, ratio)) * 100
    return (
        f'<div class="row"><div class="name">{escape(name)}</div>'
        f'<div class="track"><div class="bar {css}" '
        f'style="width:{width:.1f}%"></div></div>'
        f'<div class="val">{escape(value_text)}</div></div>'
    )


def _result_class(result: str) -> str:
    return {"victoire": "win", "defaite": "loss"}.get(result, "draw")


def _skill_label(key: str) -> str:
    skill = SKILLS.get(key)
    return skill.label if skill else key


def _composition_label(comp: str) -> str:
    return "+".join(_skill_label(part) for part in comp.split("+"))


def _summary_cards(history: list[dict]) -> str:
    games = len(history)
    wins = sum(1 for m in history if m["result"] == "victoire")
    draws = sum(1 for m in history if m["result"] == "egalite")
    losses = games - wins - draws
    streak = 0
    for match in reversed(history):
        if match["result"] != "victoire":
            break
        streak += 1
    durations = [m["duration_min"] for m in history]
    avg_duration = sum(durations) / games if games else 0
    win_durations = [
        m["duration_min"] for m in history if m["result"] == "victoire"
    ]
    best = min(win_durations) if win_durations else None
    cards = [
        ("Parties", str(games), ""),
        ("Victoires", str(wins), "win"),
        ("Défaites", str(losses), "loss"),
        ("Égalités", str(draws), "draw"),
        ("Taux de victoire", f"{100 * wins / games:.0f}%" if games else "0%", ""),
        ("Série en cours", str(streak), "win" if streak else ""),
        ("Durée moyenne", f"{avg_duration:.1f} min", ""),
        (
            "Victoire la plus rapide",
            f"{best:.1f} min" if best is not None else "aucune",
            "",
        ),
    ]
    return '<div class="cards">' + "".join(
        f'<div class="card"><div class="v {cls}">{escape(value)}</div>'
        f'<div class="l">{escape(label)}</div></div>'
        for label, value, cls in cards
    ) + "</div>"


def _winrate_section(history: list[dict], key, label_fn) -> str:
    groups: dict[str, list[dict]] = {}
    for match in history:
        groups.setdefault(key(match), []).append(match)
    if not groups:
        return '<p class="empty">Pas encore de données.</p>'
    rows = []
    for name in sorted(groups, key=lambda n: -len(groups[n])):
        matches = groups[name]
        wins = sum(1 for m in matches if m["result"] == "victoire")
        ratio = wins / len(matches)
        rows.append(
            _bar_row(
                label_fn(name), ratio, "g" if ratio >= 0.5 else "r",
                f"{wins}/{len(matches)} ({100 * ratio:.0f}%)",
            )
        )
    return "".join(rows)


def _skill_section(history: list[dict]) -> str:
    wins = [m for m in history if m["result"] == "victoire"]
    losses = [m for m in history if m["result"] == "defaite"]
    if not wins and not losses:
        return '<p class="empty">Pas encore de données.</p>'

    def averages(matches: list[dict]) -> dict[str, float]:
        totals: dict[str, float] = {}
        for match in matches:
            for skill, points in match["player_skills"].items():
                totals[skill] = totals.get(skill, 0.0) + points
        return {s: t / len(matches) for s, t in totals.items()} if matches else {}

    avg_win = averages(wins)
    avg_loss = averages(losses)
    keys = [k for k in SKILLS if k in avg_win or k in avg_loss]
    scale = max(
        [*avg_win.values(), *avg_loss.values(), 1.0]
    )
    rows = []
    for skill in keys:
        w = avg_win.get(skill, 0.0)
        lo = avg_loss.get(skill, 0.0)
        rows.append(
            _bar_row(
                f"{_skill_label(skill)} (victoires)", w / scale, "g", f"{w:.1f} pts"
            )
        )
        rows.append(
            _bar_row(
                f"{_skill_label(skill)} (défaites)", lo / scale, "r", f"{lo:.1f} pts"
            )
        )
    return "".join(rows)


def _history_table(history: list[dict], limit: int = 25) -> str:
    if not history:
        return '<p class="empty">Pas encore de données.</p>'
    head = (
        "<tr><th>Date</th><th>Niv.</th><th>Résultat</th><th>Durée</th>"
        "<th>Adversaire</th><th>Composition</th><th>Score</th>"
        "<th>Éliminations</th></tr>"
    )
    rows = []
    for match in reversed(history[-limit:]):
        result = match["result"]
        rows.append(
            "<tr>"
            f"<td>{escape(str(match['date']).replace('T', ' '))}</td>"
            f"<td>{match['level']}</td>"
            f'<td class="{_result_class(result)}">{escape(result)}</td>'
            f"<td>{match['duration_min']:.1f} min</td>"
            f"<td>{escape(match['ai_profile'])}</td>"
            f"<td>{escape(_composition_label(match['composition']))}</td>"
            f"<td>{match['player']['score']} vs {match['ai']['score']}</td>"
            f"<td>{match['player']['units_killed']} vs "
            f"{match['ai']['units_killed']}</td>"
            "</tr>"
        )
    return f"<table>{head}{''.join(rows)}</table>"


def generate_report(
    history: list[dict], path: Path = DEFAULT_REPORT_PATH
) -> Path:
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Fable, statistiques</title>
<style>{CSS}</style>
</head>
<body>
<h1>Fable</h1>
<p class="sub">Statistiques de vos parties, générées localement.</p>
{_summary_cards(history)}
<h2>Résultats par profil adverse</h2>
{_winrate_section(history, lambda m: m["ai_profile"], str)}
<h2>Résultats par composition jouée</h2>
{_winrate_section(history, lambda m: m["composition"], _composition_label)}
<h2>Points investis en moyenne, victoires contre défaites</h2>
{_skill_section(history)}
<h2>Historique des parties</h2>
{_history_table(history)}
</body>
</html>
"""
    path = Path(path)
    path.write_text(html, encoding="utf-8")
    return path
