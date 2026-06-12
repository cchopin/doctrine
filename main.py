"""Entry point: CLI arguments, preparation screen, match loop, progression.

Rendering choice: curses (stdlib). The game needs one full screen grid
with a scrolling viewport, a side panel and an event bar; curses gives
direct cell level control with zero dependency, which fits better than
textual widgets here.
"""
from __future__ import annotations

import argparse
import curses
import locale
import random
import sys
import time
from pathlib import Path

from engine.ai import allocate_ai_skills
from engine.game import DEFAULT_TIME_LIMIT_TICKS, Game, TICKS_PER_SECOND
from engine.mapgen import generate_map
from engine.team import TeamConfig
from meta.history import append_match, build_record, load_history
from meta.progress import (
    DEFAULT_PROFILE_PATH,
    Profile,
    add_xp,
    load_profile,
    save_profile,
    skill_budget,
    xp_needed,
)
from meta.report import generate_report
from meta.skills import SKILLS, unlocked_skills
from render.screen import Renderer
from render.viewport import Viewport

XP_WIN = 100
XP_DRAW = 40
XP_LOSS = 15

SPEED_STEPS = [0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Doctrine, jeu de stratégie automatisé en terminal."
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="graine pour rejouer une carte identique",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="simulation IA contre IA sans interface (équilibrage)",
    )
    parser.add_argument(
        "--games", type=int, default=1,
        help="nombre de parties en mode headless",
    )
    parser.add_argument(
        "--profile", type=Path, default=DEFAULT_PROFILE_PATH,
        help="chemin du fichier de progression JSON",
    )
    parser.add_argument(
        "--level", type=int, default=None,
        help="force un niveau (test), sans toucher au profil",
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="génère la page web de statistiques et l'ouvre",
    )
    return parser.parse_args(argv)


def next_unlock(level: int) -> str:
    """Teaser for the next skill unlocked by leveling up."""
    upcoming = [s for s in SKILLS.values() if s.min_level > level]
    if not upcoming:
        return "Toutes les compétences sont débloquées"
    skill = min(upcoming, key=lambda s: s.min_level)
    return f"Prochain déblocage: {skill.label} (niveau {skill.min_level})"


def xp_bar(profile: Profile, width: int = 20) -> str:
    needed = xp_needed(profile.level)
    filled = int(width * min(1.0, profile.xp / needed))
    return f"[{'#' * filled}{'.' * (width - filled)}] {profile.xp}/{needed} xp"


def build_game(
    player_skills: dict[str, int],
    level: int,
    seed: int | None,
) -> tuple[Game, str]:
    gmap, bases = generate_map(seed=seed)
    ai_rng = random.Random(None if seed is None else seed + 1)
    ai_skills, ai_profile = allocate_ai_skills(
        level, skill_budget(level), ai_rng
    )
    configs = [
        TeamConfig("Bleus", "blue", player_skills, is_player=True),
        TeamConfig("Rouges", "red", ai_skills),
    ]
    return Game(gmap, bases, configs, seed=seed), ai_profile


# Headless mode, used for balancing and smoke testing

def run_headless(args: argparse.Namespace) -> None:
    level = args.level or 1
    base_seed = args.seed
    for i in range(args.games):
        seed = None if base_seed is None else base_seed + i
        rng = random.Random(seed)
        skills, profile_name = allocate_ai_skills(
            level, skill_budget(level), rng
        )
        game, ai_profile = build_game(skills, level, seed)
        while not game.finished:
            game.tick()
        minutes = game.elapsed_seconds / 60
        winner = (
            game.teams[game.winner].name if game.winner is not None
            else "égalité"
        )
        scores = ", ".join(
            f"{t.name}: {game.score(t)}" for t in game.teams.values()
        )
        print(
            f"seed={seed} durée={minutes:.1f} min vainqueur={winner}"
            f" ({game.end_reason}) [{profile_name} vs {ai_profile}]"
            f" scores: {scores}"
        )


# Curses screens

