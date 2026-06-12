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
from meta.progress import (
    DEFAULT_PROFILE_PATH,
    Profile,
    add_xp,
    load_profile,
    save_profile,
    skill_budget,
    xp_needed,
)
from meta.skills import unlocked_skills
from render.screen import Renderer
from render.viewport import Viewport

XP_WIN = 100
XP_DRAW = 40
XP_LOSS = 15

SPEED_STEPS = [0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Jeu de stratégie automatisé en terminal."
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
    return parser.parse_args(argv)


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
        title = f"Préparation de la partie  |  Niveau {level}"
        xp_line = (
            f"XP {profile.xp}/{xp_needed(profile.level)}"
            f"  Victoires {profile.wins}  Défaites {profile.losses}"
        )
        stdscr.addstr(1, 2, title, curses.A_BOLD)
        stdscr.addstr(2, 2, xp_line, curses.A_DIM)
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


def end_screen(stdscr, game: Game, lines: list[str]) -> None:
    stdscr.nodelay(False)
    stdscr.erase()
    rows, cols = stdscr.getmaxyx()
    y = rows // 2 - len(lines) // 2 - 1
    for i, line in enumerate(lines):
        attr = curses.A_BOLD if i == 0 else 0
        try:
            stdscr.addstr(y + i, max(0, (cols - len(line)) // 2), line, attr)
        except curses.error:
            pass
    prompt = "Appuyez sur une touche pour quitter"
    try:
        stdscr.addstr(
            y + len(lines) + 2, max(0, (cols - len(prompt)) // 2),
            prompt, curses.A_DIM,
        )
    except curses.error:
        pass
    stdscr.refresh()
    stdscr.getch()


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
    level = args.level or profile.level
    allocation = prep_screen(stdscr, profile, level)
    if allocation is None:
        return
    seed = args.seed if args.seed is not None else random.randrange(10**9)
    game, _ = build_game(allocation, level, seed)
    finished = run_match(stdscr, game, renderer)
    if not finished:
        return
    player_tid = next(t.tid for t in game.teams.values() if t.is_player)
    lines = [f"Graine de la partie: {seed}"]
    if game.winner == player_tid:
        xp = XP_WIN
        profile.wins += 1
        lines.insert(0, "Victoire !")
    elif game.winner is None:
        xp = XP_DRAW
        lines.insert(0, "Égalité.")
    else:
        xp = XP_LOSS
        profile.losses += 1
        lines.insert(0, "Défaite...")
    minutes = game.elapsed_seconds / 60
    lines.append(f"Durée: {minutes:.1f} min ({game.end_reason})")
    if args.level is None:
        gained = add_xp(profile, xp)
        lines.append(f"Expérience gagnée: +{xp}")
        if gained:
            lines.append(f"Niveau supérieur ! Vous êtes niveau {profile.level}")
        save_profile(profile, args.profile)
    end_screen(stdscr, game, lines)


def main(argv: list[str] | None = None) -> int:
    locale.setlocale(locale.LC_ALL, "")
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if args.headless:
        run_headless(args)
        return 0
    curses.wrapper(run_ui, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
