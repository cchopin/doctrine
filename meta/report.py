"""Static HTML stats report built from the match history.

Self contained dashboard (inline CSS and SVG, no JavaScript, no
dependency), written next to the project so any browser can open it.
"""
from __future__ import annotations

import math
from html import escape
from pathlib import Path

from .progress import XP_DRAW, XP_LOSS, XP_WIN, xp_needed
from .skills import SKILLS

DEFAULT_REPORT_PATH = Path(__file__).resolve().parent.parent / "stats.html"

WIN = "victoire"
LOSS = "defaite"
DRAW = "egalite"

XP_BY_RESULT = {WIN: XP_WIN, DRAW: XP_DRAW, LOSS: XP_LOSS}

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  margin: 0; padding: 3rem 1.5rem 4rem; background: #0c0f15; color: #e3e8f2;
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.wrap { max-width: 980px; margin: 0 auto; }
header.page { margin-bottom: 1.8rem; }
header.page h1 {
  margin: 0; font-size: 1.6rem; letter-spacing: 3px; text-transform: uppercase;
}
header.page .sub { color: #79839a; margin: .15rem 0 0; font-size: .85rem; }

.panel {
  background: #11151e; border: 1px solid #1d2433; border-radius: 14px;
  padding: 1.3rem 1.5rem; margin-bottom: 1rem;
}
h2.kicker {
  display: flex; align-items: baseline; gap: .6rem;
  margin: 0 0 1rem; font-size: .8rem; letter-spacing: 2px;
  text-transform: uppercase; color: #aebdf0;
}
h2.kicker::before {
  content: attr(data-n); color: #56b4e9; font-size: .72rem;
  font-variant-numeric: tabular-nums;
}
.legendline { color: #5d6679; font-size: .75rem; margin: -0.6rem 0 1rem; }
.empty { color: #5d6679; font-style: italic; margin: .3rem 0; }
.num { font-variant-numeric: tabular-nums; }

/* Hero */
.hero { display: grid; grid-template-columns: 200px 1fr 200px; gap: 2rem;
  align-items: center; }
@media (max-width: 820px) { .hero { grid-template-columns: 1fr; } }
.donut { position: relative; width: 200px; margin: 0 auto; }
.donut svg { display: block; width: 100%; }
.donut .center {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; text-align: center;
}
.donut .pct { font-size: 2.1rem; font-weight: 800; line-height: 1; }
.donut .lbl { color: #79839a; font-size: .7rem; letter-spacing: 1.5px;
  text-transform: uppercase; margin-top: .3rem; }
.kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.1rem 1.6rem; }
.kpi .v { font-size: 1.35rem; font-weight: 750; line-height: 1.15; }
.kpi .l { color: #79839a; font-size: .7rem; letter-spacing: 1px;
  text-transform: uppercase; margin-top: .1rem; }
.c-win { color: #56b4e9; } .c-loss { color: #e69f00; } .c-draw { color: #98a2b8; }
.formcol { text-align: center; }
.formcol .squares {
  display: flex; flex-wrap: wrap; gap: 4px; justify-content: center;
  max-width: 190px; margin: 0 auto .45rem;
}
.sq {
  width: 15px; height: 15px; border-radius: 4px; display: inline-flex;
  align-items: center; justify-content: center;
  font-size: 9px; font-weight: 800; color: #0c0f15;
}
.sq.w { background: #56b4e9; }
.sq.l { background: repeating-linear-gradient(135deg,#e69f00 0 3px,#b87e0d 3px 6px); }
.sq.d { background: #98a2b8; }
.formcol .lbl { color: #79839a; font-size: .7rem; letter-spacing: 1px;
  text-transform: uppercase; }

/* Charts */
.chart svg { display: block; width: 100%; height: auto; }

/* Result rows: label, volume proportional stacked bar, count, rate */
.rows { display: grid; gap: .45rem; }
.rrow {
  display: grid; grid-template-columns: 150px 1fr 44px 52px;
  gap: .8rem; align-items: center; font-size: .85rem;
}
.rrow .rname {
  color: #b9c2d8; text-align: right; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
}
.rrow .rtrack { height: 12px; display: flex; }
.rrow .rbar {
  height: 100%; display: flex; border-radius: 6px; overflow: hidden;
  min-width: 12px;
}
.rbar i { display: block; height: 100%; }
.rbar .w { background: #56b4e9; }
.rbar .d { background: #5b6478; }
.rbar .l { background: repeating-linear-gradient(135deg,#e69f00 0 4px,#b87e0d 4px 8px); }
.rrow .rn { color: #79839a; text-align: right; font-size: .78rem; }
.rrow .rpct { text-align: right; font-weight: 700; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
@media (max-width: 820px) { .cols { grid-template-columns: 1fr; } }
.cols .panel { margin-bottom: 0; }
.cols-after { margin-top: 1rem; }
.wide-names .rrow { grid-template-columns: 250px 1fr 44px 52px; }

/* Skill deltas: centered lollipops */
.lrow {
  display: grid; grid-template-columns: 130px 1fr 120px; gap: .8rem;
  align-items: center; font-size: .85rem; margin: .42rem 0;
}
.lrow .lname { color: #b9c2d8; text-align: right; }
.ltrack { position: relative; height: 14px; }
.ltrack::before {
  content: ""; position: absolute; left: 0; right: 0; top: 6px; height: 2px;
  background: #1d2433; border-radius: 1px;
}
.ltrack::after {
  content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 2px;
  background: #2c3550;
}
.stick { position: absolute; top: 5px; height: 4px; border-radius: 2px; }
.stick.pos { background: #56b4e9; }
.stick.neg { background: #e69f00; }
.ldot {
  position: absolute; top: 1px; width: 12px; height: 12px;
  border-radius: 50%; transform: translateX(-50%); border: 2px solid #11151e;
}
.ldot.pos { background: #56b4e9; }
.ldot.neg {
  background: repeating-linear-gradient(135deg,#e69f00 0 2px,#b87e0d 2px 4px);
}
.lrow .lval { color: #79839a; font-size: .78rem; }
.lrow .lval b { color: #e3e8f2; font-size: .85rem; margin-right: .35rem; }

/* History */
table { border-collapse: collapse; width: 100%; font-size: .84rem; }
th, td { padding: .42rem .6rem; text-align: left; white-space: nowrap; }
th {
  color: #5d6679; font-weight: 600; font-size: .68rem;
  text-transform: uppercase; letter-spacing: 1px;
  border-bottom: 1px solid #1d2433;
}
td { border-bottom: 1px solid #151a25; }
tr:last-child td { border-bottom: none; }
.chip {
  display: inline-block; padding: .02rem .5rem; border-radius: 99px;
  font-size: .72rem; font-weight: 700; letter-spacing: .3px;
}
.chip.w { background: rgba(86,180,233,.12); color: #56b4e9; }
.chip.l { background: rgba(230,159,0,.12); color: #e8b54a; }
.chip.d { background: rgba(152,162,184,.12); color: #aab3c5; }
"""


# Shared helpers

def _skill_label(key: str) -> str:
    skill = SKILLS.get(key)
    return skill.label if skill else key


def _composition_label(comp: str) -> str:
    return "+".join(_skill_label(part) for part in comp.split("+"))


def _counts(matches: list[dict]) -> tuple[int, int, int]:
    wins = sum(1 for m in matches if m["result"] == WIN)
    draws = sum(1 for m in matches if m["result"] == DRAW)
    return wins, draws, len(matches) - wins - draws


def _empty() -> str:
    return '<p class="empty">Pas encore de données.</p>'


# Hero: donut, key figures, recent form

def _donut_svg(wins: int, draws: int, losses: int) -> str:
    total = max(1, wins + draws + losses)
    radius = 52.0
    circ = 2 * math.pi * radius
    segments = []
    offset = 0.0
    for count, color in (
        (wins, "#56b4e9"), (draws, "#5b6478"), (losses, "url(#hatch)"),
    ):
        length = circ * count / total
        if count:
            segments.append(
                f'<circle cx="60" cy="60" r="{radius}" fill="none" '
                f'stroke="{color}" stroke-width="13" '
                f'stroke-dasharray="{max(0.0, length - 2):.1f} {circ:.1f}" '
                f'stroke-dashoffset="{-offset:.1f}"/>'
            )
        offset += length
    return f"""<svg viewBox="0 0 120 120">
<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse"
 patternTransform="rotate(45)">
<rect width="6" height="6" fill="#e69f00"/>
<rect width="3" height="6" fill="#b87e0d"/></pattern></defs>
<g transform="rotate(-90 60 60)">
<circle cx="60" cy="60" r="{radius}" fill="none" stroke="#1a2030"
 stroke-width="13"/>
{''.join(segments)}
</g></svg>"""


def _hero(history: list[dict]) -> str:
    games = len(history)
    wins, draws, losses = _counts(history)
    streak = 0
    for match in reversed(history):
        if match["result"] != WIN:
            break
        streak += 1
    avg = sum(m["duration_min"] for m in history) / games if games else 0.0
    win_durations = [m["duration_min"] for m in history if m["result"] == WIN]
    best = f"{min(win_durations):.1f} min" if win_durations else "?"
    rate = 100 * wins / games if games else 0
    kpis = [
        (str(wins), "Victoires", "c-win"),
        (str(losses), "Défaites", "c-loss"),
        (str(draws), "Égalités", "c-draw"),
        (str(streak), "Série en cours", "c-win" if streak else ""),
        (f"{avg:.1f} min", "Durée moyenne", ""),
        (best, "Victoire éclair", ""),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="v num {cls}">{escape(v)}</div>'
        f'<div class="l">{label}</div></div>'
        for v, label, cls in kpis
    )
    style = {WIN: ("w", "V"), LOSS: ("l", "D"), DRAW: ("d", "E")}
    squares = "".join(
        '<span class="sq {0}" title="{1} · {2:.1f} min">{3}</span>'.format(
            style.get(m["result"], ("d", "E"))[0],
            escape(m["result"]),
            m["duration_min"],
            style.get(m["result"], ("d", "E"))[1],
        )
        for m in history[-24:]
    )
    return f"""<section class="panel hero">
<div class="donut">{_donut_svg(wins, draws, losses)}
<div class="center"><div class="pct num">{rate:.0f}%</div>
<div class="lbl">Taux de victoire</div></div></div>
<div class="kpis">{kpi_html}</div>
<div class="formcol"><div class="squares">{squares}</div>
<div class="lbl">Forme récente</div></div>
</section>"""


# Progression chart: cumulative experience with level marks

def _progress_chart(history: list[dict]) -> str:
    if len(history) < 2:
        return _empty()
    gains = [XP_BY_RESULT.get(m["result"], 0) for m in history]
    cumulative = []
    total = 0
    for gain in gains:
        total += gain
        cumulative.append(total)
    width, height, pad = 820, 170, 12
    max_xp = cumulative[-1]
    n = len(cumulative)

    def px(i: int) -> float:
        return pad + (width - 2 * pad) * i / (n - 1)

    def py(value: float) -> float:
        return height - pad - (height - 2 * pad) * value / max_xp

    points = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(cumulative))
    area = (
        f"M{px(0):.1f},{height - pad} L" + points.replace(" ", " L")
        + f" L{px(n - 1):.1f},{height - pad} Z"
    )
    # Level thresholds crossed within the recorded history.
    marks = []
    level, threshold = 1, xp_needed(1)
    for i, value in enumerate(cumulative):
        while value >= threshold:
            level += 1
            marks.append(
                f'<line x1="{px(i):.1f}" y1="{pad}" x2="{px(i):.1f}" '
                f'y2="{height - pad}" stroke="#2c3550" stroke-width="1" '
                f'stroke-dasharray="3 4"/>'
                f'<text x="{px(i) + 4:.1f}" y="{pad + 9}" fill="#79839a" '
                f'font-size="9">niv. {level}</text>'
            )
            threshold += xp_needed(level)
    dot_color = {WIN: "#56b4e9", LOSS: "#e69f00", DRAW: "#98a2b8"}
    dots = "".join(
        f'<circle cx="{px(i):.1f}" cy="{py(v):.1f}" r="2.6" '
        f'fill="{dot_color.get(history[i]["result"], "#98a2b8")}"/>'
        for i, v in enumerate(cumulative)
    )
    return f"""<svg viewBox="0 0 {width} {height}">
<defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#56b4e9" stop-opacity=".25"/>
<stop offset="1" stop-color="#56b4e9" stop-opacity="0"/>
</linearGradient></defs>
<path d="{area}" fill="url(#area)"/>
<polyline points="{points}" fill="none" stroke="#56b4e9"
 stroke-width="2" stroke-linejoin="round"/>
{''.join(marks)}
{dots}
</svg>"""


# Result groups: volume proportional stacked rows

def _result_rows(
    history: list[dict], key, label_fn,
    min_games: int = 1, limit: int = 8,
) -> str:
    groups: dict[str, list[dict]] = {}
    for match in history:
        groups.setdefault(key(match), []).append(match)
    if not groups:
        return _empty()
    main = {n: m for n, m in groups.items() if len(m) >= min_games}
    if not main:
        main = dict(groups)
    ordered = sorted(main, key=lambda n: -len(main[n]))[:limit]
    rest = [m for n, ms in groups.items() if n not in ordered for m in ms]
    biggest = max(
        [len(main[n]) for n in ordered] + [len(rest)] or [1]
    )
    rows = []

    def row(label: str, matches: list[dict]) -> str:
        wins, draws, losses = _counts(matches)
        total = len(matches)
        share = 100 * total / biggest
        segs = "".join(
            f'<i class="{cls}" style="width:{100 * c / total:.1f}%"></i>'
            for c, cls in ((wins, "w"), (draws, "d"), (losses, "l")) if c
        )
        return (
            f'<div class="rrow"><span class="rname" title="{escape(label)}">'
            f"{escape(label)}</span>"
            f'<span class="rtrack"><span class="rbar" '
            f'style="width:{share:.1f}%">{segs}</span></span>'
            f'<span class="rn num">{total}</span>'
            f'<span class="rpct num">{100 * wins / total:.0f}%</span></div>'
        )

    for name in ordered:
        rows.append(row(label_fn(name), main[name]))
    if rest:
        rows.append(row(f"autres ({len(rest)})", rest))
    return '<div class="rows">' + "".join(rows) + "</div>"


# Skill deltas: centered lollipops

def _skill_deltas(history: list[dict]) -> str:
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

    avg_win, avg_loss = averages(wins), averages(losses)
    deltas = [
        (skill, avg_win.get(skill, 0.0) - avg_loss.get(skill, 0.0),
         avg_win.get(skill, 0.0), avg_loss.get(skill, 0.0))
        for skill in SKILLS
        if avg_win.get(skill, 0.0) or avg_loss.get(skill, 0.0)
    ]
    if not deltas:
        return _empty()
    deltas.sort(key=lambda d: -d[1])
    scale = max(abs(d[1]) for d in deltas) or 1.0
    rows = []
    for skill, delta, w, lo in deltas:
        half = 46 * abs(delta) / scale  # percent of half track
        side = "pos" if delta >= 0 else "neg"
        if delta >= 0:
            stick = f"left:50%;width:{half:.1f}%"
            dot = f"left:{50 + half:.1f}%"
        else:
            stick = f"right:50%;width:{half:.1f}%"
            dot = f"left:{50 - half:.1f}%"
        sign = "+" if delta >= 0 else ""
        rows.append(
            f'<div class="lrow"><span class="lname">{escape(_skill_label(skill))}'
            "</span>"
            f'<span class="ltrack"><span class="stick {side}" style="{stick}">'
            f'</span><span class="ldot {side}" style="{dot}"></span></span>'
            f'<span class="lval num"><b>{sign}{delta:.1f}</b>{w:.1f} vs {lo:.1f}'
            "</span></div>"
        )
    return "".join(rows)


# History table

def _result_chip(result: str) -> str:
    cls, label = {
        WIN: ("w", "victoire"), LOSS: ("l", "défaite"),
    }.get(result, ("d", "égalité"))
    return f'<span class="chip {cls}">{label}</span>'


def _history_table(history: list[dict], limit: int = 15) -> str:
    if not history:
        return _empty()
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
            f'<td class="num">{escape(date)}</td>'
            f'<td class="num">{match["level"]}</td>'
            f"<td>{_result_chip(match['result'])}</td>"
            f'<td class="num">{match["duration_min"]:.1f} min</td>'
            f"<td>{escape(match['ai_profile'])}</td>"
            f"<td>{escape(_composition_label(match['composition']))}</td>"
            f'<td class="num">{match["player"]["score"]} vs {match["ai"]["score"]}</td>'
            f'<td class="num">{match["player"]["units_killed"]} vs '
            f'{match["ai"]["units_killed"]}</td>'
            "</tr>"
        )
    return f"<table>{head}{''.join(rows)}</table>"


def generate_report(
    history: list[dict], path: Path = DEFAULT_REPORT_PATH
) -> Path:
    games = len(history)
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Doctrine · Statistiques</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="page">
<h1>Doctrine</h1>
<p class="sub">{games} partie{"s" if games > 1 else ""} enregistrée{"s" if games > 1 else ""}</p>
</header>
{_hero(history)}
<section class="panel chart">
<h2 class="kicker" data-n="01">Progression</h2>
<p class="legendline">Expérience cumulée au fil des parties.
Point bleu: victoire · gris: égalité · orange: défaite</p>
{_progress_chart(history)}
</section>
<div class="cols">
<section class="panel">
<h2 class="kicker" data-n="02">Profils adverses</h2>
{_result_rows(history, lambda m: m["ai_profile"], str)}
</section>
<section class="panel">
<h2 class="kicker" data-n="03">Vos compositions</h2>
{_result_rows(history, lambda m: m["composition"], _composition_label,
              min_games=2)}
</section>
</div>
<section class="panel cols-after wide-names">
<h2 class="kicker" data-n="04">Confrontations</h2>
<p class="legendline">Votre doctrine face à chaque profil adverse.
Longueur de barre: nombre de parties · bleu: victoires · orange hachuré:
défaites · à droite: taux de victoire</p>
{_result_rows(history,
              lambda m: m["composition"] + "|" + m["ai_profile"],
              lambda key: _composition_label(key.partition("|")[0])
              + " vs " + key.partition("|")[2])}
</section>
<section class="panel">
<h2 class="kicker" data-n="05">Quelles compétences font gagner ?</h2>
<p class="legendline">Écart de points investis en moyenne entre victoires
et défaites. À droite en bleu: davantage présent dans vos victoires.
Détail: moyenne dans les victoires vs dans les défaites</p>
{_skill_deltas(history)}
</section>
<section class="panel">
<h2 class="kicker" data-n="06">Historique</h2>
{_history_table(history)}
</section>
</div>
</body>
</html>
"""
    path = Path(path)
    path.write_text(html, encoding="utf-8")
    return path
