"""Curses renderer for the match view.

Only this package touches curses; the engine stays renderer agnostic.
"""
from __future__ import annotations

import curses

from engine.entities import Building, BuildingType, UnitType
from engine.game import Game, TICKS_PER_SECOND
from engine.world import ResourceType, Terrain

from .viewport import Viewport

MIN_COLS = 80
MIN_ROWS = 24
PANEL_WIDTH = 26
EVENT_LINES = 3

PAIR_IDS = {
    "blue": 1,
    "red": 2,
    "green": 3,
    "yellow": 4,
    "magenta": 5,
    "cyan": 6,
    "white": 7,
}

CURSES_COLORS = {
    "blue": curses.COLOR_BLUE,
    "red": curses.COLOR_RED,
    "green": curses.COLOR_GREEN,
    "yellow": curses.COLOR_YELLOW,
    "magenta": curses.COLOR_MAGENTA,
    "cyan": curses.COLOR_CYAN,
    "white": curses.COLOR_WHITE,
}

TERRAIN_CHARS = {
    Terrain.PLAIN: (".", "white", curses.A_DIM),
    Terrain.FOREST: ('"', "green", 0),
    Terrain.MOUNTAIN: ("#", "white", 0),
    Terrain.WATER: ("~", "cyan", 0),
}

RESOURCE_CHARS = {
    ResourceType.ORE: ("^", "yellow"),
    ResourceType.WOOD: ("T", "green"),
    ResourceType.CRYSTAL: ("*", "magenta"),
    ResourceType.FOOD: ("%", "red"),
}

LEGEND_LINES = [
    ("Unités", None),
    ("s éclaireur  w ouvrier", None),
    ("t transport. S soldat", None),
    ("Bâtiments", None),
    ("B QG         E entrepôt", None),
    ("C caserne    M marché", None),
    ("Y tour de garde", None),
    ("Ressources", None),
    ("^ minerai    T bois", None),
    ("* cristal    % nourrit.", None),
    ("Terrain", None),
    ('. plaine     " forêt', None),
    ("# montagne   ~ eau", None),
    ("Touches", None),
    ("flèches: vue  p: pause", None),
    ("+/-: vitesse  l: légende", None),
    ("q: quitter", None),
]