def prep_screen(stdscr, profile: Profile, level: int) -> dict[str, int] | None:
    """Skill point allocation menu. Returns the allocation or None to quit."""
    skills = unlocked_skills(level)
    allocation = {s.key: 0 for s in skills}
    budget = skill_budget(level)
    selected = 0
    curses.curs_set(0)
    stdscr.nodelay(False)
    while True:
        stdscr.erase()
        spent = sum(allocation.values())
        title = f"DOCTRINE  |  Préparation de la partie  |  Niveau {level}"
        xp_line = (
            f"{xp_bar(profile)}  Victoires {profile.wins}"
            f"  Défaites {profile.losses}"
        )
        stdscr.addstr(1, 2, title, curses.A_BOLD)
        stdscr.addstr(2, 2, xp_line, curses.A_DIM)
        stdscr.addstr(3, 2, next_unlock(level), curses.A_DIM)
        stdscr.addstr(
            4, 2,
            f"Points à répartir: {budget - spent}/{budget}",
            curses.A_BOLD,
        )
        for i, skill in enumerate(skills):
            marker = ">" if i == selected else " "
            attr = curses.A_REVERSE if i == selected else 0
            bar = "#" * allocation[skill.key]
            stdscr.addstr(
                6 + i, 2,
                f"{marker} {skill.label:<13} [{allocation[skill.key]:>2}] {bar}",
                attr,
            )
        desc = skills[selected].description
        rows, _ = stdscr.getmaxyx()
        stdscr.addstr(7 + len(skills), 2, desc, curses.A_DIM)
        stdscr.addstr(
            rows - 2, 2,
            "haut/bas: choisir  gauche/droite: ajuster"
            "  entrée: commencer  q: quitter",
        )
        stdscr.refresh()
        key = stdscr.getch()
        skill = skills[selected]
        if key in (ord("q"), ord("Q")):
            return None
        if key == curses.KEY_UP:
            selected = (selected - 1) % len(skills)
        elif key == curses.KEY_DOWN:
            selected = (selected + 1) % len(skills)
        elif key in (curses.KEY_RIGHT, ord("+"), ord("=")):
            if spent < budget and allocation[skill.key] < skill.max_points:
                allocation[skill.key] += 1
        elif key in (curses.KEY_LEFT, ord("-")):
            if allocation[skill.key] > 0:
                allocation[skill.key] -= 1
        elif key in (curses.KEY_ENTER, 10, 13):
            return allocation


def match_recap(game: Game, player_tid: int) -> list[str]:
    """Side by side end of match statistics table."""
    player = game.teams[player_tid]
    enemy = next(t for t in game.teams.values() if t.tid != player_tid)
    rows = [
        ("", player.name, enemy.name),
        ("Score", game.score(player), game.score(enemy)),
        ("Zones explorées", len(player.explored), len(enemy.explored)),
        (
            "Ressources récoltées",
            player.stats.total_collected,
            enemy.stats.total_collected,
        ),
        ("Unités formées", player.stats.units_trained, enemy.stats.units_trained),
        ("Unités perdues", player.stats.units_lost, enemy.stats.units_lost),
        ("Unités éliminées", player.stats.units_killed, enemy.stats.units_killed),
        (
            "Bâtiments construits",
            player.stats.buildings_built,
            enemy.stats.buildings_built,
        ),
        (
            "Bâtiments détruits",
            player.stats.buildings_destroyed,
            enemy.stats.buildings_destroyed,
        ),
        ("Dégâts infligés", player.stats.damage_dealt, enemy.stats.damage_dealt),
    ]
    return [f"{label:<22}{left:>8}{right:>9}" for label, left, right in rows]


