"""Static HTML stats report built from the match history.

Self contained page (inline CSS, no JavaScript, no dependency), written
next to the project so it can be opened in any browser.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

from .skills import SKILLS

DEFAULT_REPORT_PATH = Path(__file__).resolve().parent.parent / "stats.html"

WIN = "victoire"
LOSS = "defaite"
DRAW = "egalite"

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2.5rem 1.5rem 4rem; background: #0e1116;
  color: #dfe5f1;
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.wrap { max-width: 1060px; margin: 0 auto; }
header { margin-bottom: 1.6rem; }
h1 { margin: 0; font-size: 2rem; letter-spacing: .5px; }
.sub { color: #8a94a8; margin: .2rem 0 0; }
.form { margin-top: .9rem; display: flex; align-items: center; gap: 4px; }
.form .lbl { color: #8a94a8; font-size: .8rem; margin-right: .4rem; }
.sq { width: 13px; height: 13px; border-radius: 3px; display: inline-block; }
.sq.w { background: #4ade80; } .sq.l { background: #f87171; }
.sq.d { background: #fbbf24; }

.cards {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: .7rem;
  margin-bottom: 1.6rem;
}
.card {
  background: #161b24; border: 1px solid #232b3a; border-radius: 12px;
  padding: .8rem 1rem;
}
.card .v { font-size: 1.45rem; font-weight: 700; line-height: 1.2; }
.card .l { color: #8a94a8; font-size: .78rem; margin-top: .1rem; }
.win { color: #4ade80; } .loss { color: #f87171; } .draw { color: #fbbf24; }

.cols { display: grid; grid-template-columns: 1fr 1fr; gap: .9rem; }
@media (max-width: 760px) {
  .cols { grid-template-columns: 1fr; }
  .cards { grid-template-columns: repeat(2, 1fr); }
}
section.panel {
  background: #161b24; border: 1px solid #232b3a; border-radius: 12px;
  padding: 1.1rem 1.3rem 1.2rem; margin-bottom: .9rem;
}
h2 { margin: 0 0 .9rem; font-size: 1rem; color: #aebdf0; }
.hint { color: #677085; font-size: .76rem; margin: -.6rem 0 .9rem; }

.brow { display: flex; align-items: center; gap: .7rem; margin: .45rem 0; }
.brow .name {
  width: 150px; min-width: 150px; text-align: right; color: #b9c2d8;
  font-size: .86rem; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis;
}
.stack {
  flex: 1; display: flex; height: 14px; border-radius: 7px;
  overflow: hidden; background: #0e1116;
}
.stack .s { height: 100%; }
.stack .s.w { background: #34c06b; }
.stack .s.d { background: #d9a323; }
.stack .s.l { background: #d65a5a; }
.brow .val {
  width: 120px; min-width: 120px; color: #8a94a8; font-size: .8rem;
}

.div-track { flex: 1; position: relative; height: 14px; }
.div-track::before {
  content: ""; position: absolute; left: 50%; top: -2px; bottom: -2px;
  width: 1px; background: #2c3550;
}
.div-track .rail {
  position: absolute; inset: 0; background: #0e1116; border-radius: 7px;
}
.div-track .bar { position: absolute; top: 0; bottom: 0; }
.div-track .bar.pos {
  left: 50%; background: linear-gradient(90deg, #2f9e5f, #4ade80);
  border-radius: 0 7px 7px 0;
}
.div-track .bar.neg {
  right: 50%; background: linear-gradient(270deg, #b04848, #f87171);
  border-radius: 7px 0 0 7px;
}

table { border-collapse: collapse; width: 100%; font-size: .86rem; }
th, td { padding: .42rem .6rem; text-align: left; white-space: nowrap; }
th {
  color: #8a94a8; font-weight: 600; font-size: .76rem;
  text-transform: uppercase; letter-spacing: .4px;
  border-bottom: 1px solid #232b3a;
}
tr:not(:last-child) td { border-bottom: 1px solid #1c2330; }
.chip {
  display: inline-block; padding: .05rem .55rem; border-radius: 99px;
  font-size: .76rem; font-weight: 600;
}
.chip.w { background: #173527; color: #4ade80; }
.chip.l { background: #3a1d1d; color: #f87171; }
.chip.d { background: #3a2f15; color: #fbbf24; }
.empty { color: #677085; font-style: italic; }
"""


