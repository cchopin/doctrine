"""Full rules reference, generated from the engine data structures.

The tables (units, buildings, skills, constants) are read straight from
the engine so the documentation cannot drift from the code. Output is a
single static HTML page with a sidebar, in the dashboard style.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

from engine import combat
from engine import game as game_mod
from engine.ai import (
    ALARM_RADIUS,
    ATTACK_SQUAD_SIZE,
    HOME_GROUND_BONUS,
    HOME_GROUND_RADIUS,
    MAX_BUILDERS_PER_SITE,
    REPAIR_HP_PER_WORK,
    REPAIR_TRIGGER,
)
from engine.entities import (
    BUILDING_ATTACKS,
    BUILDING_SPECS,
    UNIT_SPECS,
)
from engine.world import RESOURCE_LABEL_FR, TERRAIN_COST, Terrain
from .progress import XP_DRAW, XP_LOSS, XP_WIN, skill_budget, xp_needed
from .skills import SKILLS

DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent / "docs" / "regles.html"

# Effect formulas per skill, kept next to the table generator so adding a
# skill nudges you to document it.
SKILL_EFFECTS: dict[str, str] = {
    "exploration": "Vitesse: éclaireurs ×(1 + 0.10·n), autres unités ×(1 + 0.05·n)",
    "combat": "Dégâts ×(1 + 0.10·n), PV ×(1 + 0.06·n), coût des soldats ×(1 + 0.06·n)",
    "recolte": "Extraction ×(1 + 0.20·n)",
    "transport": "Ramassage ×(1 + 0.20·n), capacité ×(1 + 0.12·n)",
    "construction": "Travail de construction et de réparation ×(1 + 0.25·n)",
    "tradeur": "Taux de revente = 0.4 + 0.15·n nourriture par unité vendue",
    "science": "Débloque la tour de garde",
    "mecanique": "+n PV toutes les 10 ticks près d'un bâtiment allié (rayon 6)",
    "logistique": "Transporteurs ×(1 + 0.15·n), portée de ravitaillement +8·n cases",
    "espionnage": "Toutes les 60 s, révèle un rayon de 5 autour d'un bâtiment ennemi",
    "fortification": "PV des bâtiments ×(1 + 0.20·n)",
    "cartographie": "Rayon de vision de toutes les unités +n",
    "conscription": "Temps de formation des soldats ÷(1 + 0.15·n)",
    "pillage": "+8·n nourriture par unité éliminée, +25·n ressources par bâtiment détruit",
    "frenesie": "Période d'attaque ÷(1 + 0.12·n), plancher 2 ticks",
}

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  margin: 0; background: #0c0f15; color: #e3e8f2;
  font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.layout { display: grid; grid-template-columns: 230px 1fr; min-height: 100vh; }
nav {
  border-right: 1px solid #1d2433; padding: 2rem 1.2rem;
  position: sticky; top: 0; height: 100vh; overflow-y: auto;
}
nav .brand { font-weight: 800; letter-spacing: 2px; margin-bottom: .2rem; }
nav .vtag { color: #5d6679; font-size: .72rem; margin-bottom: 1.2rem; }
nav a {
  display: block; color: #98a2b8; text-decoration: none;
  padding: .28rem .5rem; border-radius: 7px; font-size: .85rem;
}
nav a:hover { color: #56b4e9; background: rgba(86,180,233,.06); }
main { padding: 2.5rem 3rem 5rem; max-width: 860px; }
h1 { margin: 0 0 .3rem; font-size: 1.7rem; }
.sub { color: #79839a; margin: 0 0 2rem; }
h2 {
  margin: 2.6rem 0 .7rem; font-size: 1.15rem; color: #aebdf0;
  padding-top: 1rem; border-top: 1px solid #1d2433;
}
h2:first-of-type { border-top: none; padding-top: 0; }
p, li { color: #c4ccdd; font-size: .92rem; }
code {
  background: #161b26; border: 1px solid #232b3a; border-radius: 5px;
  padding: .05rem .35rem; font-size: .84rem; color: #8fd0ff;
}
table { border-collapse: collapse; width: 100%; margin: .7rem 0 1rem; }
th, td { padding: .4rem .6rem; text-align: left; font-size: .85rem; }
th {
  color: #5d6679; font-weight: 600; font-size: .68rem;
  text-transform: uppercase; letter-spacing: 1px;
  border-bottom: 1px solid #1d2433;
}
td { border-bottom: 1px solid #151a25; color: #c4ccdd; }
td.sym { color: #56b4e9; font-weight: 700; font-family: monospace; }
.formula {
  background: #11151e; border: 1px solid #1d2433; border-radius: 10px;
  padding: .7rem 1rem; margin: .6rem 0; font-size: .88rem; color: #c4ccdd;
}
.back { color: #56b4e9; text-decoration: none; font-size: .85rem; }
"""


def _cost(cost: dict) -> str:
    if not cost:
        return "gratuit"
    return ", ".join(
        f"{n} {RESOURCE_LABEL_FR[r]}" for r, n in cost.items()
    )