def end_screen(
    stdscr, renderer: Renderer, title: str, title_color: str,
    lines: list[str],
) -> bool:
    """Show the recap. Returns True to start a new match, False to quit."""
    stdscr.nodelay(False)
    stdscr.erase()
    rows, cols = stdscr.getmaxyx()
    total = len(lines) + 2
    y = max(1, rows // 2 - total // 2 - 1)
    try:
        stdscr.addstr(
            y, max(0, (cols - len(title)) // 2), title,
            renderer.bright(title_color) | curses.A_BOLD,
        )
    except curses.error:
        pass
    for i, line in enumerate(lines):
        try:
            stdscr.addstr(
                y + 2 + i, max(0, (cols - len(line)) // 2), line
            )
        except curses.error:
            pass
    prompt = "Une touche: nouvelle partie  |  q: quitter"
    try:
        stdscr.addstr(
            min(rows - 1, y + total + 1),
            max(0, (cols - len(prompt)) // 2),
            prompt, curses.A_DIM,
        )
    except curses.error:
        pass
    stdscr.refresh()
    key = stdscr.getch()
    return key not in (ord("q"), ord("Q"))


def run_match(stdscr, game: Game, renderer: Renderer) -> bool:
    """Run the interactive match loop. Returns False if the player quit."""
    viewport = Viewport(game.map.width, game.map.height)
    player_tid = next(
        t.tid for t in game.teams.values() if t.is_player
    )
    hq = game.hq(game.teams[player_tid])
    map_w, map_h = renderer.map_area()
    viewport.resize(max(1, map_w), max(1, map_h))
    if hq is not None:
        viewport.center_on(hq.x, hq.y)
    stdscr.nodelay(True)
    paused = False
    show_legend = True
    speed_index = SPEED_STEPS.index(1.0)
    last_tick = time.monotonic()
    last_draw = 0.0
    while not game.finished:
        speed = SPEED_STEPS[speed_index]
        tick_interval = 1.0 / (TICKS_PER_SECOND * speed)
        while True:
            key = stdscr.getch()
            if key == -1:
                break
            if key in (ord("q"), ord("Q")):
                return False
            if key in (ord("p"), ord("P")):
                paused = not paused
            elif key in (ord("l"), ord("L")):
                show_legend = not show_legend
            elif key in (ord("+"), ord("=")):
                speed_index = min(len(SPEED_STEPS) - 1, speed_index + 1)
            elif key == ord("-"):
                speed_index = max(0, speed_index - 1)
            elif key == curses.KEY_LEFT:
                viewport.move(-4, 0)
            elif key == curses.KEY_RIGHT:
                viewport.move(4, 0)
            elif key == curses.KEY_UP:
                viewport.move(0, -2)
            elif key == curses.KEY_DOWN:
                viewport.move(0, 2)
            elif key in (ord("b"), ord("B")):
                base = game.hq(game.teams[player_tid])
                if base is not None:
                    viewport.center_on(base.x, base.y)
            elif key == curses.KEY_RESIZE:
                pass
        now = time.monotonic()
        if not renderer.size_ok():
            renderer.draw_too_small()
            last_tick = now
            time.sleep(0.05)
            continue
        if not paused and now - last_tick >= tick_interval:
            ticks = min(4, int((now - last_tick) / tick_interval))
            for _ in range(ticks):
                game.tick()
            last_tick = now
        if now - last_draw >= 1 / 30:
            renderer.draw_game(
                game, viewport, player_tid, show_legend, paused, speed
            )
            last_draw = now
        time.sleep(0.004)
    renderer.draw_game(game, viewport, player_tid, show_legend, paused, speed)
    return True


def run_ui(stdscr, args: argparse.Namespace) -> None:
    renderer = Renderer(stdscr)
    profile = load_profile(args.profile)
    while True:
        level = args.level or profile.level
        allocation = prep_screen(stdscr, profile, level)
        if allocation is None:
            return
        seed = args.seed if args.seed is not None else random.randrange(10**9)
        game, ai_profile = build_game(allocation, level, seed)
        finished = run_match(stdscr, game, renderer)
        if not finished:
            return
        player_tid = next(t.tid for t in game.teams.values() if t.is_player)
        if game.winner == player_tid:
            xp, result, title, color = XP_WIN, "victoire", "VICTOIRE !", "green"
            profile.wins += 1
        elif game.winner is None:
            xp, result, title, color = XP_DRAW, "egalite", "ÉGALITÉ", "yellow"
        else:
            xp, result, title, color = XP_LOSS, "defaite", "DÉFAITE...", "red"
            profile.losses += 1
        minutes = game.elapsed_seconds / 60
        lines = [
            f"Durée {minutes:.1f} min ({game.end_reason})"
            f"  |  adversaire {ai_profile}  |  graine {seed}",
            "",
        ]
        lines.extend(match_recap(game, player_tid))
        lines.append("")
        if args.level is None:
            gained = add_xp(profile, xp)
            save_profile(profile, args.profile)
            lines.append(
                f"Expérience +{xp}   niveau {profile.level} {xp_bar(profile)}"
            )
            if gained:
                lines.append(
                    f"NIVEAU SUPÉRIEUR ! Vous êtes maintenant"
                    f" niveau {profile.level}"
                )
            lines.append(next_unlock(profile.level))
        record = build_record(game, player_tid, result, seed, level, ai_profile)
        append_match(record)
        report_path = generate_report(load_history())
        lines.append(f"Statistiques détaillées: {report_path.name}")
        if not end_screen(stdscr, renderer, title, color, lines):
            return


def main(argv: list[str] | None = None) -> int:
    locale.setlocale(locale.LC_ALL, "")
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if args.stats:
        import webbrowser

        path = generate_report(load_history())
        print(f"Page de statistiques générée: {path}")
        webbrowser.open(path.as_uri())
        return 0
    if args.headless:
        run_headless(args)
        return 0
    curses.wrapper(run_ui, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