def _result_chip(result: str) -> str:
    cls, label = {
        WIN: ("w", "victoire"),
        LOSS: ("l", "défaite"),
    }.get(result, ("d", "égalité"))
    return f'<span class="chip {cls}">{label}</span>'


def _skill_label(key: str) -> str:
    skill = SKILLS.get(key)
    return skill.label if skill else key


def _composition_label(comp: str) -> str:
    return "+".join(_skill_label(part) for part in comp.split("+"))


def _counts(matches: list[dict]) -> tuple[int, int, int]:
    wins = sum(1 for m in matches if m["result"] == WIN)
    draws = sum(1 for m in matches if m["result"] == DRAW)
    return wins, draws, len(matches) - wins - draws


def _recent_form(history: list[dict], limit: int = 20) -> str:
    if not history:
        return ""
    cls = {WIN: "w", LOSS: "l", DRAW: "d"}
    squares = "".join(
        f'<span class="sq {cls.get(m["result"], "d")}" '
        f'title="{escape(m["result"])} · {m["duration_min"]:.1f} min"></span>'
        for m in history[-limit:]
    )
    return (
        '<div class="form"><span class="lbl">Forme récente</span>'
        f"{squares}</div>"
    )


def _summary_cards(history: list[dict]) -> str:
    games = len(history)
    wins, draws, losses = _counts(history)
    streak = 0
    for match in reversed(history):
        if match["result"] != WIN:
            break
        streak += 1
    durations = [m["duration_min"] for m in history]
    avg_duration = sum(durations) / games if games else 0
    win_durations = [m["duration_min"] for m in history if m["result"] == WIN]
    best = min(win_durations) if win_durations else None
    cards = [
        ("Parties", str(games), ""),
        ("Taux de victoire", f"{100 * wins / games:.0f}%" if games else "0%",
         "win" if games and wins / games >= 0.5 else "loss"),
        ("Bilan", f"{wins}V {losses}D {draws}E", ""),
        ("Série en cours", str(streak), "win" if streak else ""),
        ("Durée moyenne", f"{avg_duration:.1f} min", ""),
        ("Victoire éclair", f"{best:.1f} min" if best is not None else "?", ""),
        ("Niveau max joué", str(max((m["level"] for m in history), default=1)), ""),
        ("Éliminations", str(sum(m["player"]["units_killed"] for m in history)), ""),
    ]
    return '<div class="cards">' + "".join(
        f'<div class="card"><div class="v {cls}">{escape(value)}</div>'
        f'<div class="l">{escape(label)}</div></div>'
        for label, value, cls in cards
    ) + "</div>"


def _stacked_row(name: str, matches: list[dict]) -> str:
    wins, draws, losses = _counts(matches)
    total = len(matches)
    segments = ""
    for count, cls in ((wins, "w"), (draws, "d"), (losses, "l")):
        if count:
            segments += (
                f'<div class="s {cls}" '
                f'style="width:{100 * count / total:.1f}%"></div>'
            )
    rate = 100 * wins / total
    plural = "s" if total > 1 else ""
    return (
        f'<div class="brow"><div class="name" title="{escape(name)}">'
        f"{escape(name)}</div>"
        f'<div class="stack">{segments}</div>'
        f'<div class="val">{total} partie{plural} · {rate:.0f}%</div></div>'
    )