def _units_table() -> str:
    rows = "".join(
        f'<tr><td class="sym">{spec.symbol}</td><td>{escape(spec.label_fr)}</td>'
        f"<td>{spec.hp}</td><td>{spec.damage}</td><td>{spec.speed:.2f}</td>"
        f"<td>{spec.capacity or '·'}</td><td>{spec.sight}</td>"
        f"<td>{_cost(spec.cost)}</td><td>{spec.train_work}</td></tr>"
        for spec in UNIT_SPECS.values()
    )
    return (
        "<table><tr><th></th><th>Unité</th><th>PV</th><th>Dégâts</th>"
        "<th>Vitesse (cases/tick)</th><th>Capacité</th><th>Vision</th>"
        "<th>Coût</th><th>Formation (ticks)</th></tr>" + rows + "</table>"
    )


def _buildings_table() -> str:
    rows = []
    for btype, spec in BUILDING_SPECS.items():
        extra = []
        if spec.min_level > 1:
            extra.append(f"niveau {spec.min_level}")
        if spec.requires_skill:
            extra.append(f"compétence {spec.requires_skill}")
        attack = BUILDING_ATTACKS.get(btype)
        rows.append(
            f'<tr><td class="sym">{spec.symbol}</td>'
            f"<td>{escape(spec.label_fr)}</td><td>{spec.hp}</td>"
            f"<td>{spec.sight}</td><td>{_cost(spec.cost)}</td>"
            f"<td>{spec.build_work or '·'}</td>"
            f"<td>{', '.join(extra) or '·'}</td>"
            f"<td>{f'portée {attack[0]}, {attack[1]} dégâts / {attack[2]} ticks' if attack else '·'}</td></tr>"
        )
    return (
        "<table><tr><th></th><th>Bâtiment</th><th>PV</th><th>Vision</th>"
        "<th>Coût</th><th>Travail</th><th>Prérequis</th><th>Riposte</th></tr>"
        + "".join(rows) + "</table>"
    )


def _skills_table() -> str:
    rows = "".join(
        f"<tr><td>{escape(s.label)}</td>"
        f"<td>{'base' if s.kind == 'base' else f'niveau {s.min_level}'}</td>"
        f"<td>{s.max_points}</td>"
        f"<td>{escape(SKILL_EFFECTS.get(s.key, s.description))}</td></tr>"
        for s in SKILLS.values()
    )
    return (
        "<table><tr><th>Compétence</th><th>Déblocage</th><th>Max</th>"
        "<th>Effet (n = points investis)</th></tr>" + rows + "</table>"
    )


def _levels_table() -> str:
    rows = []
    for level in range(1, 17):
        unlocks = [
            s.label for s in SKILLS.values() if s.min_level == level
        ] + [
            spec.label_fr for spec in BUILDING_SPECS.values()
            if spec.min_level == level and level > 1
        ]
        rows.append(
            f"<tr><td>{level}</td><td>{skill_budget(level)}</td>"
            f"<td>{xp_needed(level)}</td>"
            f"<td>{', '.join(unlocks) or '·'}</td></tr>"
        )
    return (
        "<table><tr><th>Niveau</th><th>Points</th><th>XP vers le suivant</th>"
        "<th>Déblocages</th></tr>" + "".join(rows) + "</table>"
    )