class Renderer:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        curses.curs_set(0)
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            for name, pid in PAIR_IDS.items():
                curses.init_pair(pid, CURSES_COLORS[name], -1)

    def color(self, name: str) -> int:
        if not curses.has_colors():
            return 0
        return curses.color_pair(PAIR_IDS.get(name, PAIR_IDS["white"]))

    def _put(self, y: int, x: int, text: str, attr: int = 0) -> None:
        try:
            self.stdscr.addstr(y, x, text, attr)
        except curses.error:
            pass

    def size_ok(self) -> bool:
        rows, cols = self.stdscr.getmaxyx()
        return cols >= MIN_COLS and rows >= MIN_ROWS

    def draw_too_small(self) -> None:
        self.stdscr.erase()
        rows, cols = self.stdscr.getmaxyx()
        msg1 = "Terminal trop petit."
        msg2 = f"Taille minimale: {MIN_COLS}x{MIN_ROWS} (actuel {cols}x{rows})"
        msg3 = "Agrandissez la fenêtre ou quittez avec q."
        for i, msg in enumerate((msg1, msg2, msg3)):
            self._put(rows // 2 - 1 + i, max(0, (cols - len(msg)) // 2), msg)
        self.stdscr.refresh()

    def map_area(self) -> tuple[int, int]:
        rows, cols = self.stdscr.getmaxyx()
        return cols - PANEL_WIDTH - 1, rows - EVENT_LINES - 1

    def draw_game(
        self,
        game: Game,
        viewport: Viewport,
        player_tid: int,
        show_legend: bool,
        paused: bool,
        speed: float,
    ) -> None:
        self.stdscr.erase()
        map_w, map_h = self.map_area()
        viewport.resize(map_w, map_h)
        self._draw_map(game, viewport, player_tid)
        self._draw_panel(game, player_tid, show_legend, paused, speed)
        self._draw_events(game)
        self.stdscr.refresh()

    # Map window

    def _draw_map(self, game: Game, vp: Viewport, player_tid: int) -> None:
        team = game.teams[player_tid]
        explored = team.explored
        visible = team.visible
        gmap = game.map
        for sy in range(vp.height):
            wy = vp.y + sy
            for sx in range(vp.width):
                wx = vp.x + sx
                pos = (wx, wy)
                if pos not in explored:
                    continue
                dim = 0 if pos in visible else curses.A_DIM
                deposit = gmap.deposits.get(pos)
                if deposit is not None:
                    char, cname = RESOURCE_CHARS[deposit.rtype]
                    self._cell(sy, sx, char, self.color(cname) | dim)
                else:
                    char, cname, attr = TERRAIN_CHARS[gmap.get(wx, wy)]
                    self._cell(sy, sx, char, self.color(cname) | attr | dim)
        for building in game.buildings.values():
            self._draw_building(game, building, vp, team)
        for unit in game.units.values():
            pos = unit.pos
            if not vp.contains(*pos):
                continue
            if unit.team_id != player_tid and pos not in visible:
                continue
            color = game.teams[unit.team_id].color
            self._cell(
                pos[1] - vp.y,
                pos[0] - vp.x,
                unit.spec.symbol,
                self.color(color) | curses.A_BOLD,
            )

    def _draw_building(
        self, game: Game, building: Building, vp: Viewport, player_team
    ) -> None:
        pos = building.pos
        if not vp.contains(*pos):
            return
        own = building.team_id == player_team.tid
        if not own and pos not in player_team.visible:
            # Remembered enemy buildings stay on the map, dimmed.
            if building.bid not in player_team.known_enemy_buildings:
                return
            dim = curses.A_DIM
        else:
            dim = 0
        symbol = building.spec.symbol
        if not building.complete:
            symbol = symbol.lower()
        color = game.teams[building.team_id].color
        self._cell(
            pos[1] - vp.y, pos[0] - vp.x, symbol,
            self.color(color) | curses.A_BOLD | dim,
        )

    def _cell(self, y: int, x: int, char: str, attr: int) -> None:
        try:
            self.stdscr.addch(y, x, char, attr)
        except curses.error:
            pass

    # Right panel: status, scores, stocks, legend

    def _draw_panel(
        self,
        game: Game,
        player_tid: int,
        show_legend: bool,
        paused: bool,
        speed: float,
    ) -> None:
        rows, cols = self.stdscr.getmaxyx()
        x0 = cols - PANEL_WIDTH
        for y in range(rows - EVENT_LINES - 1):
            self._put(y, x0 - 1, "|", curses.A_DIM)
        seconds = int(game.elapsed_seconds)
        status = f"Temps {seconds // 60:02d}:{seconds % 60:02d}  x{speed:.2g}"
        if paused:
            status += " PAUSE"
        y = 0
        self._put(y, x0, status, curses.A_BOLD)
        y += 2
        for team in game.teams.values():
            name = team.name + (" (vous)" if team.is_player else "")
            attr = self.color(team.color) | curses.A_BOLD
            if not team.alive:
                name += " [détruit]"
                attr |= curses.A_DIM
            self._put(y, x0, name, attr)
            y += 1
            self._put(y, x0, f" score {game.score(team)}")
            y += 1
            s = team.stocks
            self._put(
                y, x0,
                f" N{s[ResourceType.FOOD]:>4} B{s[ResourceType.WOOD]:>4}"
                f" M{s[ResourceType.ORE]:>4}",
            )
            y += 1
            units = len(game.units_of(team.tid))
            builds = len(game.buildings_of(team.tid, only_complete=True))
            self._put(
                y, x0,
                f" C{s[ResourceType.CRYSTAL]:>4}  un.{units:>3} bât.{builds}",
            )
            y += 2
        if show_legend:
            for text, _ in LEGEND_LINES:
                if y >= rows - EVENT_LINES - 1:
                    break
                if text in (
                    "Unités", "Bâtiments", "Ressources", "Terrain", "Touches"
                ):
                    self._put(y, x0, text, curses.A_UNDERLINE)
                else:
                    self._put(y, x0, text)
                y += 1

    # Bottom event bar

    def _draw_events(self, game: Game) -> None:
        rows, cols = self.stdscr.getmaxyx()
        base = rows - EVENT_LINES
        self._put(base - 1, 0, "-" * (cols - 1), curses.A_DIM)
        recent = list(game.events)[-EVENT_LINES:]
        for i, (tick, message) in enumerate(recent):
            seconds = tick // TICKS_PER_SECOND
            line = f"[{seconds // 60:02d}:{seconds % 60:02d}] {message}"
            self._put(base + i, 0, line[: cols - 1])