def _grouped_section(
    history: list[dict], key, label_fn, min_games: int = 2
) -> str:
    groups: dict[str, list[dict]] = {}
    for match in history:
        groups.setdefault(key(match), []).append(match)
    if not groups:
        return '<p class="empty">Pas encore de données.</p>'
    main = {n: m for n, m in groups.items() if len(m) >= min_games}
    rest = [m for n, ms in groups.items() if n not in main for m in ms]
    if not main:  # everything is small, show as is
        main, rest = groups, []
    rows = [
        _stacked_row(label_fn(name), main[name])
        for name in sorted(main, key=lambda n: -len(main[n]))
    ]
    if rest:
        rows.append(_stacked_row(f"autres ({len(rest)})", rest))
    return "".join(rows)


def _skill_delta_section(history: list[dict]) -> str:
    wins = [m for m in history if m["result"] == WIN]
    losses = [m for m in history if m["result"] == LOSS]
    if not wins or not losses:
        return (
            '<p class="empty">Il faut au moins une victoire et une défaite'
            " pour comparer.</p>"
        )

    def averages(matches: list[dict]) -> dict[str, float]:
        totals: dict[str, float] = {}
        for match in matches:
            for skill, points in match["player_skills"].items():
                totals[skill] = totals.get(skill, 0.0) + points
        return {s: t / len(matches) for s, t in totals.items()}

    avg_win = averages(wins)
    avg_loss = averages(losses)
    deltas = []
    for skill in SKILLS:
        w = avg_win.get(skill, 0.0)
        lo = avg_loss.get(skill, 0.0)
        if w == 0.0 and lo == 0.0:
            continue
        deltas.append((skill, w - lo, w, lo))
    if not deltas:
        return '<p class="empty">Pas encore de données.</p>'
    deltas.sort(key=lambda d: -d[1])
    scale = max(abs(d[1]) for d in deltas) or 1.0
    rows = []
    for skill, delta, w, lo in deltas:
        width = 50 * abs(delta) / scale
        side = "pos" if delta >= 0 else "neg"
        sign = "+" if delta >= 0 else ""
        rows.append(
            f'<div class="brow"><div class="name">{escape(_skill_label(skill))}'
            "</div>"
            '<div class="div-track"><div class="rail"></div>'
            f'<div class="bar {side}" style="width:{width:.1f}%"></div></div>'
            f'<div class="val">{sign}{delta:.1f} pts ({w:.1f} vs {lo:.1f})'
            "</div></div>"
        )
    return "".join(rows)


def _history_table(history: list[dict], limit: int = 25) -> str:
    if not history:
        return '<p class="empty">Pas encore de données.</p>'
    head = (
        "<tr><th>Date</th><th>Niv.</th><th>Résultat</th><th>Durée</th>"
        "<th>Adversaire</th><th>Composition</th><th>Score</th>"
        "<th>Élim.</th></tr>"
    )
    rows = []
    for match in reversed(history[-limit:]):
        date = str(match["date"]).replace("T", " ")[:16]
        rows.append(
            "<tr>"
            f"<td>{escape(date)}</td>"
            f"<td>{match['level']}</td>"
            f"<td>{_result_chip(match['result'])}</td>"
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
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Doctrine, statistiques</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
<h1>Doctrine</h1>
<p class="sub">Statistiques de vos parties, générées localement.</p>
{_recent_form(history)}
</header>
{_summary_cards(history)}
<div class="cols">
<section class="panel">
<h2>Résultats par profil adverse</h2>
{_grouped_section(history, lambda m: m["ai_profile"], str, min_games=1)}
</section>
<section class="panel">
<h2>Résultats par composition jouée</h2>
{_grouped_section(history, lambda m: m["composition"], _composition_label)}
</section>
</div>
<section class="panel">
<h2>Quelles compétences font gagner ?</h2>
<p class="hint">Écart de points investis en moyenne entre vos victoires
et vos défaites. À droite en vert: davantage présent dans les victoires.</p>
{_skill_delta_section(history)}
</section>
<section class="panel">
<h2>Historique des parties</h2>
{_history_table(history)}
</section>
</div>
</body>
</html>
"""
    path = Path(path)
    path.write_text(html, encoding="utf-8")
    return path