def generate_rules(path: Path = DEFAULT_RULES_PATH) -> Path:
    terrain_costs = " · ".join(
        f"{t.value}: {'infranchissable' if TERRAIN_COST[t] == float('inf') else TERRAIN_COST[t]}"
        for t in Terrain
    )
    sections = f"""
<h2 id="principe">Principe</h2>
<p>Doctrine est un auto-battler stratégique inspiré des 4X. Avant la
partie, le joueur répartit un budget de points entre ses compétences
(sa doctrine), puis les deux armées jouent seules: exploration, récolte,
construction, combat. L'adversaire tire un profil au hasard parmi
guerrier, économiste, explorateur et équilibré.</p>

<h2 id="simulation">Simulation</h2>
<p>La simulation avance par ticks: <code>{game_mod.TICKS_PER_SECOND} ticks
par seconde</code>. Une partie est limitée à 20 minutes
({game_mod.DEFAULT_TIME_LIMIT_TICKS} ticks). La carte fait 120×80 cases,
générée procéduralement (graine rejouable). Coût de déplacement par
terrain: {terrain_costs}. Le brouillard de guerre est par équipe: seules
les zones explorées sont connues, seules les zones en vue sont à jour.</p>

<h2 id="unites">Unités</h2>
{_units_table()}
<p>La vitesse finale est <code>vitesse de base × multiplicateur de
marche</code>. Les capacités sont multipliées par le bonus de transport.
Les soldats formés au QG (sans caserne) subissent ×1.5 sur le temps de
formation.</p>

<h2 id="batiments">Bâtiments</h2>
{_buildings_table()}
<p>Un chantier démarre à 20% des PV finaux et au plus
{MAX_BUILDERS_PER_SITE} ouvriers y travaillent. Les bâtiments endommagés
sous {REPAIR_TRIGGER:.0%} de leurs PV sont réparés par les ouvriers à
<code>{REPAIR_HP_PER_WORK} PV × travail de construction</code> par tick.</p>

<h2 id="economie">Économie</h2>
<div class="formula">Extraction = 0.7 × (1 + 0.20 × récolte) par ouvrier
et par tick, empilée sur le gisement.</div>
<div class="formula">Ramassage = 2.5 × (1 + 0.20 × transport) par tick.
Capacité = base × (1 + 0.12 × transport).</div>
<p>Les ouvriers empilent leur récolte sur place, les transporteurs font
la navette vers le dépôt le plus proche (QG ou entrepôt). Sans
transporteur vivant, les ouvriers portent eux-mêmes. Le marché vend
toutes les {game_mod.MARKET_PERIOD} ticks jusqu'à {game_mod.MARKET_BATCH}
unités du stock le plus haut (hors nourriture) au-dessus d'un plancher de
{game_mod.MARKET_KEEP}, au taux <code>0.4 + 0.15 × tradeur</code>.</p>

<h2 id="competences">Compétences</h2>
{_skills_table()}

<h2 id="combat">Combat</h2>
<div class="formula">Dégâts par coup = arrondi(dégâts de base ×
(1 + 0.10 × combat)), une attaque toutes les
{combat.ATTACK_PERIOD} ticks (réduit par frénésie), au contact
(distance de Tchebychev ≤ 1).</div>
<div class="formula">PV au recrutement = arrondi(PV de base ×
(1 + 0.06 × combat)).</div>
<ul>
<li>Les soldats défendent leur base tant que l'escouade n'atteint pas
<code>{ATTACK_SQUAD_SIZE} + points totaux ÷ 15</code> têtes, puis passent
à l'offensive. Ils battent en retraite sous la moitié de ce seuil.</li>
<li>Alarme: un intrus à moins de {ALARM_RADIUS} cases du QG rappelle tous
les soldats.</li>
<li>Avantage du terrain: ×{HOME_GROUND_BONUS} sur les dégâts à moins de
{HOME_GROUND_RADIUS} cases de son QG (unités seulement).</li>
<li>Les civils touchés fuient vers le QG pendant 60 ticks.</li>
</ul>

<h2 id="contres">Contres et équilibrage</h2>
<ul>
<li><b>Entretien</b>: au-delà de {game_mod.FREE_SOLDIERS} soldats, chaque
soldat consomme 1 nourriture toutes les {game_mod.UPKEEP_PERIOD} ticks.
Grenier vide: tous les soldats perdent {game_mod.FAMINE_DAMAGE} PV
(famine).</li>
<li><b>Attrition</b>: un soldat à plus de {game_mod.ATTRITION_RANGE}
cases (Manhattan) de tout bâtiment allié perd
{game_mod.ATTRITION_DAMAGE} PV toutes les {game_mod.ATTRITION_PERIOD}
ticks. La logistique étend cette portée de
{game_mod.ATTRITION_RANGE_PER_LOGISTIC} cases par point.</li>
<li><b>Coût de l'élite</b>: le coût des soldats est multiplié par
<code>1 + 0.06 × combat</code>.</li>
<li><b>Défense</b>: riposte du QG et des tours (voir bâtiments),
réparation par les ouvriers, avantage du terrain.</li>
</ul>

<h2 id="progression">Progression</h2>
<p>Victoire: +{XP_WIN} xp · égalité: +{XP_DRAW} xp · défaite:
+{XP_LOSS} xp. La répartition des points est remise à zéro à chaque
partie, seuls le niveau et l'expérience persistent.</p>
{_levels_table()}

<h2 id="score">Score et fin de partie</h2>
<div class="formula">Score = somme des stocks + 5 × unités + 20 ×
bâtiments terminés + cases explorées ÷ 50.</div>
<p>La partie se termine par destruction d'un QG, ou au temps limite où
le meilleur score l'emporte (égalité possible).</p>
"""
    anchors = [
        ("principe", "Principe"), ("simulation", "Simulation"),
        ("unites", "Unités"), ("batiments", "Bâtiments"),
        ("economie", "Économie"), ("competences", "Compétences"),
        ("combat", "Combat"), ("contres", "Contres"),
        ("progression", "Progression"), ("score", "Score"),
    ]
    nav = "".join(f'<a href="#{a}">{t}</a>' for a, t in anchors)
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Doctrine · Règles complètes</title>
<style>{CSS}</style>
</head>
<body>
<div class="layout">
<nav>
<div class="brand">DOCTRINE</div>
<div class="vtag">référence des règles</div>
{nav}
</nav>
<main>
<h1>Règles complètes</h1>
<p class="sub">Toutes les formules et constantes, extraites du moteur de
jeu. n désigne le nombre de points investis dans une compétence.</p>
{sections}
</main>
</div>
</body>
</html>
"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path
